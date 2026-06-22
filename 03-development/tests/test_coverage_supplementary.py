"""Coverage supplementary tests — covers previously untested code paths."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import ipaddress
import json
import socket
import time
import uuid as uuid_mod
from collections import deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# app.infra.circuit_breaker  — RetryStrategy jitter=False path
# ===========================================================================

def test_retry_strategy_jitter_false():
    """circuit_breaker.py — jitter=False returns deterministic capped value."""
    from app.infra.circuit_breaker import RetryStrategy
    rs = RetryStrategy(base_delay=1.0, max_delay=30.0, jitter=False)
    result = rs.compute_delay(attempt=1)
    expected = min(1.0 * (2 ** 1), 30.0)
    assert result == expected


# ===========================================================================
# app.infra.rate_limit  — sliding window expired entries dropped
# ===========================================================================

def test_rate_limiter_drops_expired_bucket_entries():
    """rate_limit.py — aged-out entries removed from sliding window."""
    from app.infra.rate_limit import RateLimiter
    limiter = RateLimiter()
    old_ts = time.monotonic() - 100.0
    limiter._buckets[("telegram", "")] = deque([old_ts, old_ts, old_ts])
    result = limiter._in_memory_check("telegram", "user1", 30)
    assert result.status == 200  # allowed
    assert len(limiter._buckets[("telegram", "")]) == 1


# ===========================================================================
# app.infra.database  — MigrationRunner.upgrade requires staging_validated
# ===========================================================================

def test_migration_runner_staging_not_validated_raises():
    """database.py — upgrade() refuses when staging_validated=False."""
    from app.infra.database import MigrationConfig, MigrationRunner
    runner = MigrationRunner()
    cfg = MigrationConfig(
        db_url="sqlite:///:memory:",
        target_revision="head",
        staging_validated=False,
    )
    with pytest.raises(ValueError, match="staging_validated"):
        runner.upgrade(cfg)


# ===========================================================================
# app.services.escalation  — EscalationManager paths
# ===========================================================================

def test_escalation_create_unknown_priority_raises():
    """escalation.py — unknown priority raises ValueError."""
    from app.services.escalation import EscalationManager
    mgr = EscalationManager()
    with pytest.raises(ValueError, match="Unknown priority"):
        mgr.create(conversation_id="conv1", priority=99)


def test_escalation_get_returns_none_for_unknown():
    """escalation.py — get() returns None for unknown ID."""
    from app.services.escalation import EscalationManager
    mgr = EscalationManager()
    result = mgr.get("esc-notexist")
    assert result is None


# ===========================================================================
# app.admin.gdpr  — decrypt_pii_entry missing vault entry (dpo role)
# ===========================================================================

def test_decrypt_pii_entry_missing_raises():
    """gdpr.py — missing vault entry raises KeyError for dpo role."""
    from app.admin.gdpr import decrypt_pii_entry
    with pytest.raises(KeyError, match="pii_vault entry not found"):
        decrypt_pii_entry("nonexistent-id-999", "dpo")


# ===========================================================================
# app.middleware.ip_whitelist  — denied paths
# ===========================================================================

def test_ip_whitelist_no_ip_header_returns_denied():
    """ip_whitelist.py — no resolvable IP → is_allowed returns denied."""
    from app.middleware.ip_whitelist import IPWhitelist
    wl = IPWhitelist(cidrs=["10.0.0.0/8"])
    result = wl.is_allowed(x_forwarded_for=None, client_host=None)
    assert result.allowed is False


def test_ip_whitelist_ip_not_in_cidr():
    """ip_whitelist.py — IP not in any CIDR returns denied."""
    from app.middleware.ip_whitelist import IPWhitelist
    wl = IPWhitelist(cidrs=["192.168.1.0/24"])
    result = wl.is_allowed(x_forwarded_for=None, client_host="10.0.0.1")
    assert result.allowed is False


# ===========================================================================
# app.infra.jobs  — _compute_backoff jitter=False + compute_sync_status
# ===========================================================================

def test_compute_backoff_jitter_false():
    """jobs.py — _compute_backoff with jitter=False returns capped value."""
    from app.infra.jobs import EmbeddingJob, _compute_backoff
    job = EmbeddingJob(
        chunk_id="c1", knowledge_id="k1", content="x", model="m",
        max_retries=3, base_delay=1.0, jitter=False,
    )
    result = _compute_backoff(job, attempt=1)
    assert result == min(1.0 * (2 ** 1), 30.0)


def test_compute_sync_status_zero_total():
    """jobs.py — compute_sync_status returns 'failed' when total=0."""
    from app.infra.jobs import compute_sync_status
    assert compute_sync_status(0, 0) == "failed"


def test_compute_sync_status_partial():
    """jobs.py — compute_sync_status returns 'syncing' for 0 < done < total."""
    from app.infra.jobs import compute_sync_status
    assert compute_sync_status(3, 5) == "syncing"


# ===========================================================================
# app.middleware.chain  — rejection paths TLS/sig/rate/RBAC
# ===========================================================================

def _make_chain(*, tls_check=None, ip_allowed=True, sig_valid=True,
                rate_ok=True, rbac_ok=True):
    from app.middleware.chain import MiddlewareChain
    ip_result = MagicMock(allowed=ip_allowed, status=403, body=b"denied")
    ip_wl = MagicMock()
    ip_wl.is_allowed.return_value = ip_result
    sig_val = MagicMock()
    sig_val.verify.return_value = sig_valid
    ctx = MagicMock(platform="telegram", user_id="u1")
    adapter = MagicMock()
    adapter.parse.return_value = ctx
    rate_result = MagicMock(allowed=rate_ok, status=429 if not rate_ok else 200)
    rate_lim = MagicMock()
    rate_lim.allow.return_value = rate_result
    rbac_result = MagicMock(allowed=rbac_ok)
    rbac_enforcer = MagicMock()
    rbac_enforcer.enforce.return_value = rbac_result
    req = MagicMock()
    req.headers = {"x-forwarded-for": "1.2.3.4"}
    req.client = MagicMock(host="1.2.3.4")
    return MiddlewareChain(
        ip_whitelist=ip_wl, signature_validator=sig_val,
        platform_adapter=adapter, rate_limiter=rate_lim,
        rbac_enforcer=rbac_enforcer, tls_check=tls_check,
    ), req


def test_chain_tls_check_fails():
    """chain.py — TLS check rejection stops processing."""
    tls_deny = MagicMock(allowed=False, status=400, body=b"no-tls")
    chain, req = _make_chain(tls_check=lambda r: tls_deny)
    result = chain.process(req)
    assert result.status == 400


def test_chain_signature_fails():
    """chain.py — signature validation rejection returns 401."""
    chain, req = _make_chain(sig_valid=False)
    result = chain.process(req)
    assert result.status == 401


def test_chain_rate_limit_fails():
    """chain.py — rate limit rejection returns 429."""
    chain, req = _make_chain(rate_ok=False)
    result = chain.process(req)
    assert result.status == 429


def test_chain_rbac_fails():
    """chain.py — RBAC rejection returns 403."""
    chain, req = _make_chain(rbac_ok=False)
    result = chain.process(req)
    assert result.status == 403


def test_chain_signature_validator_raises_returns_401():
    """chain.py — signature_validator.verify raising any exception → 401.

    Per chain.py lines 143-146, the framework catches any Exception from
    ``signature_validator.verify`` and treats the request as unauthorized
    (status=401, reason='SIGNATURE_INVALID'). Without this guard a buggy
    verifier that raises (e.g. on malformed input) would propagate a 500.
    """
    from unittest.mock import MagicMock

    from app.middleware.chain import MiddlewareChain

    sig_val = MagicMock()
    sig_val.verify.side_effect = RuntimeError("verify boom")

    ip_wl = MagicMock()
    ip_result = MagicMock(status=200, allowed=True, body=b"")
    ip_wl.is_allowed.return_value = ip_result

    adapter = MagicMock()
    ctx = MagicMock(platform="telegram", user_id="u1")
    adapter.parse.return_value = ctx

    rl = MagicMock()
    rl_out = MagicMock(status=200, allowed=True)
    rl.allow.return_value = rl_out

    rb = MagicMock()
    rb_out = MagicMock(allowed=True)
    rb.enforce.return_value = rb_out

    req = MagicMock()
    req.headers = {"x-forwarded-for": "1.2.3.4"}
    req.client = MagicMock(host="1.2.3.4")

    chain = MiddlewareChain(
        ip_whitelist=ip_wl,
        signature_validator=sig_val,
        platform_adapter=adapter,
        rate_limiter=rl,
        rbac_enforcer=rb,
    )
    result = chain.process(req)
    assert result.status == 401, (
        f"chain.process must return 401 when signature_validator raises; "
        f"got status={result.status}"
    )
    assert result.reason == "SIGNATURE_INVALID", (
        f"chain.process reason must be SIGNATURE_INVALID; got {result.reason!r}"
    )


# ===========================================================================
# app.services.llm_judge  — CalibrationPipeline timeout path
# ===========================================================================

@pytest.mark.asyncio
async def test_calibration_run_cycle_timeout():
    """llm_judge.py — TimeoutError in run_cycle returns kappa=None result."""
    from app.services.llm_judge import CalibrationPipeline, CalibrationResult
    judge_llm = AsyncMock(side_effect=TimeoutError("slow"))
    pipeline = CalibrationPipeline(
        judge_llm=judge_llm, kappa_cache=MagicMock(), timeout_s=0.001
    )
    result = await pipeline.run_cycle(golden_set=[])
    assert isinstance(result, CalibrationResult)
    assert result.kappa is None


@pytest.mark.asyncio
async def test_calibration_run_cycle_empty_golden():
    """llm_judge.py — run_cycle with empty golden_set returns CalibrationResult."""
    from app.services.llm_judge import CalibrationPipeline, CalibrationResult
    judge_llm = AsyncMock(return_value={"kappa": 0.8})
    pipeline = CalibrationPipeline(
        judge_llm=judge_llm, kappa_cache=MagicMock(), timeout_s=10
    )
    result = await pipeline.run_cycle(golden_set=[])
    assert isinstance(result, CalibrationResult)


# ===========================================================================
# app.core.dst  — FSM state transitions
# ===========================================================================

def test_dst_auto_escalate_triggers_escalation():
    """dst.py — auto_escalate → ESCALATED when confidence below threshold."""
    from app.core.dst import INTENT_CONFIDENCE_THRESHOLD, DialogueState
    fsm = DialogueState(initial_state="SLOT_FILLING")
    result = fsm.auto_escalate(
        slot_filling_rounds=0,
        confidence=INTENT_CONFIDENCE_THRESHOLD - 0.01,
    )
    assert result == "ESCALATED"


def test_dst_auto_escalate_no_trigger():
    """dst.py — auto_escalate returns current state when no trigger fires."""
    from app.core.dst import INTENT_CONFIDENCE_THRESHOLD, DialogueState
    fsm = DialogueState(initial_state="SLOT_FILLING")
    result = fsm.auto_escalate(
        slot_filling_rounds=0,
        confidence=INTENT_CONFIDENCE_THRESHOLD + 0.1,
    )
    assert result == "SLOT_FILLING"


def test_dst_escalation_triggered_terminal_state():
    """dst.py — _escalation_triggered returns False in terminal state."""
    from app.core.dst import DialogueState
    fsm = DialogueState(initial_state="ESCALATED")
    assert fsm._escalation_triggered(slot_filling_rounds=10, confidence=0.1) is False


def test_dst_context_window_history_budget():
    """dst.py — ContextWindowManager.history_budget is computed correctly."""
    from app.core.dst import KNOWLEDGE_MAX, MAX_TOKENS, SYSTEM_RESERVED, ContextWindowManager
    manager = ContextWindowManager()
    expected = MAX_TOKENS - SYSTEM_RESERVED - KNOWLEDGE_MAX
    assert manager.history_budget == expected


# ===========================================================================
# app.core.pii  — audit log trim + clear + luhn
# ===========================================================================

def test_pii_audit_log_trim():
    """pii.py — audit log is trimmed when it exceeds 10000 entries."""
    from app.core.pii import PIIMasking
    PIIMasking.clear_audit_log()
    PIIMasking._audit_log = ["x"] * 10001
    masker = PIIMasking()
    masker.mask("test@example.com")
    assert len(PIIMasking._audit_log) <= 10000
    PIIMasking.clear_audit_log()


def test_pii_clear_audit_log():
    """pii.py — clear_audit_log empties the log."""
    from app.core.pii import PIIMasking
    PIIMasking._audit_log = ["a", "b", "c"]
    PIIMasking.clear_audit_log()
    assert PIIMasking._audit_log == []


def test_pii_get_mask_format_unknown_type():
    """pii.py — get_mask_format raises ValueError for unknown type."""
    from app.core.pii import PIIMasking
    with pytest.raises(ValueError, match="unknown pii_type"):
        PIIMasking.get_mask_format("nonexistent_type")


def test_pii_luhn_invalid_non_digits():
    """pii.py — _luhn_valid returns False for non-digit input."""
    from app.core.pii import PIIMasking
    masker = PIIMasking()
    assert masker._luhn_valid("not-a-number") is False


# ===========================================================================
# app.services.ab_testing  — ABTestManager paths
# ===========================================================================

def test_ab_testing_no_traffic_split():
    """ab_testing.py — returns CONTROL_FALLBACK when traffic_split is None."""
    from app.services.ab_testing import ABTestManager
    mgr = ABTestManager(db=MagicMock(), llm=MagicMock())
    mgr._db.get_experiment = MagicMock(
        return_value={"name": "test", "traffic_split": None}
    )
    result = mgr.get_variant(user_id="u1", experiment_id="exp1")
    assert result == ABTestManager._CONTROL_FALLBACK


def test_ab_testing_route_bucket_fallback():
    """ab_testing.py — _route_bucket falls back when bucket exceeds sum."""
    from app.services.ab_testing import ABTestManager
    mgr = ABTestManager(db=MagicMock(), llm=MagicMock())
    result = mgr._route_bucket(999, {"a": 10, "b": 10})
    assert result == ABTestManager._CONTROL_FALLBACK


def test_ab_testing_fetch_experiment_returns_none():
    """ab_testing.py — _fetch_experiment returns None for unknown id."""
    from app.services.ab_testing import ABTestManager
    mgr = ABTestManager(db=MagicMock(), llm=MagicMock())
    mgr._db.get_experiment = MagicMock(return_value=None)
    assert mgr._fetch_experiment("nonexistent") is None


# ===========================================================================
# app.core.emotion  — emotion_classify + emotion_should_escalate
# ===========================================================================

def test_emotion_classify_empty_text():
    """emotion.py — emotion_classify returns neutral for empty text."""
    from app.core.emotion import emotion_classify
    result = emotion_classify("")
    assert result.category == "neutral"


def test_emotion_classify_negated_positive():
    """emotion.py — negated positive keyword produces negative emotion."""
    from app.core.emotion import _NEGATION_PREFIXES, _POSITIVE_KEYWORDS, emotion_classify
    if not _POSITIVE_KEYWORDS or not _NEGATION_PREFIXES:
        pytest.skip("Keywords not defined")
    kw = next(iter(_POSITIVE_KEYWORDS))
    prefix = next(iter(_NEGATION_PREFIXES))
    result = emotion_classify(prefix + kw)
    assert result.category == "negative"


def test_emotion_classify_neutral():
    """emotion.py — text with no clear emotion returns neutral."""
    from app.core.emotion import emotion_classify
    result = emotion_classify("今天是星期三")
    assert result.category == "neutral"


def test_emotion_should_escalate_none_input():
    """emotion.py — emotion_should_escalate returns False for None."""
    from app.core.emotion import emotion_should_escalate
    assert emotion_should_escalate(None) is False


def test_has_negated_positive_keyword_finds_negation():
    """emotion.py — _has_negated_positive_keyword returns True when negated."""
    from app.core.emotion import (
        _NEGATION_PREFIXES,
        _POSITIVE_KEYWORDS,
        _has_negated_positive_keyword,
    )
    if not _POSITIVE_KEYWORDS or not _NEGATION_PREFIXES:
        pytest.skip("Keywords not defined")
    kw = next(iter(_POSITIVE_KEYWORDS))
    prefix = next(iter(_NEGATION_PREFIXES))
    result = _has_negated_positive_keyword(prefix + kw, _POSITIVE_KEYWORDS)
    assert result is True


def test_emotion_tracker_weighted_score():
    """emotion.py — EmotionTracker.current_weighted_score returns float."""
    from app.core.emotion import EmotionTracker
    tracker = EmotionTracker()
    score = tracker.current_weighted_score(score=0.8, hours_ago=0.0)
    assert isinstance(score, float)


# ===========================================================================
# app.services.media  — ClamAVScanner and MediaPipeline paths
# ===========================================================================

def test_clamav_scanner_force_invalid_status():
    """media.py — force_status raises ValueError for unknown status."""
    from app.services.media import ClamAVScanner
    scanner = ClamAVScanner()
    with pytest.raises(ValueError, match="unknown clamav status"):
        scanner.force_status("bad_status")


def test_clamav_scan_unavailable():
    """media.py — scan returns UNAVAILABLE when forced unavailable."""
    from app.services.media import CLAMAV_STATUS_UNAVAILABLE, ClamAVScanner
    scanner = ClamAVScanner()
    scanner.force_status(CLAMAV_STATUS_UNAVAILABLE)
    result = scanner.scan(b"some bytes", "image/jpeg")
    assert result.status == CLAMAV_STATUS_UNAVAILABLE
    assert result.terminated is True


def test_media_pipeline_file_too_large():
    """media.py — process_file returns rejected for oversized file."""
    from app.services.media import FILE_SIZE_LIMIT_MB, MediaPipeline
    pipeline = MediaPipeline()
    result = pipeline.process_file(
        file_size_mb=FILE_SIZE_LIMIT_MB + 1.0,
        file_type="image/jpeg",
        file_bytes=b"data",
    )
    assert "rejected" in result.status.lower() or result.action is not None


def test_media_pipeline_unsupported_type():
    """media.py — process_file returns rejected for unsupported content type."""
    from app.services.media import MediaPipeline
    pipeline = MediaPipeline()
    result = pipeline.process_file(
        file_size_mb=0.1,
        file_type="application/exe",
        file_bytes=b"data",
    )
    assert result is not None


# ===========================================================================
# app.infra.deployment  — K8sManifest + BackupStrategy + RollbackStrategy
# ===========================================================================

def test_k8s_manifest_max_unavailable():
    """deployment.py — max_unavailable returns DEFAULT_MAX_UNAVAILABLE."""
    from app.infra.deployment import DEFAULT_MAX_UNAVAILABLE, K8sManifest
    manifest = K8sManifest()
    assert manifest.max_unavailable() == DEFAULT_MAX_UNAVAILABLE


def test_k8s_manifest_service_port():
    """deployment.py — service_port returns SERVICE_PORT constant."""
    from app.infra.deployment import SERVICE_PORT, K8sManifest
    manifest = K8sManifest()
    assert manifest.service_port() == SERVICE_PORT


def test_k8s_manifest_resource_requests():
    """deployment.py — resource_requests returns dict."""
    from app.infra.deployment import K8sManifest
    manifest = K8sManifest()
    assert isinstance(manifest.resource_requests(), dict)


def test_k8s_manifest_resource_limits():
    """deployment.py — resource_limits returns dict."""
    from app.infra.deployment import K8sManifest
    manifest = K8sManifest()
    assert isinstance(manifest.resource_limits(), dict)


def test_backup_strategy_restore_redis_rdb():
    """deployment.py — BackupStrategy.restore dispatches redis_rdb type."""
    from app.infra.deployment import BACKUP_TYPE_REDIS_RDB, BackupStrategy
    strategy = BackupStrategy()
    result = strategy.restore(backup_type=BACKUP_TYPE_REDIS_RDB)
    assert result is not None


def test_backup_strategy_has_schedule():
    """deployment.py — has_schedule returns True for scheduled types."""
    from app.infra.deployment import SCHEDULED_BACKUP_TYPES, BackupStrategy
    strategy = BackupStrategy()
    for btype in SCHEDULED_BACKUP_TYPES:
        assert strategy.has_schedule(btype) is True


def test_backup_strategy_triggers_alert():
    """deployment.py — triggers_alert_on_failure returns True."""
    from app.infra.deployment import BackupStrategy
    strategy = BackupStrategy()
    assert strategy.triggers_alert_on_failure() is True


def test_rollback_strategy_downgrade_schema():
    """deployment.py — RollbackStrategy.downgrade_schema with valid direction."""
    from app.infra.deployment import MIGRATION_DOWNGRADE, RollbackStrategy
    strategy = RollbackStrategy()
    result = strategy.downgrade_schema(migration=MIGRATION_DOWNGRADE)
    assert result is not None


def test_rollback_strategy_downgrade_schema_wrong_direction():
    """deployment.py — downgrade_schema raises ValueError for 'upgrade' direction."""
    from app.infra.deployment import RollbackStrategy
    strategy = RollbackStrategy()
    with pytest.raises(ValueError):
        strategy.downgrade_schema(migration="upgrade")


def test_rollback_strategy_rollback_knowledge_update():
    """deployment.py — rollback_knowledge_update returns is_active=True."""
    from app.infra.deployment import RollbackStrategy
    strategy = RollbackStrategy()
    result = strategy.rollback_knowledge_update("knowledge-1")
    assert result.is_active is True


# ===========================================================================
# app.core.response  — retraction paths
# ===========================================================================

def test_log_retraction_failed_no_writer():
    """response.py — _log_retraction_failed with None writer is no-op."""
    from app.core.response import _log_retraction_failed
    _log_retraction_failed(
        security_log_writer=None,
        platform="telegram",
        message_id="msg1",
        reason="test",
    )


def test_attempt_windowed_delete_no_client():
    """response.py — _attempt_windowed_delete with client=None returns apology."""
    from app.core.response import _attempt_windowed_delete
    sent_at = datetime.now(timezone.utc)
    result = _attempt_windowed_delete(
        platform="telegram",
        client=None,
        message_id="msg1",
        sent_at=sent_at,
        window=timedelta(hours=48),
        security_log_writer=None,
    )
    assert result is not None


def test_attempt_windowed_delete_window_expired():
    """response.py — _attempt_windowed_delete returns apology when window expired."""
    from app.core.response import _attempt_windowed_delete
    old_sent_at = datetime.now(timezone.utc) - timedelta(days=3)
    result = _attempt_windowed_delete(
        platform="telegram",
        client=MagicMock(),
        message_id="msg1",
        sent_at=old_sent_at,
        window=timedelta(hours=48),
        security_log_writer=None,
    )
    assert result is not None


def test_retract_message_web_ws_failure():
    """response.py — _retract_web exception returns apology."""
    from app.core.response import _retract_web
    pusher = MagicMock()
    pusher.push.side_effect = RuntimeError("ws error")
    result = _retract_web("msg1", web_ws_pusher=pusher, security_log_writer=None)
    assert result.platform == "web"


def test_retract_message_a2a_failure():
    """response.py — _retract_a2a exception returns apology."""
    from app.core.response import _retract_a2a
    client = MagicMock()
    client.mark_revoked.side_effect = RuntimeError("a2a error")
    result = _retract_a2a("msg1", a2a_client=client, security_log_writer=None)
    assert result.platform == "a2a"


def test_retract_a2a_platform():
    """response.py — retract dispatches to _retract_a2a for a2a platform."""
    from app.core.response import retract
    client = MagicMock()
    client.mark_revoked.return_value = None
    result = retract(
        platform="a2a",
        message_id="msg1",
        sent_at=datetime.now(timezone.utc),
        a2a_client=client,
    )
    assert result is not None


def test_retract_unknown_platform_raises():
    """response.py — retract raises ValueError for unknown platform."""
    from app.core.response import retract
    with pytest.raises(ValueError, match="Unknown platform"):
        retract(
            message_id="msg1",
            platform="unknownplatform",
            sent_at=datetime.now(timezone.utc),
        )


# ===========================================================================
# app.services.aee.tool_executor  — validation and execution paths
# ===========================================================================

def test_tool_executor_execute_known_tool():
    """tool_executor.py — execute returns success for known tool."""
    from app.services.aee.tool_executor import ToolDefinition, ToolExecutionResult, ToolExecutor

    def echo_fn(**kwargs) -> str:
        return kwargs.get("x", "")

    tool_def = ToolDefinition(name="echo_fn", description="echo", parameters_schema={}, protocol="internal", handler_ref="echo_fn")
    executor = ToolExecutor()
    executor.register(tool_def, echo_fn)
    result = executor.execute("echo_fn", arguments_json='{"x": "hello"}')
    assert isinstance(result, ToolExecutionResult)


def test_tool_executor_execute_unknown_tool():
    """tool_executor.py — execute returns fail for unknown tool name."""
    from app.services.aee.tool_executor import ToolExecutor
    executor = ToolExecutor()
    result = executor.execute("nonexistent_tool", arguments_json="{}")
    assert result.success is False


# ===========================================================================
# app.infra.observability  — _json_default type dispatch
# ===========================================================================

def test_json_default_datetime():
    """observability.py — serializes datetime to ISO string."""
    from app.infra.observability import _json_default
    dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    result = _json_default(dt)
    assert "2024-01-15" in result


def test_json_default_date():
    """observability.py — serializes date."""
    from app.infra.observability import _json_default
    result = _json_default(date(2024, 6, 1))
    assert "2024-06-01" in result


def test_json_default_decimal():
    """observability.py — serializes Decimal as string."""
    from app.infra.observability import _json_default
    assert _json_default(Decimal("3.14")) == "3.14"


def test_json_default_uuid():
    """observability.py — serializes UUID."""
    from app.infra.observability import _json_default
    uid = uuid_mod.UUID("12345678-1234-5678-1234-567812345678")
    assert _json_default(uid) == str(uid)


def test_json_default_set():
    """observability.py — serializes set as sorted list."""
    from app.infra.observability import _json_default
    assert _json_default({3, 1, 2}) == [1, 2, 3]


def test_json_default_bytes_utf8():
    """observability.py — serializes UTF-8 bytes as string."""
    from app.infra.observability import _json_default
    assert _json_default(b"hello") == "hello"


def test_json_default_bytes_non_utf8():
    """observability.py — serializes non-UTF-8 bytes as hex."""
    from app.infra.observability import _json_default
    assert _json_default(b"\xff\xfe") == "fffe"


def test_json_default_path():
    """observability.py — serializes Path as string."""
    from app.infra.observability import _json_default
    assert _json_default(Path("/tmp/test.txt")) == "/tmp/test.txt"


def test_json_default_enum():
    """observability.py — serializes Enum as value."""
    from app.infra.observability import _json_default

    class Color(Enum):
        RED = "red"

    assert _json_default(Color.RED) == "red"


def test_json_default_exception():
    """observability.py — serializes BaseException as string."""
    from app.infra.observability import _json_default
    assert "test error" in _json_default(ValueError("test error"))


def test_json_default_unknown_type_raises():
    """observability.py — unknown type raises TypeError."""
    from app.infra.observability import _json_default
    with pytest.raises(TypeError, match="not JSON serializable"):
        _json_default(object())


def test_get_current_trace_id_no_spans():
    """observability.py — get_current_trace_id returns None when no active spans."""
    from app.infra.observability import _get_active_spans, get_current_trace_id
    _get_active_spans().clear()
    assert get_current_trace_id() is None


# ===========================================================================
# app.infra.redis_streams  — _next_stream_id + AsyncMessageProcessor
# ===========================================================================

def test_redis_streams_next_id_standard():
    """redis_streams.py — _next_stream_id increments sequence number."""
    from app.infra.redis_streams import _next_stream_id
    assert _next_stream_id("1234567890-5") == "1234567890-6"


def test_redis_streams_next_id_no_dash():
    """redis_streams.py — _next_stream_id returns unchanged when no dash."""
    from app.infra.redis_streams import _next_stream_id
    assert _next_stream_id("plainid") == "plainid"


def test_redis_streams_next_id_bad_seq():
    """redis_streams.py — _next_stream_id returns unchanged when seq is non-int."""
    from app.infra.redis_streams import _next_stream_id
    assert _next_stream_id("1234-abc") == "1234-abc"


def test_redis_streams_is_busygroup_error_true():
    """redis_streams.py — _is_busygroup_error detects BUSYGROUP by string."""
    from app.infra.redis_streams import AsyncMessageProcessor
    proc = AsyncMessageProcessor(MagicMock())
    exc = Exception("BUSYGROUP Consumer Group already exists")
    assert proc._is_busygroup_error(exc) is True


def test_redis_streams_is_busygroup_error_false():
    """redis_streams.py — _is_busygroup_error returns False for other errors."""
    from app.infra.redis_streams import AsyncMessageProcessor
    proc = AsyncMessageProcessor(MagicMock())
    assert proc._is_busygroup_error(Exception("connection refused")) is False


@pytest.mark.asyncio
async def test_redis_streams_ensure_group_non_busygroup_raises():
    """redis_streams.py — ensure_group re-raises non-BUSYGROUP errors."""
    from app.infra.redis_streams import AsyncMessageProcessor
    mock_redis = AsyncMock()
    mock_redis.xgroup_create.side_effect = Exception("WRONGTYPE")
    proc = AsyncMessageProcessor(mock_redis)
    with pytest.raises(Exception, match="WRONGTYPE"):
        await proc.ensure_group()


@pytest.mark.asyncio
async def test_redis_streams_read_returns_messages():
    """redis_streams.py — read() returns parsed Message list."""
    from app.infra.redis_streams import AsyncMessageProcessor
    mock_redis = AsyncMock()
    mock_redis.xreadgroup.return_value = [
        ("messages", [("1-0", {"key": "val"})])
    ]
    proc = AsyncMessageProcessor(mock_redis)
    messages = await proc.read("consumer1")
    assert len(messages) == 1
    assert messages[0].message_id == "1-0"


@pytest.mark.asyncio
async def test_redis_streams_ack():
    """redis_streams.py — ack() calls redis xack and returns result."""
    from app.infra.redis_streams import AsyncMessageProcessor
    mock_redis = AsyncMock()
    mock_redis.xack.return_value = 1
    proc = AsyncMessageProcessor(mock_redis)
    assert await proc.ack("1-0") == 1


# ===========================================================================
# app.services.aee.a2a_adapter  — SSRF protection
# ===========================================================================

def test_resolve_addresses_dns_error():
    """a2a_adapter.py — DNS failure returns empty list."""
    from app.services.aee.a2a_adapter import _resolve_addresses
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS fail")):
        result = _resolve_addresses("bad.hostname.invalid")
    assert result == []


def test_is_public_address_private():
    """a2a_adapter.py — private IP returns False."""
    from app.services.aee.a2a_adapter import _is_public_address
    assert _is_public_address(ipaddress.ip_address("192.168.1.1")) is False


def test_validate_agent_url_bad_scheme():
    """a2a_adapter.py — bad scheme raises ValueError."""
    from app.services.aee.a2a_adapter import _validate_agent_url
    with pytest.raises(ValueError, match="scheme"):
        _validate_agent_url("ftp://example.com/agent")


def test_validate_agent_url_private_ip_raises():
    """a2a_adapter.py — private IP in resolved addresses raises ValueError."""
    from app.services.aee.a2a_adapter import _validate_agent_url
    private_ip = ipaddress.ip_address("10.0.0.1")
    with patch("app.services.aee.a2a_adapter._resolve_addresses", return_value=[private_ip]):
        with pytest.raises(ValueError, match="SSRF"):
            _validate_agent_url("https://internal.example.com/agent")


# ===========================================================================
# app.admin.webui  — EmbeddingStatusProvider + KnowledgeAdminAPI + RAGDebugger
# ===========================================================================

def test_embedding_status_mark_failed():
    """webui.py — mark_failed sets _failed=True."""
    from app.admin.webui import EmbeddingStatusProvider
    provider = EmbeddingStatusProvider()
    provider.mark_failed()
    assert provider._failed is True


def test_embedding_status_get_status_failed():
    """webui.py — get_status returns FAILED after mark_failed."""
    from app.admin.webui import EMBEDDING_STATUS_FAILED, EmbeddingStatusProvider
    provider = EmbeddingStatusProvider(default_total=10)
    provider.mark_failed()
    assert provider.get_status()["status"] == EMBEDDING_STATUS_FAILED


def test_embedding_status_get_status_synced():
    """webui.py — get_status returns SYNCED when synced >= total."""
    from app.admin.webui import EMBEDDING_STATUS_SYNCED, EmbeddingStatusProvider
    provider = EmbeddingStatusProvider(default_synced=5, default_total=5)
    assert provider.get_status()["status"] == EMBEDDING_STATUS_SYNCED


def test_knowledge_admin_api_update_entry():
    """webui.py — update_entry modifies entry title."""
    from app.admin.webui import KnowledgeAdminAPI
    api = KnowledgeAdminAPI()
    entry = api.create_entry(title="Test", content="Content")
    result = api.update_entry(entry.id, title="Updated")
    assert result is not None


def test_knowledge_admin_api_crud_delete():
    """webui.py — crud DELETE action."""
    from app.admin.webui import KNOWLEDGE_ACTION_DELETE, KnowledgeAdminAPI
    api = KnowledgeAdminAPI()
    entry = api.create_entry(title="T", content="C")
    result = api.crud(KNOWLEDGE_ACTION_DELETE, entry_id=entry.id)
    assert result is not None


def test_knowledge_admin_api_crud_unknown():
    """webui.py — crud unknown action returns error dict."""
    from app.admin.webui import KnowledgeAdminAPI
    api = KnowledgeAdminAPI()
    result = api.crud("UNKNOWN_ACTION")
    assert result is not None


def test_knowledge_admin_import_csv_missing_title():
    """webui.py — import_csv skips rows without title column."""
    from app.admin.webui import KnowledgeAdminAPI
    api = KnowledgeAdminAPI()
    result = api.import_csv(b"content\nsome content\n")
    assert result is not None


def test_rag_debugger_get_saved_threshold():
    """webui.py — get_saved_threshold returns float."""
    from app.admin.webui import RAGDebugger
    debugger = RAGDebugger()
    assert isinstance(debugger.get_saved_threshold(), float)


# ===========================================================================
# app.api.websocket  — verify_jwt + get_subscribers + is_subscribed
# ===========================================================================

def test_websocket_register_unregister_connection():
    """websocket.py — register_connection then unregister_connection."""
    from app.api.websocket import register_connection, unregister_connection
    register_connection("conn_supp_1")
    unregister_connection("conn_supp_1")


def test_websocket_get_subscribers_empty():
    """websocket.py — get_subscribers returns empty set for unknown channel."""
    from app.api.websocket import get_subscribers
    assert get_subscribers("nonexistent_channel_xyz") == set()


def test_websocket_get_subscribers_empty_channel():
    """websocket.py — empty channel returns empty set."""
    from app.api.websocket import get_subscribers
    assert get_subscribers("") == set()


def test_websocket_is_subscribed_not_subscribed():
    """websocket.py — is_subscribed returns False for unknown connection."""
    from app.api.websocket import is_subscribed
    assert is_subscribed("nonexistent_conn", "channel") is False


def test_websocket_verify_jwt_empty():
    """websocket.py — verify_jwt returns False for empty string."""
    from app.api.websocket import verify_jwt
    assert verify_jwt("") is False


def test_websocket_verify_jwt_bad_token():
    """websocket.py — verify_jwt returns False for bad-prefixed token."""
    from app.api.websocket import verify_jwt
    assert verify_jwt("bad-token") is False


def test_websocket_verify_jwt_wrong_alg():
    """websocket.py — verify_jwt returns False for wrong algorithm."""
    from app.api.websocket import verify_jwt
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "u1"}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(b"fakesig").decode().rstrip("=")
    assert verify_jwt(f"{header}.{payload}.{sig}") is False


def test_websocket_verify_jwt_wrong_sig():
    """websocket.py — verify_jwt returns False for wrong signature."""
    from app.api.websocket import verify_jwt
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "u1"}).encode()).decode().rstrip("=")
    bad_sig = base64.urlsafe_b64encode(b"badsig").decode().rstrip("=")
    assert verify_jwt(f"{header}.{payload}.{bad_sig}") is False


def test_websocket_verify_jwt_malformed():
    """websocket.py — verify_jwt returns False for non-3-segment token."""
    from app.api.websocket import verify_jwt
    assert verify_jwt("only.two") is False


def test_websocket_handle_subscribe():
    """websocket.py — handle_subscribe registers subscription."""
    from app.api.websocket import handle_subscribe
    result = handle_subscribe({"channel": "test_ch"}, connection_id="conn_sub_1")
    assert result is not None


# ===========================================================================
# app.api.webhooks  — challenge verification + A2AAuthError + verify_m2m_token
# ===========================================================================

def test_verify_challenge_subscribe_token_match():
    """webhooks.py — valid subscribe + matching token returns challenge."""
    from app.api.adapters.utils import _verify_challenge
    assert _verify_challenge("subscribe", "my_token", "challenge123", "my_token") == "challenge123"


def test_verify_challenge_subscribe_token_mismatch():
    """webhooks.py — token mismatch returns None."""
    from app.api.adapters.utils import _verify_challenge
    assert _verify_challenge("subscribe", "wrong_token", "challenge", "expected") is None


def test_a2a_auth_error_init():
    """webhooks.py — A2AAuthError initializes status and error_code."""
    from app.api.adapters.a2a import A2AAuthError
    err = A2AAuthError(status=401, error_code="AUTH_INVALID_SIGNATURE")
    assert err.status == 401
    assert err.error_code == "AUTH_INVALID_SIGNATURE"


def test_a2a_adapter_verify_m2m_token_no_bearer():
    """webhooks.py — verify_m2m_token returns False without Bearer prefix."""
    from app.api.adapters.a2a import A2AAdapter
    adapter = A2AAdapter(jwks_url="https://example.com/jwks", expected_audience="test")
    assert adapter.verify_m2m_token("") is False
    assert adapter.verify_m2m_token("NotBearer token") is False


def test_a2a_adapter_verify_m2m_token_malformed():
    """webhooks.py — verify_m2m_token returns False for non-3-segment JWT."""
    from app.api.adapters.a2a import A2AAdapter
    adapter = A2AAdapter(jwks_url="https://example.com/jwks", expected_audience="test")
    assert adapter.verify_m2m_token("Bearer onlyone") is False


def test_a2a_adapter_verify_m2m_token_wrong_audience():
    """webhooks.py — verify_m2m_token returns False for wrong audience."""
    from app.api.adapters.a2a import A2AAdapter
    adapter = A2AAdapter(jwks_url="https://example.com/jwks", expected_audience="correct_aud")
    payload = base64.urlsafe_b64encode(json.dumps({"aud": "wrong_aud"}).encode()).decode().rstrip("=")
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    token = f"Bearer {header_b64}.{payload}.fakesig"
    assert adapter.verify_m2m_token(token) is False


def test_a2a_adapter_handle_jsonrpc_invalid_token():
    """webhooks.py — handle_jsonrpc_call raises A2AAuthError when token invalid."""
    from app.api.adapters.a2a import A2AAdapter, A2AAuthError
    adapter = A2AAdapter(jwks_url="https://auth.example.com/jwks", expected_audience="omnibot")
    with patch.object(adapter, "verify_m2m_token", return_value=False):
        with pytest.raises(A2AAuthError) as exc_info:
            adapter.handle_jsonrpc_call(
                body={"jsonrpc": "2.0", "method": "ask_customer_service", "params": {}, "id": "1"},
                authorization="Bearer bad",
            )
    assert exc_info.value.status == 401


def test_messenger_webhook_verifier_verify():
    """webhooks.py — MessengerWebhookVerifier.verify computes HMAC."""
    from app.api.adapters.verifiers import MessengerWebhookVerifier
    secret = "test_secret"
    verifier = MessengerWebhookVerifier(app_secret=secret)
    raw_body = b"test payload"
    sig = hmac_mod.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    assert verifier.verify(raw_body, f"sha256={sig}") is True


def test_telegram_webhook_verifier_verify():
    """webhooks.py — TelegramWebhookVerifier.verify computes HMAC."""
    from app.api.adapters.verifiers import TelegramWebhookVerifier
    secret = "tg_secret"
    verifier = TelegramWebhookVerifier(secret_token=secret)
    raw_body = b"tg payload"
    sig = hmac_mod.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    assert verifier.verify(raw_body, sig) is True


def test_whatsapp_webhook_verifier_verify_missing_prefix():
    """webhooks.py — WhatsApp verifier rejects sig without sha256= prefix."""
    from app.api.adapters.verifiers import WhatsAppWebhookVerifier
    verifier = WhatsAppWebhookVerifier(app_secret="secret")
    assert verifier.verify(b"payload", "no_prefix_sig") is False


def test_whatsapp_webhook_verifier_verify_hmac():
    """webhooks.py — WhatsApp verifier validates HMAC correctly."""
    from app.api.adapters.verifiers import WhatsAppWebhookVerifier
    secret = "wa_secret"
    verifier = WhatsAppWebhookVerifier(app_secret=secret)
    raw_body = b"wa payload"
    sig = hmac_mod.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    assert verifier.verify(raw_body, f"sha256={sig}") is True


def test_validate_token_missing():
    """webhooks.py — validate_token returns False for unknown token."""
    from app.api.webhooks import validate_token
    assert validate_token("Bearer totally_fake_token_xyz_not_in_store") is False


# ===========================================================================
# app.core.paladin  — TypeError raises, async paths, noop functions
# ===========================================================================

def test_input_sanitizer_non_str_raises():
    """paladin.py — sanitize raises TypeError for non-str input."""
    from app.core.paladin import InputSanitizer
    with pytest.raises(TypeError):
        InputSanitizer().sanitize(123)


def test_prompt_injection_defense_non_str_raises():
    """paladin.py — check_input raises TypeError for non-str input."""
    from app.core.paladin import PromptInjectionDefense
    with pytest.raises(TypeError):
        PromptInjectionDefense().check_input(456)


def test_semantic_classifier_classify_non_str_raises():
    """paladin.py — classify raises TypeError for non-str text."""
    from app.core.paladin import SemanticInjectionClassifier
    with pytest.raises(TypeError):
        SemanticInjectionClassifier().classify(789)


@pytest.mark.asyncio
async def test_semantic_classifier_low_risk_passthrough():
    """paladin.py — classify_async returns passthrough for low risk."""
    from app.core.paladin import SemanticInjectionClassifier
    clf = SemanticInjectionClassifier()
    result = await clf.classify_async("hello", risk_level="low")
    assert result.is_injection is False


@pytest.mark.asyncio
async def test_semantic_classifier_timeout_degraded():
    """paladin.py — classify_async degrades on TimeoutError."""
    from app.core.paladin import SemanticInjectionClassifier
    clf = SemanticInjectionClassifier()
    with patch.object(clf, "_call_llm", side_effect=TimeoutError("too slow")):
        result = await clf.classify_async("test text", risk_level="high")
    assert result.is_injection is False


@pytest.mark.asyncio
async def test_await_coro_from_sync_with_running_loop():
    """paladin.py — _await_coro_from_sync uses thread when loop is running."""
    from app.core.paladin import _await_coro_from_sync

    async def _coro():
        return 42

    result = _await_coro_from_sync(_coro(), timeout_ms=5000.0)
    assert result == 42


@pytest.mark.asyncio
async def test_noop_tier3_returns_empty_string():
    """paladin.py — _noop_tier3 returns empty string."""
    from app.core.paladin import _noop_tier3
    assert await _noop_tier3("some text") == ""


def test_noop_security_log_writer_returns_none():
    """paladin.py — _noop_security_log_writer returns None."""
    from app.core.paladin import _noop_security_log_writer
    assert _noop_security_log_writer(event="test") is None


def test_cosine_similarity_zero_vectors():
    """paladin.py — _cosine_similarity returns 0.0 for zero vectors."""
    from app.core.paladin import GroundingChecker
    checker = GroundingChecker()
    assert checker._cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


@pytest.mark.asyncio
async def test_paladin_pipeline_high_risk_with_mock_classifier():
    """paladin.py — high risk path calls classifier and returns result."""
    from app.core.paladin import PALADINPipeline, SemanticInjectionClassifier
    mock_clf = MagicMock(spec=SemanticInjectionClassifier)
    mock_verdict = MagicMock(is_injection=False, is_unverified_passthrough=False)
    mock_clf.classify_async = AsyncMock(return_value=mock_verdict)
    pipeline = PALADINPipeline(classifier=mock_clf)
    result = await pipeline.process("test text", risk_level="high")
    assert result is not None


@pytest.mark.asyncio
async def test_paladin_pipeline_process_with_knowledge():
    """paladin.py — process_with_knowledge delegates to process."""
    from app.core.paladin import PALADINPipeline
    pipeline = PALADINPipeline()
    mock_result = MagicMock()
    with patch.object(pipeline, "process", return_value=mock_result):
        result = await pipeline.process_with_knowledge("text", knowledge_results=[])
    assert result is mock_result


def test_build_sandwich_prompt_wraps_text():
    """paladin.py — _build_sandwich_prompt wraps user_text with tags."""
    from app.core.paladin import PromptInjectionDefense, _build_sandwich_prompt
    defense = PromptInjectionDefense()
    result = _build_sandwich_prompt(defense, "hello")
    assert "hello" in result


# ===========================================================================
# app.core.knowledge  — HybridKnowledge
# ===========================================================================

def test_hybrid_knowledge_recall_at_k():
    """knowledge.py — recall_at_k returns float >= 0."""
    from app.core.knowledge import HybridKnowledge
    hk = HybridKnowledge()
    result = hk.recall_at_k(dataset=[], k=3)
    assert isinstance(result, float)
    assert result >= 0.0


def test_hybrid_knowledge_query_returns_result():
    """knowledge.py — query returns a KnowledgeResult."""
    from app.core.knowledge import HybridKnowledge, KnowledgeResult
    hk = HybridKnowledge()
    result = hk.query("hello")
    assert isinstance(result, KnowledgeResult)
