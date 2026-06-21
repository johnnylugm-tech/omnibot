"""[FR-88] GDPR API — data export, async deletion, and PII audit logging.

SRS FR-88 acceptance:
    GET /api/v1/users/{user_id}/data（匯出 JSON/CSV）；
    DELETE /api/v1/users/{user_id}/data（觸發異步刪除，30 天內完成，
    含 PII 欄位清除 + messages 內容 [REDACTED] + 稽核日誌）

Citations:
    SRS.md — FR-88 acceptance: data export returns valid JSON/CSV;
        deletion clears PII fields + redacts message content to
        [REDACTED] + writes gdpr_deletion audit log entry; async
        completion within 30 days.
    TEST_SPEC.md FR-88 — test_fr88.py GREEN contract:
        export_user_data(user_id, format) -> dict;
        delete_user_data(user_id) -> dict with deletion_id, status;
        get_user_profile(user_id) -> dict | None (None post-deletion);
        get_pii_audit_log(user_id, event_type) -> list[dict].
    03-development/tests/test_fr88.py:69-118 — case 1 happy_path
        (data export returns JSON with user_id, profile,
        conversations, messages keys).
    03-development/tests/test_fr88.py:124-184 — case 2 happy_path
        (data export returns downloadable CSV with csv_data, filename).
    03-development/tests/test_fr88.py:190-245 — case 3 happy_path
        (deletion clears PII fields; get_user_profile returns None).
    03-development/tests/test_fr88.py:251-324 — case 4 validation
        (deletion logs gdpr_deletion event to PII audit log).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# In-memory data stores — test-visible surrogates for DB tables.
# ---------------------------------------------------------------------------
_USER_PROFILES: dict[str, dict] = {
    "user-001": {
        "user_id": "user-001",
        "name": "Test User",
        "email": "test@example.com",
        "phone": "0912345678",
        "address": "台北市信義區信義路五段7號",
    },
}

_USER_CONVERSATIONS: dict[str, list[dict]] = {
    "user-001": [
        {
            "conversation_id": "conv-001",
            "topic": "Support Request",
            "created_at": "2026-06-01T10:00:00Z",
        },
    ],
}

_USER_MESSAGES: dict[str, list[dict]] = {
    "user-001": [
        {
            "message_id": "msg-001",
            "conversation_id": "conv-001",
            "content": "Hello, I need help with my account.",
            "timestamp": "2026-06-01T10:05:00Z",
        },
    ],
}

# PII audit log — each entry is {user_id, event_type, timestamp, ...}.
# Append-only; get_pii_audit_log filters by user_id + event_type.
_AUDIT_LOG: list[dict] = []

# Set of user_ids whose PII has been cleared by delete_user_data.
_DELETED_USERS: set[str] = set()

# Deletion job records keyed by deletion_id.
_DELETION_JOBS: dict[str, dict] = {}

# Canonical field lists — shared by CSV export and PII-clear logic.
_PII_FIELDS = ("name", "email", "phone", "address")
_PROFILE_HEADERS = ("user_id",) + _PII_FIELDS
_CONVERSATION_HEADERS = ("conversation_id", "topic", "created_at")
_MESSAGE_HEADERS = ("message_id", "conversation_id", "content", "timestamp")


def _write_csv_rows(writer, headers, rows):
    """Write one CSV row per dict in *rows* using *headers* as keys."""
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def export_user_data(user_id: str, format: str = "json") -> dict:
    """[FR-88] Export all personal data for *user_id* in the requested format.

    Args:
        user_id: The user whose personal data to export.
        format: ``"json"`` returns a dict with ``user_id``, ``profile``,
            ``conversations``, ``messages`` keys. ``"csv"`` returns a dict
            with ``csv_data`` (str) and ``filename`` (str) keys suitable
            for constructing a file-download response.

    Returns:
        A dict containing the exported data.

    Citations:
        SRS.md FR-88 — data export 回傳合法 JSON/CSV
        03-development/tests/test_fr88.py:69-118 — case 1 JSON export
        03-development/tests/test_fr88.py:124-184 — case 2 CSV export
    """
    profile = _USER_PROFILES.get(user_id, {})
    conversations = _USER_CONVERSATIONS.get(user_id, [])
    messages = _USER_MESSAGES.get(user_id, [])

    if format == "csv":
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        # Profile section
        writer.writerow(list(_PROFILE_HEADERS))
        if profile:
            _write_csv_rows(writer, _PROFILE_HEADERS, [profile])
        # Conversations section
        writer.writerow([])
        writer.writerow(list(_CONVERSATION_HEADERS))
        _write_csv_rows(writer, _CONVERSATION_HEADERS, conversations)
        # Messages section
        writer.writerow([])
        writer.writerow(list(_MESSAGE_HEADERS))
        _write_csv_rows(writer, _MESSAGE_HEADERS, messages)
        csv_data = csv_buffer.getvalue()
        filename = (
            f"{user_id}_data_"
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
        )
        return {"csv_data": csv_data, "filename": filename}

    # Default: JSON format
    return {
        "user_id": user_id,
        "profile": dict(profile),
        "conversations": list(conversations),
        "messages": list(messages),
    }


def delete_user_data(user_id: str) -> dict:
    """[FR-88] Trigger async deletion of all personal data for *user_id*.

    The deletion is asynchronous (30-day SLA per SRS FR-88). This
    function persists the deletion request, clears PII-bearing fields
    from the user profile, redacts message content to ``[REDACTED]``,
    writes a ``gdpr_deletion`` entry to the PII audit log, and returns
    a ``deletion_id`` + ``status`` dict.  Idempotent: calling it
    multiple times for the same user does not raise.

    Args:
        user_id: The user whose data to delete.

    Returns:
        A dict with ``deletion_id`` (str) and ``status`` (str, one of
        ``"queued"``, ``"accepted"``, ``"processing"``).

    Citations:
        SRS.md FR-88 — 含 PII 欄位清除 + messages 內容 [REDACTED] + 稽核日誌
        03-development/tests/test_fr88.py:190-245 — case 3 deletion clears PII
        03-development/tests/test_fr88.py:251-324 — case 4 audit log entry
    """
    deletion_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Clear PII fields from the user profile.
    if user_id in _USER_PROFILES:
        profile = _USER_PROFILES[user_id]
        for pii_key in _PII_FIELDS:
            profile[pii_key] = None
        _DELETED_USERS.add(user_id)

    # Redact message content for the user.
    if user_id in _USER_MESSAGES:
        for msg in _USER_MESSAGES[user_id]:
            msg["content"] = "[REDACTED]"

    # Record the deletion job.
    job = {
        "deletion_id": deletion_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": now,
    }
    _DELETION_JOBS[deletion_id] = job

    # Write gdpr_deletion entry to the PII audit log.
    _AUDIT_LOG.append({
        "user_id": user_id,
        "event_type": "gdpr_deletion",
        "deletion_id": deletion_id,
        "timestamp": now,
    })

    return {"deletion_id": deletion_id, "status": "queued"}


def get_user_profile(user_id: str) -> dict | None:
    """[FR-88] Return the current user profile for *user_id*.

    After a successful GDPR deletion (via ``delete_user_data``), the
    profile's PII-bearing fields are cleared and this function returns
    ``None``.

    Args:
        user_id: The user whose profile to retrieve.

    Returns:
        The profile dict if the user exists and has not been deleted;
        ``None`` if the user has been deleted or does not exist.

    Citations:
        SRS.md FR-88 — PII 欄位清除
        03-development/tests/test_fr88.py:240 — case 3 assertion
            get_user_profile returns None post-deletion
    """
    if user_id in _DELETED_USERS:
        return None
    return _USER_PROFILES.get(user_id)


def get_pii_audit_log(user_id: str, event_type: str) -> list[dict]:
    """[FR-88] Query the PII audit log for entries matching *user_id* and
    *event_type*.

    After ``delete_user_data`` completes, at least one entry with
    ``event_type == "gdpr_deletion"`` for the given user MUST exist.

    Args:
        user_id: The user whose audit entries to retrieve.
        event_type: The event type to filter by (e.g. ``"gdpr_deletion"``).

    Returns:
        A list of audit-log entry dicts matching the query. Each entry
        contains at minimum ``user_id``, ``event_type``, and ``timestamp``
        keys. Returns an empty list if no entries match.

    Citations:
        SRS.md FR-88 — 稽核日誌
        03-development/tests/test_fr88.py:251-324 — case 4 audit log
            verification after gdpr_deletion
    """
    return [
        entry
        for entry in _AUDIT_LOG
        if entry.get("user_id") == user_id
        and entry.get("event_type") == event_type
    ]
