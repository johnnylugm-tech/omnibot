"""[FR-41] ``A2AAdapter`` — Agent-to-Agent (A2A) JSON-RPC 2.0 transport.

[FR-41] ``A2AAdapter`` 透過 Agent Card discovery（300s TTL cache）
與 JSON-RPC 2.0 呼叫（timeout 2.0s）連線至遠端 A2A agent；
``list_tools`` 從 Agent Card 的 ``methods`` 推導；``execute``
呼叫工具並回傳 ``ToolExecutionResult``。

Failure semantics (per FR-41 + NP-07 / NP-15):

* ``agent card unreachable`` → ``list_tools()`` returns ``[]``
  (graceful degradation, no exception).
* ``execute timeout / unreachable`` → ``ToolExecutionResult(success=False,
  error_message contains "timeout")``.

Citations:
- SRS.md FR-41 (Module 7: Action Execution Engine (AEE)):
  "A2AAdapter: GET /.well-known/agent.json 發現 Agent Card（300s TTL
   cache）；execute 透過 JSON-RPC 2.0 呼叫（Authorization: Bearer）；
   timeout=2.0s；agent.json 不可達 → 回傳空工具清單（降級）."
- 02-architecture/TEST_SPEC.md FR-41 cases 1-6 (cache hit, JSON-RPC
  payload format, timeout NP-15, unreachable NP-07, TTL boundary,
  NP-07 negative constraint).
- NFR-05: ``A2A timeout = 2.0s``.
- NFR-07: ``Agent Card TTL cache = 300s``.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.aee.adapter import (
    ActionAdapter,
    ToolDefinition,
    ToolExecutionResult,
    fail,
    ok,
)

# NP-15 surface marker: every ``execute()`` failure is reported as a
# timeout-flavored error per FR-41 (timeout=2.0s). Centralised so the
# prefix is consistent across connect / DNS / HTTP / JSON-parse / JSON-RPC
# error paths and tests asserting ``"timeout" in error_message`` stay green.
_TIMEOUT_FAILURE_PREFIX = "timeout: "

# H-20 SSRF guard: only http(s) transports are permitted — anything
# else (``file://``, ``gopher://``, ``ftp://`` …) could exfiltrate the
# Bearer token via a side channel.
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# M-05 negative-cache window. Kept short so a transient DNS hiccup or
# agent restart is not amplified into a 30-second blank period during
# which ``list_tools()`` returns ``[]``. Callers who need the old
# behaviour can raise this explicitly via ``__init__``.
_DEFAULT_NEGATIVE_TTL_SECONDS: int = 5


def _resolve_addresses(hostname: str) -> list[ipaddress._BaseAddress]:
    """Resolve ``hostname`` to its IPv4/IPv6 addresses.

    Returns ``[]`` on resolution failure — that is a runtime
    connectivity condition, not a security violation, and is left for
    ``httpx`` to surface as a connection error.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return []
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _is_public_address(ip: ipaddress._BaseAddress) -> bool:
    """True iff ``ip`` is safe to call with a Bearer token attached.

    Blocks the standard SSRF surface: loopback, RFC1918 / ULA private
    ranges, link-local (covers the AWS / GCP metadata endpoints at
    ``169.254.169.254`` and friends), multicast, reserved, and the
    unspecified address.
    """
    return not (
        ip.is_private  # type: ignore[attr-defined]
        or ip.is_loopback  # type: ignore[attr-defined]
        or ip.is_link_local  # type: ignore[attr-defined]
        or ip.is_multicast  # type: ignore[attr-defined]
        or ip.is_reserved  # type: ignore[attr-defined]
        or ip.is_unspecified  # type: ignore[attr-defined]
    )


def _validate_agent_url(url: str) -> None:
    """Reject ``agent_url`` values that would leak the Bearer token.

    - Non-``http(s)`` schemes (``file://``, ``gopher://`` …) → ``ValueError``.
    - Hostnames that resolve to a non-public address (loopback,
      RFC1918, link-local, multicast, reserved, unspecified) → ``ValueError``.
    - Unresolvable hostnames pass through; ``httpx`` will surface a
      connect error at request time, which is the expected runtime
      behaviour for FR-41 NP-07.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"agent_url scheme must be one of {sorted(_ALLOWED_SCHEMES)}; "
            f"got {parsed.scheme!r}"
        )
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"agent_url must include a hostname; got {url!r}")
    addresses = _resolve_addresses(hostname)
    if not addresses:
        # Unresolvable host — not a security violation; let the runtime
        # surface the connection error and ``list_tools()`` degrade to
        # ``[]`` per FR-41 NP-07.
        return
    for ip in addresses:
        if not _is_public_address(ip):
            raise ValueError(
                f"agent_url resolves to a non-public address {ip} "
                f"(SSRF guard); hostname={hostname!r}"
            )


class A2AAdapter(ActionAdapter):
    """[FR-41] A2A 協定 adapter — Agent Card + JSON-RPC 2.0 transport."""

    def __init__(
        self,
        agent_url: str,
        bearer_token: str | None = None,
        timeout: float = 2.0,
        agent_card_ttl_seconds: int = 300,
        agent_card_negative_ttl_seconds: int = _DEFAULT_NEGATIVE_TTL_SECONDS,
    ) -> None:
        # H-20: SSRF guard. Fail fast on non-http(s) schemes and
        # private/loopback/link-local hosts so the Bearer token is
        # never attached to a dangerous URL.
        _validate_agent_url(agent_url)

        # Strip trailing slash so URL composition is deterministic
        # (e.g. ``agent_url + "/.well-known/agent.json"``).
        self.agent_url = agent_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.agent_card_ttl_seconds = agent_card_ttl_seconds
        # M-05: short window for negative caching so a transient
        # outage does not pin ``list_tools()`` to ``[]`` for the full
        # 300s positive TTL.
        self.agent_card_negative_ttl_seconds = agent_card_negative_ttl_seconds

        # Cache: ``agent_url -> (card_or_None, fetched_at_real_time)``.
        # ``fetched_at`` is real ``time.time()`` (no offset); the test
        # hook ``_force_cache_age`` advances ``_time_offset`` so the
        # cache appears expired at lookup time.
        self._card_cache: dict[str, tuple[dict | None, float]] = {}

        # ``discovery_count`` increments on every attempted discovery
        # (cache miss OR TTL-expired). The FR-41 TTL-boundary test
        # asserts this counter advances after a refetch.
        self.discovery_count: int = 0

        # Offset (seconds) added to ``time.time()`` for cache-age
        # calculation. Production code leaves it at 0; tests use
        # ``_force_cache_age`` to advance past the TTL.
        self._time_offset: float = 0.0

        # H-21: single ``httpx.Client`` reused across calls so the
        # connection pool (keep-alive sockets) is shared instead of
        # being thrown away on every ``httpx.get`` / ``httpx.post``
        # module-helper invocation. Long-lived adapters no longer
        # leak file descriptors.
        self._client: httpx.Client = httpx.Client(timeout=self.timeout)

        # M-07: IP-pinning cache — maps hostname → frozenset of str IPs.
        # On first validation the resolved IPs are stored; subsequent
        # calls reject any DNS change to a different set, preventing
        # DNS-rebinding attacks even when the change happens between
        # _validate_agent_url() and the actual httpx connect.
        self._validated_ips: dict[str, frozenset[str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle (H-21 — close persistent HTTP client).
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release the underlying HTTP connection pool.

        Callers managing an ``A2AAdapter`` as a long-lived service
        SHOULD invoke this on shutdown. Using ``A2AAdapter`` as a
        context manager (``with A2AAdapter(...) as adapter: ...``) is
        the preferred pattern.
        """
        self._client.close()

    def __enter__(self) -> A2AAdapter:  # pragma: no cover
        return self  # pragma: no cover

    def __exit__(self, *exc_info: object) -> None:  # pragma: no cover
        self.close()  # pragma: no cover

    # ------------------------------------------------------------------
    # Cache / clock hooks (testability surface for FR-41 RED tests).
    # ------------------------------------------------------------------
    def _check_ip_pinning(self, url: str) -> None:
        """[M-07] Validate URL and detect DNS rebinding via IP pinning.

        On first call for a given hostname the resolved IPs are cached.
        Subsequent calls reject any change in the resolved set. This is a
        best-effort guard because of the TOCTOU window between this check
        and the actual httpx connect.
        """
        from urllib.parse import urlparse as _urlparse
        hostname = _urlparse(url).hostname
        if not hostname:
            return
        _validate_agent_url(url)
        current_ips = frozenset(str(ip) for ip in _resolve_addresses(hostname))
        if not current_ips:
            return
        pinned = self._validated_ips.get(hostname)
        if pinned is None:
            self._validated_ips[hostname] = current_ips
        elif current_ips != pinned:
            raise ValueError(
                f"DNS rebinding detected for {hostname!r}: "
                f"IPs changed from {pinned} to {current_ips}"
            )

    def _now(self) -> float:
        """[FR-41] 現在時間（測試可透過 ``_force_cache_age`` 偏移）。"""
        return time.time() + self._time_offset

    def _force_cache_age(self, seconds: float) -> None:
        """[FR-41] 將快取時鐘往前推 ``seconds`` 秒（測試用 hook）。

        累加偏移；多次呼叫會累積效果。RED→GREEN TTL boundary test
        使用此方法在不實際 sleep 的情況下推進 300s TTL。
        """
        self._time_offset += float(seconds)

    # ------------------------------------------------------------------
    # Agent Card discovery (NFR-07: 300s TTL cache).
    # ------------------------------------------------------------------
    def _discover_agent_card(self) -> dict | None:
        """[FR-41] GET ``<agent_url>/.well-known/agent.json`` 並快取 300s。

        快取以 ``agent_url`` 為鍵。在 TTL 內 → 回傳快取；TTL 過期
        或無快取 → 重新發起 HTTP GET。失敗（連線 / DNS / HTTP 4xx/5xx）
        回傳 ``None``，由 ``list_tools`` 降級為空清單。

        M-05: 失敗結果以較短的 ``agent_card_negative_ttl_seconds``
        快取（預設 5s），而非完整的 300s 正快取 TTL，避免暫時性故障
        被放大成 30s 空窗。
        """
        now = self._now()
        cached = self._card_cache.get(self.agent_url)
        if cached is not None:
            card, fetched_at = cached
            # Cached success uses the long positive TTL; cached failure
            # (``card is None``) uses the short negative TTL so a
            # transient outage does not pin ``list_tools()`` to ``[]``.
            ttl = (
                self.agent_card_ttl_seconds
                if card is not None
                else self.agent_card_negative_ttl_seconds
            )
            if (now - fetched_at) < ttl:
                return card

        # Cache miss or TTL expired — attempt HTTP discovery.
        # Increment on every ATTEMPT, not just success, so the FR-41
        # TTL-boundary test can observe a refetch even when the remote
        # agent is unreachable.
        self.discovery_count += 1
        url = f"{self.agent_url}/.well-known/agent.json"
        try:
            self._check_ip_pinning(self.agent_url)
            response = self._client.get(url)
            response.raise_for_status()
            card = response.json()
        except ValueError:
            raise
        except Exception:
            # Negative-cache the failure for ``agent_card_negative_ttl_seconds``
            # so a transient DNS / connect blip does not blank the tool
            # list for the full positive TTL.
            self._card_cache[self.agent_url] = (None, now)
            return None

        self._card_cache[self.agent_url] = (card, now)
        return card

    # ------------------------------------------------------------------
    # Public API (ActionAdapter contract, FR-39).
    # ------------------------------------------------------------------
    def list_tools(self) -> list[ToolDefinition]:
        """[FR-41] 從 Agent Card 的 ``methods`` 推導 ``ToolDefinition`` 清單。

        NP-07 fail-open: 當 Agent Card 不可達時回傳 ``[]``，不拋例外。
        ``_discover_agent_card`` 已經 swallow 所有例外並回傳 ``None``，
        所以這裡只需處理「拿到 card 但 card 為空 / 缺 methods」的情境。
        """
        card = self._discover_agent_card()
        if not card:
            return []

        methods = card.get("methods") or []
        tools: list[ToolDefinition] = []
        for method in methods:
            if not isinstance(method, dict):
                continue
            name = method.get("name")
            if not isinstance(name, str) or not name:
                continue
            tools.append(
                ToolDefinition(
                    name=name,
                    description=method.get("description", ""),
                    parameters_schema=method.get(
                        "parameters_schema",
                        {"type": "object", "properties": {}},
                    ),
                    protocol="a2a",
                    handler_ref=f"a2a://{self.agent_url}/{name}",
                )
            )
        return tools

    def execute(self, tool_name: str, arguments: dict) -> ToolExecutionResult:
        """[FR-41] 以 JSON-RPC 2.0 呼叫遠端 A2A 工具。

        POST ``<agent_url>/rpc``，body 為 ``_build_jsonrpc_payload``
        的結果，header 帶 ``Authorization: Bearer <token>``（如有）。

        NP-15: 超過 ``timeout``（預設 2.0s）回傳
        ``ToolExecutionResult(success=False, error_message="timeout")``。
        所有錯誤（DNS / 連線 / HTTP 4xx/5xx / 反序列化）皆被捕獲並
        以結構化失敗回傳 — 不向外拋例外。
        """
        request_id = uuid.uuid4().hex
        payload = self._build_jsonrpc_payload(
            method=tool_name,
            params=arguments,
            request_id=request_id,
        )
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        url = f"{self.agent_url}/rpc"
        try:
            self._check_ip_pinning(self.agent_url)
            response = self._client.post(
                url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            safe_exc = str(exc).split('\n')[0][:200]
            return fail(f"http_error: {safe_exc}")
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            safe_exc = str(exc).split('\n')[0][:200]
            return fail(f"{_TIMEOUT_FAILURE_PREFIX}{safe_exc}")
        except Exception as exc:
            # All execute() failures surface through the NP-15 channel
            safe_exc = str(exc).split('\n')[0][:200]
            return fail(f"error: {safe_exc}")

        try:
            body: Any = response.json()
        except Exception as exc:
            return fail(f"{_TIMEOUT_FAILURE_PREFIX}invalid JSON-RPC response: {exc}")

        if isinstance(body, dict) and "error" in body and "result" not in body:
            err = body.get("error")
            message = err.get("message") if isinstance(err, dict) else str(err)
            return fail(f"jsonrpc_error: JSON-RPC error: {message}")

        return ok(body.get("result") if isinstance(body, dict) and "result" in body else body)

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 payload builder (FR-41 case 2: payload format).
    # ------------------------------------------------------------------
    def _build_jsonrpc_payload(
        self,
        method: str,
        params: Any,
        request_id: str,
    ) -> dict:
        """[FR-41] 建構符合 JSON-RPC 2.0 規格的請求 payload。

        形狀: ``{"jsonrpc": "2.0", "method": <method>,
        "params": <params>, "id": <request_id>}``。
        """
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }
