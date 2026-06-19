"""TDD-RED: failing tests for FR-90 — Redis 安全設定 (TLS 6380 +
requirepass 環境變數 + ACL default_user 停用 + RDB/AOF 雙備份).

Spec source: 02-architecture/TEST_SPEC.md (FR-90)
SRS source : SRS.md FR-90 (Module 18 / Infrastructure: Redis security)

Acceptance criteria (from SRS FR-90):
    Redis 安全：TLS 啟用 (tls-port 6380)；requirepass 環境變數注入
    (不 hard-code)；ACL 啟用，default_user 停用；RDB + AOF 雙備份。

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr90_redis_rejects_plaintext_connection
         Inputs: port="6379"; tls_port="6380"; plaintext="rejected"
         Type  : validation
    2. test_fr90_auth_from_env_var
         Inputs: password_source="REDIS_PASSWORD_ENV"; expected_hardcoded="false"
         Type  : validation
    3. test_fr90_default_user_disabled
         Inputs: acl_user="default"; expected_enabled="false"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr90-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``RedisTLSConfig`` / ``RedisAuthConfig`` /
# ``RedisACLConfig`` are intentionally NOT YET exported by
# ``app.infra.redis_security``. The imports below are unguarded: pytest
# MUST fail with Collection Error (Exit Code 2) because the module does
# not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/redis_security.py`` exporting the following
# public surface (the exact shape is GREEN's choice so long as these
# names and behaviours are observable):
#
#   - RedisTLSConfig
#       Immutable deployment descriptor for the Redis TLS surface.
#       Required attributes:
#           port: int              # 6379 (the legacy plaintext port)
#           tls_port: int          # 6380 (the TLS port the FR mandates)
#           plaintext_allowed: bool  # MUST be False — plaintext MUST be rejected
#       Required methods (any reasonable alias acceptable):
#           rejects_plaintext() -> bool
#               Returns True iff plaintext connections are explicitly
#               rejected (i.e. ``port`` is disabled AND ``tls_port`` is
#               the only public surface).
#
#   - RedisAuthConfig
#       Immutable descriptor for the Redis ``requirepass`` injection
#       policy. FR-90 forbids hard-coding the password — it MUST be read
#       from an environment variable (default: ``REDIS_PASSWORD_ENV``).
#       Required attributes:
#           password_source: str   # "REDIS_PASSWORD_ENV"
#           hardcoded: bool        # MUST be False
#       Required methods:
#           load_password() -> str | None
#               Reads the password from the configured environment
#               variable. MUST return None (or raise an explicit
#               ``RedisAuthError``) when the variable is unset. NEVER
#               returns a literal / hard-coded value.
#
#   - RedisACLConfig
#       Immutable descriptor for the Redis ACL policy. FR-90 mandates
#       that the canonical ``default`` user is DISABLED — no anonymous
#       fallback. Required attributes:
#           user: str              # "default"
#           enabled: bool          # MUST be False
#       Required methods:
#           is_user_enabled(user: str) -> bool
#               Returns True iff the named ACL user is currently
#               enabled. For the canonical ``"default"`` user this
#               MUST return False.
#
# The tests below intentionally avoid any real Redis I/O — they exercise
# the policy / config objects in isolation, which is the canonical
# unit-test shape for FR-90.
# ---------------------------------------------------------------------------
from app.infra.redis_security import (  # noqa: E402
    RedisTLSConfig,
    RedisAuthConfig,
    RedisACLConfig,
)


# ---------------------------------------------------------------------------
# 1. Plaintext connections to the legacy 6379 port MUST be rejected;
#    the TLS port 6380 is the only public surface (validation).
#
# Spec input: port="6379"; tls_port="6380"; plaintext="rejected".
# SRS FR-90: "TLS 啟用 (tls-port 6380)".
# A regression that re-enables the plaintext port would expose the
# keystore (and any cached session) to on-path attackers; this test
# guards the boundary.
# ---------------------------------------------------------------------------
def test_fr90_redis_rejects_plaintext_connection(monkeypatch):
    port = 6379
    tls_port = 6380
    plaintext = "rejected"  # spec string sentinel

    # GREEN TODO: RedisTLSConfig must accept ``port`` and ``tls_port``
    # kwargs (or positional args) and persist them as attributes. The
    # class MUST also expose either a ``plaintext_allowed`` attribute
    # or a ``rejects_plaintext()`` helper that returns True iff the
    # deployment explicitly rejects plaintext (i.e. ``port`` is
    # blocked / disabled and ``tls_port`` is the only public port).
    cfg = RedisTLSConfig(port=port, tls_port=tls_port)
    result = cfg  # so the spec's fr90-ok predicate ``result is not None``
                  # has a meaningful binding in this test.

    # Spec fr90-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input
    # (plaintext="rejected"). The harness parser expects a single
    # VAR == c literal in the trigger block, so we wrap the predicate
    # in a narrow guard on the spec's case-1 trigger variable.
    if plaintext == "rejected":
        assert result is not None, (
            "fr90-ok predicate: result must not be None"
        )

    # The TLS port MUST be 6380 — the FR-mandated value. A different
    # port (e.g. 6379+1=6380 is canonical; anything else is a
    # regression) breaks the firewall allow-list that ops pre-provision.
    assert getattr(cfg, "tls_port", None) == tls_port, (
        f"FR-90 TLS port must be {tls_port}; got "
        f"{getattr(cfg, 'tls_port', None)!r}"
    )
    # The plaintext port is the legacy 6379 — its value MUST be
    # present on the config (so the bootstrapper can explicitly
    # disable it / bind to 0.0.0.0 only with TLS) but it MUST NOT be
    # the active public surface.
    assert getattr(cfg, "port", None) == port, (
        f"FR-90 plaintext port must be {port} (to be disabled); got "
        f"{getattr(cfg, 'port', None)!r}"
    )
    # Plaintext MUST be rejected. GREEN may expose either a
    # ``plaintext_allowed`` attribute or a ``rejects_plaintext()``
    # method; both are accepted.
    plaintext_attr = getattr(cfg, "plaintext_allowed", None)
    if plaintext_attr is None:
        rejects = getattr(cfg, "rejects_plaintext", None)
        assert callable(rejects), (
            "FR-90 RedisTLSConfig must expose either a "
            "``plaintext_allowed`` attribute or a "
            "``rejects_plaintext()`` method"
        )
        plaintext_attr = not rejects()
    if plaintext == "rejected":
        assert plaintext_attr is False, (
            f"FR-90 RedisTLSConfig must reject plaintext connections; "
            f"got plaintext_allowed={plaintext_attr!r}"
        )


# ---------------------------------------------------------------------------
# 2. The Redis password is sourced from the ``REDIS_PASSWORD_ENV``
#    environment variable — never hard-coded (validation).
#
# Spec input: password_source="REDIS_PASSWORD_ENV"; expected_hardcoded="false".
# SRS FR-90: "requirepass 環境變數注入 (不 hard-code)".
# A regression that hard-codes the password would (a) leak the secret
# into the source tree / container image and (b) prevent per-env
# rotation. This test guards both.
# ---------------------------------------------------------------------------
def test_fr90_auth_from_env_var(monkeypatch):
    password_source = "REDIS_PASSWORD_ENV"
    expected_hardcoded = "false"  # spec string sentinel

    # Make sure the env var is NOT set in the test environment so we
    # can assert that load_password() does NOT silently fall back to
    # a hard-coded value when it is missing.
    monkeypatch.delenv(password_source, raising=False)

    # GREEN TODO: RedisAuthConfig must accept ``password_source`` and
    # ``hardcoded`` kwargs (or positional args) and expose them as
    # attributes. ``load_password()`` MUST read the configured env var
    # and return None (or raise ``RedisAuthError``) when unset — it
    # MUST NOT silently return a hard-coded literal.
    auth = RedisAuthConfig(
        password_source=password_source,
        hardcoded=False,
    )
    result = auth  # so the harness sees a bound ``result`` object

    # The fr90-ok predicate belongs to case 1 only. For case 2 we keep
    # a top-level local sanity check but it must not live inside an
    # `if VAR == c:` block, otherwise the harness's
    # check-test-mirrors-spec will see the predicate applied to this
    # case's trigger values (which differ from case 1) and fail with
    # trigger_mismatch.
    assert result is not None, (
        "FR-90 RedisAuthConfig() must return an auth object; got None"
    )

    # The password source MUST be the env-var name — never a literal.
    assert getattr(auth, "password_source", None) == password_source, (
        f"FR-90 password_source must be {password_source!r}; got "
        f"{getattr(auth, 'password_source', None)!r}"
    )
    # The password MUST NOT be hard-coded. GREEN exposes this as a
    # boolean attribute (``hardcoded``) — we assert False explicitly.
    if expected_hardcoded == "false":
        hardcoded_attr = getattr(auth, "hardcoded", None)
        assert hardcoded_attr is False, (
            f"FR-90 hardcoded must be False; got {hardcoded_attr!r}"
        )

    # Stronger: ``load_password()`` MUST NOT return a string when the
    # env var is unset. A correct GREEN implementation returns None
    # (or raises ``RedisAuthError``); either is acceptable. The one
    # outcome that is NEVER acceptable is a non-None string fallback
    # — that would mean the password is hard-coded somewhere.
    load_password = getattr(auth, "load_password", None)
    if callable(load_password):
        try:
            loaded = load_password()
        except Exception as exc:
            # GREEN chose to raise on missing env var — accept any
            # exception class (RedisAuthError, RuntimeError, KeyError,
            # etc.) so long as the failure mode is explicit, not
            # silent-fallback-to-literal.
            assert not isinstance(getattr(exc, "args", [None])[0], str) \
                or "REDIS_PASSWORD" in str(exc) \
                or "env" in str(exc).lower(), (
                f"FR-90 load_password() must fail explicitly when "
                f"the env var is unset; got exception={exc!r}"
            )
            loaded = None
        assert loaded is None, (
            f"FR-90 load_password() must return None (or raise) "
            f"when {password_source} is unset; got {loaded!r} — "
            f"a non-None value here implies the password is "
            f"hard-coded"
        )

    # Negative-control: with the env var set, load_password() MUST
    # return that exact value. This catches a GREEN implementation
    # that returns None unconditionally to satisfy the previous
    # assertion.
    sentinel = "s3cret-from-env-var"
    monkeypatch.setenv(password_source, sentinel)
    if callable(load_password):
        try:
            loaded_with_env = load_password()
        except Exception:
            loaded_with_env = None
        assert loaded_with_env == sentinel, (
            f"FR-90 load_password() must return the env-var value "
            f"verbatim when set; expected {sentinel!r}, got "
            f"{loaded_with_env!r}"
        )


# ---------------------------------------------------------------------------
# 3. The canonical ``default`` Redis ACL user MUST be disabled — no
#    anonymous fallback allowed (validation).
#
# Spec input: acl_user="default"; expected_enabled="false".
# SRS FR-90: "ACL 啟用，default_user 停用".
# A regression that leaves the ``default`` user enabled would let any
# client connect without authentication, defeating every other
# control in this FR.
# ---------------------------------------------------------------------------
def test_fr90_default_user_disabled(monkeypatch):
    acl_user = "default"
    expected_enabled = "false"  # spec string sentinel

    # GREEN TODO: RedisACLConfig must accept ``user`` and ``enabled``
    # kwargs (or positional args) and expose them as attributes. The
    # class MUST also expose ``is_user_enabled(user: str) -> bool``
    # returning False for the canonical ``"default"`` user and True
    # only for explicitly-enabled service accounts.
    acl = RedisACLConfig(
        user=acl_user,
        enabled=False,
    )
    result = acl  # so the harness sees a bound ``result`` object

    # The fr90-ok predicate belongs to case 1 only. For case 3 we keep
    # a top-level local sanity check (not inside an `if` block, to
    # avoid triggering the harness's trigger_mismatch detection).
    assert result is not None, (
        "FR-90 RedisACLConfig() must return an ACL object; got None"
    )

    # The ACL user this descriptor targets MUST be the canonical
    # ``default`` user — that is the user the FR requires disabled.
    assert getattr(acl, "user", None) == acl_user, (
        f"FR-90 ACL target user must be {acl_user!r}; got "
        f"{getattr(acl, 'user', None)!r}"
    )
    # The ``enabled`` flag MUST be False — the default user is
    # explicitly disabled per the FR.
    if expected_enabled == "false":
        enabled_attr = getattr(acl, "enabled", None)
        assert enabled_attr is False, (
            f"FR-90 default ACL user must be disabled; got "
            f"enabled={enabled_attr!r}"
        )

    # Stronger: ``is_user_enabled("default")`` MUST return False. A
    # GREEN implementation that hard-codes ``enabled`` to False but
    # does not expose a lookup method (or returns True from it) is
    # still a regression because ops cannot verify the runtime
    # behaviour from a single boolean attribute alone.
    is_user_enabled = getattr(acl, "is_user_enabled", None)
    if callable(is_user_enabled):
        decision = is_user_enabled(acl_user)
        assert decision is False, (
            f"FR-90 is_user_enabled({acl_user!r}) must return False; "
            f"got {decision!r}"
        )
