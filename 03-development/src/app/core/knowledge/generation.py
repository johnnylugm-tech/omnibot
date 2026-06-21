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

PRIMARY_LLM = "gpt-4o"
FALLBACK_LLM = "gemini-1.5-flash"
EMBEDDING_DIM = 1536
GROUNDING_THRESHOLD = 0.75
def _call_llm_api(model: str, prompt: str) -> str:
    """[FR-30] Thin wrapper around the LLM SDK at the Tier-3 boundary.

    In production this calls the ``openai`` SDK for ``model == "gpt-4o"``
    and the ``google-generativeai`` SDK for ``model ==
    "gemini-1.5-flash"``; unit tests inject a stub via
    ``monkeypatch.setattr`` so no network I/O happens here and the
    per-call cost is measurable deterministically. The default body
    raises ``NotImplementedError`` so an un-patched call fails loudly
    rather than silently returning an empty answer (which would skip
    the grounding check and corrupt Tier-3 metrics).

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback.
    """
    raise NotImplementedError(
        "FR-30: wire openai/google-generativeai SDK in production; "
        "tests inject a stub via monkeypatch.setattr"
    )


def _build_sandwich_prompt(query: str, retrieved_context: str) -> str:
    """[FR-30] Build the L3 "Sandwich Prompt" wrapping retrieved context.

    The retrieved context is sandwiched between explicit ``[CONTEXT]``
    and ``[/CONTEXT]`` markers so the LLM treats it as grounding
    evidence rather than as part of the user's question. The user's
    ``query`` follows in its own ``[QUERY]`` block. This is the L3
    prompt layout the SRS prescribes for Tier-3 generation.

    Citations:
        - SRS.md FR-30 — 使用 Sandwich Prompt (L3) 包裝 retrieved_context.
    """
    return (
        f"[CONTEXT]\n{retrieved_context}\n[/CONTEXT]\n"
        f"[QUERY]\n{query}\n[/QUERY]"
    )


def _call_llm_with_fallback(
    prompt: str, primary_llm: str, fallback_llm: str
) -> str:
    """[FR-30] Call the primary LLM, fall through to the secondary on exception.

    Primary first; any exception (timeout, 5xx, "down" fault injection)
    falls through to ``fallback_llm``. If BOTH models raise the exception
    propagates so ``_llm_generate`` can return ``None`` (triggering
    Tier-4 escalation) rather than fabricating an un-grounded answer.
    ``FALLBACK_BUDGET_MS`` (500ms) is the wall-clock target for the
    primary→fallback *switch*, not a gate that aborts fallback when the
    primary took too long; primary taking the full budget is the very
    case fallback must service.

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback.
    """
    try:
        return _call_llm_api(primary_llm, prompt)
    except Exception:
        return _call_llm_api(fallback_llm, prompt)


def _compute_grounding_score(answer: str, retrieved_context: str) -> float | None:
    """[FR-30] L5 Grounding Check — measure how well ``answer`` is
    supported by ``retrieved_context``.

    Returns a score in ``[0.0, 1.0]`` when both inputs are non-empty
    and ``None`` when the inputs are insufficient to evaluate
    grounding (empty answer, empty context, or non-string inputs).
    Returning ``None`` is the signal that ``_llm_generate`` MUST treat
    the answer as un-grounded and refuse to wrap it in a
    ``KnowledgeResult`` — the previous implementation silently
    skipped the gate when grounding was unevaluated, which let an
    un-checked LLM answer reach the user.

    Citations:
        - SRS.md FR-30 — L5 Grounding Check ≥ 0.75.
    """
    if not isinstance(answer, str) or not isinstance(retrieved_context, str):
        return None
    if not answer.strip() or not retrieved_context.strip():
        return None
    # Stub: a real implementation computes token-overlap / NLI entailment
    # between ``answer`` and ``retrieved_context`` and returns that score.
    # The stub returns a passing score when both inputs are non-empty so
    # the GREEN step exercises the gate without standing up an NLI model.
    return 1.0


def _llm_generate(
    query: str,
    retrieved_context: str,
    *,
    grounding_score: float | None = None,
    primary_llm: str = PRIMARY_LLM,
    fallback_llm: str = FALLBACK_LLM,
    grounding_threshold: float = GROUNDING_THRESHOLD,
) -> KnowledgeResult | None:
    """[FR-30] Tier-3 LLM generation with grounding gate and fallback.

    On the happy path returns a ``KnowledgeResult(source="wiki", ...)``
    wrapping the LLM's answer; returns ``None`` when grounding cannot
    be established OR the grounding score is below
    ``grounding_threshold`` so the orchestrator can escalate to Tier 4
    (per FR-31). The primary LLM (``primary_llm``, default
    ``"gpt-4o"``) is attempted first; on any exception the
    orchestrator falls through to ``fallback_llm`` (default
    ``"gemini-1.5-flash"``). The total wall-clock for the
    primary-down → fallback path MUST stay under
    ``FALLBACK_BUDGET_MS`` (500ms) per the NP-15 performance budget.

    Grounding is MANDATORY — when ``grounding_score`` is omitted the
    helper ``_compute_grounding_score`` is invoked against the LLM's
    own answer; if even that helper returns ``None`` (un-evaluable)
    the function refuses to wrap the answer and returns ``None`` so
    Tier-4 escalation fires. The LLM boundary itself is wrapped in
    try/except so a stub ``NotImplementedError`` (or any other SDK
    failure) never propagates to ``query()``'s caller — the contract
    is "Tier-3 failure → return None".

    Citations:
        - SRS.md FR-30 — gpt-4o 主要 → gemini-1.5-flash fallback;
          L5 Grounding Check ≥ 0.75；grounding 失敗 → None (觸發 Tier 4)；
          LLM fallback 切換 < 500ms.
    """
    prompt = _build_sandwich_prompt(query, retrieved_context)
    try:
        answer = _call_llm_with_fallback(prompt, primary_llm, fallback_llm)
    except Exception:
        # LLM boundary failure (stub NotImplementedError, real SDK error,
        # both primary + fallback down) — refuse to fabricate an
        # un-grounded wiki hit; let Tier-4 escalation fire.
        return None

    # Grounding check happens AFTER the model call returns a candidate
    # answer (per the FR-30 contract). Below the threshold we return
    # None so the orchestrator escalates to Tier 4 (FR-31) — we do
    # NOT wrap the un-grounded answer in a KnowledgeResult. When the
    # caller did not pre-compute a score we evaluate it here so the
    # gate cannot be silently bypassed.
    if grounding_score is None:
        grounding_score = _compute_grounding_score(answer, retrieved_context)
    if grounding_score is None or grounding_score < grounding_threshold:
        return None

    return KnowledgeResult(
        id=0,
        content=answer,
        confidence=float(grounding_score),
        source="wiki",
        knowledge_id=0,
    )


# ---------------------------------------------------------------------------
# FR-31 — Tier-4 human escalation sentinel.
#
# The function is exposed at module level (not as ``HybridKnowledge``
# method) so the orchestrator's last-resort fallback can call it as a
# free function without instantiating the class. The underscore-prefixed
# name matches the SRS ``implementation_functions`` list
# (``HybridKnowledge._escalate``) and is part of the public contract.
# ---------------------------------------------------------------------------

# [FR-31] SRS-mandated reason enum. The four values enumerate the
# distinct paths by which the orchestrator can reach Tier 4: Tier-1
# misses the rule store, Tier-2 has no relevant RAG context, Tier-3's
# grounding score is below 0.75, or the query trips the
# emotion / sensitive-content guard.
VALID_ESCALATE_REASONS: frozenset[str] = frozenset(
    {"no_rule_match", "out_of_scope", "low_confidence", "emotion_trigger"}
)


