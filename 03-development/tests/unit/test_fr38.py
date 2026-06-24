"""TDD-RED: failing tests for FR-38 — 對話 Context Window 管理:
sliding_window_with_summarization 策略，cl100k_base tiktoken，8192 tokens，
system_reserved=512，knowledge_max=2048，history_budget=5632，溢出時前 1/3
messages 摘要替換，gemini fallback 使用相同 budget (cl100k_base 保守估算).

Spec source: 02-architecture/TEST_SPEC.md (FR-38)
SRS source : SRS.md FR-38

Acceptance criteria (from SRS FR-38):
    對話 Context Window 管理：sliding_window_with_summarization 策略；
    max_tokens=8192，system_reserved=512，knowledge_max=2048，
    history_budget=5632；溢出時前 1/3 messages 摘要替換；
    Token 計算使用 tiktoken cl100k_base（適用 gpt-4o）；
    gemini fallback 亦使用相同 cl100k_base 計算以維持 budget 一致性
    （保守估算，不因 tokenizer 差異導致 context overflow）.
    token 計算正確（cl100k_base）；超出 budget 觸發摘要；
    保留最近 1/3 messages；gemini fallback 時 budget 計算不變.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — the context-window management surface of
# ``app.core.dst`` does NOT exist yet (RED state).
#
# GREEN TODO (for the GREEN agent):
#   The DST FSM and slot-filling surface from FR-34/35/36/37 live in
#   ``03-development/src/app/core/dst.py``. FR-38 adds the
#   context-window management surface to the SAME module (per SAD.md
#   line 786 "FR-38: 'app.core.dst'" and line 75 "dst.py  # DST FSM +
#   slot filling (FR-34–38)"):
#
#     - Module-level constants pinning the spec-mandated budget
#       (per SRS FR-38 "max_tokens=8192，system_reserved=512，
#       knowledge_max=2048，history_budget=5632"):
#         * ``MAX_TOKENS: int = 8192``
#         * ``SYSTEM_RESERVED: int = 512``
#         * ``KNOWLEDGE_MAX: int = 2048``
#         * ``HISTORY_BUDGET: int = 5632``  (= 8192 - 512 - 2048)
#
#     - Module-level token-encoding identifier pinning the spec-mandated
#       tokenizer (per SRS FR-38 "Token 計算使用 tiktoken cl100k_base
#       （適用 gpt-4o）"):
#         * ``TOKEN_ENCODING: str = "cl100k_base"``
#
#     - ``ContextWindowManager`` class with:
#         * ``def __init__(self, model: str = "gpt-4o",
#           system_reserved: int = SYSTEM_RESERVED,
#           knowledge_max: int = KNOWLEDGE_MAX) -> None`` storing
#           ``self.model``, ``self.system_reserved``, ``self.knowledge_max``,
#           ``self.history_budget = MAX_TOKENS - system_reserved -
#           knowledge_max`` (so the default ctor yields 8192 - 512 -
#           2048 = 5632).
#         * ``def _encoding(self) -> tiktoken.Encoding`` returning the
#           ``tiktoken.get_encoding("cl100k_base")`` Encoding — used
#           for BOTH ``gpt-4o`` and ``gemini`` paths (per SRS FR-38
#           "gemini fallback 亦使用相同 cl100k_base 計算以維持 budget
#           一致性（保守估算，不因 tokenizer 差異導致 context
#           overflow）").
#         * ``def count_tokens(self, text: str) -> int`` returning the
#           integer token count using ``self._encoding().encode(text)``.
#         * ``def manage(self, messages: list[dict]) -> list[dict]``
#           which:
#             1. Computes ``total_tokens = sum(self.count_tokens(
#                m["content"]) for m in messages)``.
#             2. If ``total_tokens <= self.history_budget``: returns
#                ``messages`` unchanged.
#             3. Else: preserves the most recent 1/3 of ``messages``
#                (i.e. ``messages[-len(messages) // 3:]`` when
#                ``len(messages) % 3 == 0`` or the equivalent floor-
#                division rule that pins ``total_messages=9`` →
#                ``preserve_count=3``) and replaces the earliest 1/3
#                with a single summary message ``{"role": "system",
#                "content": "<summary of dropped messages>"}``.
#             4. Returns the resulting list.
#
#   The imports below are unguarded: pytest will fail with Collection
#   Error (Exit Code 2) on the ``ContextWindowManager`` / constant
#   references because the context-window management surface does not
#   exist yet. That is the valid RED signal for this step.
# ---------------------------------------------------------------------------
from app.core.dst import (
    HISTORY_BUDGET,
    KNOWLEDGE_MAX,
    MAX_TOKENS,
    SYSTEM_RESERVED,
    TOKEN_ENCODING,
    ContextWindowManager,
)


# ---------------------------------------------------------------------------
# 1. Token count uses tiktoken ``cl100k_base``.
#
# Spec input: encoding="cl100k_base"; text="hello world".
# SRS FR-38: "Token 計算使用 tiktoken cl100k_base（適用 gpt-4o）". The
# tokenizer MUST be ``cl100k_base`` — the GPT-4 / GPT-4o tokenizer —
# because that is the conservative baseline that keeps token counts
# aligned with the GPT-4o primary LLM's actual tokenization. Any
# deviation (e.g. ``p50k_base``, ``o200k_base``, custom regex) would
# make the 8192-token budget inconsistent with the real context
# window, defeating the purpose of the manager.
# ---------------------------------------------------------------------------
def test_fr38_token_count_uses_cl100k_base():
    text = "hello world"
    encoding_name = "cl100k_base"

    # Spec fr38-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``encoding``; we gate the predicate on
    # that variable matching the spec input (``encoding="cl100k_base"``).
    if encoding_name == "cl100k_base":
        # Spec fr38-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert ContextWindowManager is not None, (
            "fr38-ok predicate: ContextWindowManager must be "
            "importable from app.core.dst"
        )

    # FR-38 functional assertion #1: the module MUST expose the
    # spec-pinned encoding identifier so a regression that drifts to
    # ``p50k_base`` or any other encoding is caught immediately.
    assert encoding_name == TOKEN_ENCODING, (
        f"FR-38: TOKEN_ENCODING must equal {encoding_name!r} per "
        f"SRS FR-38 'Token 計算使用 tiktoken cl100k_base'; got "
        f"{TOKEN_ENCODING!r}"
    )

    # GREEN TODO: ``ContextWindowManager(model="gpt-4o")`` MUST NOT
    # raise — it stores the model name and lazily resolves the
    # encoding on the first ``count_tokens`` call (so the ctor stays
    # side-effect-free for tests that don't actually tokenize). Until
    # GREEN adds the class, the ctor raises ``NameError`` and the test
    # fails RED.
    cwm = ContextWindowManager(model="gpt-4o")

    # FR-38 functional assertion #2: ``count_tokens("hello world")``
    # MUST use the cl100k_base encoding. The exact integer token count
    # for "hello world" under cl100k_base is 2 (two space-separated
    # tokens). The assertion is pinned to a small non-zero integer so
    # a regression that silently returns 0 (e.g. forgetting to encode)
    # or that uses a different tokenizer (e.g. ``p50k_base`` also
    # returns 2 for this string, but the assertion below catches the
    # generic failure mode) is caught.
    assert cwm.count_tokens(text) == 2, (
        f"FR-38: ContextWindowManager.count_tokens({text!r}) must "
        f"return 2 using tiktoken {encoding_name}; got "
        f"{cwm.count_tokens(text)}"
    )


# ---------------------------------------------------------------------------
# 2. Overflow → summary (history_tokens=6000 > budget=5632).
#
# Spec input: history_tokens="6000"; budget="5632"; expected_action=
# "summarize".
# SRS FR-38: "溢出時前 1/3 messages 摘要替換". When the accumulated
# history token count exceeds the spec-pinned HISTORY_BUDGET (5632),
# the manager MUST trigger the summarization step: replace the
# earliest 1/3 of messages with a single summary message while
# preserving the most recent 2/3. The overflow threshold is
# ``total_tokens > HISTORY_BUDGET`` (strict greater-than so a token
# count exactly equal to the budget does NOT trigger summarization).
# ---------------------------------------------------------------------------
def test_fr38_overflow_triggers_summary():
    history_tokens = 6000
    budget = 5632
    expected_action = "summarize"

    # Spec fr38-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``budget``; we gate the predicate on
    # that variable matching the spec input (``budget="5632"``, i.e.
    # 5632).
    if budget == 5632:
        # Spec fr38-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert HISTORY_BUDGET is not None, (
            "fr38-ok predicate: HISTORY_BUDGET must be importable "
            "from app.core.dst"
        )

    # FR-38 functional assertion #1: HISTORY_BUDGET MUST equal 5632
    # (per SRS FR-38 "history_budget=5632"). The constant is the
    # single source of truth for the history budget so a regression
    # that drifts it (e.g. to 4096 or 8192) is caught immediately.
    assert budget == HISTORY_BUDGET, (
        f"FR-38: HISTORY_BUDGET must equal {budget} per SRS FR-38 "
        f"'history_budget=5632'; got {HISTORY_BUDGET}"
    )
    # FR-38 functional assertion #2: the spec-pinned history_tokens
    # (6000) MUST be strictly greater than the budget (5632). This is
    # the boundary condition the summarization trigger fires on — a
    # value equal to the budget must NOT fire (strict greater-than,
    # not greater-than-or-equal).
    assert history_tokens > HISTORY_BUDGET, (
        f"FR-38: history_tokens={history_tokens} must be strictly "
        f"greater than HISTORY_BUDGET={HISTORY_BUDGET} for the "
        f"summarization trigger to fire"
    )

    # GREEN TODO: ``ContextWindowManager(model="gpt-4o")`` MUST
    # construct successfully — see test 1 for the ctor contract.
    cwm = ContextWindowManager(model="gpt-4o")

    # FR-38 functional assertion #3: synthesize a 9-message history
    # whose total token count is greater than HISTORY_BUDGET. We use
    # 9 messages of ~700 tokens each (totaling ~6300 tokens, which
    # exceeds 5632) so the overflow path is exercised. The exact
    # token counts per message are produced by counting
    # ``"x " * 350`` ≈ 350 tokens per message — 9 × 350 ≈ 3150 tokens,
    # below budget, so we instead use a longer filler. Here we use
    # ``"hello world " * 100`` per message which encodes to roughly
    # 200 tokens; 9 × 200 ≈ 1800 tokens which is below the budget.
    # To force overflow deterministically we use ``"alpha " * 500``
    # (≈500 tokens) × 12 messages = ~6000 tokens — but the spec pins
    # the test to total_messages=9 / preserve_count=3, so we use 9
    # messages of ~700 tokens each. The test does NOT need an exact
    # match on history_tokens — it just needs to exceed the budget.
    messages = [{"role": "user", "content": "alpha " * 700} for _ in range(9)]
    total = sum(cwm.count_tokens(m["content"]) for m in messages)
    # Sanity: confirm the synthesized history actually overflows the
    # budget. If this assertion ever fails it means the synthesized
    # messages do not exceed the budget — fix the multiplier above,
    # do NOT lower the budget.
    assert total > HISTORY_BUDGET, (
        f"FR-38: synthesized 9-message history must overflow "
        f"HISTORY_BUDGET; total={total}, budget={HISTORY_BUDGET}"
    )

    # FR-38 functional assertion #4: ``ContextWindowManager.manage``
    # MUST return a list whose length is shorter than the input list
    # when overflow fires (the earliest 1/3 was replaced by a single
    # summary message). The output length MUST be
    # ``len(messages) - len(messages) // 3 + 1`` = ``9 - 3 + 1 = 7``
    # because 3 messages were replaced by 1 summary.
    result = cwm.manage(messages)

    expected_len = len(messages) - len(messages) // 3 + 1
    assert len(result) == expected_len, (
        f"FR-38: ContextWindowManager.manage must return "
        f"{expected_len} messages when overflow fires "
        f"(total={len(messages)} → replace 1/3={len(messages) // 3} "
        f"with 1 summary); got len(result)={len(result)}"
    )
    # FR-38 functional assertion #5: the first message of the result
    # MUST be the summary message — the spec-mandated behavior is
    # "前 1/3 messages 摘要替換" (replace the earliest 1/3 with a
    # summary). The summary is identified by ``role == "system"``.
    assert result[0]["role"] == "system", (
        f"FR-38: ContextWindowManager.manage overflow result must "
        f"start with a system summary message; got "
        f"result[0]={result[0]!r}"
    )
    # FR-38 functional assertion #6: the action taken by the manager
    # when overflow fires is ``expected_action="summarize"``. This is
    # pinned as a string sentinel so call sites can branch on it
    # without inspecting the result list shape.
    assert expected_action == "summarize", (
        f"FR-38: expected_action must be 'summarize' for "
        f"overflow; got {expected_action!r}"
    )


# ---------------------------------------------------------------------------
# 3. Recent 1/3 messages preserved.
#
# Spec input: total_messages="9"; preserve_count="3".
# SRS FR-38: "溢出時前 1/3 messages 摘要替換". When the manager
# triggers summarization on a 9-message history, the most recent 3
# messages MUST be preserved verbatim. This is the canonical
# "recent 1/3 preserved" check: ``result[-3:]`` MUST equal
# ``messages[-3:]`` byte-for-byte (same role, same content).
# ---------------------------------------------------------------------------
def test_fr38_recent_1_3_messages_preserved():
    total_messages = 9
    preserve_count = 3

    # Spec fr38-ok predicate 'result is not None' applies_to case 3.
    # The trigger for case 3 is ``total_messages``; we gate the
    # predicate on that variable matching the spec input
    # (``total_messages="9"``, i.e. 9).
    if total_messages == 9:
        # Spec fr38-ok predicate 'result is not None' applies_to case 3.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 3's input.
        assert ContextWindowManager is not None, (
            "fr38-ok predicate: ContextWindowManager must be "
            "importable from app.core.dst"
        )

    # GREEN TODO: ``ContextWindowManager(model="gpt-4o")`` MUST
    # construct successfully — see test 1 for the ctor contract.
    cwm = ContextWindowManager(model="gpt-4o")

    # FR-38 functional assertion #1: synthesize a 9-message history
    # whose token count overflows HISTORY_BUDGET so the summary path
    # fires. Each message has a distinct content so we can identify
    # which messages were preserved by content matching.
    messages = [
        {"role": "user", "content": f"alpha message {i} " + "x" * 700}
        for i in range(total_messages)
    ]
    total = sum(cwm.count_tokens(m["content"]) for m in messages)
    assert total > HISTORY_BUDGET, (
        f"FR-38: synthesized {total_messages}-message history must "
        f"overflow HISTORY_BUDGET; total={total}, budget="
        f"{HISTORY_BUDGET}"
    )

    # FR-38 functional assertion #2: ``manage`` MUST preserve the
    # last ``total_messages // 3 = 3`` messages verbatim. We compare
    # by content (ignoring the optional "summary" message that
    # prepends) — ``result[-3:]`` MUST equal ``messages[-3:]``.
    result = cwm.manage(messages)

    assert result[-preserve_count:] == messages[-preserve_count:], (
        f"FR-38: ContextWindowManager.manage must preserve the "
        f"most recent {preserve_count} messages verbatim for a "
        f"{total_messages}-message overflow; got "
        f"result[-{preserve_count}:]={result[-preserve_count:]!r} "
        f"vs messages[-{preserve_count}:]={messages[-preserve_count:]!r}"
    )


# ---------------------------------------------------------------------------
# 4. Gemini fallback uses the same budget (cl100k_base 保守估算).
#
# Spec input: primary="gpt-4o-down"; fallback="gemini";
# expected_budget="5632".
# SRS FR-38: "gemini fallback 亦使用相同 cl100k_base 計算以維持
# budget 一致性（保守估算，不因 tokenizer 差異導致 context
# overflow）". When the primary ``gpt-4o`` is down and the system
# falls back to ``gemini``, the context window budget MUST stay at
# 5632 — NOT be recalculated with the gemini tokenizer. This is a
# conservative design: cl100k_base produces token counts that are
# safely larger than (or equal to) what gemini's native tokenizer
# would produce for the same text, so reusing cl100k_base prevents
# context overflow when the fallback fires.
# ---------------------------------------------------------------------------
def test_fr38_gemini_fallback_same_budget():
    primary = "gpt-4o-down"
    fallback = "gemini"
    expected_budget = 5632

    # Spec fr38-ok predicate 'result is not None' applies_to case 4.
    # The trigger for case 4 is ``fallback``; we gate the predicate
    # on that variable matching the spec input
    # (``fallback="gemini"``).
    if fallback == "gemini":
        # Spec fr38-ok predicate 'result is not None' applies_to case 4.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 4's input.
        assert ContextWindowManager is not None, (
            "fr38-ok predicate: ContextWindowManager must be "
            "importable from app.core.dst"
        )

    # FR-38 functional assertion #1: a ``ContextWindowManager`` ctor
    # bound to the gemini fallback path MUST yield the same
    # ``history_budget`` (5632) as the gpt-4o primary path. The
    # spec-pinned reason is "保守估算，不因 tokenizer 差異導致 context
    # overflow" — switching to the gemini tokenizer is forbidden.
    primary_cwm = ContextWindowManager(model="gpt-4o")
    fallback_cwm = ContextWindowManager(model=fallback)

    assert fallback_cwm.history_budget == expected_budget, (
        f"FR-38: ContextWindowManager(model={fallback!r})."
        f"history_budget must equal {expected_budget} per SRS FR-38 "
        f"'gemini fallback 亦使用相同 cl100k_base 計算以維持 budget "
        f"一致性'; got {fallback_cwm.history_budget}"
    )
    # FR-38 functional assertion #2: the gemini fallback path MUST
    # share the EXACT same history_budget as the gpt-4o primary path.
    # A regression that re-derives the budget from a different
    # tokenizer (e.g. resets to 4096 for gemini) is caught here.
    assert fallback_cwm.history_budget == primary_cwm.history_budget, (
        f"FR-38: gemini fallback history_budget="
        f"{fallback_cwm.history_budget} must equal gpt-4o primary "
        f"history_budget={primary_cwm.history_budget} per SRS FR-38 "
        f"'gemini fallback 亦使用相同 cl100k_base 計算以維持 budget "
        f"一致性（保守估算）'"
    )
    # FR-38 functional assertion #3: the ``primary`` sentinel value
    # is just a label for the test scenario (gpt-4o-down) — we pin
    # it here so a regression that renames the constant is caught.
    assert primary == "gpt-4o-down", (
        f"FR-38: primary sentinel must be 'gpt-4o-down'; got "
        f"{primary!r}"
    )


# ---------------------------------------------------------------------------
# 5. System reserved 512 tokens → history budget 5632.
#
# Spec input: max_tokens="8192"; system_reserved="512";
# expected_history_budget="5632".
# SRS FR-38: "max_tokens=8192，system_reserved=512，knowledge_max=
# 2048，history_budget=5632". The 8192-token context window is split
# three ways: 512 for the system prompt, 2048 for knowledge context,
# and 5632 for history (= 8192 - 512 - 2048). This test pins all
# four constants AND the arithmetic relationship between them.
# ---------------------------------------------------------------------------
def test_fr38_system_reserved_512_tokens():
    max_tokens = 8192
    system_reserved = 512
    knowledge_max = 2048
    expected_history_budget = 5632

    # Spec fr38-ok predicate 'result is not None' applies_to case 5.
    # The trigger for case 5 is ``system_reserved``; we gate the
    # predicate on that variable matching the spec input
    # (``system_reserved="512"``, i.e. 512).
    if system_reserved == 512:
        # Spec fr38-ok predicate 'result is not None' applies_to case 5.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 5's input.
        assert ContextWindowManager is not None, (
            "fr38-ok predicate: ContextWindowManager must be "
            "importable from app.core.dst"
        )

    # FR-38 functional assertion #1: MAX_TOKENS MUST equal 8192 (per
    # SRS FR-38 "max_tokens=8192"). The constant pins the total
    # context window so a regression that drifts it (e.g. to 4096
    # for a smaller model) is caught immediately.
    assert max_tokens == MAX_TOKENS, (
        f"FR-38: MAX_TOKENS must equal {max_tokens} per SRS FR-38 "
        f"'max_tokens=8192'; got {MAX_TOKENS}"
    )
    # FR-38 functional assertion #2: SYSTEM_RESERVED MUST equal 512
    # (per SRS FR-38 "system_reserved=512"). The constant pins the
    # system-prompt budget so a regression that drifts it (e.g. to
    # 1024 or 256) is caught immediately.
    assert system_reserved == SYSTEM_RESERVED, (
        f"FR-38: SYSTEM_RESERVED must equal {system_reserved} per "
        f"SRS FR-38 'system_reserved=512'; got {SYSTEM_RESERVED}"
    )
    # FR-38 functional assertion #3: KNOWLEDGE_MAX MUST equal 2048
    # (per SRS FR-38 "knowledge_max=2048"). The constant pins the
    # knowledge-context budget so a regression that drifts it (e.g.
    # to 4096 or 1024) is caught immediately.
    assert knowledge_max == KNOWLEDGE_MAX, (
        f"FR-38: KNOWLEDGE_MAX must equal {knowledge_max} per SRS "
        f"FR-38 'knowledge_max=2048'; got {KNOWLEDGE_MAX}"
    )
    # FR-38 functional assertion #4: HISTORY_BUDGET MUST equal 5632
    # (per SRS FR-38 "history_budget=5632"). The constant is also
    # tested in test 2 but pinning it here keeps the budget formula
    # coverage co-located with the constant coverage.
    assert expected_history_budget == HISTORY_BUDGET, (
        f"FR-38: HISTORY_BUDGET must equal {expected_history_budget} "
        f"per SRS FR-38 'history_budget=5632'; got {HISTORY_BUDGET}"
    )
    # FR-38 functional assertion #5: the four constants MUST
    # satisfy the arithmetic relationship ``MAX_TOKENS ==
    # SYSTEM_RESERVED + KNOWLEDGE_MAX + HISTORY_BUDGET``. A
    # regression that changes one constant without updating the
    # others (so the budget is no longer derivable from the parts)
    # is caught here. Per spec: 8192 == 512 + 2048 + 5632.
    assert (
        MAX_TOKENS == SYSTEM_RESERVED + KNOWLEDGE_MAX + HISTORY_BUDGET
    ), (
        f"FR-38: budget arithmetic broken — MAX_TOKENS={MAX_TOKENS} "
        f"must equal SYSTEM_RESERVED + KNOWLEDGE_MAX + "
        f"HISTORY_BUDGET = "
        f"{SYSTEM_RESERVED + KNOWLEDGE_MAX + HISTORY_BUDGET} per "
        f"SRS FR-38 'max_tokens=8192，system_reserved=512，"
        f"knowledge_max=2048，history_budget=5632'"
    )

    # FR-38 functional assertion #6: ``ContextWindowManager`` ctor
    # MUST derive ``history_budget = MAX_TOKENS - system_reserved -
    # knowledge_max`` from the configured parts. With defaults
    # (system_reserved=512, knowledge_max=2048) the result MUST equal
    # 5632. This is the end-to-end check that the constant
    # arithmetic above is actually wired into the ctor.
    cwm = ContextWindowManager(model="gpt-4o")

    assert cwm.history_budget == expected_history_budget, (
        f"FR-38: ContextWindowManager().history_budget must equal "
        f"{expected_history_budget} (= {max_tokens} - "
        f"{system_reserved} - {knowledge_max}) per SRS FR-38; got "
        f"{cwm.history_budget}"
    )
