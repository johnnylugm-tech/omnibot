from __future__ import annotations

import re
from dataclasses import dataclass

"""[FR-18] PIIMasking — detect and mask Taiwan phone / email / address / credit-card.

SRS FR-18: "PIIMasking: 偵測並遮蔽電話 (台灣格式 \\d{10,11}), Email,
台灣地址 (市縣路街巷弄號樓正則), 信用卡 (16 位 + Luhn 校驗); 遮蔽
格式 `[{pii_type}_masked]`. 所有四類 PII 正確遮蔽; 信用卡 Luhn 校驗
失敗者不遮蔽; mask_count 正確回傳."

The masker is pure-Python (regex + Luhn checksum). It performs no I/O so
the call fits inside the request hot path without extra latency budget.

Detection order matters:
    1. credit_card — 16 consecutive digits that PASS Luhn. Word-bounded so
       a 10/11-digit phone substring is not promoted to credit_card.
       Checked first so a Luhn-valid PAN is masked as credit_card rather
       than as phone. Luhn-invalid 16-digit runs are left untouched.
    2. phone       — Taiwan mobile / landline ``\\b\\d{10,11}\\b``.
       Word boundaries prevent a phone match from slicing out of a
       longer digit run (e.g. a Luhn-invalid 16-digit tracking number).
    3. email       — ``\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b``.
    4. address     — Taiwan address ``[一-鿿]+市/縣 + …路/街 + …號/樓`` lazy
       match; the lazy quantifiers keep the match tight enough to swallow
       the entire address fragment that triggered the rule.

Citations:
    - SRS.md FR-18 (PIIMasking acceptance criteria — four PII types,
      Luhn validation, mask_count accuracy, placeholder convention)
    - SRS.md FR-20 (pii_audit_log write per mask event; 90-day
      anonymization via FR-91 retention policy)
    - 02-architecture/TEST_SPEC.md FR-18 (cases 1-7: phone, email,
      address, Luhn-valid CC, Luhn-invalid CC, multi-PII mask_count,
      mask_format placeholder)
    - 02-architecture/TEST_SPEC.md FR-20 (cases 1-3: audit log write,
      conversation_id field, 90-day anonymize schedule)
    - 03-development/tests/test_fr18.py:101-148 (phone TW-format case)
    - 03-development/tests/test_fr18.py:154-194 (email case)
    - 03-development/tests/test_fr18.py:200-242 (Taiwan address case)
    - 03-development/tests/test_fr18.py:248-296 (Luhn-valid credit card)
    - 03-development/tests/test_fr18.py:302-352 (Luhn-invalid credit card)
    - 03-development/tests/test_fr18.py:358-413 (multi-PII mask_count)
    - 03-development/tests/test_fr18.py:419-489 (mask_format placeholder)
    - 03-development/tests/test_fr20.py:101-159 (mask_event_writes_audit_log)
    - 03-development/tests/test_fr20.py:163-217 (audit_log_has_conversation_id)
    - 03-development/tests/test_fr20.py:245-288 (90day_anonymize_scheduled)
"""


# ---------------------------------------------------------------------------
# Pattern catalogue
# ---------------------------------------------------------------------------
# Phone: word-bounded 10 or 11 consecutive digits. The word-boundary
# anchors on BOTH sides are mandatory — without them, ``\\d{10,11}`` would
# happily slice the first 11 digits out of a 16-digit credit-card
# candidate, producing a false-positive phone match and a corrupted
# ``mask_count``. With ``\\b``, the regex only fires when the digit run
# is exactly 10 or 11 characters long (so a 16-digit tracking number
# never matches as a phone).
_PHONE_RE = re.compile(r"\b\d{10,11}\b")

# Credit card: 16 consecutive digits, word-bounded. A Luhn check gates
# the actual replacement so Luhn-invalid 16-digit strings (order IDs,
# tracking numbers) survive verbatim. The gate lives in ``_mask_credit_card``
# below, not in the regex.
_CREDIT_CARD_RE = re.compile(r"\b\d{16}\b")

# Email: pragmatic RFC-ish pattern. Avoids whitespace / angle brackets so
# the match is safe to splice back into a log line.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Taiwan address: ``<chinese>+市/縣 + <mixed>* + 路/街 + <mixed>* + 號/樓``.
# Lazy quantifiers on every internal step keep the match from running
# past the address fragment into unrelated Chinese text that happens to
# follow on the same line. ``<mixed>`` includes digits so the trailing
# ``7號`` in ``信義路五段7號`` is swallowed by the rule — without digits
# in the char class, the regex stops at the boundary between Chinese
# (``五段``) and the Arabic numeral (``7``) and leaves the address
# fragment unmasked.
_ADDRESS_RE = re.compile(
    r"[一-鿿]+?[市縣]"
    r"[0-9一-鿿]*?"
    r"[路街巷]"
    r"[0-9一-鿿]*?"
    r"[號樓]"
)


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MaskResult:
    """[FR-18] Outcome of a single ``PIIMasking.mask()`` call.

    Attributes:
        masked_text:  text with every detected PII substring replaced by
                      its canonical ``[<pii_type>_masked]`` placeholder.
        mask_count:   total number of PII substrings masked (across all
                      four types).
        masked_types: tuple of pii_type strings, in detection order, so
                      callers can render a per-type breakdown without
                      re-scanning ``masked_text``.
    """

    masked_text: str
    mask_count: int
    masked_types: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# [FR-20] Audit log record — one row per successful mask() call.
#
# Field names mirror SRS FR-20 verbatim so a downstream privacy-officer
# query (FR-60) does not have to remap columns: ``conversation_id``,
# ``mask_count``, ``pii_types``, ``action``, ``performed_by``.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditEntry:
    """[FR-20] One row in the ``pii_audit_log``.

    Attributes:
        conversation_id: ID of the originating conversation — lets a
            privacy officer correlate the scrub to its session.
        mask_count:      number of PII substrings masked in this event.
        pii_types:       ordered tuple of pii_type strings actually
            masked (e.g. ``("phone", "email")``). Preserves detection
            order for forensic replay.
        action:          action token (always ``"mask"`` here; reserved
            for future audit actions such as ``"unmask_admin"``).
        performed_by:    role / service identifier that invoked
            ``mask()`` (default ``"system"``).
    """

    conversation_id: str
    mask_count: int
    pii_types: tuple[str, ...]
    action: str
    performed_by: str


# ---------------------------------------------------------------------------
# Masker
# ---------------------------------------------------------------------------
class PIIMasking:
    """[FR-18] Detect and mask PII substrings inside free-form text.

    The instance carries no state — every regex is a module-level compiled
    pattern and Luhn validation is a pure function — so constructing an
    instance is allocation-free and the object is safe to share across
    threads.
    """

    # Canonical placeholder per PII type. Exposed as a class attribute so
    # callers that prefer attribute access (``PIIMasking.MASK_FORMATS[...]``)
    # resolve the same string ``get_mask_format(...)`` returns.
    MASK_FORMATS: dict[str, str] = {
        "phone": "[phone_masked]",
        "email": "[email_masked]",
        "address": "[address_masked]",
        "credit_card": "[credit_card_masked]",
    }

    # [FR-20] In-memory pii_audit_log. Every successful ``mask()`` call
    # appends one ``AuditEntry``. Class-level (not instance-level) so the
    # log survives instance churn and the scheduler (FR-91) can read it
    # via the class accessor without holding a masker instance. A real
    # deployment writes to a DB; this list is the test-visible surrogate.
    _audit_log: list[AuditEntry] = []  # type: ignore[assignment]

    # -- public API --------------------------------------------------------

    # Order matters: phone / email / address are independent regex passes
    # applied AFTER the credit_card pass (see ``mask()``). The credit_card
    # rule MUST run first so a Luhn-valid 16-digit PAN is masked as
    # ``credit_card`` rather than as ``phone`` — the phone regex's word
    # boundary already prevents a 16-digit run from being sliced into an
    # 11-digit phone match, but running credit_card first makes the
    # ordering intentional rather than incidental.
    _PATTERN_PASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("phone", _PHONE_RE),
        ("email", _EMAIL_RE),
        ("address", _ADDRESS_RE),
    )

    # FR-19 escalation keywords. SRS FR-19: "密碼/銀行帳戶/信用卡號/提款卡
    # 關鍵字 → should_escalate() 回傳 True". A plain ``in`` substring
    # scan is sufficient — none of the four tokens is a substring of any
    # other, and the negative-path test ("我想查詢訂單狀態") shares zero
    # characters with any token, so a substring check cannot spuriously
    # match ordinary support vocabulary. No regex compile cost on the
    # hot path.
    _ESCALATION_KEYWORDS: tuple[str, ...] = (
        "密碼",
        "銀行帳戶",
        "信用卡號",
        "提款卡",
    )

    def mask(
        self,
        text: str,
        *,
        conversation_id: str = "unknown",
        performed_by: str = "system",
    ) -> MaskResult:
        """[FR-18, FR-20] Detect + mask every PII substring AND emit one
        ``pii_audit_log`` row per call.

        Args:
            text: free-form input that may contain phone / email /
                address / credit-card substrings.
            conversation_id: ID of the originating conversation. Defaults
                to ``"unknown"`` so callers that pre-date the FR-20 audit
                hook (FR-18 happy-path tests) keep working; production
                callers MUST pass the real conversation_id so the row
                is correlatable for §30 GDPR / §17 個資法 reporting.
            performed_by: role or service identifier that invoked
                ``mask()`` (default ``"system"``).

        Returns:
            MaskResult with the rewritten text, total mask count, and
            the ordered tuple of pii_types that were actually masked.
        """
        masked, types = self._mask_credit_card(text)
        for pii_type, pattern in self._PATTERN_PASSES:
            masked, found = self._apply_pattern(masked, pattern, pii_type)
            types.extend(found)

        result = MaskResult(
            masked_text=masked,
            mask_count=len(types),
            masked_types=tuple(types),
        )

        # [FR-20] Audit write fires from inside mask() so every future
        # caller path participates automatically. Field names mirror SRS
        # FR-20 verbatim — no remap needed for downstream privacy queries.
        self._record_audit(result, conversation_id, performed_by)
        return result

    def _record_audit(
        self,
        result: MaskResult,
        conversation_id: str,
        performed_by: str,
    ) -> None:
        """[FR-20] Append one ``pii_audit_log`` row for a successful mask.

        ``action`` is reserved as ``"mask"`` today; future audit actions
        (``"unmask_admin"`` etc.) can be threaded through this method
        without touching ``mask()``.
        """
        PIIMasking._audit_log.append(
            AuditEntry(
                conversation_id=conversation_id,
                mask_count=result.mask_count,
                pii_types=result.masked_types,
                action="mask",
                performed_by=performed_by,
            )
        )

    @classmethod
    def read_audit_log(cls) -> list[AuditEntry]:
        """[FR-20] Return a snapshot of the in-memory ``pii_audit_log``.

        Returns:
            List of ``AuditEntry`` in write order (oldest first). The
            list is a snapshot — the caller cannot mutate the live
            buffer via the returned reference because we hand back a
            shallow copy.
        """
        return list(cls._audit_log)

    @classmethod
    def clear_audit_log(cls) -> None:
        """[FR-20] Reset the in-memory ``pii_audit_log``.

        Provided for test isolation only. A real deployment persists to
        a DB; the reset is safe here because the audit-log buffer is
        purely the test-visible surrogate.
        """
        cls._audit_log.clear()

    def should_escalate(self, text: str) -> bool:
        """[FR-19] Return True iff ``text`` carries a PII-escalation keyword.

        SRS FR-19: "PII 敏感關鍵字觸發轉接：偵測 密碼/銀行帳戶/信用卡號/
        提款卡 關鍵字 → should_escalate() 回傳 True. 四個敏感關鍵字觸發
        should_escalate()=True；其他關鍵字不誤判."

        Returns:
            True the moment any of the four canonical keywords appears
            as a substring of ``text``; False otherwise (including on
            empty input — no token can match an empty string).

        Citations:
            - SRS.md FR-19 (PII escalation trigger, false-positive guard)
            - 02-architecture/TEST_SPEC.md FR-19 (cases 1-5: 密碼,
              銀行帳戶, 信用卡號, 提款卡, neutral text)
            - 03-development/tests/test_fr19.py:55-77 (password case)
            - 03-development/tests/test_fr19.py:82-106 (bank-account case)
            - 03-development/tests/test_fr19.py:111-139 (credit-card case)
            - 03-development/tests/test_fr19.py:144-173 (debit-card case)
            - 03-development/tests/test_fr19.py:178-209 (negative case)
        """
        return any(keyword in text for keyword in self._ESCALATION_KEYWORDS)

    @staticmethod
    def get_mask_format(pii_type: str) -> str:
        """[FR-18] Return the canonical placeholder for ``pii_type``.

        Args:
            pii_type: one of ``"phone"``, ``"email"``, ``"address"``,
                ``"credit_card"``.

        Returns:
            The placeholder string ``f"[{pii_type}_masked]"``.

        Raises:
            ValueError: if ``pii_type`` is not one of the four supported
                PII categories. Silently returning the raw key would let
                a typo (``"phon"``) leak downstream renderers that
                grep-parse the audit log for the canonical placeholder.
        """
        try:
            return PIIMasking.MASK_FORMATS[pii_type]
        except KeyError as exc:
            raise ValueError(
                f"unknown pii_type {pii_type!r}; expected one of "
                f"{sorted(PIIMasking.MASK_FORMATS)!r}"
            ) from exc

    # -- internals ---------------------------------------------------------

    def _mask_credit_card(self, text: str) -> tuple[str, list[str]]:
        """Mask every 16-digit run whose Luhn checksum is valid.

        Luhn-invalid runs are returned verbatim — they are almost
        certainly tracking numbers / order IDs, not PANs, and masking
        them would inflate the ``pii_masked_total`` audit counter.
        """
        types: list[str] = []
        placeholder = self.get_mask_format("credit_card")

        def _replace(match: re.Match[str]) -> str:
            digits = match.group()
            if self._luhn_valid(digits):
                types.append("credit_card")
                return placeholder
            return digits

        masked = _CREDIT_CARD_RE.sub(_replace, text)
        return masked, types

    @staticmethod
    def _apply_pattern(
        text: str, pattern: re.Pattern[str], pii_type: str
    ) -> tuple[str, list[str]]:
        """Replace every match of ``pattern`` with the canonical placeholder.

        A single ``sub`` pass records each match via its callback so the
        replacement and the per-type count come from one scan rather
        than from a separate ``findall`` after ``sub``.

        Returns:
            (masked_text, masked_types) where ``masked_types`` has one
            ``pii_type`` entry per match, in detection order. Its length
            is the per-type contribution to ``MaskResult.mask_count``.
        """
        placeholder = PIIMasking.get_mask_format(pii_type)
        types: list[str] = []

        def _replace(match: re.Match[str]) -> str:
            types.append(pii_type)
            return placeholder

        return pattern.sub(_replace, text), types

    @staticmethod
    def _luhn_valid(number: str) -> bool:
        """Return True iff ``number`` (digits only) passes the Luhn checksum.

        The check uses the standard right-to-left doubling pattern:
        every second digit from the right is doubled, with the doubled
        value reduced modulo 9 (subtract 9 when the doubled value
        exceeds 9). The total modulo 10 must equal 0 for the number
        to be considered a syntactically valid PAN.
        """
        if not number.isdigit() or len(number) != 16:
            return False
        total = 0
        for i, ch in enumerate(reversed(number)):
            digit = ord(ch) - 48  # ord('0') == 48; faster than int(ch)
            if i & 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0