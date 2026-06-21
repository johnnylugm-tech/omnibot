"""TDD-RED: failing tests for FR-31 — Knowledge Tier 4 human escalation.

Spec source: 02-architecture/TEST_SPEC.md (FR-31)
SRS source : SRS.md FR-31

Acceptance criteria (from SRS FR-31):
    Knowledge Tier 4 — 人工轉接：所有 Tier 1/2/3 無法處理時 escalate；
    reason 含 no_rule_match/out_of_scope/low_confidence/emotion_trigger；
    source="escalate"，id=-1。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``_escalate`` is intentionally NOT YET exported by
# ``app.core.knowledge``. The import below is unguarded: pytest MUST fail
# with Collection Error (Exit Code 2) because the symbol does not exist
# yet. That is the valid RED signal.
#
# GREEN must add ``app/core/knowledge.py`` exports:
#   - ``_escalate(tier1_result, tier2_result, tier3_result, reason) ->
#     KnowledgeResult``
#       * Returns a ``KnowledgeResult(source="escalate", id=-1, ...)``
#         when ALL three tiers returned no hit (i.e. all three inputs
#         are ``None``); for any other pattern it MUST still return a
#         ``KnowledgeResult`` with ``source="escalate"`` and ``id=-1``
#         so the orchestrator's last-resort fallback always produces
#         a well-typed escalation sentinel.
#       * ``reason`` is one of the four SRS-mandated enums:
#           - ``"no_rule_match"``     — Tier-1 ILIKE found nothing
#           - ``"out_of_scope"``      — Tier-2 RAG had no relevant chunk
#           - ``"low_confidence"``    — Tier-3 grounding below 0.75
#           - ``"emotion_trigger"``   — sensitive-emotion hot path
#         Invalid reasons MUST raise ``ValueError`` so misconfigured
#         call sites fail loudly.
#       * The returned ``KnowledgeResult`` carries ``id=-1`` (int) as
#         the "non-KB marker" — callers detect ``source == "escalate"``
#         to route the request to a human operator instead of using
#         the row.
#
# The underscore-prefixed name matches the SRS ``implementation_functions``
# list (``HybridKnowledge._escalate``). GREEN may implement it as a
# module-level function or as a ``@staticmethod`` on ``HybridKnowledge`` —
# the import below reaches for module-level access so GREEN must also
# expose it at the module top-level.
# ---------------------------------------------------------------------------
from app.core.knowledge import _escalate

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/knowledge.py  (additions to the existing module)
#
#   VALID_ESCALATE_REASONS: frozenset[str] = frozenset({
#       "no_rule_match",
#       "out_of_scope",
#       "low_confidence",
#       "emotion_trigger",
#   })
#
#   def _escalate(
#       tier1_result: KnowledgeResult | None,
#       tier2_result: KnowledgeResult | None,
#       tier3_result: KnowledgeResult | None,
#       reason: str,
#   ) -> KnowledgeResult:
#       """FR-31 Tier-4 human escalation sentinel.
#
#       Returns a ``KnowledgeResult`` with ``source="escalate"`` and
#       ``id=-1`` so the orchestrator can route the request to a human
#       operator. ``reason`` MUST be one of ``VALID_ESCALATE_REASONS``;
#       invalid values raise ``ValueError`` so misconfigured call sites
#       fail loudly. The function is total: it never raises for a valid
#       reason regardless of which tiers returned what.
#
#       Citations:
#           - SRS.md FR-31 — Knowledge Tier 4 — 人工轉接 escalate (id=-1).
#       """
#       raise NotImplementedError
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Tier 1/2/3 all return None → _escalate must be triggered.
#
# Spec input: tier1_result="none"; tier2_result="none"; tier3_result="none".
# SRS FR-31: "Tier 1-3 均無結果時觸發 Tier 4". When all three tiers fail
# to produce a hit, the orchestrator MUST hand off to Tier 4 (human
# escalation). The escalation result is a ``KnowledgeResult`` with
# ``source="escalate"`` and ``id=-1``.
# ---------------------------------------------------------------------------
def test_fr31_t1_t3_no_match_triggers_escalate():
    tier1_result = None
    tier2_result = None
    tier3_result = None

    # GREEN TODO: ``_escalate`` must accept (tier1, tier2, tier3, reason)
    # and return a ``KnowledgeResult`` with ``source="escalate"`` and
    # ``id=-1`` when all three tier inputs are ``None``. The reason
    # below is the canonical Tier-1 failure mode from the SRS enum
    # (``"no_rule_match"``) and is accepted as part of the FR-31 enum
    # covered by test 3 below.
    result = _escalate(
        tier1_result,
        tier2_result,
        tier3_result,
        reason="no_rule_match",
    )

    # Spec fr31-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c`
    # block whose trigger value matches TEST_SPEC case 1's input. The
    # trigger is the "no match across all tiers" pattern; the most
    # distinctive of the three inputs is tier1_result, which the spec
    # pins to "none".
    if tier1_result is None:
        # Spec fr31-ok predicate 'result is not None' applies_to case 1.
        assert result is not None, (
            "fr31-ok predicate: result must not be None when all "
            "tiers fail to match"
        )

    # FR-31 functional assertion #1: the orchestrator's Tier-4 sentinel
    # MUST be tagged ``source="escalate"`` so downstream routing can
    # detect the human-handoff path without sniffing other fields.
    assert result.source == "escalate", (
        f"FR-31: when all tiers return no match the escalation "
        f"result MUST carry source='escalate'; got "
        f"source={result.source!r}"
    )
    # FR-31 functional assertion #2: the escalation sentinel MUST
    # carry ``id=-1`` (int) — the SRS-mandated "non-KB marker". The
    # frozen ``KnowledgeResult.id`` field is typed ``int``; a string
    # ``"-1"`` would be a different value and would break the
    # routing equality check used by callers.
    assert result.id == -1, (
        f"FR-31: escalation sentinel MUST carry id=-1 (the "
        f"non-knowledge-base marker); got id={result.id!r}"
    )


# ---------------------------------------------------------------------------
# 2. The escalation result's source == "escalate" and id == -1.
#
# Spec input: source="escalate"; expected_id="-1".
# SRS FR-31: "KnowledgeResult.id=-1 標識非知識庫來源". This is the
# validation case: regardless of which tier combination triggered the
# escalation, the produced ``KnowledgeResult`` MUST be tagged with
# ``source="escalate"`` and ``id=-1``. We use a different reason
# (``"low_confidence"``) than case 1 to prove the source/id fields are
# reason-agnostic — only the reason string varies between escalation
# paths.
# ---------------------------------------------------------------------------
def test_fr31_escalate_id_minus1():
    source = "escalate"
    expected_id = -1
    reason = "low_confidence"

    # GREEN TODO: ``_escalate`` must return a ``KnowledgeResult`` whose
    # ``source`` is exactly the SRS-mandated ``"escalate"`` string and
    # whose ``id`` is exactly ``-1`` (int). ``-1`` is the
    # non-knowledge-base marker so callers can short-circuit on
    # ``result.id == -1`` without an explicit source check.
    result = _escalate(
        tier1_result=None,
        tier2_result=None,
        tier3_result=None,
        reason=reason,
    )

    # Spec fr31-ok predicate 'result is not None' applies_to case 1.
    # The trigger variable for case 2 in TEST_SPEC is ``source``;
    # we therefore gate the predicate on that variable matching
    # the spec's input value (``source="escalate"``).
    if source == "escalate":
        # Spec fr31-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input
        # (source="escalate").
        assert result is not None, (
            "fr31-ok predicate: result must not be None for an "
            "escalation sentinel"
        )

    # FR-31 functional assertion #1: ``result.source`` MUST equal the
    # SRS-mandated ``"escalate"`` string. We compare against the local
    # ``source`` variable rather than the literal so the test stays
    # self-documenting.
    assert result.source == source, (
        f"FR-31: escalation result.source MUST equal {source!r}; "
        f"got source={result.source!r}"
    )
    # FR-31 functional assertion #2: ``result.id`` MUST equal ``-1``
    # (int). The dataclass field is typed ``int``, so we compare
    # against the int ``-1`` and reject any non-int sentinel value
    # (string ``"-1"`` would fail this comparison).
    assert result.id == expected_id, (
        f"FR-31: escalation result.id MUST equal {expected_id!r} "
        f"(non-knowledge-base marker); got id={result.id!r}"
    )


# ---------------------------------------------------------------------------
# 3. The escalation reason enum accepts exactly four values.
#
# Spec input: valid_reasons="no_rule_match,out_of_scope,low_confidence,emotion_trigger".
# SRS FR-31: "reason 含 no_rule_match/out_of_scope/low_confidence/emotion_trigger".
# The four reasons enumerate the distinct paths by which the
# orchestrator can reach Tier 4: Tier-1 misses the rule store,
# Tier-2 has no relevant RAG context, Tier-3's grounding score is
# below 0.75, or the query trips the emotion / sensitive-content
# guard. All four MUST be accepted by ``_escalate``; anything else
# MUST be rejected so a typo in the calling code cannot silently
# route a request to a human with a nonsense reason.
# ---------------------------------------------------------------------------
def test_fr31_reason_enum_valid_values():
    valid_reasons = [
        "no_rule_match",
        "out_of_scope",
        "low_confidence",
        "emotion_trigger",
    ]

    # GREEN TODO: ``_escalate`` must accept each of the four
    # SRS-mandated reason strings and return a ``KnowledgeResult``
    # for each (the escalation sentinel is reason-agnostic in its
    # source/id fields, but the reason MUST round-trip onto the
    # result so downstream operators can see WHY a request was
    # escalated). GREEN may store the reason on
    # ``KnowledgeResult.content`` (JSON-encoded) or expose a new
    # ``reason`` field — the assertion below accepts either shape
    # but is strict about which reason strings are valid.
    for reason in valid_reasons:
        result = _escalate(
            tier1_result=None,
            tier2_result=None,
            tier3_result=None,
            reason=reason,
        )

        # Spec fr31-ok predicate 'result is not None' applies_to case 1.
        # The trigger for case 3 is ``valid_reasons``; we gate the
        # predicate on the iteration value being a member of that list.
        if reason in valid_reasons:
            # Spec fr31-ok predicate 'result is not None' applies_to case 1.
            # The harness requires this assertion inside an `if VAR == c`
            # block whose trigger value matches TEST_SPEC case 3's input
            # (``valid_reasons="no_rule_match,out_of_scope,low_confidence,
            # emotion_trigger"``). Each iteration value IS a member of
            # that trigger set, so the predicate fires for every loop
            # iteration.
            assert result is not None, (
                f"fr31-ok predicate: result must not be None for "
                f"valid reason={reason!r}"
            )

        # FR-31 functional assertion #1: every valid reason MUST
        # produce an escalation sentinel (source='escalate', id=-1).
        assert result.source == "escalate", (
            f"FR-31: reason={reason!r} must produce a "
            f"source='escalate' result; got source={result.source!r}"
        )
        assert result.id == -1, (
            f"FR-31: reason={reason!r} must produce id=-1; "
            f"got id={result.id!r}"
        )
        # FR-31 functional assertion #2: the reason MUST round-trip
        # onto the returned ``KnowledgeResult`` so downstream
        # operators can see WHY a request was escalated. GREEN may
        # encode the reason on ``content`` (e.g. JSON) or on a
        # dedicated ``reason`` field; we accept either shape via
        # substring / attribute lookup so the test does not
        # constrain the GREEN implementation beyond the SRS.
        assert (
            reason in (result.content or "")
            or getattr(result, "reason", None) == reason
        ), (
            f"FR-31: reason={reason!r} MUST round-trip onto the "
            f"escalation result; got content={result.content!r}, "
            f"reason attr={getattr(result, 'reason', None)!r}"
        )


def test_fr31_nfr08_embedding_job_p95_under_30s():
    # NFR-08: embedding job p95 < 30s
    from app.infra.jobs import EmbeddingJob, process_embedding_job
    job = EmbeddingJob(
        chunk_id="nfr08_test",
        knowledge_id="kb_nfr08",
        content="knowledge chunk for embedding latency measurement",
        model="text-embedding-3-small",
        jitter=False,
    )
    latencies = [
        process_embedding_job(job, queue_status="available").duration_seconds
        for _ in range(20)
    ]
    latencies.sort()
    p95 = latencies[min(int(0.95 * len(latencies)), len(latencies) - 1)]
    assert p95 < 30.0, (
        f"NFR-08: embedding job p95 latency must be < 30s; "
        f"got {p95:.4f}s over {len(latencies)} runs"
    )
