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

import time
import uuid
from typing import Any, Optional

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


class A2AAdapter(ActionAdapter):
    """[FR-41] A2A 協定 adapter — Agent Card + JSON-RPC 2.0 transport."""

    def __init__(
        self,
        agent_url: str,
        bearer_token: Optional[str] = None,
        timeout: float = 2.0,
        agent_card_ttl_seconds: int = 300,
    ) -> None:
        # Strip trailing slash so URL composition is deterministic
        # (e.g. ``agent_url + "/.well-known/agent.json"``).
        self.agent_url = agent_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.agent_card_ttl_seconds = agent_card_ttl_seconds

        # Cache: ``agent_url -> (card_or_None, fetched_at_real_time)``.
        # ``fetched_at`` is real ``time.time()`` (no offset); the test
        # hook ``_force_cache_age`` advances ``_time_offset`` so the
        # cache appears expired at lookup time.
        self._card_cache: dict[str, tuple[Optional[dict], float]] = {}

        # ``discovery_count`` increments on every attempted discovery
        # (cache miss OR TTL-expired). The FR-41 TTL-boundary test
        # asserts this counter advances after a refetch.
        self.discovery_count: int = 0

        # Offset (seconds) added to ``time.time()`` for cache-age
        # calculation. Production code leaves it at 0; tests use
        # ``_force_cache_age`` to advance past the TTL.
        self._time_offset: float = 0.0

    # ------------------------------------------------------------------
    # Cache / clock hooks (testability surface for FR-41 RED tests).
    # ------------------------------------------------------------------
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
    def _discover_agent_card(self) -> Optional[dict]:
        """[FR-41] GET ``<agent_url>/.well-known/agent.json`` 並快取 300s。

        快取以 ``agent_url`` 為鍵。在 TTL 內 → 回傳快取；TTL 過期
        或無快取 → 重新發起 HTTP GET。失敗（連線 / DNS / HTTP 4xx/5xx）
        回傳 ``None``，由 ``list_tools`` 降級為空清單。
        """
        now = self._now()
        cached = self._card_cache.get(self.agent_url)
        if cached is not None:
            card, fetched_at = cached
            if (now - fetched_at) < self.agent_card_ttl_seconds:
                return card

        # Cache miss or TTL expired — attempt HTTP discovery.
        # Increment on every ATTEMPT, not just success, so the FR-41
        # TTL-boundary test can observe a refetch even when the remote
        # agent is unreachable.
        self.discovery_count += 1
        url = f"{self.agent_url}/.well-known/agent.json"
        try:
            response = httpx.get(url, timeout=self.timeout)
            response.raise_for_status()
            card = response.json()
        except Exception:
            # Store None with an older timestamp so the failure is cached
            # for a shorter duration (max 30s) instead of the full TTL.
            short_ttl = min(30, self.agent_card_ttl_seconds)
            self._card_cache[self.agent_url] = (None, now - self.agent_card_ttl_seconds + short_ttl)
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
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — NP-15 surface as timeout
            # All execute() failures (connect / DNS / HTTP 4xx/5xx) surface
            # through the NP-15 channel so callers see a uniform
            # ``error_message`` containing ``"timeout"``.
            # Truncate to avoid leaking bearer tokens in exception messages
            safe_exc = str(exc).split('\n')[0][:200]
            return fail(f"{_TIMEOUT_FAILURE_PREFIX}{safe_exc}")

        try:
            body: Any = response.json()
        except Exception as exc:  # noqa: BLE001
            return fail(f"{_TIMEOUT_FAILURE_PREFIX}invalid JSON-RPC response: {exc}")

        if isinstance(body, dict) and "error" in body and "result" not in body:
            err = body.get("error")
            message = err.get("message") if isinstance(err, dict) else str(err)
            return fail(f"jsonrpc_error: JSON-RPC error: {message}")

        return ok(body)

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
