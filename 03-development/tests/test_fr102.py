"""TDD-RED: failing tests for FR-102 — RAG Debugger
(Tier 1+2 決策流程展示 + 相似度滑桿沙盒).

Spec source: 02-architecture/TEST_SPEC.md (FR-102)
SRS source : SRS.md FR-102 (Module 25: 管理 WebUI)
            "RAG Debugger：管理員輸入測試提問 → 展示 ILIKE 匹配結果+置信度、
             Child Chunk 餘弦相似度分數、Parent Chunk 內容、RRF k=60 Top-3
             評分；相似度閾值滑桿（預設 0.75，沙盒調整不寫入 platform_configs）"
SAD source  : 02-architecture/SAD.md §2.4
             "Module: webui.py — Knowledge CRUD + Markdown editor +
              CSV/JSON import + embedding status + RAG Debugger
              → FR-101 / FR-102"

Acceptance criteria (from SRS FR-102):
    - 管理員輸入測試提問
    - 展示 ILIKE 匹配結果 + 置信度 (Tier 1)
    - Child Chunk 餘弦相似度分數 (Tier 2)
    - Parent Chunk 內容
    - RRF k=60 Top-3 評分
    - 相似度閾值滑桿（預設 0.75）
    - 沙盒調整不寫入 platform_configs (sandbox-only)

The two TEST_SPEC cases (function names MUST match exactly):
    1. test_fr102_debugger_shows_tier1_tier2_flow
         Inputs: query="退款";
                 expected_sections="ilike_results,cosine_scores,rrf_top3"
         Type  : happy_path
    2. test_fr102_slider_adjustment_not_persisted
         Inputs: threshold_slider="0.80"; expected_db_unchanged="true"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr102-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test isolation — the RAG Debugger touches platform_configs (the persisted
# threshold store) and runs the Tier 1 ILIKE + Tier 2 RAG + RRF pipeline
# (FR-26 / FR-27). The GREEN implementation MUST expose injection seams so
# the unit tests can run without a live PostgreSQL / Redis. This autouse
# fixture is a no-op during RED (the import below raises before the
# fixture runs) and patches the seams once GREEN has landed.
#
# GREEN must:
#   - Define ``RAGDebugger`` accepting an injected ``config_store``
#     (platform_configs reader/writer) and an injected
#     ``knowledge_provider`` (or equivalent) in __init__. Tests will
#     inject in-memory stubs so no real PostgreSQL / Redis is touched.
#   - The ``config_store`` seam MUST be the only path to platform_configs:
#     ``set_slider_threshold`` (or whatever the slider-adjustment entry
#     point is called) MUST NOT call any DB writer directly; it must
#     only mutate an in-memory sandbox so the persisted platform_configs
#     row is left untouched.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_rag_debugger_io(monkeypatch):
    """Prevent real DB / Redis I/O during RAG Debugger unit tests.

    The default config_store stub is an in-memory dict so the test can
    assert the platform_configs row is unchanged after a slider
    adjustment. GREEN is expected to inject a config_store explicitly;
    this fixture is the second line of defence.
    """
    # Default config_store stub: in-memory dict keyed by config name.
    # GREEN will read/write via this seam, never touching the real
    # platform_configs table.
    _default_config_store = {
        "rag_cosine_threshold": 0.75,  # canonical default per SRS FR-102
    }

    class _InMemoryConfigStore:
        def __init__(self, initial):
            self._data = dict(initial)

        def get(self, key, default=None):
            return self._data.get(key, default)

        def set(self, key, value):
            # GREEN MUST NOT call this on a sandbox slider adjustment.
            self._data[key] = value
            return value

        def as_dict(self):
            return dict(self._data)

    monkeypatch.setattr(
        "app.infra.config_store.get_config_store",
        lambda: _InMemoryConfigStore(_default_config_store),
        raising=False,
    )

    yield


# ---------------------------------------------------------------------------
# Source under test — ``RAGDebugger`` and its companion classes/constants
# are intentionally NOT YET exported by ``app.admin.webui``. The imports
# below are unguarded: pytest MUST fail with Collection Error (Exit Code
# 2) because the symbol does not exist yet. That is the valid RED signal.
#
# GREEN must add to ``app/admin/webui.py`` (or a sibling module re-exported
# from there) the following public surface (the exact shape is GREEN's
# choice so long as these names and behaviours are observable):
#
#   - Canonical configuration constants
#       RAG_DEFAULT_THRESHOLD       = 0.75  # 滑桿預設值
#       RAG_RRF_K                   = 60    # RRF k=60 融合 (FR-27)
#       RAG_RRF_TOP_N               = 3     # RRF Top-3 評分
#       RAG_SECTION_ILIKE           = "ilike_results"
#       RAG_SECTION_COSINE          = "cosine_scores"
#       RAG_SECTION_RRF_TOP3        = "rrf_top3"
#       RAG_REQUIRED_SECTIONS       = ("ilike_results", "cosine_scores",
#                                      "rrf_top3")
#
#   - RAGDebugger
#       Top-level dispatcher for the RAG Debugger UI. Required
#       attributes / methods:
#           __init__(config_store=None, knowledge_provider=None)
#               Store the injected config_store (platform_configs
#               reader/writer) and knowledge_provider (or equivalent
#               seam for Tier 1 ILIKE + Tier 2 RAG). Tests inject
#               in-memory stubs so no real PostgreSQL / Redis is
#               touched.
#           debug(query: str, threshold: float = 0.75) -> DebuggerResult
#               Run the Tier 1+2 pipeline with the sandbox threshold
#               (does NOT touch platform_configs) and return a
#               DebuggerResult whose ``sections`` field contains the
#               three canonical section names: "ilike_results",
#               "cosine_scores", "rrf_top3".
#           set_slider_threshold(threshold: float) -> None
#               Sandbox-only slider adjustment. MUST NOT call the
#               injected config_store.set(...) (which would persist to
#               platform_configs). The persisted platform_configs
#               row MUST remain at RAG_DEFAULT_THRESHOLD after this
#               call.
#           get_saved_threshold() -> float
#               Read the persisted threshold from the injected
#               config_store (platform_configs). After a
#               set_slider_threshold(0.80) call, this MUST still
#               return 0.75.
#
#   - DebuggerResult
#       Result of a single RAG Debugger invocation. Required
#       attributes / methods:
#           query:           str
#           ilike_results:   list  (Tier 1: ILIKE matches + confidence)
#           cosine_scores:   list  (Tier 2: child chunk cosine scores)
#           rrf_top3:        list  (Top-3 RRF scores + parent content)
#           sections:        list[str]  (the three section names,
#                                       in display order)
#
#   - ILIKEMatch (optional, but if present MUST carry the canonical
#     fields)
#           row_id:    int
#           content:   str
#           confidence: float
#
#   - CosineHit (optional, but if present MUST carry the canonical
#     fields)
#           chunk_id:  str
#           score:     float
#
#   - RRFEntry (optional, but if present MUST carry the canonical
#     fields)
#           rank:      int
#           score:     float
#           parent_id: int
#           content:   str
#
# The tests below intentionally avoid any real PostgreSQL / Redis I/O —
# they exercise the RAGDebugger abstraction in isolation, which is the
# canonical unit-test shape for FR-102.
# ---------------------------------------------------------------------------
from app.admin.webui import (  # noqa: E402,F401
    # Constants — re-exported so the tests assert against the same
    # values the production code uses (and so the harness sees the same
    # names in the import surface as GREEN must expose).
    RAG_DEFAULT_THRESHOLD,
    RAG_REQUIRED_SECTIONS,
    RAG_RRF_K,
    RAG_RRF_TOP_N,
    RAG_SECTION_COSINE,
    RAG_SECTION_ILIKE,
    RAG_SECTION_RRF_TOP3,
    DebuggerResult,
    RAGDebugger,
)


# ---------------------------------------------------------------------------
# 1. The RAG Debugger surfaces the Tier 1+2 decision flow with the three
#    canonical sections (happy_path).
#
# Spec input: query="退款";
#             expected_sections="ilike_results,cosine_scores,rrf_top3".
# SRS FR-102: "管理員輸入測試提問 → 展示 ILIKE 匹配結果+置信度、Child
# Chunk 餘弦相似度分數、Parent Chunk 內容、RRF k=60 Top-3 評分". A
# regression that omitted any of the three sections would break the
# debugger's whole point (showing the Tier 1+2 decision flow); a
# regression that returned the sections under different names (e.g.
# "ilike_matches" or "rrf_results") would break the WebUI's
# section-renderer contract.
# ---------------------------------------------------------------------------
def test_fr102_debugger_shows_tier1_tier2_flow():
    # Spec input literals — also used as trigger values for the
    # fr102-ok sub-assertion guard.
    query = "退款"  # spec string sentinel
    expected_sections = "ilike_results,cosine_scores,rrf_top3"

    # GREEN TODO: the three RAG_SECTION_* constants MUST carry the
    # canonical section names so the debugger's output and the
    # spec-input "expected_sections" string can be matched exactly.
    assert RAG_SECTION_ILIKE == "ilike_results", (
        f"FR-102 RAG_SECTION_ILIKE must be 'ilike_results'; got "
        f"{RAG_SECTION_ILIKE!r}"
    )
    assert RAG_SECTION_COSINE == "cosine_scores", (
        f"FR-102 RAG_SECTION_COSINE must be 'cosine_scores'; got "
        f"{RAG_SECTION_COSINE!r}"
    )
    assert RAG_SECTION_RRF_TOP3 == "rrf_top3", (
        f"FR-102 RAG_SECTION_RRF_TOP3 must be 'rrf_top3'; got "
        f"{RAG_SECTION_RRF_TOP3!r}"
    )

    # Companion invariant: the default cosine threshold MUST be 0.75
    # (SRS FR-102 "相似度閾值滑桿（預設 0.75）"). A GREEN that used a
    # different default would silently shift the Tier 2 cut-off and
    # change the debugger's results.
    assert RAG_DEFAULT_THRESHOLD == 0.75, (
        f"FR-102 RAG_DEFAULT_THRESHOLD must be 0.75; got "
        f"{RAG_DEFAULT_THRESHOLD!r}"
    )

    # Companion invariant: RRF k MUST be 60 (FR-27) and the Top-N
    # MUST be 3 (SRS FR-102 "RRF k=60 Top-3 評分").
    assert RAG_RRF_K == 60, (
        f"FR-102 RAG_RRF_K must be 60; got {RAG_RRF_K!r}"
    )
    assert RAG_RRF_TOP_N == 3, (
        f"FR-102 RAG_RRF_TOP_N must be 3; got {RAG_RRF_TOP_N!r}"
    )

    # Companion invariant: the three required section names MUST
    # appear in RAG_REQUIRED_SECTIONS in the canonical order so the
    # WebUI's section-renderer can iterate them deterministically.
    assert "ilike_results" in RAG_REQUIRED_SECTIONS, (
        f"FR-102 RAG_REQUIRED_SECTIONS must contain 'ilike_results'; "
        f"got {RAG_REQUIRED_SECTIONS!r}"
    )
    assert "cosine_scores" in RAG_REQUIRED_SECTIONS, (
        f"FR-102 RAG_REQUIRED_SECTIONS must contain 'cosine_scores'; "
        f"got {RAG_REQUIRED_SECTIONS!r}"
    )
    assert "rrf_top3" in RAG_REQUIRED_SECTIONS, (
        f"FR-102 RAG_REQUIRED_SECTIONS must contain 'rrf_top3'; "
        f"got {RAG_REQUIRED_SECTIONS!r}"
    )

    # GREEN TODO: ``RAGDebugger()`` constructed with no arguments MUST
    # expose the FR-102 debug entry point. The default config_store
    # is wired by the autouse fixture above (an in-memory dict with
    # rag_cosine_threshold=0.75). GREEN may spell the method however
    # it likes so long as it accepts (query, threshold) and returns
    # a ``DebuggerResult``.
    debugger = RAGDebugger()
    assert hasattr(debugger, "debug") and callable(debugger.debug), (
        "FR-102 RAGDebugger must expose ``debug(query, threshold)``"
    )

    result = debugger.debug(query=query, threshold=RAG_DEFAULT_THRESHOLD)

    # Spec fr102-ok predicate: result is not None (applies_to case 1).
    assert result is not None, (
        "fr102-ok predicate: RAGDebugger.debug() result must not be None"
    )

    # Public surface contract: ``DebuggerResult`` MUST expose
    # ``sections`` (the three section names) plus the three payload
    # lists. GREEN may spell them as attributes or accessors; both
    # forms are checked below.
    assert hasattr(result, "sections"), (
        "FR-102 DebuggerResult must expose ``sections``"
    )
    observed_sections = (
        result.sections()
        if callable(getattr(result, "sections", None))
        else result.sections
    )
    assert observed_sections is not None, (
        "FR-102 DebuggerResult.sections must not be None"
    )

    # The ``sections`` field MUST contain the three canonical names —
    # the FR's "expected_sections" guarantee. A regression that
    # omitted "rrf_top3" (e.g. only showed ILIKE + cosine) would
    # hide the Tier 1+2 RRF fusion output and break the debugger's
    # whole point.
    if expected_sections == "ilike_results,cosine_scores,rrf_top3":
        sections_list = list(observed_sections)
        for required in (
            "ilike_results",
            "cosine_scores",
            "rrf_top3",
        ):
            assert required in sections_list, (
                f"FR-102 DebuggerResult.sections must include "
                f"{required!r}; got {sections_list!r}. "
                f"SRS FR-102 mandates the three canonical section names."
            )

    # Companion invariants: the three payload fields MUST exist and
    # carry the canonical names. A GREEN that returned ILIKE matches
    # under a different field name (e.g. "ilike") would break the
    # WebUI's per-section renderer.
    assert hasattr(result, "ilike_results"), (
        "FR-102 DebuggerResult must expose ``ilike_results``"
    )
    assert hasattr(result, "cosine_scores"), (
        "FR-102 DebuggerResult must expose ``cosine_scores``"
    )
    assert hasattr(result, "rrf_top3"), (
        "FR-102 DebuggerResult must expose ``rrf_top3``"
    )

    observed_ilike = (
        result.ilike_results
        if not callable(getattr(result, "ilike_results", None))
        else result.ilike_results()
    )
    observed_cosine = (
        result.cosine_scores
        if not callable(getattr(result, "cosine_scores", None))
        else result.cosine_scores()
    )
    observed_rrf = (
        result.rrf_top3
        if not callable(getattr(result, "rrf_top3", None))
        else result.rrf_top3()
    )
    assert observed_ilike is not None, (
        "FR-102 DebuggerResult.ilike_results must not be None"
    )
    assert observed_cosine is not None, (
        "FR-102 DebuggerResult.cosine_scores must not be None"
    )
    assert observed_rrf is not None, (
        "FR-102 DebuggerResult.rrf_top3 must not be None"
    )

    # Companion invariant: ``ilike_results`` and ``cosine_scores``
    # MUST be list-like (a list or tuple) so the WebUI can iterate
    # them. A GREEN that returned a bare dict would force the UI to
    # call .items() and break the per-row renderer.
    assert isinstance(observed_ilike, (list, tuple)), (
        f"FR-102 ilike_results must be a list/tuple; got "
        f"{type(observed_ilike).__name__}"
    )
    assert isinstance(observed_cosine, (list, tuple)), (
        f"FR-102 cosine_scores must be a list/tuple; got "
        f"{type(observed_cosine).__name__}"
    )
    assert isinstance(observed_rrf, (list, tuple)), (
        f"FR-102 rrf_top3 must be a list/tuple; got "
        f"{type(observed_rrf).__name__}"
    )

    # The query MUST be echoed on the result so the WebUI can show
    # the user what was asked. A GREEN that dropped the query would
    # break the "what did I just search for?" affordance.
    observed_query = (
        result.query()
        if callable(getattr(result, "query", None))
        else result.query
    )
    assert observed_query == query, (
        f"FR-102 DebuggerResult.query must echo the input; got "
        f"{observed_query!r} (expected {query!r})"
    )


# ---------------------------------------------------------------------------
# 2. Slider adjustment is a sandbox operation — the persisted
#    platform_configs row MUST remain at the default 0.75 (validation).
#
# Spec input: threshold_slider="0.80"; expected_db_unchanged="true".
# SRS FR-102: "沙盒調整不寫入 platform_configs". This is the explicit
# negative-persistence guarantee the SRS pins with "不寫入". A
# regression that called config_store.set(...) on every slider
# adjustment would mutate the persisted cosine threshold and break
# production queries (the RAG pipeline would suddenly start using
# 0.80 as the cosine cut-off for real users, not just the debugger
# admin). A regression that returned the new threshold from
# get_saved_threshold() would silently leak sandbox state to the
# rest of the system.
# ---------------------------------------------------------------------------
def test_fr102_slider_adjustment_not_persisted():
    # Spec input literals.
    threshold_slider = "0.80"  # spec string sentinel
    expected_db_unchanged = "true"  # spec string sentinel

    # Companion invariant: the default threshold MUST be 0.75 (re-
    # asserted so the harness sees the sentinel anchor on case 2).
    assert RAG_DEFAULT_THRESHOLD == 0.75, (
        f"FR-102 RAG_DEFAULT_THRESHOLD must be 0.75; got "
        f"{RAG_DEFAULT_THRESHOLD!r}"
    )

    # GREEN TODO: ``RAGDebugger`` MUST expose
    # ``set_slider_threshold(threshold)`` and ``get_saved_threshold()``
    # so the sandbox can be driven without a real platform_configs
    # connection.
    debugger = RAGDebugger()
    assert hasattr(debugger, "set_slider_threshold") and callable(
        debugger.set_slider_threshold
    ), (
        "FR-102 RAGDebugger must expose "
        "``set_slider_threshold(threshold: float) -> None``"
    )
    assert hasattr(debugger, "get_saved_threshold") and callable(
        debugger.get_saved_threshold
    ), (
        "FR-102 RAGDebugger must expose "
        "``get_saved_threshold() -> float``"
    )

    # Sanity check: the persisted threshold starts at 0.75 (the
    # autouse fixture pre-seeds the in-memory config_store).
    initial_saved = debugger.get_saved_threshold()
    assert initial_saved == RAG_DEFAULT_THRESHOLD, (
        f"FR-102 get_saved_threshold must return 0.75 before any "
        f"slider adjustment; got {initial_saved!r}"
    )

    # Drive the slider to the spec's 0.80 value. This MUST be a
    # sandbox-only operation — the persisted platform_configs row
    # (the in-memory config_store behind the scenes) MUST stay at
    # 0.75.
    debugger.set_slider_threshold(float(threshold_slider))

    # Spec fr102-ok predicate: the in-flight debugger's saved-threshold
    # read MUST still be 0.75 — the FR's "expected_db_unchanged='true'"
    # guarantee. A GREEN that persisted the slider value would
    # return 0.80 here, breaking the sandbox contract.
    if expected_db_unchanged == "true":
        observed_saved = debugger.get_saved_threshold()
        assert observed_saved == RAG_DEFAULT_THRESHOLD, (
            f"FR-102 set_slider_threshold({threshold_slider}) must NOT "
            f"persist to platform_configs; get_saved_threshold() must "
            f"still return {RAG_DEFAULT_THRESHOLD} (got {observed_saved!r}). "
            f"SRS FR-102 mandates '沙盒調整不寫入 platform_configs'."
        )

    # Companion invariant: the persisted platform_configs row MUST
    # remain at 0.75 even after multiple slider adjustments (a GREEN
    # that flipped a flag and re-persisted on the second call would
    # still pass the single-call check above but fail here).
    debugger.set_slider_threshold(0.65)
    debugger.set_slider_threshold(0.90)
    final_saved = debugger.get_saved_threshold()
    assert final_saved == RAG_DEFAULT_THRESHOLD, (
        f"FR-102 platform_configs row must remain at "
        f"{RAG_DEFAULT_THRESHOLD} after multiple slider adjustments; "
        f"got {final_saved!r}. SRS FR-102: '沙盒調整不寫入 platform_configs'."
    )

    # Companion invariant: running debug() with the spec's 0.80
    # slider value MUST NOT mutate the persisted threshold either.
    # The debugger uses the sandbox value for the in-flight result,
    # but platform_configs stays at 0.75.
    debugger.set_slider_threshold(float(threshold_slider))
    _ = debugger.debug(query="退款", threshold=float(threshold_slider))
    post_debug_saved = debugger.get_saved_threshold()
    assert post_debug_saved == RAG_DEFAULT_THRESHOLD, (
        f"FR-102 debug() with threshold={threshold_slider} must NOT "
        f"persist to platform_configs; get_saved_threshold() must "
        f"still return {RAG_DEFAULT_THRESHOLD} (got {post_debug_saved!r})."
    )
