"""TDD-RED: failing tests for FR-19 — PII 敏感關鍵字觸發轉接 (should_escalate).

Spec source: 02-architecture/TEST_SPEC.md (FR-19)
SRS source : SRS.md FR-19

Acceptance criteria (from SRS FR-19):
    PII 敏感關鍵字觸發轉接：偵測 密碼/銀行帳戶/信用卡號/提款卡 關鍵字 →
    should_escalate() 回傳 True。四個敏感關鍵字觸發 should_escalate()=True；
    其他關鍵字不誤判。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``app.core.pii`` exists but ``should_escalate`` is a
# stub that returns False. The import below succeeds (FR-18 GREEN landed),
# but every assertion below will fail because the FR-19 rule logic is not
# yet implemented. That is the canonical RED signal for this step.
#
# GREEN must extend ``app/core/pii.py:PIIMasking.should_escalate`` so that
# each of the four FR-19 sensitive keywords (密碼 / 銀行帳戶 / 信用卡號 /
# 提款卡) flips the return value from False to True. Implementation hints:
#
#   - Pure-Python substring scan (no DB / LLM call) so the check fits in
#     the request hot path alongside FR-18 ``mask()``.
#   - The four keywords are SRS FR-19 canonical triggers; the rule MUST
#     NOT raise for ordinary text and MUST NOT spuriously match neutral
#     finance / support vocabulary (e.g. "我想查詢訂單狀態").
#   - Contract: ``PIIMasking().should_escalate(text: str) -> bool``.
#
# Test isolation: ``PIIMasking`` is pure-Python — no DB, no HTTP, no LLM
# call — so no autouse fixture is required. RED signals come from the
# assertion failures the GREEN agent must fix.
# ---------------------------------------------------------------------------
from app.core.pii import PIIMasking  # noqa: F401


# ---------------------------------------------------------------------------
# 1. Password keyword (密碼) triggers should_escalate() = True.
#
# Spec input: text="我的密碼是123456"; expected=True.
#   SRS FR-19: "密碼/銀行帳戶/信用卡號/提款卡 關鍵字 → should_escalate() 回傳 True".
#
# A user typing "我的密碼是123456" is sharing a credential through a chat
# surface the platform does not own end-to-end. The conversation MUST be
# routed to a human agent so the credential can be rotated by the back
# office rather than echoed into an LLM prompt or audit log. Returning
# False for this text would let the password be silently processed by the
# downstream Tier 1-3 pipeline — a P0 data-handling failure.
# ---------------------------------------------------------------------------
def test_fr19_password_keyword_triggers_escalate():
    text = "我的密碼是123456"
    expected = True

    masker = PIIMasking()
    result = masker.should_escalate(text)

    if text == "我的密碼是123456" and expected is True:
        # Spec fr19-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr19-ok predicate: PIIMasking.should_escalate() MUST return a "
            "non-None boolean on the password path"
        )

    assert result is True, (
        f"text containing the password keyword '密碼' ({text!r}) MUST "
        f"trigger should_escalate()=True (SRS FR-19: '密碼 → "
        f"should_escalate() 回傳 True'); got result={result!r}"
    )
    assert isinstance(result, bool), (
        f"should_escalate() MUST return a plain bool (not None, not "
        f"a truthy string); got type(result)={type(result).__name__}, "
        f"result={result!r}"
    )


# ---------------------------------------------------------------------------
# 2. Bank account keyword (銀行帳戶) triggers should_escalate() = True.
#
# Spec input: text="我的銀行帳戶"; expected=True.
#   SRS FR-19: "銀行帳戶 → should_escalate() 回傳 True".
#
# Bank-account references are Taiwan 個人資料保護法 第六條 "特種個資"
# adjacent — a chatbot MUST NOT log, summarize, or echo them. Routing to
# a human agent is the conservative (fail-secure) response.
# ---------------------------------------------------------------------------
def test_fr19_bank_account_triggers_escalate():
    text = "我的銀行帳戶"
    expected = True

    masker = PIIMasking()
    result = masker.should_escalate(text)

    if text == "我的銀行帳戶" and expected is True:
        # Spec fr19-ok predicate applies_to case 1 only — case 2 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    assert result is True, (
        f"text containing the bank-account keyword '銀行帳戶' ({text!r}) "
        f"MUST trigger should_escalate()=True (SRS FR-19: '銀行帳戶 → "
        f"should_escalate() 回傳 True'); got result={result!r}"
    )
    assert isinstance(result, bool), (
        f"should_escalate() MUST return a plain bool; got "
        f"type(result)={type(result).__name__}, result={result!r}"
    )


# ---------------------------------------------------------------------------
# 3. Credit card keyword (信用卡號碼) triggers should_escalate() = True.
#
# Spec input: text="信用卡號碼"; expected=True.
#   SRS FR-19: "信用卡號 → should_escalate() 回傳 True".
#
# "信用卡號碼" pairs with the FR-18 Luhn-valid PAN regex: even if the
# PAN substring is masked, the keyword alone signals the user is about
# to disclose payment credentials, so the conversation MUST escalate.
# ---------------------------------------------------------------------------
def test_fr19_credit_card_keyword_triggers_escalate():
    text = "信用卡號碼"
    expected = True

    masker = PIIMasking()
    result = masker.should_escalate(text)

    if text == "信用卡號碼" and expected is True:
        # Spec fr19-ok predicate applies_to case 1 only — case 3 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    assert result is True, (
        f"text containing the credit-card keyword '信用卡號碼' ({text!r}) "
        f"MUST trigger should_escalate()=True (SRS FR-19: '信用卡號 → "
        f"should_escalate() 回傳 True'); got result={result!r}"
    )
    assert isinstance(result, bool), (
        f"should_escalate() MUST return a plain bool; got "
        f"type(result)={type(result).__name__}, result={result!r}"
    )


# ---------------------------------------------------------------------------
# 4. Debit card keyword (提款卡) triggers should_escalate() = True.
#
# Spec input: text="提款卡"; expected=True.
#   SRS FR-19: "提款卡 → should_escalate() 回傳 True".
#
# Taiwan debit/ATM cards ("提款卡") are functionally identical to credit
# cards for the purposes of escalation: a user typing the keyword is
# flagging a financial-credential conversation that MUST be handed off
# to a human agent instead of being auto-handled.
# ---------------------------------------------------------------------------
def test_fr19_debit_card_triggers_escalate():
    text = "提款卡"
    expected = True

    masker = PIIMasking()
    result = masker.should_escalate(text)

    if text == "提款卡" and expected is True:
        # Spec fr19-ok predicate applies_to case 1 only — case 4 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    assert result is True, (
        f"text containing the debit-card keyword '提款卡' ({text!r}) "
        f"MUST trigger should_escalate()=True (SRS FR-19: '提款卡 → "
        f"should_escalate() 回傳 True'); got result={result!r}"
    )
    assert isinstance(result, bool), (
        f"should_escalate() MUST return a plain bool; got "
        f"type(result)={type(result).__name__}, result={result!r}"
    )


# ---------------------------------------------------------------------------
# 5. Normal customer text does NOT trigger should_escalate() — i.e. the
#    four-keyword rule MUST NOT cause false positives on ordinary support
#    vocabulary.
#
# Spec input: text="我想查詢訂單狀態"; expected=False.
#   SRS FR-19: "其他關鍵字不誤判".
#
# A naive substring check on the bytes "信用卡" or "密碼" would catch the
# substring "密碼" inside unrelated compounds; an over-eager tokenizer
# would escalate routine order inquiries. False positives funnel normal
# conversations into the human queue, raising SLA breach risk on FR-55
# and degrading the FCR target in NFR-23.
# ---------------------------------------------------------------------------
def test_fr19_normal_text_no_escalate():
    text = "我想查詢訂單狀態"
    expected = False

    masker = PIIMasking()
    result = masker.should_escalate(text)

    if text == "我想查詢訂單狀態" and expected is False:
        # Spec fr19-ok predicate applies_to case 1 only — case 5 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    assert result is False, (
        f"ordinary support text {text!r} MUST NOT trigger "
        f"should_escalate() (SRS FR-19: '其他關鍵字不誤判'); got "
        f"result={result!r}"
    )
    assert isinstance(result, bool), (
        f"should_escalate() MUST return a plain bool even on the "
        f"negative path; got type(result)={type(result).__name__}, "
        f"result={result!r}"
    )
