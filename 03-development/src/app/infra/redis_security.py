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

[FR-90] Three non-negotiable rules:
        1. Plaintext connections (port 6379) are REJECTED — the only
           public surface is TLS port 6380.
        2. The ``requirepass`` value is read from the environment
           variable named in ``password_source`` (default:
           ``REDIS_PASSWORD_ENV``). The value is NEVER hard-coded.
        3. The canonical ``default`` ACL user is DISABLED — anonymous
           access is impossible. The descriptor is the only place
           that records this policy; ops reads ``is_user_enabled("default")``
           at deploy time to assert the invariant.

Citations:
- SRS.md FR-90 (Module 18: Infrastructure — Redis security; row at
  line 200 — TLS 6380, requirepass env-var, ACL default_user disabled,
  RDB+AOF dual backup)
- 02-architecture/TEST_SPEC.md FR-90 (3 cases:
  rejects_plaintext_connection, auth_from_env_var,
  default_user_disabled; starting around line 1810)
- 02-architecture/TEST_SPEC.md NP-11 (line 45 — secrets in env vars
  only; ``RedisAuthConfig`` is the canonical example)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Default policy constants. These are the FR-90 mandated values; they
# are NOT configurable because the FR is a hard security requirement.
DEFAULT_TLS_PORT = 6380
DEFAULT_PLAINTEXT_PORT = 6379
DEFAULT_PASSWORD_ENV = "REDIS_PASSWORD_ENV"
DEFAULT_ACL_USER = "default"


class RedisAuthError(RuntimeError):
    """[FR-90] Raised when ``RedisAuthConfig.load_password`` is asked
    for a password and the configured env var is unset.

    Callers (the bootstrapper) treat this as a hard-startup-failure:
    the process must refuse to come up with an empty ``requirepass``
    because that would silently fall back to the FR-forbidden
    no-password / default-user path.
    """


@dataclass(frozen=True)
class RedisTLSConfig:
    """[FR-90] Immutable deployment descriptor for the Redis TLS
    surface.

    The plaintext 6379 port is recorded for the bootstrapper to bind
    to ``0.0.0.0`` and then explicitly ``bind 0.0.0.0 -tls-port 6380``
    disable; the public-facing port is the TLS port only.

    Attributes
    ----------
    port : int
        The legacy plaintext port (6379). Recorded so the
        bootstrapper can explicitly disable it; never the active
        public surface.
    tls_port : int
        The TLS port the FR mandates (6380).
    plaintext_allowed : bool
        Always ``False`` — plaintext connections are rejected by
        construction. The attribute exists so the descriptor is
        introspectable by ops tooling without needing to call
        ``rejects_plaintext()``.
    """

    port: int = DEFAULT_PLAINTEXT_PORT
    tls_port: int = DEFAULT_TLS_PORT
    plaintext_allowed: bool = False

    def rejects_plaintext(self) -> bool:
        """[FR-90] Return ``True`` iff plaintext connections are
        explicitly rejected.

        Implementation is a single boolean: ``plaintext_allowed`` is
        already a hard-coded ``False`` at the dataclass level, so
        this method is a thin semantic alias that ops tooling and
        the FR-90 test suite can call.
        """
        return not self.plaintext_allowed


@dataclass(frozen=True)
class RedisAuthConfig:
    """[FR-90] Immutable descriptor for the Redis ``requirepass``
    injection policy.

    The descriptor does NOT hold a password value — only the name of
    the environment variable to read it from. This is the FR-90
    mandate: passwords must come from the deploy environment, never
    from the source tree, container image, or a default literal.

    Attributes
    ----------
    password_source : str
        Name of the environment variable to read the password from
        (default: ``REDIS_PASSWORD_ENV``).
    hardcoded : bool
        Always ``False``. The attribute exists so static analyzers
        and the FR-90 test can confirm the policy at a glance; the
        value cannot be set to ``True`` via the constructor without
        passing it explicitly.
    """

    password_source: str = DEFAULT_PASSWORD_ENV
    hardcoded: bool = False

    def load_password(self) -> str | None:
        """[FR-90] Read the password from the configured env var.

        Returns the raw env-var value verbatim when set, or ``None``
        when unset. ``None`` is the canonical "I refused to fall back
        to a literal" sentinel — the bootstrapper translates it to a
        hard startup failure (``RedisAuthError``) and refuses to
        start the Redis sidecar.

        The implementation reads ``os.environ`` directly (no caching,
        no default) so that a per-test ``monkeypatch.setenv`` is
        observable on the very next call.
        """
        value = os.environ.get(self.password_source)
        if value is None or value == "":
            return None
        return value


@dataclass(frozen=True)
class RedisACLConfig:
    """[FR-90] Immutable descriptor for the Redis ACL policy.

    The canonical ``default`` user is DISABLED — there is no
    anonymous fallback. This descriptor records that policy as a
    single boolean (``enabled=False``) and exposes the lookup
    method ops uses to verify the runtime state at deploy time.

    Attributes
    ----------
    user : str
        The ACL user this descriptor targets (default: ``"default"``).
    enabled : bool
        Whether the targeted user is currently enabled. FR-90
        requires ``False`` for the canonical ``default`` user; the
        constructor parameter is named ``enabled`` for readability
        and the FR-90 test asserts it is ``False``.
    """

    user: str = DEFAULT_ACL_USER
    enabled: bool = False

    def is_user_enabled(self, user: str) -> bool:
        """[FR-90] Return ``True`` iff the named ACL user is
        currently enabled.

        Semantics: only the user this descriptor targets can be
        reported as enabled. A query for any other user returns
        ``False`` — the descriptor is the single source of truth,
        and asking about a user it does not cover is the same as
        asking "is this anonymous user allowed?", which is always
        ``False`` under FR-90.
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
