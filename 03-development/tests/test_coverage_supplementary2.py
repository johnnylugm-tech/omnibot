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
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "src")


# ---------------------------------------------------------------------------
# app.infra.config — lines 61-65, 93-95, 101
# ---------------------------------------------------------------------------


def test_dict_config_store_init_default():
    """config.py — _DictConfigStore init seeds rag_cosine_threshold."""
    from app.infra.config import _DictConfigStore, DEFAULT_RAG_COSINE_THRESHOLD

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

    with obs.start_as_current_span("outer") as outer_span:
        with obs.start_as_current_span("inner") as inner_span:
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
    from app.infra.redis_streams import AsyncMessageProcessor, _PEL_BATCH_SIZE

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
    from app.infra.deployment import K8sManifest, HPA_MIN_REPLICAS, HPA_CPU_TARGET_PERCENT

    manifest = K8sManifest()
    r = manifest.hpa_scale_test(HPA_CPU_TARGET_PERCENT - 1)
    assert r.replicas == HPA_MIN_REPLICAS


def test_backup_strategy_restore_other_type():
    """deployment.py — restore() with unknown type returns BackupResult."""
    from app.infra.deployment import BackupStrategy, BackupResult

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
    from datetime import timedelta

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
    from app.services.aee.tool_executor import ToolExecutor, ToolDefinition

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
    from app.services.aee.tool_executor import ToolExecutor, ToolDefinition

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
    from app.services.aee.tool_executor import ToolExecutor, ToolDefinition

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
    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep"):
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
    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep"):
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
    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep"):
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
    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep"):
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
    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep"):
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
    from app.services.aee.mcp_adapter import MCPAdapter
    from app.services.aee.adapter import ToolDefinition

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
    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(TimeoutError):
            adapter._execute_stdio_call("tool1", {})


def test_mcp_execute_stdio_call_nonzero_returncode():
    """mcp_adapter.py — _execute_stdio_call raises RuntimeError on nonzero exit."""
    from app.services.aee.mcp_adapter import MCPAdapter

    adapter = MCPAdapter(transport="stdio", command="false_cmd")
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (b"", b"error message")
    mock_proc.returncode = 1
    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(RuntimeError):
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
    import hmac as _hmac, hashlib as _hashlib, base64 as _b64, json as _json, os as _os
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
    import hmac as _hmac, hashlib as _hashlib, base64 as _b64, json as _json, os as _os
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
    from app.api.adapters.verifiers import WebJwtVerifier
    import hmac as _hmac, hashlib as _hashlib, base64 as _b64, json as _json

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
    from app.core.knowledge import ParentChildIndex, Chunk

    idx = ParentChildIndex()
    bad_chunk = Chunk(chunk_id="c1", content="content", chunk_type="child", parent_id=None, token_count=1)
    with pytest.raises(ValueError, match="chunk_type='parent'"):
        idx.add_parent(bad_chunk)


def test_knowledge_parent_child_add_parent_empty_content():
    """knowledge.py — ParentChildIndex.add_parent raises ValueError on empty content."""
    from app.core.knowledge import ParentChildIndex, Chunk

    idx = ParentChildIndex()
    empty_chunk = Chunk(chunk_id="p1", content="", chunk_type="parent", parent_id=None, token_count=0)
    with pytest.raises(ValueError, match="non-empty content"):
        idx.add_parent(empty_chunk)


def test_knowledge_parent_child_add_parent_success():
    """knowledge.py — ParentChildIndex.add_parent stores parent correctly."""
    from app.core.knowledge import ParentChildIndex, Chunk

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
    result = checker.check(response="some answer", sources=["text1", "text2"])
    assert isinstance(result, GroundingResult)
    assert result.grounded is True


def test_paladin_pipeline_process_unknown_risk():
    """PALADINPipeline raises ValueError for unknown risk_level."""
    from app.core.paladin import PALADINPipeline

    import asyncio
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
    from app.services.llm_judge import LLMJudge, JudgeResult

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
    from app.services.media import MediaPipeline, ClamAVScanResult, CLAMAV_STATUS_OK, MEDIA_ACTION_AUTO_ESCALATE

    pipeline = MediaPipeline()
    fake = ClamAVScanResult(status=CLAMAV_STATUS_OK, terminated=False, p95_ms=1.0)
    with patch.object(pipeline.scanner, "scan", return_value=fake):
        result = pipeline.process_file(0.5, "txt", b"x")
    assert result.action == MEDIA_ACTION_AUTO_ESCALATE


def test_clamav_scanner_scan_holder_error():
    """ClamAVScanner.scan returns UNAVAILABLE when _runner raises Exception."""
    from app.services.media import ClamAVScanner, CLAMAV_STATUS_UNAVAILABLE

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
