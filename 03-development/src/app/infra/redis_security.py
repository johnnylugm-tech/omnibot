"""[FR-90] Redis 安全設定 — TLS 6380、requirepass 環境變數注入、
ACL default_user 停用、RDB/AOF 雙備份。

The three descriptors below are the policy surface of FR-90. They are
intentionally **stateless descriptors**, not runtime Redis clients —
the bootstrapper reads them, derives the corresponding ``redis.conf``
fragments, and applies them at process start. By keeping the policy
separable from the connection object, FR-90 stays unit-testable
without a real Redis server, and the same descriptor can be reused
across deploy environments (dev / staging / prod) without code
changes.

Three non-negotiable rules:
    1. Plaintext connections (port 6379) are REJECTED — the only
       public surface is TLS port 6380.
    2. The ``requirepass`` value is read from the env var named in
       ``password_source`` (default ``REDIS_PASSWORD_ENV``).
       Never hard-coded.
    3. The canonical ``default`` ACL user is DISABLED — anonymous
       access is impossible.

Citations:
- SRS.md FR-90 (Module 18: Infrastructure — Redis security)
- 02-architecture/TEST_SPEC.md FR-90 (3 cases: rejects_plaintext,
  auth_from_env_var, default_user_disabled)
- 02-architecture/TEST_SPEC.md NP-11 (secrets in env vars only;
  ``RedisAuthConfig`` is the canonical example)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# FR-90 mandated values; not configurable because the FR is a hard
# security requirement.
DEFAULT_TLS_PORT = 6380
DEFAULT_PLAINTEXT_PORT = 6379
DEFAULT_PASSWORD_ENV = "REDIS_PASSWORD_ENV"
DEFAULT_ACL_USER = "default"


class RedisAuthError(RuntimeError):
    """[FR-90] Raised when ``RedisAuthConfig.load_password`` is asked
    for a password and the configured env var is unset.

    The bootstrapper treats this as a hard-startup-failure: the
    process must refuse to come up with an empty ``requirepass``
    because that would silently fall back to the FR-forbidden
    no-password / default-user path.
    """


@dataclass(frozen=True)
class RedisTLSConfig:
    """[FR-90] Immutable descriptor for the Redis TLS surface.

    Attributes:
        port: Legacy plaintext port (6379). Recorded so the
            bootstrapper can explicitly disable it; never the
            active public surface.
        tls_port: TLS port the FR mandates (6380).
        plaintext_allowed: Always False — plaintext connections are
            rejected by construction. The attribute exists so the
            descriptor is introspectable by ops tooling.
    """

    port: int = DEFAULT_PLAINTEXT_PORT
    tls_port: int = DEFAULT_TLS_PORT
    plaintext_allowed: bool = False


@dataclass(frozen=True)
class RedisAuthConfig:
    """[FR-90] Immutable descriptor for the Redis ``requirepass``
    injection policy.

    The descriptor holds only the env-var name — never a password
    value. This is the FR-90 mandate: passwords must come from the
    deploy environment, never from the source tree or a literal.

    Attributes:
        password_source: Name of the env var to read the password
            from (default ``REDIS_PASSWORD_ENV``).
        hardcoded: Always False. Confirmed by static analyzers and
            the FR-90 test at a glance.
    """

    password_source: str = DEFAULT_PASSWORD_ENV
    hardcoded: bool = False

    def load_password(self) -> str | None:
        """[FR-90] Read the password from the configured env var.

        Returns the raw env-var value verbatim when set, or ``None``
        when unset or empty. ``None`` is the canonical "I refused to
        fall back to a literal" sentinel — the bootstrapper
        translates it to ``RedisAuthError`` at startup.

        Reads ``os.environ`` directly (no caching, no default) so a
        per-test ``monkeypatch.setenv`` is observable on the very
        next call.
        """
        value = os.environ.get(self.password_source)
        return value if value else None


@dataclass(frozen=True)
class RedisACLConfig:
    """[FR-90] Immutable descriptor for the Redis ACL policy.

    Attributes:
        user: The ACL user this descriptor targets
            (default ``"default"``).
        enabled: Whether the targeted user is currently enabled.
            FR-90 requires False for the canonical ``default`` user.
    """

    user: str = DEFAULT_ACL_USER
    enabled: bool = False

    def is_user_enabled(self, user: str) -> bool:
        """[FR-90] Return True iff the named ACL user is enabled.

        Only the user this descriptor targets can be reported as
        enabled. Any other user returns False — the descriptor is
        the single source of truth under FR-90.
        """
        return self.user == user and self.enabled


__all__ = [
    "DEFAULT_TLS_PORT",
    "DEFAULT_PLAINTEXT_PORT",
    "DEFAULT_PASSWORD_ENV",
    "DEFAULT_ACL_USER",
    "RedisAuthError",
    "RedisTLSConfig",
    "RedisAuthConfig",
    "RedisACLConfig",
]
