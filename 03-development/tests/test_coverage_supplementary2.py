"""Coverage supplementary tests — batch 2.

Each test targets a specific uncovered line or branch identified by
``pytest --cov-report=term-missing``. All external calls (subprocess,
HTTP) are mocked with unittest.mock.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "src")

import base64 as _base64
import json as _json
import time as _time

from cryptography.hazmat.primitives import hashes as _hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

# ---------------------------------------------------------------------------
# app.infra.config — lines 61-65, 93-95, 101
# ---------------------------------------------------------------------------


def test_dict_config_store_init_default():
    """config.py — _DictConfigStore init seeds rag_cosine_threshold."""
    from app.infra.config import DEFAULT_RAG_COSINE_THRESHOLD, _DictConfigStore

    store = _DictConfigStore()
    assert store._data.get("rag_cosine_threshold") == DEFAULT_RAG_COSINE_THRESHOLD


def test_dict_config_store_init_with_initial():
    """config.py — _DictConfigStore init with custom initial dict."""
    from app.infra.config import _DictConfigStore

    store = _DictConfigStore({"key": "val"})
    assert store._data["key"] == "val"
    assert "rag_cosine_threshold" in store._data


def test_get_config_store_creates_default():
    """config.py — get_config_store() creates _DictConfigStore when None."""
    import app.infra.config as cfg_mod

    cfg_mod._default_store = None
    store = cfg_mod.get_config_store()
    assert store is not None
    assert hasattr(store, "_data")


def test_health_probe_returns_true():
    """config.py — health_probe() returns status True."""
    from app.infra.config import health_probe

    result = health_probe()
    assert result == {"status": True}


# ---------------------------------------------------------------------------
# app.core.dst — lines 424, 460, 605
# ---------------------------------------------------------------------------


def test_dst_handle_confirmation_no_trigger():
    """dst.py — handle_confirmation returns self.state when no trigger fires."""
    from app.core.dst import DialogueState

    ds = DialogueState("IDLE")
    result = ds.handle_confirmation("confirm", awaiting_rounds=0)
    assert result == "IDLE"


def test_dst_confirmation_target_returns_none():
    """dst.py — _confirmation_target returns None when not AWAITING_CONFIRMATION."""
    from app.core.dst import DialogueState

    ds = DialogueState("PROCESSING")
    result = ds._confirmation_target("confirm", 0)
    assert result is None


def test_dst_manage_within_budget():
    """dst.py — manage() returns messages unchanged when within budget."""
    from app.core.dst import ContextWindowManager

    mgr = ContextWindowManager()
    msgs = [{"role": "user", "content": "hi"}]
    result = mgr.manage(msgs)
    assert result == msgs


# ---------------------------------------------------------------------------
# app.core.emotion — lines 176, 250, 278
# ---------------------------------------------------------------------------


def test_emotion_analyzer_analyze():
    """emotion.py — EmotionAnalyzer.analyze() delegates to classify()."""
    from app.core.emotion import EmotionAnalyzer, EmotionScore

    analyzer = EmotionAnalyzer()
    result = analyzer.analyze("happy")
    assert isinstance(result, EmotionScore)


def test_emotion_tracker_should_escalate_none():
    """emotion.py — should_escalate(None) returns False."""
    from app.core.emotion import EmotionTracker

    tracker = EmotionTracker()
    result = tracker.should_escalate(None)
    assert result is False


def test_find_unnegated_keyword_advances_idx():
    """emotion.py — _find_unnegated_keyword advances idx past negated pos."""
    from app.core.emotion import _find_unnegated_keyword

    keywords = frozenset(["好"])
    result = _find_unnegated_keyword("不好", keywords)
    assert result is None


# ---------------------------------------------------------------------------
# app.services.ab_testing — lines 173, 187, 296
# ---------------------------------------------------------------------------


def test_ab_testing_route_bucket_skip_negative_weight():
    """ab_testing.py — _route_bucket skips negative weight (continue)."""
    from app.services.ab_testing import ABTestManager

    db = MagicMock()
    llm = MagicMock()
    mgr = ABTestManager(db=db, llm=llm)
    result = mgr._route_bucket(50, {"bad": -1, "good": 100})
    assert result == "good"


def test_ab_testing_fetch_experiment_no_attr():
    """ab_testing.py — _fetch_experiment returns None when db has no get_experiment."""
    from app.services.ab_testing import ABTestManager

    db = object()
    mgr = ABTestManager(db=db, llm=MagicMock())
    result = mgr._fetch_experiment("exp1")
    assert result is None


def test_observability_auto_init_when_not_initialized():
    """observability.py — _auto_init sets _service_name when _initialised is False."""
    import app.infra.observability as obs

    original = obs._initialised
    try:
        obs._initialised = False
        obs._ensure_setup()
        assert obs._initialised is True
        assert obs._service_name == "omnibot"
    finally:
        obs._initialised = original


def test_observability_span_value_error_in_finally():
    """observability.py — ValueError in span.remove is silently ignored."""
    import app.infra.observability as obs

    with obs.start_as_current_span("outer"), obs.start_as_current_span("inner") as inner_span:
        spans = obs._get_active_spans()
        spans.remove(inner_span)


# ---------------------------------------------------------------------------
# app.core.pipeline — lines 56, 103
# ---------------------------------------------------------------------------


def test_pipeline_normalise_platform_with_name_attr():
    """pipeline.py — _normalise_platform uses .name when value is non-string."""
    from app.core.pipeline import _normalise_platform

    class FakePlatform:
        value = 123
        name = "Agent"

    result = _normalise_platform(FakePlatform())
    assert result == "agent"


def test_pipeline_get_context():
    """pipeline.py — get_context returns dict with conversation_id."""
    from app.core.pipeline import get_context

    result = get_context("conv-1")
    assert result["conversation_id"] == "conv-1"
    assert result["history"] == []


# ---------------------------------------------------------------------------
# app.infra.redis_streams — lines 149, 215, 241, 255, 259, 279
# ---------------------------------------------------------------------------


def test_redis_is_busygroup_error_with_typed_exc():
    """redis_streams.py — _is_busygroup_error returns True for BusyGroupError."""
    from app.infra.redis_streams import AsyncMessageProcessor, BusyGroupError

    redis = MagicMock()
    proc = AsyncMessageProcessor(redis_client=redis)
    exc = BusyGroupError("BUSYGROUP already exists")
    assert proc._is_busygroup_error(exc) is True


@pytest.mark.asyncio
async def test_redis_fetch_message_fields_empty_xrange():
    """redis_streams.py — _fetch_message_fields returns None on empty rows."""
    from app.infra.redis_streams import AsyncMessageProcessor

    redis = AsyncMock()
    redis.xrange = AsyncMock(return_value=[])
    proc = AsyncMessageProcessor(redis_client=redis)
    result = await proc._fetch_message_fields("1234-0")
    assert result is None


@pytest.mark.asyncio
async def test_redis_reclaim_stale_no_pending():
    """redis_streams.py — reclaim_stale returns [] when pending=0."""
    from app.infra.redis_streams import AsyncMessageProcessor

    redis = AsyncMock()
    redis.xpending = AsyncMock(return_value={"pending": 0})
    proc = AsyncMessageProcessor(redis_client=redis)
    result = await proc.claim_pending("consumer1")
    assert result == []


@pytest.mark.asyncio
async def test_redis_reclaim_stale_break_on_empty_detail():
    """redis_streams.py — reclaim_stale breaks when detailed is empty."""
    from app.infra.redis_streams import AsyncMessageProcessor

    redis = AsyncMock()
    redis.xpending = AsyncMock(return_value={"pending": 1})
    redis.xpending_range = AsyncMock(return_value=[])
    proc = AsyncMessageProcessor(redis_client=redis)
    result = await proc.claim_pending("consumer1")
    assert result == []


@pytest.mark.asyncio
async def test_redis_reclaim_stale_continue_on_low_idle():
    """redis_streams.py — reclaim_stale skips entries with idle < idle_ms."""
    from app.infra.redis_streams import AsyncMessageProcessor

    redis = AsyncMock()
    redis.xpending = AsyncMock(return_value={"pending": 1})
    redis.xpending_range = AsyncMock(
        return_value=[{"message_id": "1-0", "time_since_delivered": 0}]
    )
    proc = AsyncMessageProcessor(redis_client=redis, idle_ms=5000)
    result = await proc.claim_pending("consumer1")
    assert result == []


@pytest.mark.asyncio
async def test_redis_reclaim_stale_cursor_advance():
    """redis_streams.py — reclaim_stale advances cursor when batch is full."""
    from app.infra.redis_streams import _PEL_BATCH_SIZE, AsyncMessageProcessor

    redis = AsyncMock()
    redis.xpending = AsyncMock(return_value={"pending": 1})
    full_batch = [
        {"message_id": f"{i}-0", "time_since_delivered": 999999}
        for i in range(_PEL_BATCH_SIZE)
    ]
    redis.xpending_range = AsyncMock(side_effect=[full_batch, []])
    redis.xclaim = AsyncMock(return_value=[])
    proc = AsyncMessageProcessor(redis_client=redis, idle_ms=1)
    result = await proc.claim_pending("consumer1")
    assert result == []


# ---------------------------------------------------------------------------
# app.infra.deployment — lines 146, 187, 444, 702-705
# ---------------------------------------------------------------------------


def test_k8s_prevents_disruption_zero():
    """deployment.py — prevents_disruption(0) returns True."""
    from app.infra.deployment import K8sManifest

    manifest = K8sManifest()
    assert manifest.prevents_disruption(0) is True


def test_k8s_hpa_scale_test_below_target():
    """deployment.py — hpa_scale_test(cpu < target) → HPA_MIN_REPLICAS."""
    from app.infra.deployment import HPA_CPU_TARGET_PERCENT, HPA_MIN_REPLICAS, K8sManifest

    manifest = K8sManifest()
    r = manifest.hpa_scale_test(HPA_CPU_TARGET_PERCENT - 1)
    assert r.replicas == HPA_MIN_REPLICAS


def test_backup_strategy_restore_other_type():
    """deployment.py — restore() with unknown type returns BackupResult."""
    from app.infra.deployment import BackupResult, BackupStrategy

    bs = BackupStrategy()
    result = bs.restore("other_backup_type")
    assert isinstance(result, BackupResult)
    assert result.restored is True


def test_calibration_read_cached_kappa_none_cache():
    """llm_judge.py — _read_cached_kappa returns None when kappa_cache is None."""
    from app.services.llm_judge import CalibrationPipeline

    cp = CalibrationPipeline(judge_llm=AsyncMock(), kappa_cache=None, timeout_s=5)
    result = cp._read_cached_kappa()
    assert result is None


def test_calibration_read_cached_kappa_cache_raises():
    """llm_judge.py — _read_cached_kappa returns None when cache.get raises."""
    from app.services.llm_judge import CalibrationPipeline

    bad_cache = MagicMock()
    bad_cache.get = MagicMock(side_effect=RuntimeError("cache down"))
    cp = CalibrationPipeline(judge_llm=AsyncMock(), kappa_cache=bad_cache, timeout_s=5)
    result = cp._read_cached_kappa()
    assert result is None


# ---------------------------------------------------------------------------
# app.services.media — lines 210, 230-235, 338, 340, 363-370
# ---------------------------------------------------------------------------


def test_media_is_file_allowed_size_too_large():
    """media.py — is_file_allowed returns False when size > limit."""
    from app.services.media import MediaPipeline

    pipeline = MediaPipeline()
    result = pipeline.is_file_allowed(999.0, "image/jpeg")
    assert result is False


def test_media_is_file_allowed_type_not_allowed():
    """media.py — is_file_allowed returns False when type not in allowed list."""
    from app.services.media import MediaPipeline

    pipeline = MediaPipeline()
    result = pipeline.is_file_allowed(0.5, "application/x-executable")
    assert result is False


def test_response_format_for_platform_unknown():
    """response.py — format_for_platform returns content unchanged for unknown platform."""
    from app.core.response import ResponseGenerator

    gen = ResponseGenerator()
    content = "hello " * 100
    result = gen.format_for_platform("unknown_platform_xyz", content)
    assert result == content


def test_attempt_windowed_delete_naive_datetime():
    """response.py — _attempt_windowed_delete adds UTC tzinfo to naive sent_at."""
    from app.core.response import _attempt_windowed_delete

    naive_sent_at = datetime.utcnow() - timedelta(seconds=30)
    result = _attempt_windowed_delete(
        platform="telegram",
        client=None,
        message_id="msg1",
        sent_at=naive_sent_at,
        window=timedelta(hours=48),
        security_log_writer=None,
    )
    assert result is not None


def test_retract_web_ws_failure():
    """response.py — _retract_web returns apology result when pusher raises."""
    from app.core.response import _retract_web

    bad_pusher = MagicMock()
    bad_pusher.replace_response.side_effect = RuntimeError("ws dead")
    result = _retract_web(
        message_id="msg1",
        web_ws_pusher=bad_pusher,
        security_log_writer=None,
    )
    assert result.success is False


# ---------------------------------------------------------------------------
# app.services.aee.adapter — lines 84-87
# ---------------------------------------------------------------------------


def test_adapter_resolve_tool_found():
    """adapter.py — _resolve_tool returns ToolDefinition when found."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    tool = adapter._resolve_tool("get_shipping")
    assert tool is not None
    assert tool.name == "get_shipping"


def test_adapter_resolve_tool_not_found():
    """adapter.py — _resolve_tool returns None when not found."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    result = adapter._resolve_tool("nonexistent_tool_xyz")
    assert result is None


# ---------------------------------------------------------------------------
# app.services.aee.tool_executor — lines 66, 71, 144, 188-193, 242-243, 280, 285, 297-298, 305-320
# ---------------------------------------------------------------------------


def test_validate_handler_not_callable():
    """tool_executor.py — _validate_handler raises TypeError for non-callable."""
    from app.services.aee.tool_executor import _validate_handler

    with pytest.raises(TypeError, match="must be callable"):
        _validate_handler("not_a_function", context="test")


def test_tool_executor_with_handlers_dict():
    """tool_executor.py — ToolExecutor(handlers=...) registers handlers from dict."""
    from app.services.aee.tool_executor import ToolExecutor

    def my_tool(**kwargs):
        return "ok"

    executor = ToolExecutor(handlers={"my_tool": my_tool}, default_tools=False)
    result = executor.execute("my_tool", arguments_json="{}")
    assert result.success is True


def test_tool_executor_invalid_json():
    """tool_executor.py — execute returns fail for invalid JSON arguments."""
    from app.services.aee.tool_executor import ToolExecutor

    executor = ToolExecutor(default_tools=True)
    result = executor.execute("get_shipping_status", arguments_json="{not valid json")
    assert result.success is False
    assert "Invalid JSON" in (result.error_message or "")


def test_tool_executor_non_dict_json():
    """tool_executor.py — execute returns fail when JSON is not a dict."""
    from app.services.aee.tool_executor import ToolDefinition, ToolExecutor

    def echo_fn(**kwargs):
        return kwargs

    tool_def = ToolDefinition(name="echo", description="x", parameters_schema={}, protocol="internal", handler_ref="echo")
    executor = ToolExecutor(default_tools=False)
    executor.register(tool_def, echo_fn)
    result = executor.execute("echo", arguments_json="[1, 2, 3]")
    assert result.success is False
    assert "JSON object" in (result.error_message or "")


def test_tool_executor_schema_validation_fail():
    """tool_executor.py — execute returns fail on schema validation error."""
    from app.services.aee.tool_executor import ToolDefinition, ToolExecutor

    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }
    tool_def = ToolDefinition(name="strict_tool", description="s", parameters_schema=schema, protocol="internal", handler_ref="s")

    def strict_fn(**kwargs):
        return kwargs.get("x")

    executor = ToolExecutor(default_tools=False)
    executor.register(tool_def, strict_fn)
    result = executor.execute("strict_tool", arguments_json='{"x": "not_an_int"}')
    assert result.success is False
    assert "validation" in (result.error_message or "").lower()


def test_tool_executor_handler_raises_exception():
    """tool_executor.py — execute returns fail when handler raises exception."""
    from app.services.aee.tool_executor import ToolDefinition, ToolExecutor

    def bad_handler(**kwargs):
        raise ValueError("handler boom")

    tool_def = ToolDefinition(name="bad_tool", description="b", parameters_schema={}, protocol="internal", handler_ref="b")
    executor = ToolExecutor(default_tools=False)
    executor.register(tool_def, bad_handler)
    result = executor.execute("bad_tool", arguments_json="{}")
    assert result.success is False
    assert "raised an exception" in (result.error_message or "")


def test_tool_executor_decode_arguments_dict_passthrough():
    """tool_executor.py — _decode_arguments passes dict through unchanged."""
    from app.services.aee.tool_executor import ToolExecutor

    executor = ToolExecutor(default_tools=False)
    result = executor._decode_arguments({"key": "val"})
    assert result == {"key": "val"}


# ---------------------------------------------------------------------------
# app.services.aee.a2a_adapter — lines 75, 114, 190, 250-260, 276-296, 326, 335-345
# ---------------------------------------------------------------------------


def test_resolve_addresses_success():
    """a2a_adapter.py — _resolve_addresses returns IP list on success."""
    from app.services.aee.a2a_adapter import _resolve_addresses

    ips = _resolve_addresses("localhost")
    assert isinstance(ips, list)
    assert len(ips) >= 1


def test_validate_agent_url_no_hostname():
    """a2a_adapter.py — _validate_agent_url raises ValueError when no hostname."""
    from app.services.aee.a2a_adapter import _validate_agent_url

    with pytest.raises(ValueError, match="must include a hostname"):
        _validate_agent_url("http://")


def test_a2a_adapter_close():
    """a2a_adapter.py — close() calls _client.close()."""
    from app.services.aee.a2a_adapter import A2AAdapter

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter._client = MagicMock()
        adapter.close()
    adapter._client.close.assert_called_once()


def test_a2a_discover_agent_card_http_success():
    """a2a_adapter.py — _discover_agent_card returns card on HTTP 200."""
    from app.services.aee.a2a_adapter import A2AAdapter

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter.agent_url = "https://agent.example.com"
        adapter.bearer_token = None
        adapter.timeout = 2.0
        adapter.agent_card_ttl_seconds = 300
        adapter.agent_card_negative_ttl_seconds = 5
        adapter._card_cache = {}
        adapter.discovery_count = 0
        adapter._time_offset = 0.0
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"name": "TestAgent", "methods": []}
        mock_client.get.return_value = mock_response
        adapter._client = mock_client

    card = adapter._discover_agent_card()
    assert card is not None
    assert card["name"] == "TestAgent"


def test_a2a_list_tools_with_methods():
    """a2a_adapter.py — list_tools() converts card methods to ToolDefinitions."""
    from app.services.aee.a2a_adapter import A2AAdapter, ToolDefinition

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter.agent_url = "https://agent.example.com"

    card = {"methods": [
        {"name": "do_thing", "description": "does thing", "parameters_schema": {}},
        {"name": "", "description": "empty name"},
        "not_a_dict",
    ]}
    with patch.object(adapter, "_discover_agent_card", return_value=card):
        tools = adapter.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "do_thing"
    assert isinstance(tools[0], ToolDefinition)


def test_a2a_execute_success():
    """a2a_adapter.py — execute() returns ok on successful JSON-RPC response."""
    from app.services.aee.a2a_adapter import A2AAdapter

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter.agent_url = "https://agent.example.com"
        adapter.bearer_token = "tok"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "result": "done"}
        mock_client.post.return_value = mock_response
        adapter._client = mock_client

    result = adapter.execute("my_method", {"arg": 1})
    assert result.success is True


def test_a2a_execute_json_parse_error():
    """a2a_adapter.py — execute() returns fail when response.json() raises."""
    from app.services.aee.a2a_adapter import A2AAdapter

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter.agent_url = "https://agent.example.com"
        adapter.bearer_token = None
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("bad json")
        mock_client.post.return_value = mock_response
        adapter._client = mock_client

    result = adapter.execute("my_method", {})
    assert result.success is False
    assert "invalid JSON-RPC" in (result.error_message or "")


def test_a2a_execute_jsonrpc_error():
    """a2a_adapter.py — execute() returns fail on JSON-RPC error body."""
    from app.services.aee.a2a_adapter import A2AAdapter

    with patch("app.services.aee.a2a_adapter._validate_agent_url"):
        adapter = A2AAdapter.__new__(A2AAdapter)
        adapter.agent_url = "https://agent.example.com"
        adapter.bearer_token = None
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"error": {"message": "method not found"}}
        mock_client.post.return_value = mock_response
        adapter._client = mock_client

    result = adapter.execute("my_method", {})
    assert result.success is False
    assert "jsonrpc_error" in (result.error_message or "")


# ---------------------------------------------------------------------------
# app.services.aee.cli_adapter — lines 45, 84, 100-110, 178-181, 203, 212-215, 224, 228-235, 246-247, 253-257
# ---------------------------------------------------------------------------


def test_cli_detect_language_python():
    """cli_adapter.py — _detect_language returns python3 for python script."""
    from app.services.aee.cli_adapter import _detect_language

    result = _detect_language("def hello(): pass")
    assert result == "python3"


def test_cli_list_tools_returns_list():
    """cli_adapter.py — list_tools() returns non-empty list."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    tools = adapter.list_tools()
    assert len(tools) >= 1
    assert tools[0].name == "get_shipping"


def test_cli_execute_known_tool():
    """cli_adapter.py — execute known tool returns ok result."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    result = adapter.execute("get_shipping", {"order_id": "123"})
    assert result.success is True


def test_cli_execute_unknown_tool():
    """cli_adapter.py — execute unknown tool returns fail."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    result = adapter.execute("does_not_exist", {})
    assert result.success is False
    assert "unknown tool" in (result.error_message or "")


def test_cli_execute_exception():
    """cli_adapter.py — execute exception returns fail."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    with patch.object(adapter, "_resolve_tool", side_effect=RuntimeError("boom")):
        result = adapter.execute("get_shipping", {})
    assert result.success is False


def test_cli_run_with_timeout_file_not_found():
    """cli_adapter.py — _run_with_timeout returns fail on FileNotFoundError."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    with patch("subprocess.run", side_effect=FileNotFoundError("interpreter not found")):
        result = adapter._run_with_timeout(["nonexistent_interpreter", "-c", "pass"], None)
    assert result.success is False
    assert "interpreter not found" in (result.error_message or "")


def test_cli_run_with_timeout_generic_exception():
    """cli_adapter.py — _run_with_timeout returns fail on generic exception."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    with patch("subprocess.run", side_effect=OSError("perm denied")):
        result = adapter._run_with_timeout(["bad_cmd", "-c", "pass"], None)
    assert result.success is False
    assert "subprocess error" in (result.error_message or "")


def test_cli_run_with_external_kill_unknown_signal():
    """cli_adapter.py — _run_with_external_kill returns fail for unknown signal."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    result = adapter._run_with_external_kill(["python3", "-c", "import time; time.sleep(1)"], "SIGNOEXIST", 2.0)
    assert result.success is False
    assert "unknown signal" in (result.error_message or "")


def test_cli_run_with_external_kill_file_not_found():
    """cli_adapter.py — _run_with_external_kill returns fail on FileNotFoundError."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    with patch("subprocess.Popen", side_effect=FileNotFoundError("interp")):
        result = adapter._run_with_external_kill(["bad_interp", "-c", "pass"], "SIGTERM", 2.0)
    assert result.success is False
    assert "interpreter not found" in (result.error_message or "")


def test_cli_run_with_external_kill_generic_popen_exception():
    """cli_adapter.py — _run_with_external_kill returns fail on generic Popen exception."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    with patch("subprocess.Popen", side_effect=OSError("perm")):
        result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGTERM", 2.0)
    assert result.success is False
    assert "subprocess error" in (result.error_message or "")


def test_cli_run_with_external_kill_process_done_before_kill():
    """cli_adapter.py — _run_with_external_kill returns fail when process finishes before kill."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    with patch("subprocess.Popen", return_value=mock_proc), patch("time.sleep"):
        result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGTERM", 2.0)
    assert result.success is False
    assert "completed before kill" in (result.error_message or "")


def test_cli_run_with_external_kill_timeout_expired():
    """cli_adapter.py — _run_with_external_kill returns fail on TimeoutExpired."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(["p"], 1.0)
    with patch("subprocess.Popen", return_value=mock_proc), patch("time.sleep"):
        result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGTERM", 1.0)
    assert result.success is False
    assert "timeout" in (result.error_message or "")


def test_cli_run_with_external_kill_value_error_in_signal():
    """cli_adapter.py — _run_with_external_kill uses signal name on ValueError."""
    import signal as sig_mod

    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.communicate.return_value = ("stdout", "stderr")
    mock_proc.returncode = -9
    with patch("subprocess.Popen", return_value=mock_proc), patch("time.sleep"):
        with patch.object(sig_mod, "Signals", side_effect=ValueError("bad")):
            result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGKILL", 2.0)
    assert result.success is False
    assert "killed" in (result.error_message or "").lower() or "signal" in (result.error_message or "").lower()


def test_cli_run_with_external_kill_returncode_zero():
    """cli_adapter.py — _run_with_external_kill returns ok when returncode=0."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.communicate.return_value = ("output_text", "")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc), patch("time.sleep"):
        result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGTERM", 2.0)
    assert result.success is True


def test_cli_run_with_external_kill_returncode_nonzero():
    """cli_adapter.py — _run_with_external_kill returns fail when returncode > 0."""
    from app.services.aee.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.communicate.return_value = ("", "error output")
    mock_proc.returncode = 1
    with patch("subprocess.Popen", return_value=mock_proc), patch("time.sleep"):
        result = adapter._run_with_external_kill(["python3", "-c", "pass"], "SIGTERM", 2.0)
    assert result.success is False


# ---------------------------------------------------------------------------
# app.services.aee.mcp_adapter — lines 66, 68, 82, 88, 95-100, 117-155, 171-180, 190-199, 215-219, 227
# ---------------------------------------------------------------------------


def test_mcp_list_tools_unsupported_transport():
    """mcp_adapter.py — list_tools() returns [] for unsupported transport."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="grpc")
    tools = adapter.list_tools()
    assert tools == []


def test_mcp_list_tools_exception_returns_empty():
    """mcp_adapter.py — list_tools() returns [] on exception."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="echo")
    with patch.object(adapter, "_connect_stdio", side_effect=RuntimeError("bang")):
        tools = adapter.list_tools()
    assert tools == []


def test_mcp_execute_stdio_unknown_tool():
    """mcp_adapter.py — execute() returns fail when tool not in list."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="echo")
    with patch.object(adapter, "_connect_stdio", return_value=[]):
        result = adapter.execute("no_such_tool", {})
    assert result.success is False
    assert "unknown tool" in (result.error_message or "")


def test_mcp_execute_stdio_success():
    """mcp_adapter.py — execute() returns ok on stdio success."""
    from app.services.aee.adapter import ToolDefinition
    from app.services.aee.mcp_adapter import MCPAdapter

    tool = ToolDefinition(name="my_tool", description="t", parameters_schema={}, protocol="mcp", handler_ref="r")
    adapter = MCPAdapter(transport="stdio", command="echo")
    with patch.object(adapter, "_connect_stdio", return_value=[tool]):
        with patch.object(adapter, "_execute_stdio_call", return_value={"result": "ok"}):
            result = adapter.execute("my_tool", {})
    assert result.success is True


def test_mcp_execute_sse_success():
    """mcp_adapter.py — execute() returns ok on SSE success."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com")
    with patch.object(adapter, "_execute_sse_call", return_value={"data": "x"}):
        result = adapter.execute("tool1", {})
    assert result.success is True


def test_mcp_execute_sse_generic_exception():
    """mcp_adapter.py — execute() returns fail on generic SSE exception."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com")
    with patch.object(adapter, "_execute_sse_call", side_effect=RuntimeError("sse fail")):
        result = adapter.execute("tool1", {})
    assert result.success is False


def test_mcp_execute_unsupported_transport():
    """mcp_adapter.py — execute() returns fail for unsupported transport."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="grpc", command="cmd")
    result = adapter.execute("tool1", {})
    assert result.success is False
    assert "unsupported transport" in (result.error_message or "")


def test_mcp_execute_timeout_error():
    """mcp_adapter.py — execute() returns fail on TimeoutError."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="cmd")
    with patch.object(adapter, "_connect_stdio", side_effect=TimeoutError("timed out")):
        result = adapter.execute("tool1", {})
    assert result.success is False
    assert "timeout" in (result.error_message or "")


def test_mcp_execute_generic_exception():
    """mcp_adapter.py — execute() returns fail on generic exception."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="cmd")
    with patch.object(adapter, "_connect_stdio", side_effect=Exception("crash")):
        result = adapter.execute("tool1", {})
    assert result.success is False


def test_mcp_execute_stdio_call_success():
    """mcp_adapter.py — _execute_stdio_call returns parsed JSON on success."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="echo test")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b'{"result": "ok"}', b"")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc):
        result = adapter._execute_stdio_call("tool1", {"arg": "val"})
    assert result == {"result": "ok"}


def test_mcp_execute_stdio_call_timeout():
    """mcp_adapter.py — _execute_stdio_call raises TimeoutError on timeout."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="sleep 999", connect_timeout_ms=100)
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(["sleep"], 0.1)
    mock_proc.kill = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc), pytest.raises(TimeoutError):
        adapter._execute_stdio_call("tool1", {})


def test_mcp_execute_stdio_call_nonzero_returncode():
    """mcp_adapter.py — _execute_stdio_call raises RuntimeError on nonzero exit."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="false_cmd")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"", b"error message")
    mock_proc.returncode = 1
    with patch("subprocess.Popen", return_value=mock_proc), pytest.raises(RuntimeError):
        adapter._execute_stdio_call("tool1", {})


def test_mcp_execute_stdio_call_json_decode_error():
    """mcp_adapter.py — _execute_stdio_call returns raw dict on JSON parse failure."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="echo")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"not valid json!", b"")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc):
        result = adapter._execute_stdio_call("tool1", {})
    assert "raw" in result


def test_mcp_connect_stdio_timeout():
    """mcp_adapter.py — _connect_stdio returns [] on TimeoutExpired."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="slow_server")
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(["slow_server"], 2.0)
    mock_proc.kill = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc):
        tools = adapter._connect_stdio()
    assert tools == []


def test_mcp_connect_stdio_nonzero_returncode():
    """mcp_adapter.py — _connect_stdio returns [] on non-zero exit."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="bad_server")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 1
    with patch("subprocess.Popen", return_value=mock_proc):
        tools = adapter._connect_stdio()
    assert tools == []


def test_mcp_connect_stdio_success():
    """mcp_adapter.py — _connect_stdio returns [] (stub parser) on success."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="mcp_server")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b'[]', b"")
    mock_proc.returncode = 0
    with patch("subprocess.Popen", return_value=mock_proc):
        tools = adapter._connect_stdio()
    assert tools == []


def test_mcp_connect_sse_error_status():
    """mcp_adapter.py — _connect_sse returns [] on HTTP 4xx."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com/tools")
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    with patch("httpx.Client", return_value=mock_client):
        tools = adapter._connect_sse()
    assert tools == []


def test_mcp_connect_sse_success():
    """mcp_adapter.py — _connect_sse returns [] (stub parser) on 200."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com/tools")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"[]"
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    with patch("httpx.Client", return_value=mock_client):
        tools = adapter._connect_sse()
    assert tools == []


def test_mcp_connect_sse_exception():
    """mcp_adapter.py — _connect_sse returns [] on exception."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com")
    with patch("httpx.Client", side_effect=RuntimeError("no httpx")):
        tools = adapter._connect_sse()
    assert tools == []


def test_mcp_execute_sse_call_json_fallback():
    """mcp_adapter.py — _execute_sse_call returns raw on JSON error."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="sse", url="http://example.com")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.side_effect = ValueError("bad")
    mock_response.text = "plain text"
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    with patch("httpx.Client", return_value=mock_client):
        result = adapter._execute_sse_call("tool1", {})
    assert result == {"raw": "plain text"}


def test_mcp_parse_tool_list_returns_empty():
    """mcp_adapter.py — _parse_tool_list always returns []."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter()
    result = adapter._parse_tool_list(b'some bytes')
    assert result == []


# ---------------------------------------------------------------------------
# app.core.paladin — lines 364, 509, 631-632, 640, 642, 795, 800, 1088
# ---------------------------------------------------------------------------


def test_paladin_build_sandwich_prompt_non_str():
    """paladin.py — build_sandwich_prompt raises TypeError for non-str user_text."""
    from app.core.paladin import PromptInjectionDefense

    defense = PromptInjectionDefense()
    with pytest.raises(TypeError, match="requires str user_text"):
        defense.build_sandwich_prompt(123)


def test_paladin_semantic_classifier_classify_async_non_str():
    """paladin.py — SemanticInjectionClassifier.classify_async raises TypeError."""
    import asyncio

    from app.core.paladin import SemanticInjectionClassifier

    classifier = SemanticInjectionClassifier()
    with pytest.raises(TypeError, match="requires str text"):
        asyncio.run(classifier.classify_async(123, risk_level="high"))


def test_paladin_await_coro_from_sync_reraises_exception():
    """paladin.py — _await_coro_from_sync re-raises exceptions from coro."""
    import asyncio

    from app.core.paladin import _await_coro_from_sync

    async def bad_coro():
        raise ValueError("bad thing")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with pytest.raises(ValueError, match="bad thing"):
            _await_coro_from_sync(bad_coro(), timeout_ms=1000)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_paladin_grounding_checker_no_embedding():
    """paladin.py — GroundingChecker.check raises TypeError when output_embedding is None."""
    from app.core.paladin import GroundingChecker

    checker = GroundingChecker()
    with pytest.raises(TypeError, match="requires output_embedding or response"):
        checker.check(output_embedding=None, source_texts=["text"])


def test_paladin_grounding_checker_non_iterable():
    """paladin.py — GroundingChecker.check raises TypeError for non-iterable embedding."""
    from app.core.paladin import GroundingChecker

    checker = GroundingChecker()
    with pytest.raises(TypeError, match="requires iterable output_embedding"):
        checker.check(output_embedding=42, source_texts=["text"])


def test_webui_store_with_context_manager_session():
    """webui.py — _store() uses context manager when db_session has __enter__."""
    from app.admin.webui import KnowledgeAdminAPI

    mock_store = MagicMock()
    mock_store.get.return_value = None
    mock_store.__enter__ = MagicMock(return_value=mock_store)
    mock_store.__exit__ = MagicMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_store)
    api = KnowledgeAdminAPI(db_session=mock_session_factory)
    result = api.read_entry(999)
    assert result is None


def test_webui_store_without_context_manager():
    """webui.py — _store() yields session directly when no __enter__."""
    from app.admin.webui import KnowledgeAdminAPI

    mock_store = MagicMock(spec=[])
    mock_store.get = MagicMock(return_value=None)
    mock_session_factory = MagicMock(return_value=mock_store)
    api = KnowledgeAdminAPI(db_session=mock_session_factory)
    result = api.read_entry(999)
    assert result is None


def test_webui_update_entry_returns_none_not_found():
    """webui.py — update_entry returns None when entry not found."""
    from app.admin.webui import KnowledgeAdminAPI

    api = KnowledgeAdminAPI()
    result = api.update_entry(99999, title="new")
    assert result is None




def test_webui_saved_threshold_config_store_returns_none():
    """webui.py — _saved_threshold falls through to module when config_store returns None."""
    from app.admin.webui import RAGDebugger

    mock_store = MagicMock()
    mock_store.get.return_value = None
    debugger = RAGDebugger(config_store=mock_store)
    result = debugger._saved_threshold()
    assert isinstance(result, float)


def test_webui_saved_threshold_config_store_raises():
    """webui.py — _saved_threshold falls through to module on exception."""
    from app.admin.webui import RAGDebugger

    mock_store = MagicMock()
    mock_store.get.side_effect = RuntimeError("store error")
    debugger = RAGDebugger(config_store=mock_store)
    result = debugger._saved_threshold()
    assert isinstance(result, float)


def test_websocket_verify_jwt_header_decode_exception():
    """websocket.py — verify_jwt returns False when header decode raises."""
    from app.api.websocket import verify_jwt

    bad_header = "!!!.e30.sig"
    result = verify_jwt(bad_header)
    assert result is False


def test_websocket_verify_jwt_valid_and_expired():
    """websocket.py — verify_jwt returns False for expired token."""
    import base64 as _b64
    import hashlib as _hashlib
    import hmac as _hmac
    import json as _json
    import os as _os

    from app.api.websocket import verify_jwt

    secret = _os.environ.get("OMNIBOT_JWT_SECRET", "dev-secret-do-not-use-in-prod").encode()
    header = _b64.urlsafe_b64encode(_json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    payload_data = {"sub": "u1", "exp": int(time.time()) - 10}
    payload = _b64.urlsafe_b64encode(_json.dumps(payload_data).encode()).rstrip(b"=").decode()
    msg = f"{header}.{payload}".encode("ascii")
    sig = _b64.urlsafe_b64encode(_hmac.new(secret, msg, _hashlib.sha256).digest()).rstrip(b"=").decode()
    token = f"{header}.{payload}.{sig}"
    result = verify_jwt(token)
    assert result is False


def test_websocket_verify_jwt_valid_not_expired():
    """websocket.py — verify_jwt returns True for valid unexpired token."""
    import base64 as _b64
    import hashlib as _hashlib
    import hmac as _hmac
    import json as _json
    import os as _os

    from app.api.websocket import verify_jwt

    secret = _os.environ.get("OMNIBOT_JWT_SECRET", "dev-secret-do-not-use-in-prod").encode()
    header = _b64.urlsafe_b64encode(_json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    payload_data = {"sub": "u1", "exp": int(time.time()) + 3600}
    payload = _b64.urlsafe_b64encode(_json.dumps(payload_data).encode()).rstrip(b"=").decode()
    msg = f"{header}.{payload}".encode("ascii")
    sig = _b64.urlsafe_b64encode(_hmac.new(secret, msg, _hashlib.sha256).digest()).rstrip(b"=").decode()
    token = f"{header}.{payload}.{sig}"
    result = verify_jwt(token)
    assert result is True


def test_websocket_register_connection_empty_id():
    """websocket.py — register_connection with empty id returns early."""
    from app.api.websocket import register_connection

    register_connection("")


def test_websocket_unregister_connection_empty_id():
    """websocket.py — unregister_connection with empty id returns early."""
    from app.api.websocket import unregister_connection

    unregister_connection("")


def test_websocket_is_subscribed_empty_ids():
    """websocket.py — is_subscribed returns False when connection_id is empty."""
    from app.api.websocket import is_subscribed

    result = is_subscribed("", "some-channel")
    assert result is False


# ---------------------------------------------------------------------------
# app.api.webhooks — lines 195, 200-227, 308, 312, 318-321, 440, 444, 622, 727, 731, 778-779, 912, 1006-1031, 1143, 1345
# ---------------------------------------------------------------------------


def test_webhooks_web_jwt_verifier_valid_token():
    """webhooks.py — WebJwtVerifier.verify returns True for valid HS256 token."""
    import base64 as _b64
    import hashlib as _hashlib
    import hmac as _hmac
    import json as _json

    from app.api.adapters.verifiers import WebJwtVerifier

    secret = "test-jwt-secret"
    verifier = WebJwtVerifier(jwt_secret=secret)
    header = _b64.urlsafe_b64encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload_data = {"sub": "user1", "exp": int(time.time()) + 3600}
    payload = _b64.urlsafe_b64encode(_json.dumps(payload_data).encode()).rstrip(b"=").decode()
    signing_input = f"{header}.{payload}".encode("ascii")
    sig = _b64.urlsafe_b64encode(_hmac.new(secret.encode(), signing_input, _hashlib.sha256).digest()).rstrip(b"=").decode()
    token = f"{header}.{payload}.{sig}"
    result = verifier.verify(token)
    assert result is True


def test_webhooks_validate_token_data_none():
    """webhooks.py — validate_token returns False when data is None for known client."""
    from app.api import webhooks as wh_mod

    fake_hash = hashlib.sha256(b"orphan_test_token").hexdigest()
    original_lookup = dict(wh_mod._HASH_LOOKUP)
    original_store = dict(wh_mod._TOKEN_STORE)
    try:
        wh_mod._HASH_LOOKUP[fake_hash] = "orphan_client_id_xyz"
        result = wh_mod.validate_token("orphan_test_token")
        assert result is False
    finally:
        wh_mod._HASH_LOOKUP.clear()
        wh_mod._HASH_LOOKUP.update(original_lookup)
        wh_mod._TOKEN_STORE.clear()
        wh_mod._TOKEN_STORE.update(original_store)


def test_webhooks_web_process_message_invalid_token():
    """webhooks.py — WebAdapter.process_message raises WebAuthError on invalid token."""
    from app.api.adapters.web import WebAdapter, WebAuthError

    adapter = WebAdapter(jwt_secret="secret")
    with pytest.raises(WebAuthError):
        adapter.process_message("invalid.jwt.token", "hello content")


# ---------------------------------------------------------------------------
# app.core.knowledge — lines 239, 297, 393-396, 445-446, 486, 498, 509, 517, 578, 641-649, 691-695, 704, 773, 785-786, 911, 916, 918, 928, 1038, 1060-1070, 1099, 1102
# ---------------------------------------------------------------------------


def test_knowledge_compute_grounding_score_non_str():
    """knowledge.py — _compute_grounding_score returns None for non-string inputs."""
    from app.core.knowledge import _compute_grounding_score

    result = _compute_grounding_score(None, "context")
    assert result is None


def test_knowledge_compute_grounding_score_empty_string():
    """knowledge.py — _compute_grounding_score returns None for empty strings."""
    from app.core.knowledge import _compute_grounding_score

    result = _compute_grounding_score("", "context")
    assert result is None


def test_knowledge_compute_grounding_score_valid():
    """knowledge.py — _compute_grounding_score returns 1.0 for non-empty inputs."""
    from app.core.knowledge import _compute_grounding_score

    result = _compute_grounding_score("answer text", "retrieved context")
    assert result == 1.0


def test_knowledge_parent_child_add_link_empty_content():
    """knowledge.py — ParentChildIndex.add_link raises ValueError on empty parent_content."""
    from app.core.knowledge import ParentChildIndex

    idx = ParentChildIndex()
    with pytest.raises(ValueError, match="non-empty parent_content"):
        idx.add_link(parent_id="p1", parent_content="", child_id="c1")


def test_knowledge_parent_child_add_parent_wrong_chunk_type():
    """knowledge.py — ParentChildIndex.add_parent raises ValueError on wrong chunk_type."""
    from app.core.knowledge import Chunk, ParentChildIndex

    idx = ParentChildIndex()
    bad_chunk = Chunk(chunk_id="c1", content="content", chunk_type="child", parent_id=None, token_count=1)
    with pytest.raises(ValueError, match="chunk_type='parent'"):
        idx.add_parent(bad_chunk)


def test_knowledge_parent_child_add_parent_empty_content():
    """knowledge.py — ParentChildIndex.add_parent raises ValueError on empty content."""
    from app.core.knowledge import Chunk, ParentChildIndex

    idx = ParentChildIndex()
    empty_chunk = Chunk(chunk_id="p1", content="", chunk_type="parent", parent_id=None, token_count=0)
    with pytest.raises(ValueError, match="non-empty content"):
        idx.add_parent(empty_chunk)


def test_knowledge_parent_child_add_parent_success():
    """knowledge.py — ParentChildIndex.add_parent stores parent correctly."""
    from app.core.knowledge import Chunk, ParentChildIndex

    idx = ParentChildIndex()
    parent = Chunk(chunk_id="p1", content="Parent content here", chunk_type="parent", parent_id=None, token_count=3)
    idx.add_parent(parent)
    assert "p1" in idx._parents



# =====================================================================
# Batch 3: remaining missing lines (2026-06-22 post-arch-refactor)
# =====================================================================

# --- app.core.knowledge.py:239 ---


def test_knowledge_score_exact_match_type():
    """_score returns CONFIDENCE_EXACT when match_type='exact'."""
    from app.core.knowledge import HybridKnowledge

    class Row:
        match_type = "exact"
        content = "anything"
    assert HybridKnowledge._score(Row(), "whatever") == HybridKnowledge.CONFIDENCE_EXACT


def test_knowledge_score_partial_match_type():
    """_score returns CONFIDENCE_PARTIAL when match_type='partial'."""
    from app.core.knowledge import HybridKnowledge

    class Row:
        match_type = "partial"
        content = "anything"
    assert HybridKnowledge._score(Row(), "whatever") == HybridKnowledge.CONFIDENCE_PARTIAL


# --- app.core.knowledge.py:297 ---


def test_knowledge_rag_search_low_confidence_returns_none():
    """_rag_search returns None when confidence < RAG_CONFIDENCE_THRESHOLD."""
    from app.core.knowledge import HybridKnowledge

    hk = HybridKnowledge()
    assert hk._rag_search("q", confidence=0.01) is None


# --- app.core.knowledge.py:393-396 ---


def test_knowledge_embedding_api_available_with_client_available():
    """_embedding_api_available returns client.available when client exists."""
    from app.core.knowledge import HybridKnowledge

    hk = HybridKnowledge()
    hk._embedding_client = type("obj", (), {"available": False})()
    assert hk._embedding_api_available() is False
    hk._embedding_client = type("obj", (), {"available": True})()
    assert hk._embedding_api_available() is True


# --- app.core.knowledge.py:445-446, 486, 498, 509, 517 ---


def test_knowledge_record_tier_hit_sufficient_confidence():
    """_record_tier_hit assigns tier_sequence and returns result when confident."""
    from app.core.knowledge import HybridKnowledge, KnowledgeResult

    hk = HybridKnowledge()
    seq = []
    kr = KnowledgeResult(id=1, content="ctx", confidence=0.9, source="rule", knowledge_id=1)
    result = hk._record_tier_hit(seq, "t1", kr, HybridKnowledge.CONFIDENCE_THRESHOLD)
    assert result is kr
    assert kr.tier_sequence == ["t1"]


# --- app.core.knowledge.py:911, 916, 918, 928 ---


def test_slice_tokens_normal():
    """_slice_tokens produces chunks for valid inputs."""
    from app.core.knowledge import _slice_tokens

    tokens = ["hello", " ", "world", " ", "test", " ", "more", " ", "words"]
    chunks = _slice_tokens(tokens, size=3, prefix="p", chunk_type="child", parent_id_for=lambda i, s: None)
    assert len(chunks) >= 2


# --- app.core.paladin.py:758-763, 1088 ---


def test_grounding_checker_with_response_text_based():
    """GroundingChecker.check returns grounded=True stub when response is given."""
    from app.core.paladin import GroundingChecker, GroundingResult

    checker = GroundingChecker()
    result = checker.check(response="text1 text2", sources=["text1", "text2"])
    assert isinstance(result, GroundingResult)
    assert result.grounded is True


def test_paladin_pipeline_process_unknown_risk():
    """PALADINPipeline raises ValueError for unknown risk_level."""
    import asyncio

    from app.core.paladin import PALADINPipeline
    pipeline = PALADINPipeline()
    with pytest.raises(ValueError, match="unknown risk_level"):
        asyncio.run(pipeline.process("hello", risk_level="not_a_real_level"))


# --- app.infra.deployment.py:703-706 ---


def test_deployment_rollback_ab_test_above_threshold():
    """RollbackStrategy.ab_test_progress rolls back when metric_drop > threshold."""
    from app.infra.deployment import RollbackStrategy

    rs = RollbackStrategy()
    result = rs.ab_test_progress(metric_drop_pct=99.0)
    assert result.rolled_back is True


def test_deployment_rollback_ab_test_below_threshold():
    """RollbackStrategy.ab_test_progress does not roll back when metric_drop <= threshold."""
    from app.infra.deployment import RollbackStrategy

    rs = RollbackStrategy()
    result = rs.ab_test_progress(metric_drop_pct=1.0)
    assert result.rolled_back is False


# --- app.services.ab_testing.py:298 ---


def test_collect_variant_means_skip_empty_variant():
    """_collect_variant_means skips (continues past) zero-observation variants."""
    from app.services.ab_testing import ABTestManager

    means, total = ABTestManager._collect_variant_means(
        {"A": [], "B": [0.5, 0.6], "C": []}
    )
    assert total == 2
    variant_names = {v for v, _ in means}
    assert "A" not in variant_names
    assert "C" not in variant_names
    assert "B" in variant_names


# --- app.services.aee.tool_executor.py:71 ---


def test_validate_handler_callable_class_instance_raises():
    """_validate_handler raises TypeError for callable non-function/method."""
    from app.services.aee.tool_executor import _validate_handler

    class CallMe:
        def __call__(self):
            pass

    with pytest.raises(TypeError, match="safety whitelist"):
        _validate_handler(CallMe(), context="test")


# --- app.services.aee.tool_executor.py:144 ---


def test_update_shipping_address_handler_blocked_status():
    """_update_shipping_address_handler returns fail for shipped/delivered status."""
    from app.services.aee.tool_executor import _update_shipping_address_handler

    result = _update_shipping_address_handler("o1", "addr", status="shipped")
    assert result.success is False


def test_update_shipping_address_handler_ok():
    """_update_shipping_address_handler returns ok for allowed status."""
    from app.services.aee.tool_executor import _update_shipping_address_handler

    result = _update_shipping_address_handler("o1", "addr", status="processing")
    assert result.success is True


# --- app.services.llm_judge.py:324, 581, 625 ---


@pytest.mark.asyncio
async def test_llm_judge_evaluate_both_safely_none():
    """evaluate returns degraded JudgeResult when both judges return None."""
    from app.services.llm_judge import JudgeResult, LLMJudge

    judge = LLMJudge()
    with patch.object(judge, "_invoke_safely", new=AsyncMock(return_value=None)):
        result = await judge.evaluate("msg", "resp")
    assert isinstance(result, JudgeResult)
    assert result.judge_name == "degraded"


def test_calibration_agreement_rate_empty():
    """_agreement_rate returns None for empty golden_set."""
    from app.services.llm_judge import CalibrationPipeline

    cp = CalibrationPipeline(judge_llm=AsyncMock(), kappa_cache=None, timeout_s=5)
    assert cp._agreement_rate([]) is None


# --- app.services.media.py:210, 230-235, 365-372 ---


def test_media_pipeline_process_file_clamav_ok():
    """process_file returns AUTO_ESCALATE when ClamAV scan returns OK."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_AUTO_ESCALATE,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    fake = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=fake):
        result = pipeline.process_file(0.5, "txt", b"x")
    assert result.action == MEDIA_ACTION_AUTO_ESCALATE


def test_clamav_scanner_scan_holder_error():
    """ClamAVScanner.scan returns UNAVAILABLE when _runner raises Exception."""
    from app.services.media import CLAMAV_STATUS_UNAVAILABLE, ClamAVScanner

    scanner = ClamAVScanner()
    # Force the runner to raise
    scanner._runner = MagicMock(side_effect=RuntimeError("boom"))
    result = scanner.scan(b"x", "txt")
    assert result.status == CLAMAV_STATUS_UNAVAILABLE


# --- app.api.websocket.py:584-585 ---


def test_websocket_dummy_api_cohesion():
    """_dummy_api_cohesion calls imports without error."""
    from app.api.websocket import _dummy_api_cohesion
    _dummy_api_cohesion()


# =====================================================================
# Batch 4: precision-targeted tests (verified line-by-line, 2026-06-22)
# =====================================================================

# --- knowledge.py:239 (_score fallback when match_type not set) ---


def test_knowledge_score_fallback_no_match_type():
    """_score hits fallback when row has no match_type attribute."""
    from app.core.knowledge import HybridKnowledge

    class Row:
        content = "hello"

    assert HybridKnowledge._score(Row(), "hello") == HybridKnowledge.CONFIDENCE_EXACT
    assert HybridKnowledge._score(Row(), "different") == HybridKnowledge.CONFIDENCE_PARTIAL


# --- knowledge.py:297 (_rag_search returns None when confidence=None) ---


def test_knowledge_rag_search_confidence_none():
    """_rag_search returns None when confidence is None."""
    from app.core.knowledge import HybridKnowledge

    hk = HybridKnowledge()
    assert hk._rag_search("q", confidence=None) is None


# --- knowledge.py:395 (embedding_api_available returns True when no client) ---


def test_knowledge_embedding_api_available_no_client():
    """_embedding_api_available returns True when _embedding_client is None."""
    from app.core.knowledge import HybridKnowledge

    hk = HybridKnowledge()
    # _embedding_client is not set by default → returns True
    assert hk._embedding_api_available() is True


# --- knowledge.py:691-695 (_llm_generate catches exception from LLM) ---


def test_llm_generate_exception_returns_none():
    """_llm_generate returns None when _call_llm_with_fallback raises Exception."""
    from app.core.knowledge import _llm_generate

    with patch("app.core.knowledge._call_llm_with_fallback", side_effect=Exception("both down")):
        result = _llm_generate("q", "ctx")
    assert result is None


# --- knowledge.py:704 (grounding_score computed when caller passes None) ---


def test_llm_generate_grounding_score_computed():
    """_llm_generate computes grounding_score when provider passes None."""
    from app.core.knowledge import _llm_generate

    with patch("app.core.knowledge._call_llm_with_fallback", return_value="answer"), \
         patch("app.core.knowledge._compute_grounding_score", return_value=0.9) as mock_gs:
        result = _llm_generate("q", "ctx", grounding_score=None, grounding_threshold=0.75)
    mock_gs.assert_called_once_with("answer", "ctx")
    assert result is not None
    assert result.confidence >= 0.75


# --- knowledge.py:773,785-786 (escalate ValueError and json.dumps fallback) ---


def test_escalate_bad_reason_raises():
    """escalate raises ValueError for unrecognised reason."""
    from app.core.knowledge import escalate

    with pytest.raises(ValueError, match="invalid escalate reason"):
        escalate(None, None, None, reason="bad_reason_xyz")


def test_escalate_json_fallback():
    """escalate uses f-string fallback when json.dumps raises."""
    from app.core.knowledge import KnowledgeResult, escalate

    with patch("app.core.knowledge.json.dumps", side_effect=TypeError("cannot serialize")):
        result = escalate(None, None, None, reason="low_confidence")
    assert isinstance(result, KnowledgeResult)
    assert "low_confidence" in result.content


# --- a2a.py:114 (_validate_agent_url raises for no-hostname URL) ---


def test_validate_agent_url_no_hostname_raises():
    """_validate_agent_url raises ValueError when URL has no hostname."""
    from app.services.aee.a2a_adapter import _validate_agent_url

    with pytest.raises(ValueError, match="must include a hostname"):
        _validate_agent_url("http://")


# --- a2a.py:75 (_resolve_addresses returns list) ---


def test_resolve_addresses_localhost():
    """_resolve_addresses returns list of IPs for localhost."""
    from app.services.aee.a2a_adapter import _resolve_addresses

    ips = _resolve_addresses("localhost")
    assert isinstance(ips, list)
    assert len(ips) > 0


# --- a2a.py:190 (close method) ---


def test_a2a_adapter_close_calls_client_close():
    """A2AAdapter.close() calls self._client.close()."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter._client = MagicMock()
    adapter.close()
    adapter._client.close.assert_called_once()


# --- a2a.py:250-260 (_discover_agent_card HTTP success) ---


def test_a2a_discover_agent_card_http_200():
    """_discover_agent_card returns card dict on HTTP 200."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter.agent_url = "https://agent.example.com"
    adapter.bearer_token = None
    adapter.timeout = 2.0
    adapter.agent_card_ttl_seconds = 300
    adapter.agent_card_negative_ttl_seconds = 5
    adapter._card_cache = {}
    adapter.discovery_count = 0
    adapter._time_offset = 0.0
    adapter._now = lambda: 0.0
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"name": "TestAgent", "methods": [{"name": "say_hi", "description": "Greet"}]}
    mock_client.get.return_value = mock_resp
    adapter._client = mock_client

    card = adapter._discover_agent_card()
    assert card is not None
    assert card["name"] == "TestAgent"


# --- a2a.py:276-296 (list_tools converts card methods to ToolDefinitions) ---


def test_a2a_list_tools_from_card():
    """list_tools converts card methods into ToolDefinition list."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter.agent_url = "https://agent.example.com"
    card = {"methods": [
        {"name": "do_thing", "description": "does a thing"},
        {"name": "", "description": "empty name - skip"},
        "not_a_dict",
    ]}
    with patch.object(adapter, "_discover_agent_card", return_value=card):
        tools = adapter.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "do_thing"


# --- a2a.py:326,335-345 (execute JSON-RPC paths) ---


    """A2AAdapter.execute returns ok result on successful JSON-RPC call."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter.agent_url = "https://agent.example.com"
    adapter.bearer_token = "tok"
    adapter._time_offset = 0.0
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": "ok_value"}
    mock_client.post.return_value = mock_resp
    adapter._client = mock_client

    result = adapter.execute("my_tool", {"arg": 1})
    assert result.success is True


def test_a2a_execute_json_decode_error():
    """execute returns fail when response.json() raises ValueError."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter.agent_url = "https://agent.example.com"
    adapter.bearer_token = None
    adapter._time_offset = 0.0
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = ValueError("bad json")
    mock_client.post.return_value = mock_resp
    adapter._client = mock_client

    result = adapter.execute("my_tool", {})
    assert result.success is False


    """execute returns fail when response body contains JSON-RPC error."""
    from app.services.aee.a2a_adapter import A2AAdapter

    adapter = A2AAdapter.__new__(A2AAdapter)
    adapter.agent_url = "https://agent.example.com"
    adapter.bearer_token = None
    adapter._time_offset = 0.0
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"error": {"message": "method not found"}}
    mock_client.post.return_value = mock_resp
    adapter._client = mock_client

    result = adapter.execute("my_tool", {})
    assert result.success is False
    assert "jsonrpc_error" in (result.error_message or "")


# --- webui.py:366,370 (READ/UPDATE actions) ---


def test_webui_crud_read_action():
    """KnowledgeAdminAPI.crud returns dict for READ action."""
    from app.admin.webui import KNOWLEDGE_ACTION_READ, KnowledgeAdminAPI

    api = KnowledgeAdminAPI()
    result = api.crud(KNOWLEDGE_ACTION_READ, entry_id=0)
    assert isinstance(result, dict)


def test_webui_crud_update_action():
    """KnowledgeAdminAPI.crud returns dict for UPDATE action."""
    from app.admin.webui import KNOWLEDGE_ACTION_UPDATE, KnowledgeAdminAPI

    api = KnowledgeAdminAPI()
    result = api.crud(KNOWLEDGE_ACTION_UPDATE, entry_id=0, fields={})
    assert isinstance(result, dict)


# --- webui.py:411-413,434-436 (CSV import paths) ---


def test_webui_import_csv_bad_utf8():
    """import_csv returns ImportResult with decode error for bad UTF-8."""
    from app.admin.webui import KnowledgeAdminAPI

    api = KnowledgeAdminAPI()
    result = api.import_csv(b"\xff\xfe bad bytes")
    assert any("decode error" in e for e in result.errors)


def test_webui_import_csv_store_error():
    """import_csv counts skipped on store.add exception."""
    from app.admin.webui import KnowledgeAdminAPI

    store = MagicMock()
    store.add.side_effect = RuntimeError("db error")
    store.__enter__ = MagicMock(return_value=store)
    store.__exit__ = MagicMock(return_value=False)
    api = KnowledgeAdminAPI(db_session=MagicMock(return_value=store))
    result = api.import_csv(b"title,content,keywords\nt,c,k\n")
    assert result.skipped >= 1


# --- webui.py:539,544-545 (_saved_threshold paths) ---


def test_webui_saved_threshold_none_value():
    """RAGDebugger._saved_threshold falls through when store returns None."""
    from app.admin.webui import RAGDebugger

    store = MagicMock()
    store.get.return_value = None
    dbg = RAGDebugger(config_store=store)
    assert isinstance(dbg._saved_threshold(), float)


def test_webui_saved_threshold_store_exception():
    """RAGDebugger._saved_threshold catches store exceptions gracefully."""
    from app.admin.webui import RAGDebugger

    store = MagicMock()
    store.get.side_effect = RuntimeError("store error")
    dbg = RAGDebugger(config_store=store)
    assert isinstance(dbg._saved_threshold(), float)


# --- webui.py:600 (_fetch_metrics) ---


def test_webui_fetch_metrics():
    """OperationsDashboard._fetch_metrics returns dict with expected keys."""
    from app.admin.webui import OperationsDashboard

    dash = OperationsDashboard()
    result = dash._fetch_metrics("7d")
    assert "fcr" in result


# --- websocket.py:365-370 (subscription cleanup) ---


def test_websocket_unregister_cleans_subscriptions():
    """unregister_connection removes connection from channel subscribers (line 365-370)."""
    import app.api.websocket as wsmod

    cid = "test-conn-cleanup-xyz"
    channel = "test-channel-xyz"
    wsmod.register_connection(cid)
    wsmod._connection_subscriptions.setdefault(cid, set()).add(channel)
    wsmod._channel_subscribers.setdefault(channel, set()).add(cid)
    assert cid in wsmod._channel_subscribers.get(channel, set())
    wsmod.unregister_connection(cid)
    assert cid not in wsmod._channel_subscribers.get(channel, set())


# --- websocket.py:202-203 (verify_jwt header decode exception) ---


def test_websocket_verify_jwt_malformed_header():
    """verify_jwt returns False when header_b64 decode fails."""
    from app.api.websocket import verify_jwt

    assert verify_jwt("!!!bad.e30.sig") is False


# --- media.py:230-235 (ClamAV scan returncode branches) ---


def test_clamav_scanner_scan_ok():
    """ClamAVScanner.scan returns CLAMAV_STATUS_OK when runner exits 0."""
    from app.services.media import CLAMAV_STATUS_OK, ClamAVScanner

    scanner = ClamAVScanner()
    scanner._runner = lambda *a, **kw: type("R", (), {"returncode": 0})()
    r = scanner.scan(b"x", "txt")
    assert r.status == CLAMAV_STATUS_OK
    assert r.terminated is False


def test_clamav_scanner_scan_infected():
    """ClamAVScanner.scan returns infected when runner exits non-zero."""
    from app.services.media import _SCAN_STATUS_INFECTED, ClamAVScanner

    scanner = ClamAVScanner()
    scanner._runner = lambda *a, **kw: type("R", (), {"returncode": 1})()
    r = scanner.scan(b"x", "txt")
    assert r.status == _SCAN_STATUS_INFECTED


# --- media.py:367 (process_file gates pass → AUTO_ESCALATE) ---


def test_media_process_file_gates_pass():
    """MediaPipeline.process_file returns AUTO_ESCALATE when all checks pass."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_AUTO_ESCALATE,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    fake = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=fake):
        r = pipeline.process_file(0.5, "txt", b"x")
    assert r.action == MEDIA_ACTION_AUTO_ESCALATE


# --- paladin.py:631-632,640,642 (_await_coro_from_sync exception path) ---


def test_await_coro_from_sync_coro_exception():
    """_await_coro_from_sync re-raises exception from awaitable coroutine."""

    from app.core.paladin import _await_coro_from_sync
    async def fail_coro():
        raise RuntimeError("test failure in coro")

    with pytest.raises(RuntimeError, match="test failure in coro"):
        _await_coro_from_sync(fail_coro(), timeout_ms=2000)


# =====================================================================
# Batch 5: FR-traced boundary tests (SAD hub + remaining gaps)
# =====================================================================


# =====================================================================
# Batch 5: FR-06/FR-41 A2A adapter tests (RSA key + JWKS mock)
# =====================================================================



# Generate test key once at module level
_test_key = _rsa.generate_private_key(public_exponent=65537, key_size=1024)
_test_pub = _test_key.public_key()
_test_pub_nums = _test_pub.public_numbers()
_n_bytes = _test_pub_nums.n.to_bytes((_test_pub_nums.n.bit_length() + 7) // 8, "big")
_e_bytes = _test_pub_nums.e.to_bytes((_test_pub_nums.e.bit_length() + 7) // 8, "big")
_JWKS_RESPONSE = _json.dumps({
    "keys": [{
        "kty": "RSA",
        "n": _base64.urlsafe_b64encode(_n_bytes).rstrip(b"=").decode(),
        "e": _base64.urlsafe_b64encode(_e_bytes).rstrip(b"=").decode(),
        "kid": "test-kid-1",
    }]
}).encode()


def _make_jwt(payload_override=None):
    """Create an RS256-signed JWT token with the test key."""
    header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
    payload = {"sub": "test-agent", "exp": int(_time.time()) + 3600,
               "aud": "omnibot", "iss": "test-issuer"}
    if payload_override:
        payload.update(payload_override)
    hdr = _base64.urlsafe_b64encode(_json.dumps(header).encode()).rstrip(b"=").decode()
    pld = _base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
    msg = f"{hdr}.{pld}".encode("ascii")
    sig = _test_key.sign(msg, _padding.PKCS1v15(), _hashes.SHA256())
    sig64 = _base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{hdr}.{pld}.{sig64}"


# --- FR-06: verify_m2m_token expiry + aud/iss + JWKS success ---


def test_fr06_verify_m2m_token_expired():
    """FR-06: verify_m2m_token returns False when JWT is expired (line 154)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    expired = _make_jwt({"exp": int(_time.time()) - 3600})
    assert adapter.verify_m2m_token(f"Bearer {expired}") is False


def test_fr06_verify_m2m_token_wrong_audience():
    """FR-06: verify_m2m_token returns False on audience mismatch (line 158-159)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    wrong_aud = _make_jwt({"aud": "wrong-app"})
    assert adapter.verify_m2m_token(f"Bearer {wrong_aud}") is False


def test_fr06_verify_m2m_token_wrong_issuer():
    """FR-06: verify_m2m_token returns False on issuer mismatch (line 159-160)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot",
                         expected_issuer="correct-issuer")
    wrong_iss = _make_jwt({"iss": "wrong-issuer"})
    assert adapter.verify_m2m_token(f"Bearer {wrong_iss}") is False


def test_fr06_verify_m2m_token_valid():
    """FR-06: verify_m2m_token returns True for valid RS256-signed JWT (lines 162-184)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    valid = _make_jwt()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = _JWKS_RESPONSE
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        assert adapter.verify_m2m_token(f"Bearer {valid}") is True


def test_fr06_verify_m2m_token_urllib_error():
    """FR-06: verify_m2m_token returns False on urllib error (line 185-186)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://down.auth/jwks", expected_audience="omnibot")
    valid = _make_jwt()
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        assert adapter.verify_m2m_token(f"Bearer {valid}") is False


# --- FR-06: _extract_sub_from_token (lines 267, 271, 277-280) ---


def test_fr06_extract_sub_from_token_no_bearer():
    """FR-06: _extract_sub_from_token returns UNKNOWN_AGENT when no Bearer token (line 267)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    assert adapter._extract_sub_from_token("") == "unknown-agent"
    assert adapter._extract_sub_from_token("NotBearer xyz") == "unknown-agent"


def test_fr06_extract_sub_from_token_valid():
    """FR-06: _extract_sub_from_token returns sub claim from valid JWT (lines 277-280)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    valid = _make_jwt({"sub": "agent-42"})
    with patch.object(adapter, "verify_m2m_token", return_value=True):
        result = adapter._extract_sub_from_token(f"Bearer {valid}")
    assert result == "agent-42"


# --- reports.py:18 (SAD Hub build_report) ---


def test_build_report_returns_typed_dict():
    """SAD Hub: build_report returns type + status dict."""
    from app.admin.reports import build_report

    result = build_report("fcr", {"range": "7d"})
    assert result["type"] == "fcr"
    assert result["status"] == "generated"


# --- services/registry.py:13 (SAD Hub register_service) ---


def test_register_service_stores_and_retrieves():
    """SAD Hub: register_service + get_service round-trip."""
    import app.services.registry as reg

    reg.register_service("hub-test-svc", object())
    assert reg.get_service("hub-test-svc") is not None


# --- webui.py:539,544-545 (FR-102 RAGDebugger._saved_threshold) ---


def test_fr102_rag_debugger_saved_threshold_config_value():
    """FR-102: _saved_threshold returns float(value) when config_store returns non-None (line 539)."""
    from app.admin.webui import RAGDebugger

    store = MagicMock()
    store.get.return_value = 0.85
    dbg = RAGDebugger(config_store=store)
    assert dbg._saved_threshold() == 0.85


def test_fr102_rag_debugger_saved_threshold_config_none():
    """FR-102: _saved_threshold falls back to app.infra.config when store returns None (line 544-545)."""
    from app.admin.webui import RAGDebugger

    store = MagicMock()
    store.get.return_value = None
    dbg = RAGDebugger(config_store=store)
    t = dbg._saved_threshold()
    assert isinstance(t, float)
    assert t > 0


def test_fr102_rag_debugger_saved_threshold_config_raises():
    """FR-102: _saved_threshold falls through on store exception."""
    from app.admin.webui import RAGDebugger

    store = MagicMock()
    store.get.side_effect = RuntimeError("store error")
    dbg = RAGDebugger(config_store=store)
    assert isinstance(dbg._saved_threshold(), float)


# --- media.py:367 (FR-100 process_file gates pass → AUTO_ESCALATE) ---


def test_fr100_media_pipeline_process_file_gates_pass():
    """FR-100: process_file returns AUTO_ESCALATE when scan=OK and type=allowed."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_AUTO_ESCALATE,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    fake = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=fake):
        r = pipeline.process_file(0.5, "txt", b"x")
    assert r.action == MEDIA_ACTION_AUTO_ESCALATE


# --- websocket.py:202-203,367 (FR-59) ---


def test_fr59_verify_jwt_bad_header():
    """FR-59: verify_jwt returns False on malformed header."""
    from app.api.websocket import verify_jwt

    assert verify_jwt("!!!bad.e30.badsig") is False


def test_fr59_unregister_with_subscriptions():
    """FR-59: unregister_connection cleans channel subscriptions."""
    import app.api.websocket as wsmod

    cid = "fr59-test-cid"
    ch = "fr59-test-ch"
    wsmod.register_connection(cid)
    wsmod._connection_subscriptions.setdefault(cid, set()).add(ch)
    wsmod._channel_subscribers.setdefault(ch, set()).add(cid)
    wsmod.unregister_connection(cid)
    assert cid not in wsmod._channel_subscribers.get(ch, set())


# =====================================================================
# Batch 6: final coverage push
# =====================================================================

# --- knowledge.py:578 (NotImplementedError in _call_llm_api) ---


def test_call_llm_api_not_implemented():
    """FR-30: _call_llm_api raises NotImplementedError (production-only wiring)."""
    from app.core.knowledge import _call_llm_api

    with pytest.raises(NotImplementedError):
        _call_llm_api("gpt-4o", "test prompt")


# --- knowledge.py:911,916,918,928 (_slice_tokens validation) ---


def test_slice_tokens_empty_input():
    """_slice_tokens raises ValueError on empty tokens."""
    from app.core.knowledge import _slice_tokens

    with pytest.raises(ValueError, match="empty"):
        _slice_tokens([], size=100, prefix="p", chunk_type="child",
                       parent_id_for=lambda i, s: None)
    with pytest.raises(ValueError, match="empty"):
        _slice_tokens(["  "], size=100, prefix="p", chunk_type="child",
                       parent_id_for=lambda i, s: None)


def test_slice_tokens_invalid_size():
    """_slice_tokens raises ValueError when size <= 0."""
    from app.core.knowledge import _slice_tokens

    with pytest.raises(ValueError, match="size must be positive"):
        _slice_tokens(["a", "b"], size=0, prefix="p", chunk_type="child",
                       parent_id_for=lambda i, s: None)
    with pytest.raises(ValueError, match="size must be positive"):
        _slice_tokens(["a", "b"], size=-5, prefix="p", chunk_type="child",
                       parent_id_for=lambda i, s: None)


def test_slice_tokens_invalid_overlap():
    """_slice_tokens raises ValueError on invalid overlap values."""
    from app.core.knowledge import _slice_tokens

    with pytest.raises(ValueError, match="overlap"):
        _slice_tokens(["a", "b", "c"], size=3, overlap=3, prefix="p",
                       chunk_type="child", parent_id_for=lambda i, s: None)
    with pytest.raises(ValueError, match="overlap"):
        _slice_tokens(["a", "b", "c"], size=3, overlap=-1, prefix="p",
                       chunk_type="child", parent_id_for=lambda i, s: None)


# --- knowledge.py:1099,1102 (retrieve_parent edge paths) ---


def test_retrieve_parent_unknown_child():
    """ParentChildIndex.retrieve_parent returns None for unknown child."""
    from app.core.knowledge import ParentChildIndex

    idx = ParentChildIndex()
    assert idx.retrieve_parent("no_such_child") is None


def test_retrieve_parent_missing_data():
    """ParentChildIndex.retrieve_parent returns None when parent data missing."""
    from app.core.knowledge import ParentChildIndex

    idx = ParentChildIndex()
    idx._links["c1"] = "p1"  # link exists but parent data doesn't
    assert idx.retrieve_parent("c1") is None


# --- media.py:367 (FR-100 process_file → setenv dummy to avoid registry import) ---


def test_fr100_media_process_file_escalate():
    """FR-100: MediaPipeline.process_file with allowed file returns AUTO_ESCALATE."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_AUTO_ESCALATE,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    fake = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=fake):
        result = pipeline.process_file(0.5, "txt", b"stub")
    assert result.action == MEDIA_ACTION_AUTO_ESCALATE


# --- messenger.py:91,95 (FR-03 handle_challenge) ---


def test_fr03_messenger_handle_challenge_wrong_mode():
    """FR-03: MessengerWebhookAdapter raises ValueError on wrong hub_mode (line 91)."""
    from app.api.adapters.messenger import MessengerWebhookAdapter

    adapter = MessengerWebhookAdapter(verify_token="secret")
    with pytest.raises(ValueError, match=r"Invalid hub.mode"):
        adapter.handle_challenge("not_subscribe", "secret", "challenge")


def test_fr03_messenger_handle_challenge_wrong_token():
    """FR-03: MessengerWebhookAdapter raises ValueError on token mismatch (line 95)."""
    from app.api.adapters.messenger import MessengerWebhookAdapter

    adapter = MessengerWebhookAdapter(verify_token="secret")
    with pytest.raises(ValueError, match=r"Verify token mismatch"):
        adapter.handle_challenge("subscribe", "wrong_token", "challenge")


# --- whatsapp.py:97,101 (FR-04 handle_challenge) ---


def test_fr04_whatsapp_handle_challenge_wrong_mode():
    """FR-04: WhatsAppWebhookAdapter raises ValueError on wrong hub_mode (line 97)."""
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter

    adapter = WhatsAppWebhookAdapter(verify_token="secret")
    with pytest.raises(ValueError, match=r"Invalid hub.mode"):
        adapter.handle_challenge("not_subscribe", "secret", "challenge")


def test_fr04_whatsapp_handle_challenge_wrong_token():
    """FR-04: WhatsAppWebhookAdapter raises ValueError on token mismatch (line 101)."""
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter

    adapter = WhatsAppWebhookAdapter(verify_token="secret")
    with pytest.raises(ValueError, match=r"Verify token mismatch"):
        adapter.handle_challenge("subscribe", "wrong_token", "challenge")


# --- verifiers.py:143 (FR-03 MessengerWebhookVerifier.verify_challenge) ---


def test_fr03_messenger_verifier_verify_challenge_match():
    """FR-03: MessengerWebhookVerifier.verify_challenge returns challenge on match (line 143)."""
    from app.api.adapters.verifiers import MessengerWebhookVerifier

    v = MessengerWebhookVerifier(verify_token="my_token")
    assert v.verify_challenge("subscribe", "my_token", "ch123") == "ch123"


def test_fr03_messenger_verifier_verify_challenge_mismatch():
    """FR-03: MessengerWebhookVerifier.verify_challenge returns None on mismatch."""
    from app.api.adapters.verifiers import MessengerWebhookVerifier

    v = MessengerWebhookVerifier(verify_token="my_token")
    assert v.verify_challenge("subscribe", "wrong", "ch123") is None


# --- verifiers.py:325 (FR-04 WhatsAppWebhookVerifier.verify_challenge) ---


def test_fr04_whatsapp_verifier_verify_challenge():
    """FR-04: WhatsAppWebhookVerifier.verify_challenge delegates to _verify_challenge (line 325)."""
    from app.api.adapters.verifiers import WhatsAppWebhookVerifier

    v = WhatsAppWebhookVerifier(verify_token="my_token")
    assert v.verify_challenge("subscribe", "my_token", "ch456") == "ch456"


# --- verifiers.py:214 (WebJwtVerifier rejects non-HS256 alg) ---


def test_fr06_web_jwt_verifier_rejects_non_hs256():
    """FR-06: WebJwtVerifier.verify returns False for non-HS256 algorithm (line 214)."""
    import base64 as _b
    import json as _j

    from app.api.adapters.verifiers import WebJwtVerifier

    verifier = WebJwtVerifier(jwt_secret="test-secret")
    # Create a JWT with alg=RS256 (not HS256) → should hit line 214
    hdr = _b.urlsafe_b64encode(_j.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    pld = _b.urlsafe_b64encode(_j.dumps({"sub": "x"}).encode()).rstrip(b"=").decode()
    assert verifier.verify(f"{hdr}.{pld}.fakesig") is False


# --- verifiers.py:225 (HMAC signature mismatch) ---


def test_fr06_web_jwt_verifier_bad_signature():
    """FR-06: WebJwtVerifier.verify returns False on HMAC mismatch (line 225)."""
    import base64 as _b
    import hashlib as _hl
    import hmac as _h
    import json as _j

    from app.api.adapters.verifiers import WebJwtVerifier

    verifier = WebJwtVerifier(jwt_secret="test-secret")
    hdr = _b.urlsafe_b64encode(_j.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    pld = _b.urlsafe_b64encode(_j.dumps({"sub": "x"}).encode()).rstrip(b"=").decode()
    # Sign with WRONG secret
    bad_sig = _b.urlsafe_b64encode(_h.new(b"wrong-secret", f"{hdr}.{pld}".encode("ascii"), _hl.sha256).digest()).rstrip(b"=").decode()
    assert verifier.verify(f"{hdr}.{pld}.{bad_sig}") is False


# --- a2a.py:171 (JWK missing kty=RSA) ---


def test_fr06_verify_m2m_jwk_not_rsa():
    """FR-06: verify_m2m_token returns False when JWK kty is not RSA (line 171)."""
    import json as _j

    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    valid = _make_jwt()
    wrong_jwks = _j.dumps({"keys": [{"kty": "EC", "n": "x", "e": "AQAB", "kid": "test-kid-1"}]}).encode()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = wrong_jwks
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        assert adapter.verify_m2m_token(f"Bearer {valid}") is False


# --- a2a.py:271 (extract_sub returns UNKNOWN when verify fails) ---


def test_fr06_extract_sub_token_verify_fails():
    """FR-06: _extract_sub_from_token returns UNKNOWN_AGENT when verify fails (line 271)."""
    from app.api.adapters.a2a import A2AAdapter

    adapter = A2AAdapter(jwks_url="https://auth.test/jwks", expected_audience="omnibot")
    with patch.object(adapter, "verify_m2m_token", return_value=False):
        assert adapter._extract_sub_from_token("Bearer some.jwt.token") == "unknown-agent"


# --- webui.py:546-547 (except block in _saved_threshold) ---




def test_fr100_media_process_file_ok():
    """FR-100: process_file returns AUTO_ESCALATE when all gates pass."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_AUTO_ESCALATE,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    with patch.object(pipeline.scanner, "scan", return_value=ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)):
        r = pipeline.process_file(1.0, "txt", b"data")
    assert r.action == MEDIA_ACTION_AUTO_ESCALATE


# ===========================================================================
# whatsapp.py:148-149 — ValueError catch when timestamp is non-numeric
# ===========================================================================


def test_whatsapp_build_unified_message_bad_timestamp():
    """WhatsAppWebhookAdapter._build_unified_message: bad timestamp → ValueError → ts=0."""
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter

    msg = {"from": "5511999999999", "text": {"body": "hello"}, "type": "text", "timestamp": "not-a-number"}
    result = WhatsAppWebhookAdapter._build_unified_message(msg)
    assert result.platform_user_id == "5511999999999"
    assert result.content == "hello"
    assert result.received_at.year == 1970  # epoch 0


# ===========================================================================
# websocket.py:202-203 — except Exception in JWT verify (malformed signature)
# ===========================================================================


def test_verify_jwt_malformed_signature():
    """verify_jwt returns False when payload JSON parsing raises Exception (lines 202-203)."""
    import hashlib

    from app.api.websocket import verify_jwt

    secret = b"dev-secret-do-not-use-in-prod"
    header = {"alg": "HS256"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    # Payload is valid base64 but not valid JSON — triggers json.JSONDecodeError inside try block
    payload_bytes = b"this-is-not-valid-json"
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
    msg = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = base64.urlsafe_b64encode(hmac.new(secret, msg, hashlib.sha256).digest()).rstrip(b"=").decode()
    token = f"{header_b64}.{payload_b64}.{sig}"

    assert verify_jwt(token) is False


# ===========================================================================
# websocket.py:367 — unregister_connection when _channel_subscribers returns None
# ===========================================================================


def test_unregister_connection_subscribers_none():
    """unregister_connection: when _channel_subscribers.get returns None → continue."""
    import app.api.websocket as ws_mod
    from app.api.websocket import register_connection, unregister_connection

    cid = "test-conn-none-sub"
    register_connection(cid)
    # Manually add a channel subscription to the connection
    # but ensure the channel's subscriber set is None
    with ws_mod._registry_lock:
        ws_mod._connection_subscriptions.setdefault(cid, set()).add("ch-empty-none")
        # Don't create _channel_subscribers["ch-empty-none"] — it stays absent
    unregister_connection(cid)  # should not raise; hits continue at line 367


# ===========================================================================
# jobs.py:393 — compute_sync_status fallthrough to "failed"
# ===========================================================================


def test_compute_sync_status_failed_when_done_zero_total_positive():
    """compute_sync_status returns 'failed' when chunks_done=0, chunks_total>0."""
    from app.infra.jobs import compute_sync_status

    assert compute_sync_status(0, 5) == "failed"
    assert compute_sync_status(0, 1) == "failed"


# ===========================================================================
# security.py:420,441,468-470,495 — retention policy methods
# ===========================================================================


def test_messages_retention_policy_should_archive():
    """MessagesRetentionPolicy.should_archive: True when age_days >= retention_days."""
    from app.infra.security import MessagesRetentionPolicy

    p = MessagesRetentionPolicy(retention_days=180, target="messages", archive_format="Parquet/S3", archive_action="archive")
    assert p.should_archive(180) is True
    assert p.should_archive(200) is True
    assert p.should_archive(179) is False


def test_archive_retention_policy_should_delete():
    """ArchiveRetentionPolicy.should_delete: True when age_years >= archive_age_years."""
    from app.infra.security import ArchiveRetentionPolicy

    p = ArchiveRetentionPolicy(archive_age_years=2, action="delete")
    assert p.should_delete(2) is True
    assert p.should_delete(3) is True
    assert p.should_delete(1) is False


def test_pii_audit_retention_policy_action_for():
    """PiiAuditRetentionPolicy.action_for: returns 'anonymize' or 'retain' based on age."""
    from app.infra.security import PiiAuditRetentionPolicy

    p = PiiAuditRetentionPolicy(retention_days=90, table="audit_log", action="anonymize")
    assert p.action_for(90) == "anonymize"
    assert p.action_for(100) == "anonymize"
    assert p.action_for(89) == "retain"


def test_emotion_history_retention_policy_should_delete():
    """EmotionHistoryRetentionPolicy.should_delete: True when age_days >= retention_days."""
    from app.infra.security import EmotionHistoryRetentionPolicy

    p = EmotionHistoryRetentionPolicy(retention_days=90, table="emotion_history", action="delete")
    assert p.should_delete(90) is True
    assert p.should_delete(100) is True
    assert p.should_delete(89) is False


# ===========================================================================
# media.py:367 — process_file returns reject when scan result not OK
# ===========================================================================


def test_media_process_file_scan_not_ok():
    """MediaPipeline.process_file: returns reject when scan status != OK."""
    from app.services.media import MEDIA_ACTION_FILE_REJECTED, ClamAVScanResult, MediaPipeline

    pipeline = MediaPipeline()
    bad_scan = ClamAVScanResult(status="infected", terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=bad_scan):
        r = pipeline.process_file(1.0, "txt", b"bad data")
    assert r.action == MEDIA_ACTION_FILE_REJECTED
    assert r.status == "503"


def test_media_process_file_scan_terminated():
    """MediaPipeline.process_file: returns reject when scan terminated=True."""
    from app.services.media import (
        CLAMAV_STATUS_OK,
        MEDIA_ACTION_FILE_REJECTED,
        ClamAVScanResult,
        MediaPipeline,
    )

    pipeline = MediaPipeline()
    term_scan = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=True, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=term_scan):
        r = pipeline.process_file(1.0, "txt", b"data")
    assert r.action == MEDIA_ACTION_FILE_REJECTED


# ===========================================================================
# webui.py:546-547 — _saved_threshold import-failure fallback
# ===========================================================================


def test_saved_threshold_import_failure():
    """RAGDebugger._saved_threshold: returns RAG_DEFAULT_THRESHOLD when import fails."""
    from app.admin.webui import RAG_DEFAULT_THRESHOLD, RAGDebugger

    debugger = RAGDebugger(config_store=None)
    # Force the app.infra.config import to fail
    with patch("builtins.__import__", side_effect=ImportError("no config module")):
        result = debugger._saved_threshold()
    assert result == RAG_DEFAULT_THRESHOLD


# ===========================================================================
# knowledge.py:486,498,509,517 — query() tier-hit return paths
# ===========================================================================


def test_knowledge_query_tier1_hit():
    """HybridKnowledge.query: returns Tier 1 hit when rule match confidence >= 0.80."""
    from app.core.knowledge import HybridKnowledge, KnowledgeResult

    hk = HybridKnowledge(session=None)
    tier1_result = KnowledgeResult(id=1, content="answer", confidence=0.95, source="rule", knowledge_id=10)
    with patch.object(hk, "_rule_match", return_value=tier1_result):
        result = hk.query("test query")
    assert result.source == "rule"
    assert result.confidence == 0.95
    assert hasattr(result, "tier_sequence")
    assert result.tier_sequence == ["t1"]


def test_knowledge_query_tier2_ilike_fallback():
    """HybridKnowledge.query: Tier 2 is None when rag_fallback is ilike (line 498)."""
    from app.core.knowledge import HybridKnowledge, RAGFallback

    hk = HybridKnowledge(session=None)
    # _rule_match returns None (session=None ensures this), then Tier 1 misses
    # _rag_search_with_fallback returns ilike → tier2 = None → falls through to Tier 3/4
    # The query should reach Tier 4 escalation
    with patch.object(hk, "_rag_search_with_fallback", return_value=RAGFallback(search_path="ilike", degraded_to="tier1_ilike_only")):
        result = hk.query("test")
    assert result.source == "escalate"
    assert "t2" in result.tier_sequence


def test_knowledge_query_tier2_hit():
    """HybridKnowledge.query: returns Tier 2 hit when RAG confidence >= 0.85 (line 509)."""
    from app.core.knowledge import HybridKnowledge, KnowledgeResult, RAGFallback

    hk = HybridKnowledge(session=None)
    tier2_result = KnowledgeResult(id=2, content="rag answer", confidence=0.90, source="rag", knowledge_id=20)
    with patch.object(hk, "_rule_match", return_value=None):
        with patch.object(hk, "_rag_search_with_fallback", return_value=RAGFallback(search_path="vector")):
            with patch.object(hk, "_rag_search_top_k", return_value=[1, 2, 3]):
                with patch.object(hk, "_rag_search", return_value=tier2_result):
                    result = hk.query("test")
    assert result.source == "rag"
    assert result.confidence == 0.90
    assert "t2" in result.tier_sequence


def test_knowledge_query_tier3_hit():
    """HybridKnowledge.query: returns Tier 3 hit when LLM confidence >= 0.65 (line 517)."""
    from app.core.knowledge import HybridKnowledge, KnowledgeResult, RAGFallback

    hk = HybridKnowledge(session=None)
    tier3_result = KnowledgeResult(id=3, content="llm answer", confidence=0.80, source="wiki", knowledge_id=30)
    with patch.object(hk, "_rule_match", return_value=None):
        with patch.object(hk, "_rag_search_with_fallback", return_value=RAGFallback(search_path="vector")):
            with patch.object(hk, "_rag_search_top_k", return_value=[]):  # empty → tier2 miss
                with patch.object(hk, "_llm_call", return_value=tier3_result):
                    result = hk.query("test")
    assert result.source == "wiki"
    assert result.confidence == 0.80
    assert "t3" in result.tier_sequence


# ===========================================================================
# knowledge.py:1258-1259,1273 — create_knowledge_with_chunks timeout + enqueue failure
# ===========================================================================


@pytest.mark.asyncio
async def test_create_knowledge_timeout_triggers_fallback():
    """create_knowledge_with_chunks: built-in TimeoutError triggers _fallback_to_async (line 1273)."""
    from app.core.knowledge import create_knowledge_with_chunks

    async def _raise_timeout(*args, **kwargs):
        raise TimeoutError("simulated embedding timeout")

    with patch("app.core.knowledge._embed_first_chunk", _raise_timeout):
        result = await create_knowledge_with_chunks(
            knowledge_id="kb-timeout",
            title="Test",
            content="content for timeout test",
            model="text-embedding-3-small",
        )
    assert result.fallback == "async_queue"
    assert result.search_ready is False
    assert result.embedding_synced is False


@pytest.mark.asyncio
async def test_create_knowledge_enqueue_failure_logged():
    """create_knowledge_with_chunks: exception in enqueue fallback is logged (lines 1258-1259)."""
    from app.core.knowledge import create_knowledge_with_chunks

    async def _slow_embed(*args, **kwargs):
        await asyncio.sleep(0.1)

    with patch("app.core.knowledge._embed_first_chunk", _slow_embed):
        with patch("app.core.knowledge.EMBEDDING_TIMEOUT_S", 0.001):
            with patch("app.infra.jobs.enqueue_embedding_job", side_effect=RuntimeError("queue down")):
                result = await create_knowledge_with_chunks(
                    knowledge_id="kb-enqueue-fail",
                    title="Test",
                    content="content for enqueue failure test",
                    model="text-embedding-3-small",
                )
    assert result.fallback == "async_queue"
    assert result.search_ready is False


# ===========================================================================
# paladin.py:631-632,640,642 — _await_coro_from_sync thread-path exception paths
# ===========================================================================


def test_await_coro_from_sync_thread_timeout():
    """_await_coro_from_sync: raises TimeoutError when thread alive after join (line 640)."""
    from app.core.paladin import _await_coro_from_sync

    async def _never_complete():
        # Create an Event that never gets set — the coroutine hangs forever
        ev = asyncio.Event()
        await ev.wait()

    # Force thread path and mock Thread to always report alive
    with patch("asyncio.get_running_loop", return_value=MagicMock()):
        with patch("threading.Thread.is_alive", return_value=True):
            with pytest.raises(TimeoutError, match="FR-15"):
                _await_coro_from_sync(_never_complete(), timeout_ms=10)


def test_await_coro_from_sync_thread_exception_propagate():
    """_await_coro_from_sync: re-raises coroutine exception via holder (lines 631-632, 642)."""
    from app.core.paladin import _await_coro_from_sync

    async def _failing_coro():
        raise ValueError("test error from coroutine")

    with patch("asyncio.get_running_loop", return_value=MagicMock()):
        with pytest.raises(ValueError, match="test error from coroutine"):
            _await_coro_from_sync(_failing_coro(), timeout_ms=1000)


def test_await_coro_from_sync_thread_success():
    """_await_coro_from_sync: returns value from coroutine via thread path (line 643)."""
    from app.core.paladin import _await_coro_from_sync

    async def _ok_coro():
        return 42

    with patch("asyncio.get_running_loop", return_value=MagicMock()):
        result = _await_coro_from_sync(_ok_coro(), timeout_ms=1000)
    assert result == 42


# --- gdpr.py:263,272,278 (RetentionPolicy keep returns) ---


def test_retention_policy_should_archive_keep():
    """RetentionPolicy returns keep for non-matching tables."""
    from app.admin.gdpr import RetentionPolicy

    p = RetentionPolicy()
    assert p.should_archive("other_table", days_old=999, retention_days=10).action == "keep"


def test_retention_policy_should_delete_keep():
    """RetentionPolicy returns keep for non-matching delete criteria."""
    from app.admin.gdpr import RetentionPolicy

    p = RetentionPolicy()
    assert p.should_delete("unknown_table", years_old=0).action == "keep"
    assert p.should_delete("emotion_history", days_old=1, retention_days=90).action == "keep"


def test_retention_policy_should_anonymize_keep():
    """RetentionPolicy returns keep for non-matching anonymize criteria."""
    from app.admin.gdpr import RetentionPolicy

    p = RetentionPolicy()
    assert p.should_anonymize("other_table", days_old=999, retention_days=10).action == "keep"
