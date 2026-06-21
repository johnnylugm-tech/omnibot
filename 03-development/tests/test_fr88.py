from __future__ import annotations
"""TDD-RED: failing tests for FR-88 — GDPR API (data export + async deletion).

Spec source: 02-architecture/TEST_SPEC.md (FR-88)
SRS source : 01-requirements/SRS.md FR-88

Acceptance criteria (from SRS FR-88):
    GET /api/v1/users/{user_id}/data（匯出 JSON/CSV）；
    DELETE /api/v1/users/{user_id}/data（觸發異步刪除，30 天內完成，
    含 PII 欄位清除 + messages 內容 [REDACTED] + 稽核日誌）

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-88 (SRS.md) requires a GDPR compliance module providing:
#   1. ``export_user_data(user_id: str, format: str = "json") -> dict``
#      Returns user personal data.  When ``format="json"``, the result dict
#      MUST contain all personal data fields (conversations, messages,
#      profile, emotion history, etc.).  When ``format="csv"``, the result
#      dict MUST contain ``csv_data: str`` and ``filename: str`` suitable
#      for a file-download response.
#   2. ``delete_user_data(user_id: str) -> dict``
#      Triggers an async deletion job (30-day SLA).  Returns a dict with
#      ``deletion_id: str`` and ``status: str`` (e.g. ``"queued"``).
#   3. ``get_user_profile(user_id: str) -> dict | None``
#      Returns the current user profile dict.  After a successful deletion,
#      MUST return ``None`` (or a dict whose PII-bearing fields are all
#      ``None`` / empty).
#   4. ``get_pii_audit_log(user_id: str, event_type: str) -> list[dict]``
#      Queries the PII audit log for entries matching *user_id* and
#      *event_type*.  After a GDPR deletion, at least one entry with
#      ``event_type == "gdpr_deletion"`` MUST exist.
#
# GREEN contract pinned by this spec:
#   - ``app.api.gdpr`` MUST be a package or module.
#   - ``export_user_data(user_id, format)`` MUST return a dict.  JSON mode
#     MUST include ``user_id``, ``profile``, ``conversations``, ``messages``
#     keys.  CSV mode MUST include ``csv_data`` and ``filename`` keys.
#   - ``delete_user_data(user_id)`` MUST persist a deletion job record,
#     return ``deletion_id`` and ``status="queued"``, and MUST NOT raise
#     for a non-existent user (idempotent per spec input).
#   - ``get_user_profile(user_id)`` MUST return ``None`` post-deletion.
#   - ``get_pii_audit_log(user_id, event_type="gdpr_deletion")`` MUST
#     return a non-empty list after ``delete_user_data`` completes.
#
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because ``app.api.gdpr`` does not exist yet.  That is the
# valid RED signal — GREEN adds the module and tightens the behaviour to
# make every assertion hold.
# ---------------------------------------------------------------------------
from app.admin.gdpr import (
    delete_user_data,
    export_user_data,
    get_pii_audit_log,
    get_user_profile,
)


# ============================================================================
# 1. Data export MUST return valid JSON with user personal data (happy_path).
#
# Spec input: user_id="user-001"; format="json".
# Spec sub-assertion: fr88-ok: result is not None.
# SRS FR-88 acceptance:
#    "data export 回傳合法 JSON".
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr88_data_export_returns_json():
    user_id = "user-001"
    fmt = "json"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-88: user_id sentinel must be 'user-001' (SRS FR-88 "
        f"GDPR export probe); got {user_id!r}."
    )
    assert fmt == "json", (
        "FR-88: format sentinel must be 'json' (SRS FR-88 "
        f"JSON export probe); got {fmt!r}."
    )

    # GREEN TODO: ``export_user_data(user_id, format="json")`` MUST return
    # a dict containing the user's complete personal data.  Required keys:
    # ``user_id``, ``profile``, ``conversations``, ``messages``.
    result = export_user_data(user_id=user_id, format=fmt)

    # fr88-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr88-ok predicate: export_user_data() must not return None for "
        "valid user_id and format='json'."
    )

    assert isinstance(result, dict), (
        "FR-88: export_user_data() must return a dict; "
        f"got type={type(result).__name__}."
    )

    # GREEN TODO: JSON export response MUST include the standard personal-data
    # keys: user_id, profile, conversations, messages.
    for key in ("user_id", "profile", "conversations", "messages"):
        assert key in result, (
            f"FR-88: export_user_data(format='json') result MUST contain "
            f"key {key!r} per SRS FR-88 data export spec; got "
            f"keys={sorted(result.keys())!r}."
        )

    # GREEN TODO: ``user_id`` field MUST match the requested user.
    assert result["user_id"] == user_id, (
        f"FR-88: export result user_id must match request; "
        f"expected {user_id!r}, got {result['user_id']!r}."
    )

    # GREEN TODO: ``profile`` MUST be a dict (may be empty/anonymised but
    # MUST be present and dict-typed).
    assert isinstance(result["profile"], dict), (
        "FR-88: export result 'profile' must be a dict; "
        f"got {type(result['profile']).__name__}."
    )

    # GREEN TODO: ``conversations`` MUST be a list.
    assert isinstance(result["conversations"], list), (
        "FR-88: export result 'conversations' must be a list; "
        f"got {type(result['conversations']).__name__}."
    )

    # GREEN TODO: ``messages`` MUST be a list.
    assert isinstance(result["messages"], list), (
        "FR-88: export result 'messages' must be a list; "
        f"got {type(result['messages']).__name__}."
    )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-88: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert fmt == "json", (
        f"FR-88: format sentinel must remain 'json'; got {fmt!r}."
    )


# ============================================================================
# 2. Data export MUST return downloadable CSV content (happy_path).
#
# Spec input: user_id="user-001"; format="csv".
# SRS FR-88 acceptance:
#    "data export 回傳合法 CSV".
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr88_data_export_csv_downloadable():
    user_id = "user-001"
    fmt = "csv"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-88: user_id sentinel must be 'user-001' (SRS FR-88 "
        f"GDPR CSV export probe); got {user_id!r}."
    )
    assert fmt == "csv", (
        "FR-88: format sentinel must be 'csv' (SRS FR-88 "
        f"CSV export probe); got {fmt!r}."
    )

    # GREEN TODO: ``export_user_data(user_id, format="csv")`` MUST return
    # a dict with ``csv_data`` (str) and ``filename`` (str) keys so the API
    # layer can construct a ``StreamingResponse`` / ``FileResponse`` for
    # download.
    result = export_user_data(user_id=user_id, format=fmt)

    assert result is not None, (
        "FR-88: export_user_data(format='csv') must not return None."
    )
    assert isinstance(result, dict), (
        "FR-88: export_user_data(format='csv') must return a dict; "
        f"got type={type(result).__name__}."
    )

    # GREEN TODO: CSV mode MUST provide ``csv_data`` (the raw CSV string)
    # and ``filename`` (the Content-Disposition filename).
    for key in ("csv_data", "filename"):
        assert key in result, (
            f"FR-88: export_user_data(format='csv') result MUST contain "
            f"key {key!r} for a downloadable CSV response; got "
            f"keys={sorted(result.keys())!r}."
        )

    # GREEN TODO: ``csv_data`` MUST be a non-empty string — there is at
    # minimum a header row even if the user has no data.
    csv_data = result["csv_data"]
    assert isinstance(csv_data, str), (
        "FR-88: 'csv_data' must be a str; "
        f"got {type(csv_data).__name__}."
    )
    assert len(csv_data) > 0, (
        "FR-88: 'csv_data' must be non-empty (at minimum a header row)."
    )

    # GREEN TODO: ``filename`` MUST be a non-empty string suitable for
    # Content-Disposition (e.g. ``user-001_data_2026-06-21.csv``).
    filename = result["filename"]
    assert isinstance(filename, str), (
        "FR-88: 'filename' must be a str; "
        f"got {type(filename).__name__}."
    )
    assert len(filename) > 0, (
        "FR-88: 'filename' must be non-empty."
    )
    # GREEN TODO: filename SHOULD end with ``.csv`` or ``.tsv``.
    assert filename.endswith(".csv") or filename.endswith(".tsv"), (
        f"FR-88: 'filename' should end with .csv or .tsv; "
        f"got {filename!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-88: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert fmt == "csv", (
        f"FR-88: format sentinel must remain 'csv'; got {fmt!r}."
    )


# ============================================================================
# 3. Deletion MUST clear PII fields from the user profile (happy_path).
#
# Spec input: user_id="user-001"; expected_profile="null".
# SRS FR-88 acceptance:
#    "含 PII 欄位清除 + messages 內容 [REDACTED]".
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr88_deletion_clears_pii_fields():
    user_id = "user-001"
    expected_profile = "null"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-88: user_id sentinel must be 'user-001' (SRS FR-88 "
        f"GDPR deletion probe); got {user_id!r}."
    )
    assert expected_profile == "null", (
        "FR-88: expected_profile sentinel must be 'null' (PII fields "
        f"MUST be cleared after GDPR deletion per SRS FR-88); got "
        f"{expected_profile!r}."
    )

    # GREEN TODO: ``delete_user_data(user_id)`` MUST trigger an async
    # deletion job that clears PII-bearing fields from the user profile
    # (name, email, phone, address → null / empty), redacts message
    # bodies to ``[REDACTED]``, and returns a ``deletion_id`` +
    # ``status`` dict.  The deletion is async (30-day SLA), but
    # ``delete_user_data`` MUST at minimum persist the deletion request.
    del_result = delete_user_data(user_id=user_id)

    assert del_result is not None, (
        "FR-88: delete_user_data() must not return None."
    )
    assert isinstance(del_result, dict), (
        "FR-88: delete_user_data() must return a dict; "
        f"got type={type(del_result).__name__}."
    )

    # GREEN TODO: ``delete_user_data`` MUST return at minimum
    # ``deletion_id`` and ``status`` keys.
    for key in ("deletion_id", "status"):
        assert key in del_result, (
            f"FR-88: delete_user_data() result MUST contain key {key!r}; "
            f"got keys={sorted(del_result.keys())!r}."
        )

    assert isinstance(del_result["deletion_id"], str), (
        "FR-88: 'deletion_id' must be a str; "
        f"got {type(del_result['deletion_id']).__name__}."
    )
    assert len(del_result["deletion_id"]) > 0, (
        "FR-88: 'deletion_id' must be non-empty."
    )
    # GREEN TODO: status SHOULD indicate the deletion is queued/accepted.
    assert del_result["status"] in ("queued", "accepted", "processing"), (
        f"FR-88: delete_user_data status must be 'queued'/'accepted'/"
        f"'processing'; got {del_result['status']!r}."
    )

    # GREEN TODO: After ``delete_user_data`` is called, ``get_user_profile``
    # MUST return ``None`` (the profile has been anonymised / PII cleared).
    # For the RED step this call blows up with Collection Error if the
    # module is absent — but once GREEN wires the function, this assertion
    # ensures the deletion actually clears PII.
    profile = get_user_profile(user_id=user_id)
    assert profile is None, (
        f"FR-88: get_user_profile({user_id!r}) MUST return None after "
        f"GDPR deletion per SRS FR-88 'PII 欄位清除'; got "
        f"{profile!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-88: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert expected_profile == "null", (
        f"FR-88: expected_profile sentinel must remain 'null'; "
        f"got {expected_profile!r}."
    )


# ============================================================================
# 4. Deletion MUST write a gdpr_deletion entry to the PII audit log
#    (validation).
#
# Spec input: user_id="user-001";
#            expected_audit_event="gdpr_deletion".
# SRS FR-88 acceptance:
#    "稽核日誌".
# Test type: validation (Q2 derivation).
# Active Pattern: NP-09 (audit log).
# ============================================================================
def test_fr88_deletion_logs_gdpr_deletion_event():
    user_id = "user-001"
    expected_audit_event = "gdpr_deletion"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-88: user_id sentinel must be 'user-001' (SRS FR-88 "
        f"GDPR audit-log probe); got {user_id!r}."
    )
    assert expected_audit_event == "gdpr_deletion", (
        "FR-88: expected_audit_event sentinel must be 'gdpr_deletion' "
        f"(SRS FR-88 audit-log event type); got "
        f"{expected_audit_event!r}."
    )

    # GREEN TODO: ``delete_user_data(user_id)`` MUST write at least one
    # entry to ``pii_audit_log`` with ``event_type = "gdpr_deletion"``.
    # GREEN must implement ``get_pii_audit_log(user_id, event_type)`` to
    # query the audit-log table so this test can verify the entry exists.
    del_result = delete_user_data(user_id=user_id)

    assert del_result is not None, (
        "FR-88: delete_user_data() must not return None."
    )
    assert isinstance(del_result, dict), (
        "FR-88: delete_user_data() must return a dict; "
        f"got type={type(del_result).__name__}."
    )

    # GREEN TODO: ``get_pii_audit_log(user_id, event_type)`` MUST return
    # a list of audit-log entries (dicts) matching the query.  After a GDPR
    # deletion, the list MUST be non-empty and contain at least one entry
    # with ``event_type == "gdpr_deletion"``.
    audit_entries = get_pii_audit_log(
        user_id=user_id, event_type=expected_audit_event
    )

    assert isinstance(audit_entries, list), (
        "FR-88: get_pii_audit_log() must return a list; "
        f"got type={type(audit_entries).__name__}."
    )
    assert len(audit_entries) > 0, (
        f"FR-88: after GDPR deletion, get_pii_audit_log("
        f"user_id={user_id!r}, event_type={expected_audit_event!r}) "
        f"MUST return at least one entry per SRS FR-88 '稽核日誌'; "
        f"got empty list."
    )

    # GREEN TODO: Every returned entry MUST have the expected event_type
    # and reference the correct user.
    for i, entry in enumerate(audit_entries):
        assert isinstance(entry, dict), (
            f"FR-88: audit log entry {i} must be a dict; "
            f"got {type(entry).__name__}."
        )
        assert entry.get("event_type") == expected_audit_event, (
            f"FR-88: audit log entry {i} event_type must be "
            f"{expected_audit_event!r}; got "
            f"{entry.get('event_type')!r}."
        )
        # GREEN TODO: ``user_id`` field MUST match the requested user.
        assert entry.get("user_id") == user_id, (
            f"FR-88: audit log entry {i} user_id must be {user_id!r}; "
            f"got {entry.get('user_id')!r}."
        )
        # GREEN TODO: ``timestamp`` field MUST be present (ISO 8601).
        assert "timestamp" in entry, (
            f"FR-88: audit log entry {i} MUST have 'timestamp' field; "
            f"got keys={sorted(entry.keys())!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-88: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert expected_audit_event == "gdpr_deletion", (
        f"FR-88: expected_audit_event sentinel must remain "
        f"'gdpr_deletion'; got {expected_audit_event!r}."
    )
