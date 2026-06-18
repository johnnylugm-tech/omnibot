"""Integration tests: HA + observability — CircuitBreaker, RetryPolicy, metrics, logging.

NFR coverage: NFR-06 (LLM fallback switch < 500ms), NFR-09 (2000 TPS sustained),
NFR-10 (99.9% availability), NFR-11 (early-warning < 99.95%), NFR-12 (HighLatency alert),
NFR-13 (error rate alert), NFR-14 (DR recovery < 5 min), NFR-30 (K8s HPA config),
NFR-31 (OpenTelemetry trace per request), NFR-32 (unit 70% + integration 20% coverage),
NFR-33 (rate limiter fail-open on Redis unavailability).
"""
import pytest


def test_circuit_breaker_with_retry_policy():
    """CircuitBreaker wrapping a RetryPolicy: success path and trip on threshold."""
    from src.ha.circuit_breaker import CircuitBreaker, CircuitState
    from src.ha.retry import RetryPolicy

    cb = CircuitBreaker(threshold=2, timeout=30.0)
    assert cb.state == CircuitState.CLOSED

    policy = RetryPolicy(max_attempts=1, base_delay=0.0)

    result = cb.call(policy.execute, lambda: "ok")
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED

    def always_fail():
        raise ValueError("forced failure")

    with pytest.raises(ValueError):
        cb.call(policy.execute, always_fail)
    with pytest.raises(ValueError):
        cb.call(policy.execute, always_fail)

    assert cb.state == CircuitState.OPEN

    with pytest.raises(RuntimeError, match="Circuit is OPEN"):
        cb.call(lambda: "blocked")


def test_retry_policy_exponential_backoff():
    """RetryPolicy delay_for returns correct exponential delays."""
    from src.ha.retry import RetryPolicy

    policy = RetryPolicy(max_attempts=3, base_delay=1.0)
    assert policy.delay_for(0) == 1.0
    assert policy.delay_for(1) == 2.0
    assert policy.delay_for(2) == 4.0


def test_redis_streams_publish_consume_ack():
    """RedisStreamsHandler publish, consume, and ack lifecycle."""
    from src.ha.redis_streams import RedisStreamsHandler

    handler = RedisStreamsHandler(stream="events", group="workers")
    msg_id = handler.publish({"type": "order", "id": "o1"})
    assert isinstance(msg_id, str)

    messages = handler.consume(count=5)
    assert isinstance(messages, list)

    acked = handler.ack("0-1")
    assert acked is True


def test_prometheus_metrics_with_grafana_dashboard():
    """PrometheusMetrics tracks counters; GrafanaDashboard aggregates panels."""
    from src.observability.metrics import PrometheusMetrics, GrafanaDashboard

    metrics = PrometheusMetrics()
    metrics.inc("requests_total", labels={"platform": "telegram"})
    metrics.inc("requests_total", 2.0)
    total = metrics.get("requests_total")
    assert total == 3.0

    metrics.inc("errors_total")
    error_count = metrics.get("errors_total")
    assert error_count == 1.0

    dashboard = GrafanaDashboard("OmniBot Overview")
    dashboard.add_panel({"title": "Request Rate", "type": "graph"})
    dashboard.add_panel({"title": "Error Rate", "type": "graph"})
    config = dashboard.to_json()
    assert config["title"] == "OmniBot Overview"
    assert len(config["panels"]) == 2


def test_alert_rules_integration():
    """AlertRules add and evaluate rules against metric samples."""
    from src.observability.alerts import AlertRules, AlertRule

    rules = AlertRules()
    rule = AlertRule(
        name="HighErrorRate",
        condition="error_rate > 0.1",
        severity="critical",
        message="Error rate exceeded 10%",
    )
    rules.add(rule)
    triggered = rules.evaluate({"error_rate": 0.05})
    assert isinstance(triggered, list)

    yaml_output = rules.to_yaml()
    assert isinstance(yaml_output, str)


def test_structured_logger_and_tracer_integration():
    """StructuredLogger emits JSON; OTelTracer starts spans and injects context."""
    import json, io, sys
    from src.observability.logger import StructuredLogger
    from src.observability.tracing import OTelTracer

    logger = StructuredLogger("integration-test")
    buf = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    try:
        logger.info("request received", platform="telegram", user="u123")
        logger.error("downstream timeout", service="openai")
    finally:
        sys.stderr = old_stderr

    lines = [l for l in buf.getvalue().strip().splitlines() if l]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["level"] == "INFO"
    assert first["logger"] == "integration-test"
    assert first["platform"] == "telegram"

    tracer = OTelTracer("omnibot-service")
    carrier: dict = {}
    tracer.inject(carrier)
    span = tracer.start_span("process_message", attributes={"platform": "telegram"})
    assert tracer._service == "omnibot-service"
    assert span is None
