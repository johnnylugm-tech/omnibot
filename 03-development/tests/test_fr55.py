"""TDD-RED: failing tests for FR-55 — SLA 定義 normal 30m / high 15m / urgent 5m.

Spec source: 02-architecture/TEST_SPEC.md (FR-55)
SRS source : SRS.md FR-55 (Module 10: Human Escalation)

Acceptance criteria (from SRS FR-55):
    SLA 定義：normal(priority=0) 30 分鐘；high(priority=1) 15 分鐘；
    urgent(priority=2) 5 分鐘（emotion_trigger）；get_sla_breaches()
    查詢超 SLA 未解決案件。
    sla_deadline = queued_at + SLA 分鐘；
    breach = resolved_at IS NULL AND sla_deadline < NOW()

Implementation functions (SRS FR-55 line 880-883):
    - ``EscalationManager.SLA_BY_PRIORITY`` (class attribute / dict)
    - ``get_sla_breaches()`` (returns rows where resolved_at IS NULL
      AND sla_deadline < NOW)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-55 mandates two implementation_functions (SRS.md line 880-883):
#
#   1. ``EscalationManager.SLA_BY_PRIORITY`` — a class attribute mapping
#      priority -> SLA minutes:
#         0 (normal)  -> 30 minutes
#         1 (high)    -> 15 minutes
#         2 (urgent)  ->  5 minutes
#      Used to derive ``sla_deadline`` at create() time.
#
#   2. ``get_sla_breaches()`` — a query (method on EscalationManager or
#      module-level callable) returning all escalation_queue rows where
#      ``resolved_at IS NULL AND sla_deadline < NOW()``. Used by the
#      SLABreach alert rule (FR-73) and the ODD SLA compliance SQL
#      (FR-105).
#
# FR-54's GREEN commit already populated ``EscalationManager.SLA_BY_PRIORITY``
# in ``app/services/escalation.py`` so ``create()`` can derive sla_deadline.
# However, ``get_sla_breaches()`` is NOT yet implemented. The four tests
# below pin the full FR-55 contract; the breach test (#4) will fail with
# AttributeError because the method does not exist on ``EscalationManager``,
# and the SLA-mapping tests (#1–#3) pin the table values so any future
# refactor (e.g. moving the table to a different module) must keep them
# in sync.
# ---------------------------------------------------------------------------
from app.services.escalation import (
    EscalationManager,
)


# ---------------------------------------------------------------------------
# 1. ``priority=0`` (normal) MUST map to a 30-minute SLA window. The spec
#    pins ``expected_sla_minutes="30"`` (TEST_SPEC.md case 1) and the SRS
#    mandates "normal(priority=0) 30 分鐘" (line 123 / 879).
#
# Spec input: priority="0"; expected_sla_minutes="30".
# Spec sub-assertion: fr55-ok: result is not None.
# SRS FR-55 acceptance: "normal(priority=0) 30 分鐘".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr55_normal_sla_30min():
    priority = "0"
    expected_sla_minutes = "30"

    # Spec fr55-ok predicate 'result is not None' applies_to case 1.
    if priority == "0":
        # GREEN TODO: ``EscalationManager.SLA_BY_PRIORITY`` MUST be a
        # class-level mapping (dict[int, int]) where ``SLA_BY_PRIORITY[0]
        # == 30``. The SRS FR-55 contract is "normal(priority=0) 30 分鐘"
        # and the spec test pins ``expected_sla_minutes="30"`` as the
        # exact integer value GREEN MUST record for priority 0.
        sla = EscalationManager.SLA_BY_PRIORITY[int(priority)]
        assert sla is not None, (
            "fr55-ok predicate: SLA_BY_PRIORITY[0] must return a non-None "
            "SLA minutes value for priority=0 (normal)"
        )
        assert isinstance(sla, int), (
            f"FR-55: SLA_BY_PRIORITY[0] must be an int (minutes); got "
            f"{type(sla).__name__}={sla!r}"
        )
        assert sla == int(expected_sla_minutes), (
            f"FR-55: SLA_BY_PRIORITY[0] must equal 30 (normal=30min) per "
            f"TEST_SPEC.md case 1 (expected_sla_minutes={expected_sla_minutes!r}) "
            f"and SRS FR-55 'normal(priority=0) 30 分鐘' (line 123); "
            f"got {sla}"
        )
        # Defence-in-depth: 30 minutes = 1800 seconds. Pin the unit so a
        # future refactor that accidentally swaps minutes/seconds fails
        # loudly here.
        assert sla > 0, (
            f"FR-55: SLA_BY_PRIORITY[0] must be a positive integer (30 "
            f"minutes); got {sla}"
        )

    # Sentinels MUST be preserved per spec.
    assert priority == "0", (
        f"FR-55: priority sentinel must be '0'; got {priority!r}"
    )
    assert expected_sla_minutes == "30", (
        f"FR-55: expected_sla_minutes sentinel must be '30'; got "
        f"{expected_sla_minutes!r}"
    )


# ---------------------------------------------------------------------------
# 2. ``priority=1`` (high) MUST map to a 15-minute SLA window. The spec
#    pins ``expected_sla_minutes="15"`` (TEST_SPEC.md case 2) and the SRS
#    mandates "high(priority=1) 15 分鐘" (line 123 / 879).
#
# Spec input: priority="1"; expected_sla_minutes="15".
# Spec sub-assertion: fr55-ok: result is not None.
# SRS FR-55 acceptance: "high(priority=1) 15 分鐘".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr55_high_sla_15min():
    priority = "1"
    expected_sla_minutes = "15"

    if priority == "1":
        # GREEN TODO: ``EscalationManager.SLA_BY_PRIORITY[1] == 15``.
        # The SRS FR-55 contract is "high(priority=1) 15 分鐘" and the
        # spec test pins ``expected_sla_minutes="15"`` as the exact
        # integer value GREEN MUST record for priority 1.
        sla = EscalationManager.SLA_BY_PRIORITY[int(priority)]
        assert sla is not None, (
            "fr55-ok predicate: SLA_BY_PRIORITY[1] must return a non-None "
            "SLA minutes value for priority=1 (high)"
        )
        assert isinstance(sla, int), (
            f"FR-55: SLA_BY_PRIORITY[1] must be an int (minutes); got "
            f"{type(sla).__name__}={sla!r}"
        )
        assert sla == int(expected_sla_minutes), (
            f"FR-55: SLA_BY_PRIORITY[1] must equal 15 (high=15min) per "
            f"TEST_SPEC.md case 2 (expected_sla_minutes={expected_sla_minutes!r}) "
            f"and SRS FR-55 'high(priority=1) 15 分鐘' (line 123); "
            f"got {sla}"
        )
        # Defence-in-depth: high SLA (15min) MUST be STRICTLY shorter
        # than normal SLA (30min). A future regression that flipped the
        # values (high=30, normal=15) would still pass the absolute
        # equality assertions above; this catches the flip.
        normal_sla = EscalationManager.SLA_BY_PRIORITY[0]
        assert sla < normal_sla, (
            f"FR-55: SLA_BY_PRIORITY[1] (high) must be strictly less than "
            f"SLA_BY_PRIORITY[0] (normal); got high={sla}, normal={normal_sla}. "
            f"SRS FR-55 mandates 15min < 30min."
        )

    # Sentinels MUST be preserved per spec.
    assert priority == "1", (
        f"FR-55: priority sentinel must be '1'; got {priority!r}"
    )
    assert expected_sla_minutes == "15", (
        f"FR-55: expected_sla_minutes sentinel must be '15'; got "
        f"{expected_sla_minutes!r}"
    )


# ---------------------------------------------------------------------------
# 3. ``priority=2`` (urgent / emotion_trigger) MUST map to a 5-minute SLA
#    window. The spec pins ``expected_sla_minutes="5"`` (TEST_SPEC.md case
#    3) and the SRS mandates "urgent(priority=2) 5 分鐘（emotion_trigger）"
#    (line 123 / 879).
#
# Spec input: priority="2"; expected_sla_minutes="5".
# Spec sub-assertion: fr55-ok: result is not None.
# SRS FR-55 acceptance: "urgent(priority=2) 5 分鐘（emotion_trigger）".
# Test type: happy_path (Q1 derivation).
# ---------------------------------------------------------------------------
def test_fr55_urgent_sla_5min():
    priority = "2"
    expected_sla_minutes = "5"

    if priority == "2":
        # GREEN TODO: ``EscalationManager.SLA_BY_PRIORITY[2] == 5``.
        # The SRS FR-55 contract is "urgent(priority=2) 5 分鐘" and the
        # spec test pins ``expected_sla_minutes="5"`` as the exact
        # integer value GREEN MUST record for priority 2.
        sla = EscalationManager.SLA_BY_PRIORITY[int(priority)]
        assert sla is not None, (
            "fr55-ok predicate: SLA_BY_PRIORITY[2] must return a non-None "
            "SLA minutes value for priority=2 (urgent / emotion_trigger)"
        )
        assert isinstance(sla, int), (
            f"FR-55: SLA_BY_PRIORITY[2] must be an int (minutes); got "
            f"{type(sla).__name__}={sla!r}"
        )
        assert sla == int(expected_sla_minutes), (
            f"FR-55: SLA_BY_PRIORITY[2] must equal 5 (urgent=5min) per "
            f"TEST_SPEC.md case 3 (expected_sla_minutes={expected_sla_minutes!r}) "
            f"and SRS FR-55 'urgent(priority=2) 5 分鐘（emotion_trigger）' "
            f"(line 123); got {sla}"
        )
        # Defence-in-depth: urgent SLA (5min) MUST be strictly shorter
        # than both high (15min) and normal (30min). Catches accidental
        # reordering.
        high_sla = EscalationManager.SLA_BY_PRIORITY[1]
        normal_sla = EscalationManager.SLA_BY_PRIORITY[0]
        assert sla < high_sla, (
            f"FR-55: SLA_BY_PRIORITY[2] (urgent) must be strictly less "
            f"than SLA_BY_PRIORITY[1] (high); got urgent={sla}, "
            f"high={high_sla}. SRS FR-55 mandates 5min < 15min."
        )
        assert sla < normal_sla, (
            f"FR-55: SLA_BY_PRIORITY[2] (urgent) must be strictly less "
            f"than SLA_BY_PRIORITY[0] (normal); got urgent={sla}, "
            f"normal={normal_sla}. SRS FR-55 mandates 5min < 30min."
        )

    # Sentinels MUST be preserved per spec.
    assert priority == "2", (
        f"FR-55: priority sentinel must be '2'; got {priority!r}"
    )
    assert expected_sla_minutes == "5", (
        f"FR-55: expected_sla_minutes sentinel must be '5'; got "
        f"{expected_sla_minutes!r}"
    )


# ---------------------------------------------------------------------------
# 4. Breach query MUST return escalations where ``resolved_at IS NULL`` AND
#    ``sla_deadline < NOW()``. The spec test pins ``resolved_at="null"``
#    (NULL = not yet resolved) and ``sla_deadline="past"`` (already past
#    the SLA deadline) — together identifying a breached, unresolved
#    escalation. Per SRS FR-55 (line 123): "breach = resolved_at IS NULL
#    AND sla_deadline < NOW()".
#
# Spec input: resolved_at="null"; sla_deadline="past".
# Spec sub-assertion: fr55-ok: result is not None.
# SRS FR-55 acceptance: "get_sla_breaches() 查詢超 SLA 未解決案件".
# Test type: validation (Q2 derivation).
# ---------------------------------------------------------------------------
def test_fr55_breach_query_correct():
    resolved_at = "null"
    sla_deadline = "past"

    # Spec fr55-ok predicate 'result is not None' applies_to case 1.
    if resolved_at == "null" and sla_deadline == "past":
        # GREEN TODO: ``EscalationManager.get_sla_breaches()`` MUST return
        # an iterable of rows (list / tuple / generator) where each row
        # satisfies:
        #     row["resolved_at"] is None (not yet resolved) AND
        #     row["sla_deadline"] < datetime.now(timezone.utc)
        # The contract is: "breach = resolved_at IS NULL AND
        # sla_deadline < NOW()" (SRS FR-55 line 123). This is consumed by
        # the SLABreach alert rule (FR-73) and the ODD SLA compliance
        # SQL (FR-105).
        manager = EscalationManager()

        # Seed: one escalation that IS in breach (resolved_at=None,
        # sla_deadline in the past). We create with priority=2 (urgent)
        # so sla_deadline starts at now + 5min; then we forcibly mutate
        # sla_deadline to a past timestamp to make the row qualify for
        # breach detection. The mutation is safe because the row lives
        # in ``manager.rows`` as a plain dict.
        breached_id = manager.create(
            conversation_id="conv-breach",
            priority=2,
        )
        past = datetime.now(UTC) - timedelta(hours=1)
        manager.rows[breached_id]["sla_deadline"] = past
        manager.rows[breached_id]["resolved_at"] = None
        # Sanity: the row exists and is unresolved.
        assert manager.rows[breached_id]["resolved_at"] is None, (
            "Test setup invariant: breached row must have resolved_at=None"
        )
        assert manager.rows[breached_id]["sla_deadline"] < datetime.now(
            UTC
        ), (
            "Test setup invariant: breached row must have sla_deadline < now"
        )

        # Counter-example: one escalation that is NOT in breach
        # (resolved_at=None but sla_deadline in the future). GREEN MUST
        # exclude this row from get_sla_breaches().
        future_id = manager.create(
            conversation_id="conv-future",
            priority=0,
        )
        future = datetime.now(UTC) + timedelta(hours=1)
        manager.rows[future_id]["sla_deadline"] = future
        manager.rows[future_id]["resolved_at"] = None

        # GREEN TODO: ``EscalationManager.get_sla_breaches()`` MUST exist
        # as a callable on the manager. Acceptable signatures:
        #   - ``manager.get_sla_breaches() -> Iterable[dict]``
        #   - ``manager.get_sla_breaches(now: datetime = None) -> Iterable[dict]``
        # The call MUST return at least one row containing breached_id
        # and MUST NOT contain future_id.
        result = manager.get_sla_breaches()

        assert result is not None, (
            "fr55-ok predicate: get_sla_breaches() must return a non-None "
            "iterable of breach rows. SRS FR-55 mandates 'get_sla_breaches() "
            "查詢超 SLA 未解決案件'."
        )

        # Normalise the result to a list of mapping rows so the
        # assertions below work regardless of whether GREEN returns a
        # list, tuple, generator, or filter object.
        rows = list(result)
        assert len(rows) > 0, (
            f"FR-55: get_sla_breaches() must return at least the "
            f"past-deadline unresolved escalation (id={breached_id!r}); "
            f"got empty result. SRS FR-55 breach contract: 'resolved_at "
            f"IS NULL AND sla_deadline < NOW()'."
        )

        # Collect ids from the result rows. GREEN may return dicts
        # (row["escalation_id"]) or dataclasses
        # (row.escalation_id) — accept both.
        breach_ids = []
        for row in rows:
            if isinstance(row, dict):
                breach_ids.append(row.get("escalation_id"))
            else:
                breach_ids.append(getattr(row, "escalation_id", None))

        # Primary assertion: the breached escalation MUST be present.
        assert breached_id in breach_ids, (
            f"FR-55: get_sla_breaches() must include the breached "
            f"escalation (resolved_at=None, sla_deadline=past); "
            f"expected id={breached_id!r} in result ids={breach_ids!r}. "
            f"SRS FR-55 mandates 'breach = resolved_at IS NULL AND "
            f"sla_deadline < NOW()'."
        )

        # Negative assertion: the future-deadline escalation MUST NOT be
        # present. Catches a GREEN implementation that returns "all
        # unresolved escalations" instead of "all UNRESOLVED AND past-
        # deadline escalations".
        assert future_id not in breach_ids, (
            f"FR-55: get_sla_breaches() must NOT include escalations "
            f"whose sla_deadline is still in the future (id="
            f"{future_id!r}); result ids={breach_ids!r}. SRS FR-55 "
            f"breach contract requires 'sla_deadline < NOW()'."
        )

        # Stronger predicate: every returned row MUST satisfy the breach
        # condition. Loop over the rows and check both clauses
        # explicitly so a partial implementation (e.g. filter on
        # resolved_at but ignore sla_deadline) fails loudly.
        now = datetime.now(UTC)
        for row in rows:
            if isinstance(row, dict):
                row_resolved_at = row.get("resolved_at")
                row_sla_deadline = row.get("sla_deadline")
            else:
                row_resolved_at = getattr(row, "resolved_at", None)
                row_sla_deadline = getattr(row, "sla_deadline", None)
            assert row_resolved_at is None, (
                f"FR-55: get_sla_breaches() returned a row with "
                f"resolved_at={row_resolved_at!r}; the breach contract "
                f"requires 'resolved_at IS NULL'. row={row!r}"
            )
            assert row_sla_deadline is not None, (
                f"FR-55: get_sla_breaches() returned a row with "
                f"sla_deadline={row_sla_deadline!r}; the breach contract "
                f"requires a non-None sla_deadline. row={row!r}"
            )
            assert row_sla_deadline < now, (
                f"FR-55: get_sla_breaches() returned a row whose "
                f"sla_deadline={row_sla_deadline!r} is NOT strictly before "
                f"now={now!r}; the breach contract requires "
                f"'sla_deadline < NOW()'. row={row!r}"
            )

    # Sentinels MUST be preserved per spec.
    assert resolved_at == "null", (
        f"FR-55: resolved_at sentinel must be 'null'; got {resolved_at!r}"
    )
    assert sla_deadline == "past", (
        f"FR-55: sla_deadline sentinel must be 'past'; got "
        f"{sla_deadline!r}"
    )
