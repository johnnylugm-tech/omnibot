"""[FR-94] pii_vault application-layer encryption + dpo-only decryption.

Citations:
    SRS.md line 217 — FR-94 acceptance: pii_vault
        original_text_encrypted(BYTEA), masked_text_encrypted(BYTEA)
        均應用層加密儲存（拒絕明文）; category（PHONE/ADDRESS/SSN 等）;
        encryption_key_id 關聯外部 KMS; 僅 dpo 角色透過應用層 API 解密.
    SRS.md line 1197 — FR-94 detailed spec: encrypted BYTEA storage;
        KMS key_id; dpo-only decrypt; no plaintext storage.
    TEST_SPEC.md line 1890 — FR-94 3 test cases: plaintext_not_in_db,
        dpo_can_decrypt (happy_path), non_dpo_decrypt_fails_403 (validation).
"""

from __future__ import annotations

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from app.admin.rbac import enforce as _rbac_enforce

# In-memory PII vault — isolation-safe store for test runs.
# Keys are UUID strings (entry_id); values are the encrypted record dicts.
_VAULT: dict[str, dict] = {}

def _derive_fernet_key(encryption_key_id: str) -> bytes:
    """Derive a deterministic Fernet-compatible 32-byte key from a KMS key ID.

    Uses SHA-256 so the same ``encryption_key_id`` always yields the same
    Fernet key, enabling round-trip encrypt/decrypt without an external KMS.
    """
    digest = hashlib.sha256(encryption_key_id.encode()).digest()
    return base64.urlsafe_b64encode(digest)


# ---------------------------------------------------------------------------
# Public API — the two functions imported by test_fr94.py
# ---------------------------------------------------------------------------


def store_pii_entry(
    original_text: str,
    masked_text: str,
    category: str,
    encryption_key_id: str,
) -> dict:
    """[FR-94] Encrypt and store a PII vault entry at the application layer.

    Both ``original_text`` and ``masked_text`` are encrypted with a
    Fernet key derived from ``encryption_key_id``.  No plaintext ever
    reaches the in-memory store.

    Returns a dict with ``entry_id`` (str), ``encrypted_original``
    (bytes), ``encrypted_masked`` (bytes), ``category`` (str), and
    ``encryption_key_id`` (str).
    """
    key = _derive_fernet_key(encryption_key_id)
    fernet = Fernet(key)

    encrypted_original = fernet.encrypt(original_text.encode("utf-8"))
    encrypted_masked = fernet.encrypt(masked_text.encode("utf-8"))

    entry_id = str(uuid.uuid4())

    _VAULT[entry_id] = {
        "encrypted_original": encrypted_original,
        "encrypted_masked": encrypted_masked,
        "category": category,
        "encryption_key_id": encryption_key_id,
    }

    return {
        "entry_id": entry_id,
        "encrypted_original": encrypted_original,
        "encrypted_masked": encrypted_masked,
        "category": category,
        "encryption_key_id": encryption_key_id,
    }


def decrypt_pii_entry(entry_id: str, role: str) -> dict:
    """[FR-94] Decrypt a PII vault entry.

    Only the ``dpo`` role is authorised to decrypt; all other roles
    receive ``PermissionError`` (mapped to HTTP 403 by middleware).

    Returns a dict with ``original_text`` (str), ``masked_text`` (str),
    and ``category`` (str).
    """
    if _rbac_enforce(role, "pii", "decrypt") != 200:
        raise PermissionError("AUTHZ_INSUFFICIENT_ROLE")

    entry = _VAULT.get(entry_id)
    if entry is None:
        raise KeyError(f"pii_vault entry not found: {entry_id!r}")
    key = _derive_fernet_key(entry["encryption_key_id"])
    fernet = Fernet(key)

    original_text = fernet.decrypt(entry["encrypted_original"]).decode("utf-8")
    masked_text = fernet.decrypt(entry["encrypted_masked"]).decode("utf-8")

    return {
        "original_text": original_text,
        "masked_text": masked_text,
        "category": entry["category"],
    }
