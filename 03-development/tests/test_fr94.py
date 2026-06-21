"""TDD-RED: failing tests for FR-94 — pii_vault application-layer encryption
+ dpo-only decryption + non-dpo 403.

Spec source: 02-architecture/TEST_SPEC.md (FR-94)
SRS source : SRS.md FR-94

Acceptance criteria (from SRS FR-94):
    pii_vault：original_text_encrypted(BYTEA), masked_text_encrypted(BYTEA)
    均應用層加密儲存（拒絕明文）；category（PHONE/ADDRESS/SSN 等）；
    encryption_key_id 關聯外部 KMS；僅 dpo 角色透過應用層 API 解密

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr94_plaintext_not_in_db
         Inputs: table="pii_vault"; column="original_text_encrypted";
                 expected_plaintext="false"
         Type  : validation (Q2)
    2. test_fr94_dpo_can_decrypt
         Inputs: role="dpo"; action="decrypt"; expected_success="true"
         Type  : happy_path (Q1)
    3. test_fr94_non_dpo_decrypt_fails_403
         Inputs: role="auditor"; action="decrypt"; expected_status="403"
         Type  : validation (Q2)

Sub-assertion (per TEST_SPEC):
    fr94-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-94 (SRS.md) requires:
#   1. A ``pii_vault`` table where ``original_text_encrypted`` and
#      ``masked_text_encrypted`` are stored as application-layer encrypted
#      BYTEA — no plaintext ever touches the DB column.
#   2. The ``category`` field must accept PHONE, ADDRESS, SSN, EMAIL,
#      CREDIT_CARD values.
#   3. An ``encryption_key_id`` linking each record to an external KMS key.
#   4. Only the ``dpo`` role can decrypt vault contents via the
#      application-layer API; any other role attempting decryption receives
#      a 403 Forbidden response.
#
# GREEN contract pinned by this spec:
#   - ``app.admin.gdpr.store_pii_entry(original_text, masked_text, category,
#     encryption_key_id) -> dict`` MUST encrypt both ``original_text`` and
#     ``masked_text`` at the application layer and return a dict containing
#     ``entry_id`` (str), ``encrypted_original`` (bytes),
#     ``encrypted_masked`` (bytes), ``category`` (str), and
#     ``encryption_key_id`` (str). The ``encrypted_original`` value MUST NOT
#     equal the original plaintext bytes.
#   - ``app.admin.gdpr.decrypt_pii_entry(entry_id, role) -> dict`` MUST
#     decrypt the entry and return a dict with ``original_text`` (str),
#     ``masked_text`` (str), and ``category`` (str) when the caller has
#     the ``dpo`` role. For any other role, it MUST raise
#     ``PermissionError`` indicating HTTP 403 Forbidden.
#
# The imports below are unguarded: pytest will fail with Collection Error
# (Exit Code 2) because ``app.admin.gdpr`` does not exist yet. That is the
# valid RED signal — GREEN creates the module with the functions above.
# ---------------------------------------------------------------------------
from app.admin.gdpr import store_pii_entry, decrypt_pii_entry


# ============================================================================
# 1. pii_vault MUST NOT store plaintext — the ``original_text_encrypted``
#    column value MUST differ from the input plaintext (validation).
#
# Spec input: table="pii_vault"; column="original_text_encrypted";
#            expected_plaintext="false".
# Spec sub-assertion: fr94-ok: result is not None.
# SRS FR-94 acceptance: "明文不落地"
# Test type: validation (Q2 derivation).
# ============================================================================
def test_fr94_plaintext_not_in_db():
    original_text = "0912345678"
    masked_text = "[phone_masked]"
    category = "PHONE"
    encryption_key_id = "kms-key-001"
    expected_plaintext = "false"

    # Defence-in-depth: pin the spec sentinel strings.
    assert original_text == "0912345678", (
        "FR-94: original_text sentinel must be '0912345678' (TW phone "
        f"format per SRS FR-18); got {original_text!r}."
    )
    assert category == "PHONE", (
        "FR-94: category sentinel must be 'PHONE' (TEST_SPEC FR-94 "
        f"case 1); got {category!r}."
    )
    assert encryption_key_id == "kms-key-001", (
        "FR-94: encryption_key_id sentinel must be 'kms-key-001' "
        f"(TEST_SPEC FR-94 case 1); got {encryption_key_id!r}."
    )
    assert expected_plaintext == "false", (
        "FR-94: expected_plaintext sentinel must be 'false' (TEST_SPEC "
        f"FR-94 case 1 spec input); got {expected_plaintext!r}."
    )

    # GREEN TODO: ``store_pii_entry(original_text, masked_text, category,
    # encryption_key_id)`` MUST encrypt ``original_text`` and ``masked_text``
    # at the application layer before persisting. The returned dict MUST
    # contain ``entry_id`` (str), ``encrypted_original`` (bytes),
    # ``encrypted_masked`` (bytes), ``category`` (str), and
    # ``encryption_key_id`` (str). The ``encrypted_original`` value MUST be
    # the ciphertext bytes and MUST NOT equal the UTF-8 encoding of the
    # input plaintext — proving no plaintext ever reaches the DB column.
    result = store_pii_entry(
        original_text=original_text,
        masked_text=masked_text,
        category=category,
        encryption_key_id=encryption_key_id,
    )

    # fr94-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr94-ok predicate: store_pii_entry() must not return None; the "
        "PII vault store operation must always produce a response."
    )

    assert isinstance(result, dict), (
        "FR-94: store_pii_entry() must return a dict with encrypted PII "
        f"entry fields; got type={type(result).__name__}."
    )

    # The result MUST contain entry_id so the caller can reference this
    # vault record for later decryption.
    assert "entry_id" in result, (
        "FR-94: store_pii_entry() result MUST contain 'entry_id' key; "
        f"got keys={sorted(result.keys())!r}."
    )
    assert isinstance(result["entry_id"], str), (
        "FR-94: 'entry_id' must be a str; got "
        f"{type(result['entry_id']).__name__}."
    )

    # The encrypted_original MUST be bytes (BYTEA column) and MUST NOT
    # equal the original plaintext encoded as UTF-8.
    assert "encrypted_original" in result, (
        "FR-94: store_pii_entry() result MUST contain "
        f"'encrypted_original' key; got keys={sorted(result.keys())!r}."
    )
    assert isinstance(result["encrypted_original"], bytes), (
        "FR-94: 'encrypted_original' must be bytes (BYTEA column); got "
        f"{type(result['encrypted_original']).__name__}."
    )
    assert result["encrypted_original"] != original_text.encode("utf-8"), (
        "FR-94: 'encrypted_original' MUST NOT equal the input plaintext "
        f"('{original_text}') — pii_vault must never store plaintext "
        "per SRS FR-94 ('明文不落地')."
    )

    # The encrypted_masked MUST also be bytes and encrypted.
    assert "encrypted_masked" in result, (
        "FR-94: store_pii_entry() result MUST contain "
        f"'encrypted_masked' key; got keys={sorted(result.keys())!r}."
    )
    assert isinstance(result["encrypted_masked"], bytes), (
        "FR-94: 'encrypted_masked' must be bytes (BYTEA column); got "
        f"{type(result['encrypted_masked']).__name__}."
    )

    # category and encryption_key_id MUST be echoed back.
    assert result.get("category") == category, (
        f"FR-94: 'category' must be '{category}' as provided; got "
        f"{result.get('category')!r}."
    )
    assert result.get("encryption_key_id") == encryption_key_id, (
        f"FR-94: 'encryption_key_id' must be '{encryption_key_id}' as "
        f"provided; got {result.get('encryption_key_id')!r}."
    )

    # Sentinel: expected_plaintext spec value MUST remain "false".
    assert expected_plaintext == "false", (
        "FR-94: expected_plaintext sentinel must remain 'false' per "
        f"TEST_SPEC FR-94 case 1; got {expected_plaintext!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert original_text == "0912345678", (
        f"FR-94: original_text sentinel must remain '0912345678'; got "
        f"{original_text!r}."
    )
    assert category == "PHONE", (
        f"FR-94: category sentinel must remain 'PHONE'; got {category!r}."
    )
    assert encryption_key_id == "kms-key-001", (
        f"FR-94: encryption_key_id sentinel must remain 'kms-key-001'; "
        f"got {encryption_key_id!r}."
    )


# ============================================================================
# 2. DPO role CAN decrypt vault contents — calling decrypt_pii_entry with
#    role="dpo" MUST return the original plaintext and masked text
#    (happy_path).
#
# Spec input: role="dpo"; action="decrypt"; expected_success="true".
# SRS FR-94 acceptance: "dpo 可解密"
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr94_dpo_can_decrypt():
    original_text = "0912345678"
    masked_text = "[phone_masked]"
    category = "PHONE"
    encryption_key_id = "kms-key-001"
    role = "dpo"
    action = "decrypt"
    expected_success = "true"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "dpo", (
        "FR-94: role sentinel must be 'dpo' (TEST_SPEC FR-94 case 2 "
        f"spec input); got {role!r}."
    )
    assert action == "decrypt", (
        "FR-94: action sentinel must be 'decrypt' (TEST_SPEC FR-94 "
        f"case 2 spec input); got {action!r}."
    )
    assert expected_success == "true", (
        "FR-94: expected_success sentinel must be 'true' (TEST_SPEC "
        f"FR-94 case 2 spec input); got {expected_success!r}."
    )

    # First, store a PII entry so we have something to decrypt.
    stored = store_pii_entry(
        original_text=original_text,
        masked_text=masked_text,
        category=category,
        encryption_key_id=encryption_key_id,
    )
    entry_id = stored["entry_id"]

    # GREEN TODO: ``decrypt_pii_entry(entry_id, role)`` MUST decrypt the
    # application-layer encrypted PII vault entry when the caller has the
    # ``dpo`` role. The returned dict MUST contain ``original_text`` (str)
    # matching the original plaintext input, ``masked_text`` (str), and
    # ``category`` (str). The decryption MUST use the encryption_key_id
    # stored with the entry to derive the correct key from KMS.
    result = decrypt_pii_entry(entry_id=entry_id, role=role)

    assert result is not None, (
        "FR-94: decrypt_pii_entry() must not return None for dpo role; "
        "the DPO must always receive a decryption result."
    )

    assert isinstance(result, dict), (
        "FR-94: decrypt_pii_entry() must return a dict with decrypted "
        f"PII fields; got type={type(result).__name__}."
    )

    # The decrypted original_text MUST match the input plaintext.
    assert "original_text" in result, (
        "FR-94: decrypt result MUST contain 'original_text' key; got "
        f"keys={sorted(result.keys())!r}."
    )
    assert result["original_text"] == original_text, (
        f"FR-94: decrypted 'original_text' must be '{original_text}'; "
        f"got {result['original_text']!r}."
    )

    # The decrypted masked_text MUST match the input masked text.
    assert "masked_text" in result, (
        "FR-94: decrypt result MUST contain 'masked_text' key; got "
        f"keys={sorted(result.keys())!r}."
    )
    assert result["masked_text"] == masked_text, (
        f"FR-94: decrypted 'masked_text' must be '{masked_text}'; got "
        f"{result['masked_text']!r}."
    )

    # The category MUST be preserved through the encrypt/decrypt cycle.
    assert result.get("category") == category, (
        f"FR-94: decrypted 'category' must be '{category}'; got "
        f"{result.get('category')!r}."
    )

    # Sentinel: expected_success spec value MUST remain "true".
    assert expected_success == "true", (
        "FR-94: expected_success sentinel must remain 'true' per "
        f"TEST_SPEC FR-94 case 2; got {expected_success!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "dpo", (
        f"FR-94: role sentinel must remain 'dpo'; got {role!r}."
    )
    assert action == "decrypt", (
        f"FR-94: action sentinel must remain 'decrypt'; got {action!r}."
    )


# ============================================================================
# 3. Non-DPO role MUST receive 403 Forbidden when attempting to decrypt
#    vault contents (validation).
#
# Spec input: role="auditor"; action="decrypt"; expected_status="403".
# SRS FR-94 acceptance: "其他角色解密失敗"
# Test type: validation (Q2 derivation).
# ============================================================================
def test_fr94_non_dpo_decrypt_fails_403():
    original_text = "0912345678"
    masked_text = "[phone_masked]"
    category = "PHONE"
    encryption_key_id = "kms-key-001"
    role = "auditor"
    action = "decrypt"
    expected_status = "403"

    # Defence-in-depth: pin the spec sentinel strings.
    assert role == "auditor", (
        "FR-94: role sentinel must be 'auditor' (TEST_SPEC FR-94 case 3 "
        f"spec input); got {role!r}."
    )
    assert action == "decrypt", (
        "FR-94: action sentinel must be 'decrypt' (TEST_SPEC FR-94 "
        f"case 3 spec input); got {action!r}."
    )
    assert expected_status == "403", (
        "FR-94: expected_status sentinel must be '403' (TEST_SPEC "
        f"FR-94 case 3 spec input); got {expected_status!r}."
    )

    # First, store a PII entry so we have something to (try to) decrypt.
    stored = store_pii_entry(
        original_text=original_text,
        masked_text=masked_text,
        category=category,
        encryption_key_id=encryption_key_id,
    )
    entry_id = stored["entry_id"]

    # GREEN TODO: ``decrypt_pii_entry(entry_id, role)`` MUST raise
    # ``PermissionError`` when the caller's role is NOT ``dpo``. The
    # auditor role lacks the ``pii:decrypt`` permission (per SRS FR-60 /
    # FR-61 RBAC matrix) and MUST receive a 403 Forbidden response,
    # mapped to a Python ``PermissionError`` at the application layer.
    # GREEN must NOT silently return None or an empty dict for
    # unauthorized callers — it MUST raise.
    with pytest.raises(PermissionError):
        decrypt_pii_entry(entry_id=entry_id, role=role)

    # Sentinel: expected_status spec value MUST remain "403".
    assert expected_status == "403", (
        "FR-94: expected_status sentinel must remain '403' per "
        f"TEST_SPEC FR-94 case 3; got {expected_status!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert role == "auditor", (
        f"FR-94: role sentinel must remain 'auditor'; got {role!r}."
    )
    assert action == "decrypt", (
        f"FR-94: action sentinel must remain 'decrypt'; got {action!r}."
    )
