"""
HUB: configuration + health check utilities.
All infra modules call get_setting() and health_probe() per function body.
"""
from __future__ import annotations

import urllib.request
import json
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from openai import OpenAI


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM / Embedding
    openai_api_key: str = ""
    openai_base_url: str = "https://api.minimax.io/v1"
    minimax_api_key: str = ""
    fallback_llm_model: str = "gemini-1.5-flash"

    # LLM model names
    chat_model: str = "MiniMax-M3"
    embedding_model: str = "embo-01"
    embedding_dim: int = 1536

    # Database
    database_url: str = ""

    # Redis
    redis_url: str = ""

    # ClamAV
    clamav_host: str = "127.0.0.1"
    clamav_port: int = 3310

    # Security
    jwt_secret_key: str = ""
    m2m_secret_key: str = ""
    ip_whitelist_cidrs: str = "0.0.0.0/0"

    # Observability
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"
    prometheus_port: int = 8001

    # App
    app_env: str = "development"
    log_level: str = "DEBUG"


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings()


def get_setting(key: str, default: Any = None) -> Any:
    """Typed env var access — called by all infra modules per function body."""
    return getattr(_settings(), key.lower(), default)


@lru_cache(maxsize=1)
def get_llm_client() -> OpenAI:
    """OpenAI-compatible client pointed at MiniMax.
    For M3, always pass extra_body={'thinking': {'type': 'disabled'}} to suppress CoT output.
    """
    cfg = _settings()
    return OpenAI(api_key=cfg.openai_api_key, base_url=cfg.openai_base_url)


def embed(texts: list[str], embed_type: str = "db") -> list[list[float]]:
    # NOTE: MiniMax /v1/embeddings returns {"vectors": [...]} not OpenAI {"data":[{"embedding":[...]}]}
    # OpenAI SDK cannot parse this — must use native HTTP call.
    """MiniMax native embedding endpoint (vectors field, not OpenAI data field)."""
    cfg = _settings()
    api_key = cfg.minimax_api_key or cfg.openai_api_key
    payload = json.dumps({
        "model": cfg.embedding_model,
        "type": embed_type,
        "texts": texts,
    }).encode()
    req = urllib.request.Request(
        "https://api.minimax.io/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    base = data.get("base_resp", {})
    if base.get("status_code", 0) != 0:
        raise RuntimeError(f"MiniMax embedding error: {base}")
    vectors = data.get("vectors")
    if not vectors:
        raise RuntimeError("MiniMax embedding returned no vectors")
    return vectors


def health_probe(service: str) -> dict[str, str]:
    """Called by all infra modules for health reporting."""
    cfg = _settings()
    try:
        if service == "database":
            return {"service": service, "status": "configured", "url": cfg.database_url.split("@")[-1]}
        if service == "redis":
            import redis as redis_lib
            url = cfg.redis_url
            r = redis_lib.from_url(url, ssl_cert_reqs=None)
            r.ping()
            r.close()
            return {"service": service, "status": "ok"}
        if service == "clamav":
            import socket
            with socket.create_connection((cfg.clamav_host, cfg.clamav_port), timeout=2):
                pass
            return {"service": service, "status": "ok"}
    except Exception as exc:
        return {"service": service, "status": "error", "detail": str(exc)}
    return {"service": service, "status": "unknown"}
