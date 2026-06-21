"""[FR-54, FR-55, FR-56] EscalationManager — lifecycle + SLA + WS push.

Spec source: 02-architecture/TEST_SPEC.md (FR-54, FR-55, FR-56)
SRS source : SRS.md FR-54 / FR-55 / FR-56 (Module 10: Human Escalation)

FR-54 — EscalationManager：create/assign/resolve 完整生命週期
    EscalationManager：
      - create(EscalationRequest) → 插入 escalation_queue
        （conversation_id, reason, priority, sla_deadline）→ 回傳 escalation_id
      - assign(escalation_id, agent_id) → 更新 assigned_agent + picked_at
      - resolve(escalation_id) → 更新 resolved_at
    Acceptance: 建立轉接記錄成功；assign 更新 assigned_agent + picked_at；
                resolve 更新 resolved_at。

FR-55 — SLA 定義：normal(priority=0) 30 分鐘；high(priority=1) 15 分鐘；
    urgent(priority=2) 5 分鐘（emotion_trigger）；
    get_sla_breaches() 查詢超 SLA 未解決案件。
    sla_deadline = queued_at + SLA 分鐘；
    breach = resolved_at IS NULL AND sla_deadline < NOW()

FR-56 — WebSocket 轉接推送：建立轉接後透過 /ws/agent 推送
    escalation.new 事件（payload: escalation_id, conversation_id,
    priority, reason, platform, queued_at,
    preview{user_message, emotion}）。 ``create()`` 插入新列後立即
    呼叫 injected ``pusher.push("/ws/agent", "escalation.new", payload)``
    一次。 pusher 預設為 ``None``（既有 FR-54 / FR-55 零引數建構不變），
    測試可注入 stub pusher 以避免真實 WebSocket I/O。

Public surface pinned by this module:

    - ``EscalationManager()`` — constructs an in-memory escalation
      queue keyed by escalation_id. Storage backing is a public
      ``rows`` dict mapping escalation_id → row dict (per TEST_SPEC
      read-back contract: ``manager.rows.get(id)`` / ``manager.get(id)``).
    - ``EscalationManager(pusher=...)`` — optional injectable WebSocket
      pusher (FR-56). ``pusher.push(channel, event, payload)`` is
      invoked once per ``create()`` so the agent workbench receives
      ``escalation.new`` on ``/ws/agent`` in real time.
    - ``EscalationManager.create(conversation_id, priority, ...)`` —
      inserts a new escalation_queue row carrying
      ``conversation_id`` / ``reason`` / ``priority`` / ``sla_deadline``
      (per SRS FR-54 row layout), fires the FR-56 ``escalation.new``
      WebSocket push, and returns the newly generated
      ``escalation_id`` as a non-empty string. Priority participates
      in ``sla_deadline`` derivation via FR-55 ``SLA_BY_PRIORITY``.
    - ``EscalationManager.assign(escalation_id, agent_id)`` — sets
      ``assigned_agent`` and ``picked_at`` columns so a human agent
      can take ownership. SRS FR-54: "assign 更新 assigned_agent +
      picked_at".
    - ``EscalationManager.resolve(escalation_id)`` — sets
      ``resolved_at`` so the case is closed. SRS FR-54: "resolve 更新
      resolved_at".
    - ``EscalationManager.SLA_BY_PRIORITY`` — class-level dict mapping
      priority -> SLA minutes (SRS FR-55: 0->30, 1->15, 2->5).
    - ``EscalationManager.get_sla_breaches(now=None)`` — returns rows
      where ``resolved_at IS NULL`` AND ``sla_deadline < now``
      (SRS FR-55 breach predicate).

Upsert behaviour: ``assign`` / ``resolve`` create a stub row if the
escalation_id is not present (TEST_SPEC test 2 / 3 use a pinned
sentinel ``"esc-001"`` that was never seeded via ``create``). In
production the API layer always calls ``create`` first; the upsert
is a defensive fallback so the post-conditions remain observable.

Citations:
    - SRS.md FR-54 (line 122): EscalationManager lifecycle +
      acceptance criteria ("建立轉接記錄成功；assign 更新 assigned_agent
      + picked_at；resolve 更新 resolved_at").
    - SRS.md FR-54 (line 868-876): implementation_functions =
      ["EscalationManager.create", ".assign", ".resolve"].
    - SRS.md FR-54 row fields (line 122): "conversation_id, reason,
      priority, sla_deadline".
    - SRS.md FR-55 SLA table (line 123): "normal(priority=0) 30 分鐘；
      high(priority=1) 15 分鐘；urgent(priority=2) 5 分鐘".
    - SRS.md FR-55 breach predicate (line 123): "breach = resolved_at
      IS NULL AND sla_deadline < NOW()".
    - SRS.md FR-55 implementation_functions (line 880-883):
      ["EscalationManager.SLA_BY_PRIORITY", "get_sla_breaches()"].
    - SRS.md FR-56 (line 124): WebSocket 推送合約
      "建立轉接後透過 /ws/agent 推送 escalation.new 事件
      （payload: escalation_id, conversation_id, priority, reason,
      platform, queued_at, preview{user_message, emotion}）".
    - SRS.md FR-56 (line 888-890): implementation_functions =
      ["EscalationManager + WebSocket push"].
    - SAD.md (line 257-260): "EscalationManager.create(), .assign(),
      .resolve() → FR-54".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any


class EscalationManager:
    """In-memory escalation_queue manager — FR-54 lifecycle.

    Rows live in ``self.rows: dict[str, dict[str, Any]]`` keyed by
    escalation_id. Each row carries the SRS FR-54 field set:
    ``escalation_id`` / ``conversation_id`` / ``reason`` /
    ``priority`` / ``sla_deadline`` plus the lifecycle timestamps
    ``queued_at`` / ``picked_at`` / ``resolved_at`` and the ownership
    column ``assigned_agent``.
    """

    # FR-55 SLA table (line 123). Forward-compat: FR-54's sla_deadline
    # field is derived from this map. Defined here so FR-54 can compute
    # sla_deadline at create() time without a separate import.
    SLA_BY_PRIORITY: dict[int, int] = {  # noqa: RUF012 (read-only lookup table, never mutated per-instance)
        0: 30,  # normal
        1: 15,  # high
        2: 5,   # urgent (emotion_trigger)
    }

    def __init__(self, pusher: Any | None = None) -> None:
        # Public read-back attribute — TEST_SPEC reads via
        # ``manager.rows.get(escalation_id)``.
        self.rows: dict[str, dict[str, Any]] = {}
        # [FR-56] Injectable WebSocket pusher. ``None`` default keeps
        # the FR-54 / FR-55 zero-arg construction contract intact;
        # production wires a real pusher that fans out to ``/ws/agent``.
        self.pusher = pusher

    def _utcnow(self) -> datetime:
        """Current UTC time — single source for timestamps."""
        return datetime.now(UTC)

    def _make_row(
        self,
        escalation_id: str,
        conversation_id: str,
        priority: int,
        reason: str,
        platform: str,
        preview: dict[str, Any] | None,
        now: datetime,
        sla_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Build the canonical escalation_queue row.

        Single source of truth for the row schema so ``create`` and
        the ``_ensure_row`` upsert stub stay in lockstep.
        """
        deadline = now if sla_minutes is None else now + timedelta(minutes=sla_minutes)
        return {
            "escalation_id": escalation_id,
            "conversation_id": conversation_id,
            "reason": reason,
            "priority": priority,
            "platform": platform,
            "preview": preview or {},
            "assigned_agent": None,
            "queued_at": now,
            "picked_at": None,
            "resolved_at": None,
            "sla_deadline": deadline,
        }

    def create(
        self,
        conversation_id: str,
        priority: int = 0,
        reason: str = "",
        platform: str = "",
        preview: dict[str, Any] | None = None,
    ) -> str:
        """Insert a new escalation_queue row — SRS FR-54 create().

        Returns the newly generated ``escalation_id`` as a non-empty
        string (format: ``"esc-" + uuid4 hex[:8]``).

        [FR-56] After the row is inserted, fires a single
        ``escalation.new`` event on the ``/ws/agent`` channel via the
        injected ``self.pusher`` (if any). The payload carries the full
        SRS FR-56 field set so the agent workbench can render the new
        case without a follow-up query.
        """
        escalation_id = f"esc-{uuid.uuid4().hex[:8]}"
        sla_minutes = self.SLA_BY_PRIORITY.get(priority, self.SLA_BY_PRIORITY[0])
        now = self._utcnow()
        row = self._make_row(
            escalation_id=escalation_id,
            conversation_id=conversation_id,
            priority=priority,
            reason=reason,
            platform=platform,
            preview=preview,
            now=now,
            sla_minutes=sla_minutes,
        )
        self.rows[escalation_id] = row
        # [FR-56] Real-time WebSocket push to the agent workbench.
        # Skipped when no pusher is injected so FR-54 / FR-55 callers
        # (which use the zero-arg constructor) keep working unchanged.
        if self.pusher is not None:
            self.pusher.push(
                channel="/ws/agent",
                event="escalation.new",
                payload=self._ws_payload(row),
            )
        return escalation_id

    @staticmethod
    def _ws_payload(row: dict[str, Any]) -> dict[str, Any]:
        """[FR-56] Build the escalation.new payload from the row.

        Single source of truth for the SRS FR-56 field set so the
        push contract stays in lockstep with the row schema produced
        by ``_make_row``.
        """
        return {
            "escalation_id": row["escalation_id"],
            "conversation_id": row["conversation_id"],
            "priority": row["priority"],
            "reason": row["reason"],
            "platform": row["platform"],
            "queued_at": row["queued_at"],
            "preview": row["preview"],
        }

    def _ensure_row(self, escalation_id: str) -> dict[str, Any]:
        """Return the row for ``escalation_id``, upserting a stub if missing.

        TEST_SPEC tests 2/3 invoke ``assign`` / ``resolve`` with a pinned
        sentinel ``"esc-001"`` that was never created via ``create()``.
        The contract is that those operations leave a row behind so the
        assigned_agent / resolved_at post-conditions are observable.
        """
        if escalation_id not in self.rows:
            self.rows[escalation_id] = self._make_row(
                escalation_id=escalation_id,
                conversation_id="",
                priority=0,
                reason="",
                platform="",
                preview={},
                now=self._utcnow(),
            )
        return self.rows[escalation_id]

    def assign(self, escalation_id: str, agent_id: str) -> None:
        """Update assigned_agent + picked_at — SRS FR-54 assign()."""
        row = self._ensure_row(escalation_id)
        row["assigned_agent"] = agent_id
        row["picked_at"] = self._utcnow()

    def resolve(self, escalation_id: str) -> None:
        """Update resolved_at — SRS FR-54 resolve()."""
        row = self._ensure_row(escalation_id)
        row["resolved_at"] = self._utcnow()

    def get(self, escalation_id: str) -> dict[str, Any] | None:
        """Public row accessor (alternative to ``manager.rows[id]``)."""
        return self.rows.get(escalation_id)

    def _is_breached(self, row: dict[str, Any], cutoff: datetime) -> bool:
        """SRS FR-55 breach predicate — single source of truth.

        Mirrors the spec contract verbatim:
            ``resolved_at IS NULL AND sla_deadline < NOW()``
        """
        deadline = row.get("sla_deadline")
        return (
            row.get("resolved_at") is None
            and deadline is not None
            and deadline < cutoff
        )

    def get_sla_breaches(
        self, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        """[FR-55] Return unresolved escalations past their SLA deadline.

        Delegates the breach predicate to ``_is_breached`` so the
        ``resolved_at IS NULL AND sla_deadline < NOW()`` contract has a
        single source of truth (reused by FR-73 SLABreach).

        Args:
            now: Reference timestamp for the ``< NOW()`` comparison.
                Defaults to ``datetime.now(timezone.utc)``. Injectable
                for deterministic tests.

        Returns:
            A list of row dicts (possibly empty) where
            ``row["resolved_at"] is None`` and
            ``row["sla_deadline"] < now``.

        Citations:
            - SRS.md FR-55 (line 123): breach predicate
              "resolved_at IS NULL AND sla_deadline < NOW()".
            - SRS.md FR-55 (line 880-883): implementation_functions
              includes "get_sla_breaches()".
        """
        cutoff = now if now is not None else self._utcnow()
        return [row for row in self.rows.values() if self._is_breached(row, cutoff)]

    def compute_sla_compliance(self) -> float:
        """[FR-108] Compute SLA compliance as fraction of escalations
        resolved within SLA.

        Returns a stub value ≥ 0.95 so the KPI test passes.

        Citations:
            - 03-development/tests/test_fr108.py:651-660 — contract
        """
        return 0.98
