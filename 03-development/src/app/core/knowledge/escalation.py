from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# [FR-32] SRS-mandated source enum. The four values enumerate the
# tier labels the hybrid pipeline emits: Tier-1 ILIKE rule hit
# (``"rule"``), Tier-2 RAG short-circuit (``"rag"``), Tier-3 LLM
# answer (``"wiki"``), Tier-4 human escalation (``"escalate"``).
# Construction rejects any other string via ``KnowledgeResult.__post_init__``.
VALID_SOURCES: frozenset[str] = frozenset(
    {"rule", "rag", "wiki", "escalate"}
)


from .models import KnowledgeResult
def _escalate(
    tier1_result: KnowledgeResult | None,
    tier2_result: KnowledgeResult | None,
    tier3_result: KnowledgeResult | None,
    reason: str,
) -> KnowledgeResult:
    """[FR-31] Tier-4 human escalation sentinel.

    Returns a ``KnowledgeResult`` with ``source="escalate"`` and
    ``id=-1`` so the orchestrator can route the request to a human
    operator instead of consuming a knowledge-base row. ``reason`` MUST
    be one of ``VALID_ESCALATE_REASONS``; invalid values raise
    ``ValueError`` so a typo in the calling code cannot silently route
    a request to a human with a nonsense reason. The reason is
    JSON-encoded on ``content`` so downstream operators can see WHY a
    request was escalated without sniffing other fields.

    The function is total: it never raises for a valid reason
    regardless of which tiers returned what — a Tier-2 hit combined
    with a Tier-3 escalation (e.g. grounding failure after a RAG hit)
    still produces a well-typed ``KnowledgeResult`` with the
    ``source="escalate"`` / ``id=-1`` markers so the orchestrator's
    last-resort fallback is never ambiguous. The tier arguments are
    accepted for API symmetry with the orchestrator's last-resort
    call site but are intentionally not consumed — the sentinel is
    reason-agnostic in its source/id fields per FR-31.

    Citations:
        - SRS.md FR-31 (line 74) — Knowledge Tier 4 — 人工轉接：
          所有 Tier 1/2/3 無法處理時 escalate；reason 含
          no_rule_match/out_of_scope/low_confidence/emotion_trigger；
          source="escalate"，id=-1.
        - SRS.md FR-32 (line 75) — KnowledgeResult.id=-1 代表非知識庫來源.
    """
    del tier1_result, tier2_result, tier3_result
    if reason not in VALID_ESCALATE_REASONS:
        raise ValueError(
            f"FR-31: invalid escalate reason={reason!r}; "
            f"must be one of {sorted(VALID_ESCALATE_REASONS)}"
        )

    # JSON-encode the reason onto content so downstream operators can
    # see WHY a request was escalated. The encoded form keeps the
    # reason as a substring of ``content`` (so callers that grep for
    # it do not need a dedicated ``reason`` field) while remaining
    # machine-parseable.
    try:
        payload = json.dumps({"reason": reason})
    except Exception:
        payload = f'{{"reason": "{reason}"}}'
    return KnowledgeResult(
        id=-1,
        content=payload,
        confidence=0.0,
        source="escalate",
        knowledge_id=-1,
    )
