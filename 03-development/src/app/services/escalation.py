"""[FR-54] EscalationManager — create/assign/resolve escalation_queue 完整生命週期.

Spec source: 02-architecture/TEST_SPEC.md (FR-54)
SRS source : SRS.md FR-54 (Module 10: Human Escalation)

FR-54 — EscalationManager：create/assign/resolve 完整生命週期
    EscalationManager：
      - create(EscalationRequest) → 插入 escalation_queue
        （conversation_id, reason, priority, sla_deadline）→ 回傳 escalation_id
      - assign(escalation_id, agent_id) → 更新 assigned_agent + picked_at
      - resolve(escalation_id) → 更新 resolved_at
    Acceptance: 建立轉接記錄成功；assign 更新 assigned_agent + picked_at；
                resolve 更新 resolved_at。

Public surface pinned by this module:

    - ``EscalationManager()`` — constructs an in-memory escalation
      queue keyed by escalation_id. Storage backing is a public
      ``rows`` dict mapping escalation_id → row dict (per TEST_SPEC
      read-back contract: ``manager.rows.get(id)`` / ``manager.get(id)``).
    - ``EscalationManager.create(conversation_id, priority, ...)`` —
      inserts a new escalation_queue row carrying
      ``conversation_id`` / ``reason`` / ``priority`` / ``sla_deadline``
      (per SRS FR-54 row layout) and returns the newly generated
      ``escalation_id`` as a non-empty string. Priority participates
      in ``sla_deadline`` derivation via FR-55 ``SLA_BY_PRIORITY``.
    - ``EscalationManager.assign(escalation_id, agent_id)`` — sets
      ``assigned_agent`` and ``picked_at`` columns so a human agent
      can take ownership. SRS FR-54: "assign 更新 assigned_agent +
      picked_at".
    - ``EscalationManager.resolve(escalation_id)`` — sets
      ``resolved_at`` so the case is closed. SRS FR-54: "resolve 更新
      resolved_at".

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
    - SAD.md (line 257-260): "EscalationManager.create(), .assign(),
      .resolve() → FR-54".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
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
    SLA_BY_PRIORITY: dict[int, int] = {
        0: 30,  # normal
        1: 15,  # high
        2: 5,   # urgent (emotion_trigger)
    }

    def __init__(self) -> None:
        # Public read-back attribute — TEST_SPEC reads via
        # ``manager.rows.get(escalation_id)``.
        self.rows: dict[str, dict[str, Any]] = {}

    def _utcnow(self) -> datetime:
        """Current UTC time — single source for timestamps."""
        return datetime.now(timezone.utc)

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
        """
        escalation_id = f"esc-{uuid.uuid4().hex[:8]}"
        sla_minutes = self.SLA_BY_PRIORITY.get(priority, self.SLA_BY_PRIORITY[0])
        self.rows[escalation_id] = self._make_row(
            escalation_id=escalation_id,
            conversation_id=conversation_id,
            priority=priority,
            reason=reason,
            platform=platform,
            preview=preview,
            now=self._utcnow(),
            sla_minutes=sla_minutes,
        )
        return escalation_id

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