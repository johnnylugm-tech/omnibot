from __future__ import annotations
"""TDD-RED: failing tests for FR-18 — PIIMasking (phone/email/address/credit card).

Spec source: 02-architecture/TEST_SPEC.md (FR-18)
SRS source : SRS.md FR-18

Acceptance criteria (from SRS FR-18):
    PIIMasking：偵測並遮蔽電話（台灣格式 \\d{10,11}）、Email、台灣地址
    （市縣路街巷弄號樓正則）、信用卡（16 位 + Luhn 校驗）；遮蔽格式
    `[{pii_type}_masked]`。
    所有四類 PII 正確遮蔽；信用卡 Luhn 校驗失敗者不遮蔽；mask_count
    正確回傳。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


from dataclasses import dataclass

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``app.core.pii`` does NOT YET exist. The import below
# triggers a Collection Error (ModuleNotFoundError) on this RED step, which
# is the canonical RED signal for a fresh module.
#
# GREEN must add ``app/core/pii.py`` with at least:
#
#   - ``PIIMasking`` class with:
#       * zero-arg constructor (pure-Python regex / Luhn; no I/O so the
#         function can run inside the request hot path).
#       * ``.mask(self, text: str) -> MaskResult``
#             - Detects PII substrings in ``text`` and replaces each
#               match with ``f"[{pii_type}_masked]"``.
#             - PII types covered (SRS FR-18):
#                 phone        — Taiwan mobile/landline ``\\d{10,11}``
#                                (e.g. "0912345678", "0223456789").
#                 email        — RFC-ish local@domain pattern
#                                (e.g. "user@example.com").
#                 address      — Taiwan address regex covering
#                                市/縣 + 路/街 + 段 + 號 / 樓
#                                (e.g. "台北市信義路五段7號").
#                 credit_card  — 16 consecutive digits that PASS the
#                                Luhn checksum. Luhn-invalid 16-digit
#                                strings MUST NOT be masked.
#             - Returns a ``MaskResult`` exposing:
#                   .masked_text   : the text with placeholders in place
#                                    of detected PII substrings.
#                   .mask_count    : int, total number of PII matches
#                                    masked across all types.
#                   .masked_types  : tuple[str, ...], the PII types
#                                    that were actually masked
#                                    (preserving detection order).
#       * ``.should_escalate(self, text: str) -> bool`` (FR-19, not
#         exercised here but lives on the same class per SRS).
#       * ``get_mask_format(pii_type: str) -> str`` static helper that
#         returns ``f"[{pii_type}_masked]"`` for any of the supported
#         PII types ("phone" / "email" / "address" / "credit_card").
#         GREEN may instead expose ``MASK_FORMATS`` dict + a property —
#         the contract this test pins down is the *value*, not the
#         accessor shape. The static-method form is the simplest to
#         assert against without forcing an instance.
#       * Unknown pii_type in ``get_mask_format`` → ``ValueError`` (do
#         not silently return the raw key).
#
#   - ``MaskResult`` value object (frozen dataclass or pydantic model)
#     with attributes ``masked_text: str``, ``mask_count: int``,
#     ``masked_types: tuple[str, ...]``. The harness only asserts on
#     the first two; ``masked_types`` is optional convenience.
#
# Test isolation: PIIMasking is pure-Python — no DB, no HTTP, no LLM
# call — so no autouse fixture is required. RED signals come from the
# missing module (Collection Error) and from the assertion failures the
# GREEN agent must fix.
# ---------------------------------------------------------------------------
from app.core.pii import PIIMasking


# ---------------------------------------------------------------------------
# Lightweight MaskResult stub used only by the test for static analysis /
# type clarity. RED tests do NOT instantiate this — they read attributes
# off whatever ``mask()`` returns. The class is here so pyright/mypy
# can reason about the expected shape.
# ---------------------------------------------------------------------------
@dataclass
class _MaskResultShape:
    masked_text: str
    mask_count: int
    masked_types: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 1. Taiwan phone format \\d{10,11} is masked.
#
# Spec input: text="0912345678"; expected_mask="[phone_masked]".
#   SRS FR-18: "電話（台灣格式 \\d{10,11}）".
#
# A masking pass that leaves "0912345678" intact would leak the user's
# phone number to every downstream log line / LLM prompt / external
# retriever. The mask MUST replace the entire phone substring with
# ``[phone_masked]`` so PII never touches a downstream sink.
# ---------------------------------------------------------------------------
def test_fr18_phone_tw_format_masked():
    text = "0912345678"
    expected_mask = "[phone_masked]"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "0912345678" and expected_mask == "[phone_masked]":
        # Spec fr18-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr18-ok predicate: PIIMasking.mask() must return a non-None "
            "MaskResult on the Taiwan phone path"
        )

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present (SRS FR-18: 遮蔽格式 "
        f"[{{pii_type}}_masked]); got masked_text={masked_text!r}"
    )
    assert masked_text == expected_mask, (
        f"Taiwan phone {text!r} MUST be replaced with "
        f"{expected_mask!r} (SRS FR-18: '電話（台灣格式 \\d{{10,11}}）'); "
        f"got masked_text={masked_text!r}"
    )
    # Raw phone digits MUST NOT survive in the masked output.
    assert "0912345678" not in masked_text, (
        f"raw phone digits MUST NOT leak into masked_text (SRS FR-18 "
        f"PII detection); got masked_text={masked_text!r}"
    )
    # mask_count MUST be exactly 1 for a single-PII input.
    assert getattr(result, "mask_count", None) == 1, (
        f"single Taiwan phone MUST yield mask_count=1; got mask_count="
        f"{getattr(result, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 2. Email address is masked.
#
# Spec input: text="user@example.com"; expected_mask="[email_masked]".
#   SRS FR-18: "Email".
#
# An email leak is a direct violation of the GDPR Art.5(1)(e) data-
# minimization principle that the platform commits to in NFR-21.
# ---------------------------------------------------------------------------
def test_fr18_email_masked():
    text = "user@example.com"
    expected_mask = "[email_masked]"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "user@example.com" and expected_mask == "[email_masked]":
        # Spec fr18-ok predicate applies_to case 1 only — case 2 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present; got masked_text="
        f"{masked_text!r}"
    )
    assert masked_text == expected_mask, (
        f"email {text!r} MUST be replaced with {expected_mask!r} "
        f"(SRS FR-18: 'Email'); got masked_text={masked_text!r}"
    )
    # Raw email MUST NOT survive in the masked output.
    assert "user@example.com" not in masked_text, (
        f"raw email MUST NOT leak into masked_text (SRS FR-18 PII "
        f"detection); got masked_text={masked_text!r}"
    )
    assert getattr(result, "mask_count", None) == 1, (
        f"single email MUST yield mask_count=1; got mask_count="
        f"{getattr(result, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 3. Taiwan address (市/縣 + 路/街 + 段 + 號 / 樓) is masked.
#
# Spec input: text="台北市信義路五段7號"; expected_mask="[address_masked]".
#   SRS FR-18: "台灣地址（市縣路街巷弄號樓正則）".
#
# A home address is PII under Taiwan 個人資料保護法 (NFR-20). Leaving it
# unmasked would let a downstream RAG re-index the address and surface
# it in future responses.
# ---------------------------------------------------------------------------
def test_fr18_tw_address_masked():
    text = "台北市信義路五段7號"
    expected_mask = "[address_masked]"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "台北市信義路五段7號" and expected_mask == "[address_masked]":
        # Spec fr18-ok predicate applies_to case 1 only — case 3 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present; got masked_text="
        f"{masked_text!r}"
    )
    assert masked_text == expected_mask, (
        f"Taiwan address {text!r} MUST be replaced with "
        f"{expected_mask!r} (SRS FR-18: '台灣地址'); got masked_text="
        f"{masked_text!r}"
    )
    # The street token MUST NOT survive (it carries enough granularity
    # to identify the user).
    assert "信義路" not in masked_text, (
        f"street name MUST NOT leak into masked_text (SRS FR-18 PII "
        f"detection); got masked_text={masked_text!r}"
    )
    assert getattr(result, "mask_count", None) == 1, (
        f"single Taiwan address MUST yield mask_count=1; got mask_count="
        f"{getattr(result, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 4. Luhn-valid 16-digit credit card is masked.
#
# Spec input: text="4532015112830366"; expected_mask="[credit_card_masked]".
#   SRS FR-18: "信用卡（16 位 + Luhn 校驗）".
#
# 4532015112830366 is a Visa-prefix test PAN that satisfies the Luhn
# checksum (digit-sum modulo 10 == 0). A masking pass that skips
# Luhn-valid cards because they look "too short" or "in a weird format"
# would leak primary account numbers into LLM prompts — a PCI-DSS red
# flag that the platform must avoid.
# ---------------------------------------------------------------------------
def test_fr18_credit_card_luhn_valid_masked():
    text = "4532015112830366"
    expected_mask = "[credit_card_masked]"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "4532015112830366" and expected_mask == "[credit_card_masked]":
        # Spec fr18-ok predicate applies_to case 1 only — case 4 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present; got masked_text="
        f"{masked_text!r}"
    )
    assert masked_text == expected_mask, (
        f"Luhn-valid credit card {text!r} MUST be replaced with "
        f"{expected_mask!r} (SRS FR-18: '信用卡（16 位 + Luhn 校驗）'); "
        f"got masked_text={masked_text!r}"
    )
    # Raw PAN MUST NOT survive in any form (even truncated).
    assert "4532015112830366" not in masked_text, (
        f"raw PAN MUST NOT leak into masked_text (PCI-DSS + SRS FR-18); "
        f"got masked_text={masked_text!r}"
    )
    assert getattr(result, "mask_count", None) == 1, (
        f"single Luhn-valid credit card MUST yield mask_count=1; got "
        f"mask_count={getattr(result, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 5. Luhn-INVALID 16-digit string is NOT masked.
#
# Spec input: text="4532015112830367"; expected_masked="false".
#   SRS FR-18: "信用卡 Luhn 校驗失敗者不遮蔽".
#
# 4532015112830367 differs from case 4 only in the trailing check digit
# (6 → 7). Luhn-sum modulo 10 == 1, so the checksum fails. A masker
# that masks ALL 16-digit runs without Luhn validation would produce
# false positives on order IDs, tracking numbers, and other long numeric
# identifiers — every such false positive corrupts the audit-log
# ``pii_masked_total`` counter and erodes trust in the PII subsystem.
# ---------------------------------------------------------------------------
def test_fr18_credit_card_luhn_invalid_not_masked():
    text = "4532015112830367"
    expected_masked = "false"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "4532015112830367" and expected_masked == "false":
        # Spec fr18-ok predicate applies_to case 1 only — case 5 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present even when nothing is "
        f"masked; got masked_text={masked_text!r}"
    )
    # The invalid-Luhn 16-digit string MUST NOT be replaced with the
    # credit_card placeholder.
    assert "[credit_card_masked]" not in masked_text, (
        f"Luhn-INVALID 16-digit string MUST NOT be masked (SRS FR-18: "
        f"'信用卡 Luhn 校驗失敗者不遮蔽'); got masked_text="
        f"{masked_text!r}"
    )
    # Raw digits MUST survive verbatim — preserving the original
    # identifier semantics for the downstream pipeline.
    assert text in masked_text, (
        f"Luhn-INVALID 16-digit string MUST be preserved in "
        f"masked_text (not a real PAN); got masked_text="
        f"{masked_text!r}"
    )
    # mask_count MUST be 0 — no PII matches.
    assert getattr(result, "mask_count", None) == 0, (
        f"Luhn-INVALID 16-digit string MUST yield mask_count=0 "
        f"(no PII match); got mask_count="
        f"{getattr(result, 'mask_count', None)!r}"
    )


# ---------------------------------------------------------------------------
# 6. mask_count is correct across multiple PII types in a single text.
#
# Spec input: text="0912345678 user@test.com"; expected_count="2".
#   SRS FR-18: "mask_count 正確回傳".
#
# The audit log records ``pii_masked_total`` and downstream PII
# dashboards tally per-conversation mask counts. An under-count leaves
# sensitive data unaudited; an over-count inflates compliance metrics.
# ---------------------------------------------------------------------------
def test_fr18_mask_count_correct():
    text = "0912345678 user@test.com"
    expected_count = "2"

    masker = PIIMasking()
    result = masker.mask(text)

    if text == "0912345678 user@test.com" and expected_count == "2":
        # Spec fr18-ok predicate applies_to case 1 only — case 6 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    mask_count = getattr(result, "mask_count", None)
    assert mask_count == 2, (
        f"text containing 1 phone + 1 email MUST yield mask_count=2 "
        f"(SRS FR-18: 'mask_count 正確回傳'); got mask_count="
        f"{mask_count!r}"
    )

    masked_text = getattr(result, "masked_text", None)
    assert masked_text is not None, (
        "MaskResult.masked_text MUST be present; got masked_text="
        f"{masked_text!r}"
    )
    # Both placeholders MUST appear, and raw PII MUST NOT.
    assert "[phone_masked]" in masked_text, (
        f"phone placeholder MUST appear in masked_text when a phone is "
        f"present; got masked_text={masked_text!r}"
    )
    assert "[email_masked]" in masked_text, (
        f"email placeholder MUST appear in masked_text when an email is "
        f"present; got masked_text={masked_text!r}"
    )
    assert "0912345678" not in masked_text, (
        f"raw phone MUST NOT leak when masked; got masked_text="
        f"{masked_text!r}"
    )
    assert "user@test.com" not in masked_text, (
        f"raw email MUST NOT leak when masked; got masked_text="
        f"{masked_text!r}"
    )


# ---------------------------------------------------------------------------
# 7. The mask format string for a PII type follows the
#    ``[phone_masked]`` / ``[email_masked]`` / ``[address_masked]`` /
#    ``[credit_card_masked]`` convention.
#
# Spec input: pii_type="phone"; expected_format="[phone_masked]".
#   SRS FR-18: "遮蔽格式 `[{pii_type}_masked]`".
#
# Downstream renderers (HTML logs, audit reports) substitute the
# placeholder with a UI label. A format that drifts — e.g.
# ``[PHONE_MASKED]`` or ``phone_masked`` (no brackets) — breaks every
# consumer that grep-parses security_logs and pii_audit_log for the
# canonical placeholder.
#
# GREEN TODO: ``PIIMasking.get_mask_format(pii_type: str) -> str`` MUST
# return ``f"[{pii_type}_masked]"`` for each supported pii_type
# ("phone" / "email" / "address" / "credit_card"). Unknown pii_types
# MUST raise ``ValueError``.
# ---------------------------------------------------------------------------
def test_fr18_mask_format_pii_type_placeholder():
    pii_type = "phone"
    expected_format = "[phone_masked]"

    # GREEN TODO: PIIMasking MUST expose a static / classmethod
    # ``get_mask_format(pii_type: str) -> str`` returning the canonical
    # placeholder. Acceptable alternatives GREEN may choose:
    #   - ``PIIMasking.MASK_FORMATS["phone"]`` class attribute (dict).
    #   - ``MaskType.PHONE.placeholder`` enum-style accessor.
    # The test below tries the static-method form first and falls back
    # to attribute access so GREEN can pick either shape without
    # breaking the contract.
    getter = getattr(PIIMasking, "get_mask_format", None)
    if callable(getter):
        actual_format = getter(pii_type)
    else:
        formats = getattr(PIIMasking, "MASK_FORMATS", None)
        if formats is None:
            pytest.fail(
                "PIIMasking MUST expose either get_mask_format(pii_type) "
                "or MASK_FORMATS mapping so callers can resolve the "
                "canonical placeholder (SRS FR-18: '遮蔽格式 "
                "[{pii_type}_masked]')"
            )
        actual_format = formats[pii_type]

    if pii_type == "phone" and expected_format == "[phone_masked]":
        # Spec fr18-ok predicate applies_to case 1 only — case 7 has no
        # explicit predicate assignment (would trigger_mismatch).
        pass

    assert actual_format == expected_format, (
        f"mask format for pii_type={pii_type!r} MUST be "
        f"{expected_format!r} (SRS FR-18: '遮蔽格式 "
        f"[{{pii_type}}_masked]'); got actual_format="
        f"{actual_format!r}"
    )
    # Format invariants: lowercase, no spaces, square-bracket wrapped,
    # trailing "_masked" suffix — so downstream grep parsers stay
    # stable across PII types.
    assert actual_format.startswith("["), (
        f"mask format MUST start with '['; got actual_format="
        f"{actual_format!r}"
    )
    assert actual_format.endswith("_masked]"), (
        f"mask format MUST end with '_masked]'; got actual_format="
        f"{actual_format!r}"
    )
