"""TDD-RED: failing tests for FR-100 — 多媒體處理
(ClamAV fail-secure + 10MB limit + p95 <500ms).

Spec source: 02-architecture/TEST_SPEC.md (FR-100)
SRS source : SRS.md FR-100 (Module 24: 多媒體處理 — image/sticker/location/file)

# pyright: reportAttributeAccessIssue=false
# Test uses duck-typing via hasattr/getattr on MediaResult; attribute checks are
# the contract under test, so generic `object` typing is intentional.

Acceptance criteria (from SRS FR-100):
    image     : Image → auto_escalate（不支援圖片理解）.
    sticker   : Sticker → ignore + 固定回覆「請用文字描述您的問題」+ log.
    location  : Location → 解析經緯度，附帶於 conversation context.
    file      : File → malware scan (ClamAV) + size_limit 10MB +
                allowed_types[pdf,docx,xlsx,csv,txt] → auto_escalate.
    fail-secure: ClamAV 失敗 → 拒絕文件上傳 + 回傳 503 FILE_SCAN_UNAVAILABLE.
    p95       : ClamAV 掃描 p95 < 500ms.
    timeout   : ClamAV scan timeout → 終止該次掃描 (fail-secure).

The eight TEST_SPEC cases (function names MUST match exactly):
    1. test_fr100_image_auto_escalate
         Inputs: message_type="image"; expected_action="auto_escalate"
         Type  : happy_path
    2. test_fr100_sticker_fixed_reply
         Inputs: message_type="sticker"; expected_reply="請用文字描述您的問題"
         Type  : happy_path
    3. test_fr100_location_extracts_coordinates
         Inputs: message_type="location"; lat="25.033"; lng="121.565"
         Type  : happy_path
    4. test_fr100_file_above_10mb_rejected
         Inputs: file_size_mb="11"; limit_mb="10"; expected_status="rejected"
         Type  : boundary
    5. test_fr100_clamav_down_503_file_scan_unavailable
         Inputs: clamav_status="down"; expected_status="503";
                 expected_error="FILE_SCAN_UNAVAILABLE"
         Type  : fault_injection
    6. test_fr100_clamav_scan_p95_under_500ms
         Inputs: file_type="pdf"; p95_limit_ms="500"
         Type  : nfr_pattern
    7. test_fr100_clamav_timeout_terminates_scan
         Inputs: scan_timeout_ms="500"; clamav_delay_ms="600";
                 expected_terminated="true"
         Type  : fault_injection
    8. test_fr100_must_not_allow_file_when_clamav_unavailable
         Inputs: clamav_status="unavailable"; expected_allowed="false"
         Type  : negative_constraint

Sub-assertion (per TEST_SPEC):
    fr100-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test isolation — ClamAV scans are real subprocess I/O. The GREEN
# implementation MUST expose an injection seam (constructor arg or class
# attribute) so the scanner can be swapped for an in-memory stub in unit
# tests. This autouse fixture is a no-op during RED (the import below
# raises before the fixture runs) and patches the seam once GREEN has
# landed.
#
# GREEN must:
#   - Define ``ClamAVScanner`` accepting an injected ``subprocess_runner``
#     callable in __init__ (default: subprocess.run). Replace real I/O
#     by passing a stub that returns canned (returncode, stdout, stderr).
#   - Provide a ``force_status(status: str) -> None`` hook so tests can
#     drive the scanner into "down" / "unavailable" fault-injection
#     states without spawning an actual clamd.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_clamav_subprocess(monkeypatch):
    """Prevent real ClamAV subprocess I/O during unit tests.

    Stub ``subprocess.run`` / ``subprocess.Popen`` so a GREEN that
    forgets to inject the runner still cannot escape into real I/O.
    GREEN is expected to inject a runner explicitly; this fixture is
    the second line of defence.
    """
    import subprocess

    def _fake_run(*args, **kwargs):
        # Default stub: clean (no malware detected), exit 0.
        class _Result:
            returncode = 0
            stdout = b"OK\n"
            stderr = b""

        return _Result()

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=False)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: _fake_run(), raising=False
    )
    yield


# ---------------------------------------------------------------------------
# Source under test — ``MediaPipeline`` / ``ClamAVScanner`` are intentionally
# NOT YET exported by ``app.services.media``. The imports below are
# unguarded: pytest MUST fail with Collection Error (Exit Code 2) because
# the module does not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/services/media.py`` exporting the following public
# surface (the exact shape is GREEN's choice so long as these names and
# behaviours are observable):
#
#   - Canonical configuration constants
#       STICKER_FIXED_REPLY    = "請用文字描述您的問題"
#       FILE_SIZE_LIMIT_MB     = 10
#       ALLOWED_FILE_TYPES     = frozenset({"pdf", "docx", "xlsx", "csv", "txt"})
#       CLAMAV_SCAN_P95_LIMIT_MS = 500     # NFR-38 / SRS FR-100 p95 < 500ms
#       CLAMAV_SCAN_TIMEOUT_MS   = 500     # NP-15 scan timeout
#       FILE_SCAN_UNAVAILABLE_ERROR = "FILE_SCAN_UNAVAILABLE"
#       FILE_SCAN_HTTP_503         = 503
#       MEDIA_ACTION_AUTO_ESCALATE  = "auto_escalate"
#       MEDIA_ACTION_STICKER_REPLY  = "sticker_reply"
#       MEDIA_ACTION_FILE_REJECTED  = "file_rejected"
#       MEDIA_ACTION_LOCATION_CTX   = "location_context"
#       CLAMAV_STATUS_DOWN          = "down"
#       CLAMAV_STATUS_UNAVAILABLE   = "unavailable"
#       CLAMAV_STATUS_OK            = "ok"
#
#   - ClamAVScanner
#       External-process gateway. Required attributes / methods:
#           __init__(subprocess_runner=None, timeout_ms=500, p95_limit_ms=500)
#               Store the runner (default subprocess.run) and the timeout
#               / p95-limit budgets. Tests will inject a stub runner so no
#               real clamd is spawned.
#           scan(file_bytes: bytes, file_type: str) -> ClamAVScanResult
#               Run a scan with timeout enforcement. On real timeout the
#               scan MUST be terminated and ``ClamAVScanResult.terminated``
#               MUST be True (fail-secure: never return "clean" on a
#               timed-out scan). On any subprocess error the result MUST
#               report ``status="unavailable"`` and ``terminated=True``.
#           scan_p95(file_type: str, samples: int = 100) -> float
#               Run ``samples`` synthetic scans and return the observed
#               p95 latency in milliseconds. The contract for FR-100 is
#               that the returned value is < CLAMAV_SCAN_P95_LIMIT_MS
#               when the injected runner is fast (e.g. returns
#               instantly).
#           is_available() -> bool
#               True iff the scanner can talk to clamd right now. False
#               when ``force_status("down")`` / ``force_status
#               ("unavailable")`` has been called.
#           force_status(status: str) -> None
#               Drive the scanner into a fault-injection state. GREEN
#               must accept "down", "unavailable", "ok".
#
#   - ClamAVScanResult
#       Required attributes / methods:
#           status:     str   ("ok" / "infected" / "unavailable" / "timeout")
#           terminated: bool  (True iff the scan was killed by timeout)
#           p95_ms:     float (latency observed in ms)
#
#   - MediaResult
#       Result of a media pipeline decision. Required attributes /
#       methods:
#           action:      str    ("auto_escalate" / "sticker_reply" /
#                                "location_context" / "file_rejected")
#           status:      str | None   ("rejected" / "503" / None)
#           error:       str | None   ("FILE_SCAN_UNAVAILABLE" / None)
#           reply:       str | None   (the fixed sticker reply text)
#           coordinates: dict | None  ({"lat": float, "lng": float})
#           is_allowed:  bool | None  (file-allow gate result)
#
#   - MediaPipeline
#       Top-level dispatcher. Required attributes / methods:
#           __init__(clamav_scanner: ClamAVScanner | None = None)
#               If ``clamav_scanner`` is None, construct a default
#               ``ClamAVScanner()``. If provided, use the injected
#               scanner verbatim (the seam GREEN must expose).
#           process_image() -> MediaResult
#               Image is unsupported → action="auto_escalate".
#           process_sticker() -> MediaResult
#               Sticker → action="sticker_reply", reply=
#               STICKER_FIXED_REPLY.
#           process_location(lat: float, lng: float) -> MediaResult
#               Extract lat/lng into MediaResult.coordinates and route
#               into the location_context branch.
#           process_file(file_size_mb: float, file_type: str,
#                        file_bytes: bytes = b"") -> MediaResult
#               Enforce 10MB limit + allowed_types + ClamAV. Returns
#               MediaResult(action="auto_escalate") on success, or
#               MediaResult(action="file_rejected", status="rejected")
#               when size > 10MB, or MediaResult(action="file_rejected",
#               status="503", error="FILE_SCAN_UNAVAILABLE") when
#               ClamAV is down/unavailable.
#           is_file_allowed(file_size_mb: float, file_type: str) -> bool
#               Pre-flight check used by the API layer to gate uploads.
#               MUST be False when file_size_mb > FILE_SIZE_LIMIT_MB OR
#               file_type is not in ALLOWED_FILE_TYPES OR the injected
#               ClamAVScanner reports is_available() == False.
#
# The tests below intentionally avoid any real ClamAV / subprocess I/O —
# they exercise the MediaPipeline + ClamAVScanner abstraction in
# isolation, which is the canonical unit-test shape for FR-100.
# ---------------------------------------------------------------------------
# Re-export the constants so the tests can assert against the same values
# the production code uses (and so the harness sees the same names in the
# import surface as the green implementation must expose).
from app.services.media import (  # noqa: E402,F401
    ALLOWED_FILE_TYPES,
    CLAMAV_SCAN_P95_LIMIT_MS,
    CLAMAV_SCAN_TIMEOUT_MS,
    CLAMAV_STATUS_DOWN,
    CLAMAV_STATUS_OK,
    CLAMAV_STATUS_UNAVAILABLE,
    FILE_SCAN_HTTP_503,
    FILE_SCAN_UNAVAILABLE_ERROR,
    FILE_SIZE_LIMIT_MB,
    MEDIA_ACTION_AUTO_ESCALATE,
    MEDIA_ACTION_FILE_REJECTED,
    MEDIA_ACTION_LOCATION_CTX,
    MEDIA_ACTION_STICKER_REPLY,
    STICKER_FIXED_REPLY,
    ClamAVScanner,
    ClamAVScanResult,
    MediaPipeline,
    MediaResult,
)


# ---------------------------------------------------------------------------
# 1. An image message triggers auto_escalate (happy_path).
#
# Spec input: message_type="image"; expected_action="auto_escalate".
# SRS FR-100: "Image → auto_escalate（不支援圖片理解）".
# A regression that routed an image to LLM vision would silently expand
# the supported surface and break the FR's "不支援" guarantee; a
# regression that dropped images silently would break the escalation
# handoff contract and leave image-only users without any response.
# ---------------------------------------------------------------------------
def test_fr100_image_auto_escalate():
    # Spec input literals — also used as trigger values for the fr100-ok
    # sub-assertion guard.
    message_type = "image"
    expected_action = "auto_escalate"  # spec string sentinel

    # GREEN TODO: ``MEDIA_ACTION_AUTO_ESCALATE`` MUST be exported from
    # ``app.services.media`` and MUST equal "auto_escalate" — the
    # canonical image-routing identifier mandated by FR-100.
    assert MEDIA_ACTION_AUTO_ESCALATE == "auto_escalate", (
        f"FR-100 MEDIA_ACTION_AUTO_ESCALATE must be 'auto_escalate'; "
        f"got {MEDIA_ACTION_AUTO_ESCALATE!r}"
    )

    # GREEN TODO: ``MediaPipeline()`` constructed with no arguments MUST
    # expose the FR-100 image entry point. GREEN may spell the method
    # however it likes so long as it accepts no image-specific args and
    # returns a ``MediaResult`` whose ``action`` records the routing
    # decision.
    pipeline = MediaPipeline()
    assert hasattr(pipeline, "process_image") and callable(
        pipeline.process_image
    ), (
        "FR-100 MediaPipeline must expose "
        "``process_image() -> MediaResult``"
    )

    result = pipeline.process_image()  # bind for the fr100-ok predicate

    # Spec fr100-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input literal
    # (message_type="image"). The harness parser requires a single
    # VAR == c literal in the trigger block — compound conditions are
    # not matched. So we wrap the predicate in a narrow guard on the
    # spec's first case-1 trigger variable.
    if message_type == "image":
        assert result is not None, (
            "fr100-ok predicate: result must not be None"
        )

    # Public surface contract: ``MediaResult`` MUST expose ``action``
    # so the harness can verify the routing decision. GREEN may spell
    # it as an attribute or accessor; both forms are checked below.
    assert hasattr(result, "action"), (
        "FR-100 MediaResult must expose ``action``"
    )
    observed_action = (
        result.action()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "action", None))
        else result.action  # type: ignore[reportAttributeAccessIssue]
    )

    # The action MUST be "auto_escalate" — the FR's explicit
    # "expected_action='auto_escalate'" guarantee for image messages.
    if expected_action == "auto_escalate":
        assert observed_action == "auto_escalate", (
            f"FR-100 image message must auto_escalate; got "
            f"action={observed_action!r}"
        )


# ---------------------------------------------------------------------------
# 2. A sticker message yields the canonical fixed reply (happy_path).
#
# Spec input: message_type="sticker";
#             expected_reply="請用文字描述您的問題".
# SRS FR-100: "Sticker → ignore + 固定回覆「請用文字描述您的問題」+ log
# sticker 頻率". A regression that routed stickers to the LLM would burn
# tokens on a non-text payload and break the FR's "ignore" invariant; a
# regression that replied with anything other than the canonical Chinese
# text would break the user-facing contract.
# ---------------------------------------------------------------------------
def test_fr100_sticker_fixed_reply():
    # Spec input literals.
    expected_reply = "請用文字描述您的問題"  # spec string sentinel

    # GREEN TODO: ``STICKER_FIXED_REPLY`` MUST be exported and MUST equal
    # "請用文字描述您的問題" — the canonical Chinese fixed reply mandated
    # by FR-100.
    assert STICKER_FIXED_REPLY == "請用文字描述您的問題", (
        f"FR-100 STICKER_FIXED_REPLY must be '請用文字描述您的問題'; "
        f"got {STICKER_FIXED_REPLY!r}"
    )

    # GREEN TODO: ``MEDIA_ACTION_STICKER_REPLY`` MUST equal
    # "sticker_reply" — the canonical sticker-routing identifier.
    assert MEDIA_ACTION_STICKER_REPLY == "sticker_reply", (
        f"FR-100 MEDIA_ACTION_STICKER_REPLY must be 'sticker_reply'; "
        f"got {MEDIA_ACTION_STICKER_REPLY!r}"
    )

    pipeline = MediaPipeline()
    assert hasattr(pipeline, "process_sticker") and callable(
        pipeline.process_sticker
    ), (
        "FR-100 MediaPipeline must expose "
        "``process_sticker() -> MediaResult``"
    )

    result = pipeline.process_sticker()

    assert result is not None, (
        "FR-100 process_sticker() must return a MediaResult; got None"
    )

    # The action MUST be "sticker_reply" — the FR's sticker-routing
    # branch.
    observed_action = (
        result.action()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "action", None))
        else result.action  # type: ignore[reportAttributeAccessIssue]
    )
    assert observed_action == "sticker_reply", (
        f"FR-100 sticker must route to 'sticker_reply'; got "
        f"action={observed_action!r}"
    )

    # The reply MUST be the canonical fixed text — the FR's
    # "expected_reply" guarantee. A GREEN that localized or
    # parameterized the reply (e.g. English translation) would break
    # the user-facing contract the SRS pins to the FR.
    if expected_reply == "請用文字描述您的問題":
        assert hasattr(result, "reply"), (
            "FR-100 MediaResult must expose ``reply``"
        )
        observed_reply = (
            result.reply()  # type: ignore[reportAttributeAccessIssue]
            if callable(getattr(result, "reply", None))
            else result.reply  # type: ignore[reportAttributeAccessIssue]
        )
        assert observed_reply == "請用文字描述您的問題", (
            f"FR-100 sticker reply must be '請用文字描述您的問題'; got "
            f"{observed_reply!r}"
        )


# ---------------------------------------------------------------------------
# 3. A location message extracts latitude + longitude into the context
#    (happy_path).
#
# Spec input: message_type="location"; lat="25.033"; lng="121.565".
# SRS FR-100: "Location → 解析經緯度，附帶於 conversation context". A
# regression that dropped the coordinates would lose the most important
# piece of data on a location message and break every "near me" answer;
# a regression that swapped lat/lng would misroute the user to the
# wrong hemisphere.
# ---------------------------------------------------------------------------
def test_fr100_location_extracts_coordinates():
    # Spec input literals.
    lat = "25.033"  # spec string sentinel (Taipei 101)
    lng = "121.565"

    # GREEN TODO: ``MEDIA_ACTION_LOCATION_CTX`` MUST equal
    # "location_context" — the canonical location-routing identifier.
    assert MEDIA_ACTION_LOCATION_CTX == "location_context", (
        f"FR-100 MEDIA_ACTION_LOCATION_CTX must be 'location_context'; "
        f"got {MEDIA_ACTION_LOCATION_CTX!r}"
    )

    pipeline = MediaPipeline()
    assert hasattr(pipeline, "process_location") and callable(
        pipeline.process_location
    ), (
        "FR-100 MediaPipeline must expose "
        "``process_location(lat: float, lng: float) -> MediaResult``"
    )

    # Spec inputs arrive as strings; the pipeline MUST coerce to float
    # so downstream DST / RAG layers can do arithmetic comparisons.
    result = pipeline.process_location(float(lat), float(lng))

    assert result is not None, (
        "FR-100 process_location() must return a MediaResult; got None"
    )

    # The action MUST be "location_context" — the FR's location-routing
    # branch.
    observed_action = (
        result.action()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "action", None))
        else result.action  # type: ignore[reportAttributeAccessIssue]
    )
    assert observed_action == "location_context", (
        f"FR-100 location must route to 'location_context'; got "
        f"action={observed_action!r}"
    )

    # The coordinates MUST be preserved on the MediaResult as a dict
    # shaped ``{"lat": float, "lng": float}`` so the conversation
    # context can carry them downstream.
    assert hasattr(result, "coordinates"), (
        "FR-100 MediaResult must expose ``coordinates``"
    )
    observed_coords = (
        result.coordinates()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "coordinates", None))
        else result.coordinates  # type: ignore[reportAttributeAccessIssue]
    )
    assert observed_coords is not None, (
        "FR-100 location coordinates must not be None"
    )
    assert isinstance(observed_coords, dict), (
        f"FR-100 coordinates must be a dict; got "
        f"{type(observed_coords).__name__}"
    )

    # The lat MUST match the input exactly (no truncation / rounding /
    # swap). Use a tolerance to allow float parsing without losing
    # precision (Taipei 101 → 25.0330, 121.5654).
    assert "lat" in observed_coords, (
        f"FR-100 coordinates must contain 'lat'; got "
        f"{list(observed_coords.keys())!r}"
    )
    assert "lng" in observed_coords, (
        f"FR-100 coordinates must contain 'lng'; got "
        f"{list(observed_coords.keys())!r}"
    )
    assert abs(float(observed_coords["lat"]) - 25.033) < 1e-6, (
        f"FR-100 lat must equal 25.033; got "
        f"{observed_coords['lat']!r}"
    )
    assert abs(float(observed_coords["lng"]) - 121.565) < 1e-6, (
        f"FR-100 lng must equal 121.565; got "
        f"{observed_coords['lng']!r}"
    )


# ---------------------------------------------------------------------------
# 4. A file larger than 10MB is rejected (boundary).
#
# Spec input: file_size_mb="11"; limit_mb="10";
#             expected_status="rejected".
# SRS FR-100: "File → malware scan (ClamAV) + size_limit 10MB +
# allowed_types[...] → auto_escalate". A regression that accepted files
# larger than 10MB would risk OOM in the ClamAV subprocess and break the
# resource-budget guarantee; a regression that returned the wrong status
# string would break the API-layer rejection branch.
# ---------------------------------------------------------------------------
def test_fr100_file_above_10mb_rejected():
    # Spec input literals.
    file_size_mb = "11"
    expected_status = "rejected"  # spec string sentinel

    # GREEN TODO: ``FILE_SIZE_LIMIT_MB`` MUST equal 10 — the SRS FR-100
    # hard ceiling for file uploads.
    assert FILE_SIZE_LIMIT_MB == 10, (
        f"FR-100 FILE_SIZE_LIMIT_MB must be 10; got {FILE_SIZE_LIMIT_MB!r}"
    )

    # Companion invariant: ``ALLOWED_FILE_TYPES`` MUST contain the five
    # canonical file types mandated by the SRS FR-100 file leg. A GREEN
    # that omitted "pdf" or added "exe" would break the FR's allow-list
    # in either direction (false-negative: legitimate doc rejected;
    # false-positive: executable accepted).
    assert "pdf" in ALLOWED_FILE_TYPES, (
        f"FR-100 ALLOWED_FILE_TYPES must contain 'pdf'; got "
        f"{sorted(ALLOWED_FILE_TYPES)!r}"
    )
    for required_type in ("pdf", "docx", "xlsx", "csv", "txt"):
        assert required_type in ALLOWED_FILE_TYPES, (
            f"FR-100 ALLOWED_FILE_TYPES must contain {required_type!r}; "
            f"got {sorted(ALLOWED_FILE_TYPES)!r}"
        )

    # GREEN TODO: ``MEDIA_ACTION_FILE_REJECTED`` MUST equal
    # "file_rejected" — the canonical file-rejection identifier.
    assert MEDIA_ACTION_FILE_REJECTED == "file_rejected", (
        f"FR-100 MEDIA_ACTION_FILE_REJECTED must be 'file_rejected'; "
        f"got {MEDIA_ACTION_FILE_REJECTED!r}"
    )

    pipeline = MediaPipeline()
    assert hasattr(pipeline, "process_file") and callable(
        pipeline.process_file
    ), (
        "FR-100 MediaPipeline must expose "
        "``process_file(file_size_mb, file_type, file_bytes) -> "
        "MediaResult``"
    )

    # Inject a never-used scanner so the size-limit rejection happens
    # BEFORE ClamAV is invoked (the FR's order: size → type → scan).
    scanner = ClamAVScanner(subprocess_runner=lambda *a, **kw: None)
    pipeline = MediaPipeline(clamav_scanner=scanner)

    result = pipeline.process_file(
        file_size_mb=float(file_size_mb),  # 11.0 > 10.0 → reject
        file_type="pdf",
        file_bytes=b"%PDF-stub",
    )

    assert result is not None, (
        "FR-100 process_file() must return a MediaResult; got None"
    )

    # The action MUST be "file_rejected" — the FR's size-limit branch.
    observed_action = (
        result.action()
        if callable(getattr(result, "action", None))
        else result.action
    )
    assert observed_action == "file_rejected", (
        f"FR-100 file > 10MB must route to 'file_rejected'; got "
        f"action={observed_action!r}"
    )

    # The status MUST be "rejected" — the FR's
    # "expected_status='rejected'" guarantee. A GREEN that returned
    # status="503" for the size-limit branch would conflate the size
    # rejection with the ClamAV-down branch and break the API-layer
    # routing.
    if expected_status == "rejected":
        observed_status = (
            result.status()
            if callable(getattr(result, "status", None))
            else result.status
        )
        assert observed_status == "rejected", (
            f"FR-100 oversized file must report status='rejected'; got "
            f"{observed_status!r}"
        )


# ---------------------------------------------------------------------------
# 5. ClamAV-down returns HTTP 503 FILE_SCAN_UNAVAILABLE (fault_injection).
#
# Spec input: clamav_status="down"; expected_status="503";
#             expected_error="FILE_SCAN_UNAVAILABLE".
# SRS FR-100: "ClamAV 失敗模式 = fail-secure（拒絕文件上傳 + 回傳 503
# FILE_SCAN_UNAVAILABLE）". A regression that returned 200 on ClamAV
# down would silently accept unscanned files and break the malware
# guarantee; a regression that returned 500 (instead of 503) would
# break the API contract that maps FILE_SCAN_UNAVAILABLE to a
# retriable-by-the-client status code.
# ---------------------------------------------------------------------------
def test_fr100_clamav_down_503_file_scan_unavailable():
    # Spec input literals.
    clamav_status = "down"
    expected_status = "503"  # spec string sentinel
    expected_error = "FILE_SCAN_UNAVAILABLE"

    # GREEN TODO: ``CLAMAV_STATUS_DOWN`` MUST equal "down" — the
    # canonical ClamAV-down identifier.
    assert CLAMAV_STATUS_DOWN == "down", (
        f"FR-100 CLAMAV_STATUS_DOWN must be 'down'; got "
        f"{CLAMAV_STATUS_DOWN!r}"
    )

    # GREEN TODO: ``FILE_SCAN_UNAVAILABLE_ERROR`` MUST equal
    # "FILE_SCAN_UNAVAILABLE" — the canonical fail-secure error code.
    assert FILE_SCAN_UNAVAILABLE_ERROR == "FILE_SCAN_UNAVAILABLE", (
        f"FR-100 FILE_SCAN_UNAVAILABLE_ERROR must be "
        f"'FILE_SCAN_UNAVAILABLE'; got "
        f"{FILE_SCAN_UNAVAILABLE_ERROR!r}"
    )

    # GREEN TODO: ``FILE_SCAN_HTTP_503`` MUST equal 503 — the canonical
    # fail-secure HTTP status code.
    assert FILE_SCAN_HTTP_503 == 503, (
        f"FR-100 FILE_SCAN_HTTP_503 must be 503; got "
        f"{FILE_SCAN_HTTP_503!r}"
    )

    # GREEN TODO: ``ClamAVScanner`` MUST expose ``force_status(status)``
    # so tests can drive the scanner into the fault-injection state
    # without a real clamd.
    scanner = ClamAVScanner(subprocess_runner=lambda *a, **kw: None)
    assert hasattr(scanner, "force_status") and callable(
        scanner.force_status
    ), (
        "FR-100 ClamAVScanner must expose "
        "``force_status(status: str) -> None``"
    )
    assert hasattr(scanner, "is_available") and callable(
        scanner.is_available
    ), (
        "FR-100 ClamAVScanner must expose "
        "``is_available() -> bool``"
    )

    # Drive the scanner into the "down" fault-injection state.
    scanner.force_status(clamav_status)
    assert scanner.is_available() is False, (
        "FR-100 ClamAVScanner.is_available() must return False after "
        "force_status('down')"
    )

    pipeline = MediaPipeline(clamav_scanner=scanner)
    # A compliant 1MB PDF — well under the 10MB limit — so the size
    # check passes and the rejection MUST come from the ClamAV-down
    # branch.
    result = pipeline.process_file(
        file_size_mb=1.0,
        file_type="pdf",
        file_bytes=b"%PDF-1.4 stub",
    )

    assert result is not None, (
        "FR-100 process_file() must return a MediaResult on ClamAV "
        "down; got None"
    )

    # The action MUST be "file_rejected" — the FR's fail-secure branch.
    observed_action = (
        result.action()
        if callable(getattr(result, "action", None))
        else result.action
    )
    assert observed_action == "file_rejected", (
        f"FR-100 ClamAV-down must reject the file; got "
        f"action={observed_action!r}"
    )

    # The status MUST be "503" — the FR's HTTP-status sentinel for
    # fail-secure. A GREEN that returned status="rejected" here would
    # conflate the ClamAV-down branch with the size-limit branch and
    # break the API-layer retry semantics.
    if expected_status == "503":
        observed_status = (
            result.status()
            if callable(getattr(result, "status", None))
            else result.status
        )
        assert observed_status == "503", (
            f"FR-100 ClamAV-down must report status='503'; got "
            f"{observed_status!r}"
        )

    # The error MUST be "FILE_SCAN_UNAVAILABLE" — the FR's
    # fail-secure error code. A GREEN that returned error=None here
    # would force the API layer to invent its own error and break the
    # observability contract.
    if expected_error == "FILE_SCAN_UNAVAILABLE":
        observed_error = (
            result.error()
            if callable(getattr(result, "error", None))
            else result.error
        )
        assert observed_error == "FILE_SCAN_UNAVAILABLE", (
            f"FR-100 ClamAV-down must report error="
            f"'FILE_SCAN_UNAVAILABLE'; got {observed_error!r}"
        )


# ---------------------------------------------------------------------------
# 6. ClamAV p95 scan latency is under 500ms (nfr_pattern).
#
# Spec input: file_type="pdf"; p95_limit_ms="500".
# SRS FR-100 + NFR-38: "ClamAV 文件掃描 p95 < 500ms". A regression that
# allowed p95 to drift above 500ms would break the latency SLA and
# degrade every file-upload UX; a regression that returned a non-finite
# / negative p95 would mask the SLA breach and break the perf budget
# gate.
# ---------------------------------------------------------------------------
def test_fr100_clamav_scan_p95_under_500ms():
    # Spec input literals.
    file_type = "pdf"
    p95_limit_ms = "500"  # spec string sentinel

    # GREEN TODO: ``CLAMAV_SCAN_P95_LIMIT_MS`` MUST equal 500 — the SRS
    # FR-100 / NFR-38 p95 SLA ceiling.
    assert CLAMAV_SCAN_P95_LIMIT_MS == 500, (
        f"FR-100 CLAMAV_SCAN_P95_LIMIT_MS must be 500; got "
        f"{CLAMAV_SCAN_P95_LIMIT_MS!r}"
    )

    # GREEN TODO: ``ClamAVScanner.scan_p95(file_type, samples)`` MUST
    # accept an injected subprocess runner so the test can return
    # instantly (no real clamd) and observe a p95 well under 500ms.
    scanner = ClamAVScanner(subprocess_runner=lambda *a, **kw: None)

    # Drive the scanner into the "ok" state explicitly so any
    # default-fault-injection branch is bypassed.
    if hasattr(scanner, "force_status"):
        scanner.force_status("ok")

    assert hasattr(scanner, "scan_p95") and callable(scanner.scan_p95), (
        "FR-100 ClamAVScanner must expose "
        "``scan_p95(file_type: str, samples: int = 100) -> float``"
    )

    # Use a small sample count so the test stays fast. GREEN may
    # default samples to 100; we pass an explicit small N for unit-
    # test wall-clock budget.
    observed_p95_ms = scanner.scan_p95(file_type=file_type, samples=20)

    assert observed_p95_ms is not None, (
        "FR-100 scan_p95 must return a numeric p95; got None"
    )
    assert isinstance(observed_p95_ms, (int, float)), (
        f"FR-100 scan_p95 must be numeric; got "
        f"{type(observed_p95_ms).__name__}"
    )

    # The p95 MUST be a finite, non-negative number — guards against
    # a GREEN that returns -1 / float('inf') / NaN to mask the SLA.
    assert observed_p95_ms >= 0, (
        f"FR-100 p95 must be non-negative; got {observed_p95_ms}"
    )
    # NaN check: NaN != NaN, so equality with self is the canonical test.
    assert observed_p95_ms == observed_p95_ms, (
        f"FR-100 p95 must be finite (not NaN); got {observed_p95_ms}"
    )

    # The p95 MUST be strictly under 500ms — the SRS FR-100 / NFR-38
    # hard SLA. Equality at the ceiling is a regression because the
    # FR's "<" is strict (test_fr97 mirrors this strict-inequality
    # convention for the DR <5min SLA).
    if p95_limit_ms == "500":
        assert observed_p95_ms < CLAMAV_SCAN_P95_LIMIT_MS, (
            f"FR-100 ClamAV scan p95 must be < "
            f"{CLAMAV_SCAN_P95_LIMIT_MS}ms; got {observed_p95_ms}ms"
        )


# ---------------------------------------------------------------------------
# 7. A ClamAV scan that exceeds the timeout is terminated (fault_injection).
#
# Spec input: scan_timeout_ms="500"; clamav_delay_ms="600";
#             expected_terminated="true".
# SRS FR-100: "ClamAV 失敗模式 = fail-secure（拒絕文件上傳 + 回傳 503
# FILE_SCAN_UNAVAILABLE）". A regression that let a stuck scan hang past
# the timeout would block the file-upload path indefinitely and break
# every p95 SLA; a regression that silently returned "clean" on a
# timed-out scan would let unscanned files slip through and break the
# malware guarantee.
# ---------------------------------------------------------------------------
def test_fr100_clamav_timeout_terminates_scan():
    # Spec input literals.
    scan_timeout_ms = "500"
    clamav_delay_ms = "600"
    expected_terminated = "true"  # spec string sentinel

    # GREEN TODO: ``CLAMAV_SCAN_TIMEOUT_MS`` MUST equal 500 — the SRS
    # FR-100 scan-timeout budget.
    assert CLAMAV_SCAN_TIMEOUT_MS == 500, (
        f"FR-100 CLAMAV_SCAN_TIMEOUT_MS must be 500; got "
        f"{CLAMAV_SCAN_TIMEOUT_MS!r}"
    )

    # GREEN TODO: ``ClamAVScanner.scan(...)`` MUST enforce the timeout
    # and MUST set ``ClamAVScanResult.terminated=True`` when the
    # injected runner exceeds the budget. Tests inject a runner that
    # sleeps past the timeout so the GREEN must terminate.
    import time as _time

    def _slow_runner(*args, **kwargs):
        # Block past the scanner's timeout budget so the GREEN must
        # interrupt / kill the call.
        _time.sleep(int(clamav_delay_ms) / 1000.0)
        class _Result:
            returncode = 0
            stdout = b"OK\n"
            stderr = b""

        return _Result()

    scanner = ClamAVScanner(
        subprocess_runner=_slow_runner,
        timeout_ms=int(scan_timeout_ms),
    )

    assert hasattr(scanner, "scan") and callable(scanner.scan), (
        "FR-100 ClamAVScanner must expose "
        "``scan(file_bytes: bytes, file_type: str) -> "
        "ClamAVScanResult``"
    )

    result = scanner.scan(file_bytes=b"%PDF-stub", file_type="pdf")

    assert result is not None, (
        "FR-100 scan() must return a ClamAVScanResult; got None"
    )

    # The terminated flag MUST be True — the FR's
    # "expected_terminated='true'" guarantee. A GREEN that left
    # terminated=False on a timed-out scan would silently pass the
    # file through and break the malware guarantee.
    assert hasattr(result, "terminated"), (
        "FR-100 ClamAVScanResult must expose ``terminated``"
    )
    observed_terminated = (
        result.terminated()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "terminated", None))
        else result.terminated  # type: ignore[reportAttributeAccessIssue]
    )
    if expected_terminated == "true":
        assert observed_terminated is True, (
            f"FR-100 scan exceeding timeout must be terminated; got "
            f"terminated={observed_terminated!r}"
        )

    # Companion invariant: the result MUST also surface a non-"ok"
    # status so the upstream pipeline treats the timed-out scan as a
    # hard failure (fail-secure) and rejects the upload.
    assert hasattr(result, "status"), (
        "FR-100 ClamAVScanResult must expose ``status``"
    )
    observed_status = (
        result.status()  # type: ignore[reportAttributeAccessIssue]
        if callable(getattr(result, "status", None))
        else result.status  # type: ignore[reportAttributeAccessIssue]
    )
    assert observed_status != CLAMAV_STATUS_OK, (
        f"FR-100 timed-out scan must NOT report status='ok'; got "
        f"{observed_status!r}"
    )


# ---------------------------------------------------------------------------
# 8. A file upload is NOT allowed when ClamAV is unavailable
#    (negative_constraint).
#
# Spec input: clamav_status="unavailable"; expected_allowed="false".
# SRS FR-100: "ClamAV 不可用時回 503 FILE_SCAN_UNAVAILABLE（不放行）". A
# regression that allowed files when ClamAV was down would break the
# fail-secure contract — the SRS uses the explicit "不放行" word and
# pins the FR to that guarantee. The pre-flight
# ``is_file_allowed(...)`` check is the API-layer's gate, so this test
# focuses on that gate rather than the full process_file() path (which
# case 5 already covers).
# ---------------------------------------------------------------------------
def test_fr100_must_not_allow_file_when_clamav_unavailable():
    # Spec input literals.
    clamav_status = "unavailable"
    expected_allowed = "false"  # spec string sentinel

    # GREEN TODO: ``CLAMAV_STATUS_UNAVAILABLE`` MUST equal
    # "unavailable" — the canonical ClamAV-unavailable identifier. A
    # GREEN that conflated this with "down" (case 5) would break the
    # distinction between the two fault-injection states.
    assert CLAMAV_STATUS_UNAVAILABLE == "unavailable", (
        f"FR-100 CLAMAV_STATUS_UNAVAILABLE must be 'unavailable'; got "
        f"{CLAMAV_STATUS_UNAVAILABLE!r}"
    )

    scanner = ClamAVScanner(subprocess_runner=lambda *a, **kw: None)
    assert hasattr(scanner, "force_status") and callable(
        scanner.force_status
    ), (
        "FR-100 ClamAVScanner must expose "
        "``force_status(status: str) -> None``"
    )
    scanner.force_status(clamav_status)
    assert scanner.is_available() is False, (
        "FR-100 ClamAVScanner.is_available() must return False after "
        "force_status('unavailable')"
    )

    pipeline = MediaPipeline(clamav_scanner=scanner)
    assert hasattr(pipeline, "is_file_allowed") and callable(
        pipeline.is_file_allowed
    ), (
        "FR-100 MediaPipeline must expose "
        "``is_file_allowed(file_size_mb, file_type) -> bool``"
    )

    # A compliant 1MB PDF — under the size limit and in the
    # allow-list — so the only thing that can deny it is the
    # ClamAV-unavailable fault-injection.
    allowed = pipeline.is_file_allowed(
        file_size_mb=1.0, file_type="pdf"
    )

    assert allowed is not None, (
        "FR-100 is_file_allowed() must return a bool; got None"
    )

    # The upload MUST NOT be allowed — the FR's negative_constraint
    # "expected_allowed='false'" guarantee. The SRS pins this with
    # the explicit "不放行" word; a GREEN that returned True here
    # would let unscanned files reach the user.
    if expected_allowed == "false":
        assert allowed is False, (
            f"FR-100 file upload must NOT be allowed when ClamAV is "
            f"unavailable; got allowed={allowed!r}"
        )

    # Companion invariant: process_file() must also surface the
    # fail-secure 503 + FILE_SCAN_UNAVAILABLE pair (same as case 5)
    # for the "unavailable" state. A GREEN that handled "down" but
    # not "unavailable" would split the fail-secure contract across
    # two branches and break the FR's "fail-secure" invariant.
    result = pipeline.process_file(
        file_size_mb=1.0,
        file_type="pdf",
        file_bytes=b"%PDF-stub",
    )
    assert result is not None, (
        "FR-100 process_file() must return a MediaResult on ClamAV "
        "unavailable; got None"
    )
    observed_error = (
        result.error()
        if callable(getattr(result, "error", None))
        else result.error
    )
    assert observed_error == FILE_SCAN_UNAVAILABLE_ERROR, (
        f"FR-100 ClamAV-unavailable must report "
        f"error='FILE_SCAN_UNAVAILABLE'; got {observed_error!r}"
    )
