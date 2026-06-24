"""[FR-01..06] Unit tests for the per-platform webhook route handlers.

Covers the previously-uncovered paths inside ``webhooks.py``:

    * ``_get_pipeline`` — both the cold (no cached pipeline) and the
      warm (cached pipeline via ``_PIPELINE`` monkeypatch) branches.
    * ``_telegram_adapter`` / ``_line_adapter`` / ``_messenger_adapter``
      / ``_whatsapp_adapter`` / ``_web_adapter`` / ``_a2a_adapter`` —
      each factory must construct the right adapter class with the
      right verify_token / jwt_secret / jwks_url defaults.
    * Every per-platform POST webhook handler — happy path AND the
      ``except Exception`` envelope.
    * The Messenger / WhatsApp GET challenge handlers.

Adapter behaviour is stubbed via ``monkeypatch.setattr`` on the
module-level factory functions (``_telegram_adapter`` etc.) and the
``_PIPELINE`` sentinel so the tests stay hermetic — no real Telegram
calls, no real PALADIN, no real DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.api import webhooks as webhooks_module
from app.api.webhooks import router as webhooks_router
from app.core.unified_message import MessageType, Platform, UnifiedMessage
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(platform: Platform = Platform.TELEGRAM, content: str = "hello") -> UnifiedMessage:
    return UnifiedMessage(
        platform=platform,
        platform_user_id="user-1",
        unified_user_id=None,
        message_type=MessageType.TEXT,
        content=content,
        raw_payload={},
        received_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


def _stub_response(source_value: str = "RULE", content: str = "ok", confidence: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        source=SimpleNamespace(value=source_value),
        confidence=confidence,
        content=content,
    )


def _build_app() -> FastAPI:
    return FastAPI()


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Force the cached pipeline to a MagicMock so no real wiring runs."""
    mock = MagicMock()
    mock.handle_message.return_value = _stub_response()
    monkeypatch.setattr(webhooks_module, "_PIPELINE", mock)
    return mock


@pytest.fixture
def client() -> TestClient:
    app = _build_app()
    app.include_router(webhooks_router)
    return TestClient(app)


# ===========================================================================
# _get_pipeline — cold + warm branches.
# ===========================================================================


def test_get_pipeline_returns_cached_when_pinned(stub_pipeline: MagicMock) -> None:
    """When ``_PIPELINE`` is set, ``_get_pipeline`` returns it verbatim."""
    assert webhooks_module._get_pipeline() is stub_pipeline


def test_get_pipeline_returns_module_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``_PIPELINE is None``, ``_get_pipeline`` builds a default Pipeline."""
    from app.api import webhooks as wh

    # Reset the module-level sentinel to force the cold branch.
    monkeypatch.setattr(wh, "_PIPELINE", None)

    # Patch the real PALADIN/PII/DST/Knowledge/Response constructors to
    # MagicMocks so the cold-path build doesn't try to talk to a real
    # database / LLM.
    from app.core import pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module.Pipeline,
        "__init__",
        lambda self, **_: None,
    )

    pipeline = wh._get_pipeline()
    assert isinstance(pipeline, pipeline_module.Pipeline)


# ===========================================================================
# Adapter factories — each one must yield the right class with the right
# verify_token / jwt_secret / jwks_url defaults.
# ===========================================================================


def test_telegram_adapter_factory() -> None:
    from app.api.adapters.telegram import TelegramWebhookAdapter

    adapter = webhooks_module._telegram_adapter()
    assert isinstance(adapter, TelegramWebhookAdapter)


def test_line_adapter_factory() -> None:
    from app.api.adapters.line import LineWebhookAdapter

    adapter = webhooks_module._line_adapter()
    assert isinstance(adapter, LineWebhookAdapter)


def test_messenger_adapter_factory_uses_env_verify_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.adapters.messenger import MessengerWebhookAdapter

    monkeypatch.setenv("MESSENGER_VERIFY_TOKEN", "fb-verify-token")

    adapter = webhooks_module._messenger_adapter()
    assert isinstance(adapter, MessengerWebhookAdapter)
    assert adapter._verify_token == "fb-verify-token"


def test_messenger_adapter_factory_uses_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.adapters.messenger import MessengerWebhookAdapter

    monkeypatch.delenv("MESSENGER_VERIFY_TOKEN", raising=False)

    adapter = webhooks_module._messenger_adapter()
    assert isinstance(adapter, MessengerWebhookAdapter)
    assert adapter._verify_token == "test"  # hardcoded fallback


def test_whatsapp_adapter_factory_uses_env_verify_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.adapters.whatsapp import WhatsAppWebhookAdapter

    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "wa-verify-token")

    adapter = webhooks_module._whatsapp_adapter()
    assert isinstance(adapter, WhatsAppWebhookAdapter)
    assert adapter._verify_token == "wa-verify-token"


def test_web_adapter_factory_uses_env_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.adapters.web import WebAdapter

    monkeypatch.setenv("OMNIBOT_JWT_SECRET", "my-secret")

    adapter = webhooks_module._web_adapter()
    assert isinstance(adapter, WebAdapter)
    assert adapter._jwt_secret == "my-secret"


def test_a2a_adapter_factory_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.adapters.a2a import A2AAdapter

    monkeypatch.setenv("A2A_JWKS_URL", "https://jwks.example.com")
    monkeypatch.setenv("A2A_AUDIENCE", "aud-x")

    adapter = webhooks_module._a2a_adapter()
    assert isinstance(adapter, A2AAdapter)
    assert adapter._jwks_url == "https://jwks.example.com"
    assert adapter._expected_audience == "aud-x"


# ===========================================================================
# telegram_webhook — happy path + error envelope.
# ===========================================================================


def test_telegram_webhook_happy_path(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_telegram_adapter",
        lambda: SimpleNamespace(process_update=lambda body: _msg(Platform.TELEGRAM, body.get("text", "hi"))),
    )

    response = client.post(
        "/api/v1/webhook/telegram",
        json={"message_id": 1, "text": "hello"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == "RULE"
    assert "confidence" in body


def test_telegram_webhook_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhooks_module, "_telegram_adapter", _explode)

    response = client.post("/api/v1/webhook/telegram", json={"text": "x"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "boom"}


# ===========================================================================
# line_webhook — happy path (count > 0), empty-events path, error envelope.
# ===========================================================================


def test_line_webhook_happy_path_with_messages(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_line_adapter",
        lambda: SimpleNamespace(process_events=lambda events: [_msg(Platform.LINE, "hi")]),
    )

    response = client.post("/api/v1/webhook/line", json={"events": [{"type": "message"}]})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1


def test_line_webhook_returns_zero_count_when_no_events(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_line_adapter",
        lambda: SimpleNamespace(process_events=lambda events: []),
    )

    response = client.post("/api/v1/webhook/line", json={"events": []})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "count": 0}


def test_line_webhook_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(webhooks_module, "_line_adapter", _explode)

    response = client.post("/api/v1/webhook/line", json={"events": []})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "INTERNAL_ERROR"
    assert body["detail"] == "kaboom"


# ===========================================================================
# messenger_webhook — GET challenge + POST happy + POST error.
# ===========================================================================


def test_messenger_challenge_get_handler(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_messenger_adapter",
        lambda: SimpleNamespace(handle_challenge=lambda mode, token, challenge: challenge),
    )

    response = client.get(
        "/api/v1/webhook/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "t", "hub.challenge": "CH123"},
    )

    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "CH123"}


def test_messenger_webhook_happy_path(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_messenger_adapter",
        lambda: SimpleNamespace(parse_entries=lambda entries: [_msg(Platform.MESSENGER)]),
    )

    response = client.post("/api/v1/webhook/messenger", json={"entry": [{"id": "e-1"}]})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["source"] == "RULE"


def test_messenger_webhook_with_empty_entries_returns_count_zero(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_messenger_adapter",
        lambda: SimpleNamespace(parse_entries=lambda entries: []),
    )

    response = client.post("/api/v1/webhook/messenger", json={"entry": []})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["source"] == "rule"  # default branch when msgs is empty


def test_messenger_webhook_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise ValueError("bad payload")

    monkeypatch.setattr(webhooks_module, "_messenger_adapter", _explode)

    response = client.post("/api/v1/webhook/messenger", json={"entry": []})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "bad payload"}


# ===========================================================================
# whatsapp_webhook — GET challenge + POST happy + POST error.
# ===========================================================================


def test_whatsapp_challenge_get_handler(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_whatsapp_adapter",
        lambda: SimpleNamespace(handle_challenge=lambda mode, token, challenge: challenge),
    )

    response = client.get(
        "/api/v1/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "t", "hub.challenge": "WA-OK"},
    )

    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "WA-OK"}


def test_whatsapp_webhook_happy_path(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_whatsapp_adapter",
        lambda: SimpleNamespace(parse_messages=lambda payload: [_msg(Platform.WHATSAPP)]),
    )

    response = client.post("/api/v1/webhook/whatsapp", json={"messages": [{"id": "m-1"}]})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 1


def test_whatsapp_webhook_with_empty_messages_returns_count_zero(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_whatsapp_adapter",
        lambda: SimpleNamespace(parse_messages=lambda payload: []),
    )

    response = client.post("/api/v1/webhook/whatsapp", json={"messages": []})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["source"] == "rule"


def test_whatsapp_webhook_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise ValueError("bad whatsapp payload")

    monkeypatch.setattr(webhooks_module, "_whatsapp_adapter", _explode)

    response = client.post("/api/v1/webhook/whatsapp", json={"messages": []})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "bad whatsapp payload"}


# ===========================================================================
# web_guest_session + web_message — happy + error.
# ===========================================================================


def test_web_guest_session_happy_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_web_adapter",
        lambda: SimpleNamespace(create_guest_session=lambda: {"session_id": "guest-1"}),
    )

    response = client.post("/api/v1/web/guest-session")

    assert response.status_code == 200
    assert response.json() == {"session_id": "guest-1"}


def test_web_guest_session_returns_error_envelope_on_exception(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise RuntimeError("redis down")

    monkeypatch.setattr(webhooks_module, "_web_adapter", _explode)

    response = client.post("/api/v1/web/guest-session")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "redis down"}


def test_web_message_happy_path(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_web_adapter",
        lambda: SimpleNamespace(
            process_message=lambda token, content: _msg(Platform.WEB, content),
        ),
    )

    response = client.post(
        "/api/v1/web/message",
        json={"content": "hello"},
        headers={"Authorization": "Bearer guest-jwt"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["content"] == "ok"


def test_web_message_without_auth_header(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``authorization`` defaults to ``""`` — the route MUST tolerate that."""
    monkeypatch.setattr(
        webhooks_module,
        "_web_adapter",
        lambda: SimpleNamespace(process_message=lambda token, content: _msg(Platform.WEB, content)),
    )

    response = client.post("/api/v1/web/message", json={"content": "hello"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_message_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise RuntimeError("adapter boom")

    monkeypatch.setattr(webhooks_module, "_web_adapter", _explode)

    response = client.post("/api/v1/web/message", json={"content": "x"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "adapter boom"}


# ===========================================================================
# a2a_rpc — happy + error.
# ===========================================================================


def test_a2a_rpc_happy_path(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        webhooks_module,
        "_a2a_adapter",
        lambda: SimpleNamespace(
            handle_jsonrpc_call=lambda body, auth: _msg(Platform.A2A, body.get("params", {}).get("text", "")),
        ),
    )

    response = client.post(
        "/api/v1/a2a/rpc",
        json={"jsonrpc": "2.0", "id": 42, "method": "ask", "params": {"text": "ping"}},
        headers={"Authorization": "Bearer a2a-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == "RULE"
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 42


def test_a2a_rpc_returns_error_envelope_on_exception(
    client: TestClient,
    stub_pipeline: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode():
        raise RuntimeError("a2a boom")

    monkeypatch.setattr(webhooks_module, "_a2a_adapter", _explode)

    response = client.post("/api/v1/a2a/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "ask"})

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "error", "code": "INTERNAL_ERROR", "detail": "a2a boom"}
