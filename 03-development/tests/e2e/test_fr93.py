"""TDD-RED: failing tests for FR-93 — Right of Access + Portability (data export
with emotions section + CSV downloadable).

Spec source: 02-architecture/TEST_SPEC.md (FR-93)
SRS source : SRS.md FR-93

Acceptance criteria (from SRS FR-93):
    GET /api/v1/users/{user_id}/data 回傳結構化 JSON（含所有個人資料）；
    支援 CSV 格式

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-93 (SRS.md) requires:
#   1. ``GET /api/v1/users/{user_id}/data`` returns structured JSON containing
#      ALL personal data sections: ``profile``, ``messages``, and ``emotions``
#      (the FR-88 export already covers profile + conversations + messages;
#      FR-93 adds the emotions section and makes "all personal data" the
#      completeness requirement).
#   2. When ``format="csv"`` is requested, the endpoint MUST produce a
#      downloadable CSV with ``content_type`` set to ``text/csv``.
#
# GREEN contract pinned by this spec:
#   - ``app.api.gdpr.export_user_data(user_id, format) -> dict`` MUST
#     include an ``emotions`` key in the JSON result, containing the user's
#     emotional data history.
#   - When ``format="csv"`` is used, the returned dict MUST include a
#     ``content_type`` key with value ``"text/csv"`` (in addition to
#     the existing ``csv_data`` and ``filename`` keys from FR-88).
#
# The imports below are unguarded: pytest will fail with an assertion or
# missing-key error because ``export_user_data`` currently returns
# ``profile``, ``conversations``, ``messages`` — NOT ``emotions``. That is
# the valid RED signal — GREEN adds the emotions section and CSV
# ``content_type`` to make every assertion hold.
# ---------------------------------------------------------------------------
from app.admin.gdpr import export_user_data


# ============================================================================
# 1. Data export MUST contain ALL personal data sections: profile, messages,
#    and emotions (happy_path).
#
# Spec input: user_id="user-001";
#            expected_sections="profile,messages,emotions".
# Spec sub-assertion: fr93-ok: result is not None.
# SRS FR-93 acceptance: "回傳完整個人資料；格式符合 JSON"
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr93_export_contains_all_personal_data():
    user_id = "user-001"
    expected_sections = "profile,messages,emotions"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-93: user_id sentinel must be 'user-001' (SRS FR-93 data "
        f"export probe); got {user_id!r}."
    )
    assert expected_sections == "profile,messages,emotions", (
        "FR-93: expected_sections sentinel must be "
        "'profile,messages,emotions' (SRS FR-93 requires all personal "
        f"data sections); got {expected_sections!r}."
    )

    # GREEN TODO: ``export_user_data(user_id, format='json')`` MUST return a
    # dict containing ALL personal data sections: ``profile``, ``messages``,
    # and ``emotions``. The FR-88 implementation already returns ``profile``,
    # ``conversations``, and ``messages``. FR-93 adds the mandatory
    # ``emotions`` key containing the user's emotion history data.
    result = export_user_data(user_id=user_id)

    # fr93-ok: result is not None (predicate for case 1).
    assert result is not None, (
        "fr93-ok predicate: export_user_data() must not return None; the "
        "data export endpoint must always produce a response."
    )

    assert isinstance(result, dict), (
        "FR-93: export_user_data() must return a dict with personal data "
        f"sections; got type={type(result).__name__}."
    )

    # Every expected section MUST appear in the result.
    required_sections = expected_sections.split(",")
    for section in required_sections:
        assert section in result, (
            f"FR-93: export_user_data() result MUST contain section "
            f"{section!r} per SRS FR-93 '含所有個人資料'; got "
            f"keys={sorted(result.keys())!r}."
        )

    # profile section type contract — must be a dict.
    assert isinstance(result["profile"], dict), (
        "FR-93: 'profile' section must be a dict containing user profile "
        f"data; got {type(result['profile']).__name__}."
    )

    # messages section type contract — must be a list.
    assert isinstance(result["messages"], list), (
        "FR-93: 'messages' section must be a list of user messages; got "
        f"{type(result['messages']).__name__}."
    )

    # emotions section type contract — must be a list.
    assert isinstance(result["emotions"], list), (
        "FR-93: 'emotions' section must be a list of user emotion history "
        f"entries; got {type(result['emotions']).__name__}."
    )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-93: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert expected_sections == "profile,messages,emotions", (
        f"FR-93: expected_sections sentinel must remain "
        f"'profile,messages,emotions'; got {expected_sections!r}."
    )


# ============================================================================
# 2. CSV export MUST produce a downloadable file with content_type "text/csv"
#    (happy_path).
#
# Spec input: user_id="user-001"; format="csv";
#            expected_content_type="text/csv".
# SRS FR-93 acceptance: "CSV 可下載"
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr93_csv_format_downloadable():
    user_id = "user-001"
    format_ = "csv"
    expected_content_type = "text/csv"

    # Defence-in-depth: pin the spec sentinel strings.
    assert user_id == "user-001", (
        "FR-93: user_id sentinel must be 'user-001' (SRS FR-93 CSV "
        f"export probe); got {user_id!r}."
    )
    assert format_ == "csv", (
        "FR-93: format sentinel must be 'csv' (SRS FR-93 CSV format "
        f"probe); got {format_!r}."
    )
    assert expected_content_type == "text/csv", (
        "FR-93: expected_content_type sentinel must be 'text/csv' (SRS "
        f"FR-93 CSV downloadable contract); got {expected_content_type!r}."
    )

    # GREEN TODO: ``export_user_data(user_id, format='csv')`` MUST return a
    # dict that includes a ``content_type`` key set to ``"text/csv"``. The
    # FR-88 implementation already returns ``csv_data`` (str) and
    # ``filename`` (str) for the CSV path. FR-93 adds the ``content_type``
    # key so callers can set the correct HTTP Content-Type header for file
    # download. The ``csv_data`` field MUST contain valid CSV with headers
    # for ALL personal data sections (profile, messages, emotions).
    result = export_user_data(user_id=user_id, format=format_)

    assert result is not None, (
        "FR-93: export_user_data() must not return None for CSV format; "
        "the data export endpoint must always produce a response."
    )

    assert isinstance(result, dict), (
        "FR-93: export_user_data() with format='csv' must return a dict; "
        f"got type={type(result).__name__}."
    )

    # The CSV result MUST contain csv_data (the CSV payload string).
    assert "csv_data" in result, (
        "FR-93: CSV export result MUST contain 'csv_data' key with the "
        f"CSV payload string; got keys={sorted(result.keys())!r}."
    )
    assert isinstance(result["csv_data"], str), (
        "FR-93: 'csv_data' must be a str containing the CSV payload; got "
        f"{type(result['csv_data']).__name__}."
    )
    assert len(result["csv_data"]) > 0, (
        "FR-93: 'csv_data' must be non-empty for a valid user export."
    )

    # The CSV result MUST contain filename for Content-Disposition header.
    assert "filename" in result, (
        "FR-93: CSV export result MUST contain 'filename' key for the "
        f"Content-Disposition header; got keys={sorted(result.keys())!r}."
    )
    assert isinstance(result["filename"], str), (
        "FR-93: 'filename' must be a str suitable for download; got "
        f"{type(result['filename']).__name__}."
    )

    # GREEN TODO: ``export_user_data`` with format='csv' MUST include a
    # ``content_type`` key in the returned dict with value ``"text/csv"``.
    # This key tells the HTTP response layer to set
    # ``Content-Type: text/csv`` for proper file download handling.
    assert "content_type" in result, (
        "FR-93: CSV export result MUST contain 'content_type' key to set "
        "the HTTP Content-Type header for file download per SRS FR-93 "
        f"'CSV 可下載'; got keys={sorted(result.keys())!r}."
    )
    assert result["content_type"] == expected_content_type, (
        f"FR-93: content_type must be 'text/csv' for CSV export; got "
        f"{result['content_type']!r}."
    )
    assert isinstance(result["content_type"], str), (
        "FR-93: 'content_type' must be a str; got "
        f"{type(result['content_type']).__name__}."
    )

    # Sentinels MUST be preserved per spec.
    assert user_id == "user-001", (
        f"FR-93: user_id sentinel must remain 'user-001'; got {user_id!r}."
    )
    assert format_ == "csv", (
        f"FR-93: format sentinel must remain 'csv'; got {format_!r}."
    )
    assert expected_content_type == "text/csv", (
        f"FR-93: expected_content_type sentinel must remain 'text/csv'; "
        f"got {expected_content_type!r}."
    )
