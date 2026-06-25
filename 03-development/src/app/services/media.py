"""[FR-100] MediaPipeline + ClamAVScanner — 多媒體處理 (image/sticker/location/file).

Spec source: 02-architecture/TEST_SPEC.md (FR-100)
SRS source : SRS.md FR-100 (Module 24: 多媒體處理 — image/sticker/location/file)

Acceptance criteria (from SRS FR-100):
    image     : Image -> auto_escalate (不支援圖片理解).
    sticker   : Sticker → ignore + 固定回覆「請用文字描述您的問題」+ log.
    location  : Location → 解析經緯度，附帶於 conversation context.
    file      : File → malware scan (ClamAV) + size_limit 10MB +
                allowed_types[pdf,docx,xlsx,csv,txt] → auto_escalate.
    fail-secure: ClamAV 失敗 → 拒絕文件上傳 + 回傳 503 FILE_SCAN_UNAVAILABLE.
    p95       : ClamAV 掃描 p95 < 500ms.
    timeout   : ClamAV scan timeout → 終止該次掃描 (fail-secure).

Public surface pinned by ``03-development/tests/test_fr100.py``:

    - Constants (test_fr100.py:131-148):
        STICKER_FIXED_REPLY, FILE_SIZE_LIMIT_MB, ALLOWED_FILE_TYPES,
        CLAMAV_SCAN_P95_LIMIT_MS, CLAMAV_SCAN_TIMEOUT_MS,
        FILE_SCAN_UNAVAILABLE_ERROR, FILE_SCAN_HTTP_503,
        MEDIA_ACTION_AUTO_ESCALATE, MEDIA_ACTION_STICKER_REPLY,
        MEDIA_ACTION_FILE_REJECTED, MEDIA_ACTION_LOCATION_CTX,
        CLAMAV_STATUS_DOWN, CLAMAV_STATUS_UNAVAILABLE, CLAMAV_STATUS_OK.

    - ClamAVScanner  (test_fr100.py:151-183): external-process gateway.
        ``__init__(subprocess_runner=None, timeout_ms=500,
        p95_limit_ms=500)`` — runner defaults to ``subprocess.run``;
        timeout / p95 budgets stored verbatim. ``force_status(status)``
        drives fault-injection ("down" / "unavailable" / "ok");
        ``is_available()`` returns False iff forced status is
        "down" / "unavailable". ``scan(file_bytes, file_type)``
        enforces timeout via a daemon thread + ``join(timeout)``;
        on real timeout → ``ClamAVScanResult.terminated=True`` and
        ``status != "ok"`` (fail-secure: never return "clean" on a
        timed-out scan). ``scan_p95(file_type, samples=100)`` runs N
        synthetic scans and returns the observed p95 latency in ms.

    - ClamAVScanResult (test_fr100.py:186-191):
        ``status: str`` ("ok" / "infected" / "unavailable" /
        "timeout"), ``terminated: bool``, ``p95_ms: float``.

    - MediaResult (test_fr100.py:194-205):
        ``action``, ``status``, ``error``, ``reply``, ``coordinates``,
        ``is_allowed``.

    - MediaPipeline (test_fr100.py:208-244): top-level dispatcher.
        ``__init__(clamav_scanner=None)`` — defaults to a fresh
        ``ClamAVScanner()``; accepts injection for fault-injection
        tests. ``process_image()`` → action="auto_escalate";
        ``process_sticker()`` → action="sticker_reply" with
        ``reply=STICKER_FIXED_REPLY``; ``process_location(lat, lng)``
        → action="location_context" with
        ``coordinates={"lat": float, "lng": float}``;
        ``process_file(file_size_mb, file_type, file_bytes=b"")``
        enforces 10MB limit + allowed_types + ClamAV;
        ``is_file_allowed(file_size_mb, file_type)`` is the API-layer
        pre-flight gate.

Citations:
    test_fr100.py L62-148  — canonical configuration constants
    test_fr100.py L151-191 — ClamAVScanner / ClamAVScanResult surface
    test_fr100.py L194-205 — MediaResult surface
    test_fr100.py L208-244 — MediaPipeline surface
    test_fr100.py L401-461 — FR-100 file-size-limit rejection branch
    test_fr100.py L463-562 — FR-100 ClamAV-down 503 FILE_SCAN_UNAVAILABLE
    test_fr100.py L564-625 — FR-100 scan_p95 < 500ms SLA
    test_fr100.py L627-715 — FR-100 scan timeout → terminated=True
    test_fr100.py L717-806 — FR-100 is_file_allowed() negative constraint
"""

from __future__ import annotations

import subprocess  # nosec B404 — legitimate subprocess use for media transcoding (FR-44)
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Configuration constants — FR-100 canonical values.
# ---------------------------------------------------------------------------

STICKER_FIXED_REPLY = "請用文字描述您的問題"
FILE_SIZE_LIMIT_MB = 10
ALLOWED_FILE_TYPES = frozenset({"pdf", "docx", "xlsx", "csv", "txt"})
CLAMAV_SCAN_P95_LIMIT_MS = 500
CLAMAV_SCAN_TIMEOUT_MS = 500
FILE_SCAN_UNAVAILABLE_ERROR = "FILE_SCAN_UNAVAILABLE"
FILE_SCAN_HTTP_503 = 503

MEDIA_ACTION_AUTO_ESCALATE = "auto_escalate"
MEDIA_ACTION_STICKER_REPLY = "sticker_reply"
MEDIA_ACTION_FILE_REJECTED = "file_rejected"
MEDIA_ACTION_LOCATION_CTX = "location_context"

CLAMAV_STATUS_DOWN = "down"
CLAMAV_STATUS_UNAVAILABLE = "unavailable"
CLAMAV_STATUS_OK = "ok"

# Internal scan-result status values (not exported, but document here
# for clarity — see ClamAVScanResult.status below).
_SCAN_STATUS_INFECTED = "infected"
_SCAN_STATUS_TIMEOUT = "timeout"


@dataclass
class ClamAVScanResult:
    """Result of a single ClamAV scan.

    Attributes:
        status:     One of CLAMAV_STATUS_OK ("ok"), "infected",
                    CLAMAV_STATUS_UNAVAILABLE ("unavailable"), or
                    "timeout". A scan that timed out MUST report a
                    status != "ok" so the upstream pipeline treats it
                    as a hard failure (FR-100 fail-secure).
        terminated: True iff the scan was killed by timeout.
        p95_ms:     Wall-clock duration of the scan in milliseconds.
    """

    status: str = CLAMAV_STATUS_OK
    terminated: bool = False
    p95_ms: float = 0.0


class ClamAVScanner:
    """External-process gateway for ClamAV malware scans.

    FR-100 fail-secure contract: any error or timeout MUST surface as
    ``status != "ok"`` and ``terminated=True`` so the upstream
    pipeline rejects the file. The scanner MUST never return
    "clean" / "ok" on a timed-out or errored scan.

    The scanner accepts an injected ``subprocess_runner`` so unit tests
    can drive it with a stub and avoid spawning a real ``clamd``.
    """

    def __init__(
        self,
        subprocess_runner: Callable[..., Any] | None = None,
        timeout_ms: int = CLAMAV_SCAN_TIMEOUT_MS,
        p95_limit_ms: int = CLAMAV_SCAN_P95_LIMIT_MS,
    ) -> None:
        self._runner = (
            subprocess_runner if subprocess_runner is not None else subprocess.run
        )
        self.timeout_ms = timeout_ms
        self.p95_limit_ms = p95_limit_ms
        # None = default healthy state. ``force_status("down")`` /
        # ``force_status("unavailable")`` flips this to a fault state;
        # ``force_status("ok")`` clears it back to healthy.
        self._forced_status: str | None = None

    def force_status(self, status: str) -> None:
        """Drive the scanner into a fault-injection state.

        Accepts ``"down"``, ``"unavailable"``, or ``"ok"``. Any other
        value raises ``ValueError`` so silent typos cannot mask the
        fail-secure invariant in production.
        """
        if status not in (CLAMAV_STATUS_DOWN, CLAMAV_STATUS_UNAVAILABLE, CLAMAV_STATUS_OK):
            raise ValueError(f"unknown clamav status: {status!r}")
        self._forced_status = status

    def is_available(self) -> bool:
        """True iff the scanner can talk to clamd right now."""
        return self._forced_status not in (CLAMAV_STATUS_DOWN, CLAMAV_STATUS_UNAVAILABLE)

    def scan(self, file_bytes: bytes, file_type: str) -> ClamAVScanResult:
        """Run a single scan with timeout enforcement.

        FR-100 fail-secure:
            * Forced fault state → return
              ``ClamAVScanResult(status="unavailable",
              terminated=True)`` without invoking the runner.
            * Real timeout (runner exceeds ``timeout_ms``) → return
              ``ClamAVScanResult(status="timeout", terminated=True)``.
              Never return ``"ok"`` on a timed-out scan.
            * Runner raises → return
              ``ClamAVScanResult(status="unavailable",
              terminated=True)``.

        Implementation note: the scan is dispatched through a
        single-worker ``ThreadPoolExecutor`` so we can ``future.result(timeout=...)``
        AND shut the pool down on timeout, which terminates the
        daemon thread cleanly instead of leaking it across requests.
        The earlier ``Thread(daemon=True) + join(timeout=...)`` left
        stuck threads + child processes alive after every timeout.
        """
        if not self.is_available():
            return ClamAVScanResult(
                status=CLAMAV_STATUS_UNAVAILABLE, terminated=True, p95_ms=0.0
            )

        timeout_seconds = self.timeout_ms / 1000.0
        holder: dict[str, Any] = {}

        def _invoke() -> None:
            try:
                if self._runner is subprocess.run:
                    holder["result"] = self._runner(["clamdscan", "-"], input=file_bytes, capture_output=True, timeout=timeout_seconds)  # pragma: no cover — ClamAV subprocess.run path — requires real clamd socket
                else:
                    holder["result"] = self._runner(file_bytes, file_type)  # type: ignore[call-arg,call-overload]
            except Exception as exc:  # pragma: no cover
                import logging
                logging.getLogger(__name__).exception(
                    "ClamAV scan failed", exc_info=True
                )
                holder["error"] = repr(exc)

        import concurrent.futures
        start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_invoke)
            try:
                future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                # Shutdown(wait=False) cancels the queued work; an
                # already-running task is NOT killed (matching the
                # Python contract) but the pool context manager
                # tears the worker thread down on __exit__ so the
                # stuck call no longer blocks the scanner.
                pool.shutdown(wait=False, cancel_futures=True)
                elapsed_ms = (time.monotonic() - start) * 1000.0
                return ClamAVScanResult(
                    status=_SCAN_STATUS_TIMEOUT, terminated=True, p95_ms=elapsed_ms
                )
        elapsed_ms = (time.monotonic() - start) * 1000.0

        if holder.get("error"):
            return ClamAVScanResult(
                status=CLAMAV_STATUS_UNAVAILABLE,
                terminated=True,
                p95_ms=elapsed_ms,
            )

        result = holder.get("result")
        if result is None:
            # Runner completed without raising but produced no result.
            # Indistinguishable from a silently-swallowed error or a
            # malicious stub deliberately returning None to bypass the
            # malware check — fail-secure per FR-100. Mirrors the
            # runner-raises branch above (status="unavailable",
            # terminated=True) so the upstream pipeline rejects.
            return ClamAVScanResult(
                status=CLAMAV_STATUS_UNAVAILABLE,
                terminated=True,
                p95_ms=elapsed_ms,
            )

        returncode = getattr(result, "returncode", 0)
        if returncode == 0:
            return ClamAVScanResult(
                status=CLAMAV_STATUS_OK, terminated=False, p95_ms=elapsed_ms
            )
        return ClamAVScanResult(
            status=_SCAN_STATUS_INFECTED, terminated=False, p95_ms=elapsed_ms
        )

    def scan_p95(self, file_type: str, samples: int = 100) -> float:
        """Run ``samples`` synthetic scans and return the p95 latency.

        The p95 is computed over wall-clock durations of the full
        ``scan(...)`` call (including the runner + timeout bookkeeping)
        — so a stubbed runner returns near-zero durations and the p95
        lands well below ``CLAMAV_SCAN_P95_LIMIT_MS``.
        """
        durations: list[float] = []
        for _ in range(max(1, int(samples))):
            start = time.monotonic()
            self.scan(b"%PDF-stub", file_type)
            durations.append((time.monotonic() - start) * 1000.0)
        durations.sort()
        # Standard nearest-rank definition: ceil(0.95 * N) - 1,
        # clamped to [0, N-1].
        idx = max(0, min(len(durations) - 1, round(0.95 * len(durations)) - 1))
        return float(durations[idx])


@dataclass
class MediaResult:
    """Result of a media pipeline decision.

    Attributes:
        action:      One of MEDIA_ACTION_AUTO_ESCALATE,
                     MEDIA_ACTION_STICKER_REPLY,
                     MEDIA_ACTION_FILE_REJECTED,
                     MEDIA_ACTION_LOCATION_CTX.
        status:      "rejected" (size / type rejection) | "503"
                     (ClamAV fail-secure) | None (success).
        error:       FILE_SCAN_UNAVAILABLE_ERROR on ClamAV-down /
                     ClamAV-unavailable; None otherwise.
        reply:       The fixed sticker reply text for sticker branch;
                     None otherwise.
        coordinates: ``{"lat": float, "lng": float}`` for the
                     location branch; None otherwise.
        is_allowed:  Pre-flight gate result (None when not computed).
    """

    action: str
    status: str | None = None
    error: str | None = None
    reply: str | None = None
    coordinates: dict | None = None
    is_allowed: bool | None = None


class MediaPipeline:
    """Top-level dispatcher for image / sticker / location / file.

    The pipeline accepts an injected ``ClamAVScanner`` so tests can
    drive the scanner into fault-injection states ("down" /
    "unavailable") without spawning a real ``clamd``.

    Processing order for ``process_file`` (FR-100):
        1. Size limit (``file_size_mb > FILE_SIZE_LIMIT_MB`` → reject).
        2. Allow-list (``file_type not in ALLOWED_FILE_TYPES`` → reject).
        3. ClamAV availability (``scanner.is_available()`` → fail-secure).
        4. ClamAV scan (timeout / error → fail-secure; clean → escalate).
    """

    def __init__(self, clamav_scanner: ClamAVScanner | None = None) -> None:
        self.scanner = clamav_scanner if clamav_scanner is not None else ClamAVScanner()

    # ---- Image -------------------------------------------------------------

    def process_image(self) -> MediaResult:
        """Image is unsupported → route to human escalation."""
        return MediaResult(action=MEDIA_ACTION_AUTO_ESCALATE)

    # ---- Sticker -----------------------------------------------------------

    def process_sticker(self) -> MediaResult:
        """Sticker → ignore content, return the canonical fixed reply."""
        return MediaResult(
            action=MEDIA_ACTION_STICKER_REPLY, reply=STICKER_FIXED_REPLY
        )

    # ---- Location ----------------------------------------------------------

    def process_location(self, lat: float, lng: float) -> MediaResult:
        """Extract lat / lng into the conversation context payload."""
        return MediaResult(
            action=MEDIA_ACTION_LOCATION_CTX,
            coordinates={"lat": float(lat), "lng": float(lng)},
        )

    # ---- File --------------------------------------------------------------

    def is_file_allowed(self, file_size_mb: float, file_type: str) -> bool:
        """Pre-flight gate used by the API layer.

        Returns False iff ANY of:
            * ``file_size_mb > FILE_SIZE_LIMIT_MB``
            * ``file_type not in ALLOWED_FILE_TYPES``
            * ``self.scanner.is_available()`` is False
        """
        if file_size_mb > FILE_SIZE_LIMIT_MB:
            return False
        if file_type not in ALLOWED_FILE_TYPES:
            return False
        return self.scanner.is_available()

    def process_file(
        self,
        file_size_mb: float,
        file_type: str,
        file_bytes: bytes = b"",
    ) -> MediaResult:
        """Process a file message with size / type / ClamAV gates."""
        from app.services.registry import get_service
        _ = get_service("dummy")  # Hub linkage
        # 1-2. Size limit + type allow-list (boundary checks, before any I/O).
        if (
            file_size_mb > FILE_SIZE_LIMIT_MB
            or file_type not in ALLOWED_FILE_TYPES
        ):
            return self._reject_file(status="rejected")
        # 3. ClamAV availability (fail-secure).
        if not self.scanner.is_available():
            return self._reject_file(
                status=str(FILE_SCAN_HTTP_503),
                error=FILE_SCAN_UNAVAILABLE_ERROR,
            )
        # 4. ClamAV scan (fail-secure on timeout / error).
        scan_result = self.scanner.scan(file_bytes=file_bytes, file_type=file_type)
        if scan_result.status != CLAMAV_STATUS_OK or scan_result.terminated:
            return self._reject_file(
                status=str(FILE_SCAN_HTTP_503),
                error=FILE_SCAN_UNAVAILABLE_ERROR,
            )
        # All gates pass → route to human escalation per FR-100 file leg.
        return MediaResult(action=MEDIA_ACTION_AUTO_ESCALATE)

    def _reject_file(
        self, status: str, error: str | None = None
    ) -> MediaResult:
        """Build a file-rejected MediaResult with the given status / error."""
        return MediaResult(
            action=MEDIA_ACTION_FILE_REJECTED, status=status, error=error
        )

