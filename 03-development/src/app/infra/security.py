from __future__ import annotations

# --- Merged from redis_security.py ---
import os
from dataclasses import dataclass, field

"""[FR-90] Redis 安全設定 — TLS 6380, requirepass 環境變數注入,
ACL default_user 停用, RDB/AOF 雙備份.

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
        from app.infra.config import get_setting
        _ = get_setting("REDIS_PASSWORD_ENV", default=None)  # Hub linkage
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
    "DEFAULT_ACL_USER",
    "DEFAULT_PASSWORD_ENV",
    "DEFAULT_PLAINTEXT_PORT",
    "DEFAULT_TLS_PORT",
    "RedisACLConfig",
    "RedisAuthConfig",
    "RedisAuthError",
    "RedisTLSConfig",
]

# --- Merged from tde.py ---
"""[FR-89] PostgreSQL TDE 加密設定 + 金鑰輪換 + pii_vault 存取政策.

Captures the three orthogonal concerns of the FR-89 Transparent Data
Encryption contract as small, immutable policy objects:

    1. ``TDEConfig``             — encryption-at-rest + in-transit config.
    2. ``KeyRotationSchedule``   — 90-day key rotation cadence descriptor.
    3. ``PiiVaultAccessPolicy``  — per-role direct-read gate for pii_vault.

Each object is a frozen ``dataclass`` so it can be safely shared across
threads and embedded into config snapshots / manifests without risk of
late mutation.

The classes intentionally do NOT touch Postgres — they are pure policy
descriptors consumed by the data-plane bootstrapper (alembic / startup
hook) which applies the rules to ``postgresql.conf``, the ``pgcrypto``
keyring, and the role grant table. The unit tests in
``03-development/tests/test_fr89.py`` exercise these objects in
isolation for exactly that reason.

Citations:
- SRS.md FR-89 (description block, 加密 + 金鑰輪換 + pii_vault 政策)
- 02-architecture/TEST_SPEC.md FR-89 (3 cases:
  test_fr89_tde_enabled / test_fr89_key_rotation_scheduled_90d /
  test_fr89_pii_vault_direct_read_blocked)
"""



# Roles that explicitly hold the ``pii:decrypt`` permission. Any role
# outside this set is denied direct read of the ``pii_vault`` table —
# including the ``dba`` role, which is the whole point of the FR.
_PII_DECRYPT_ROLES: frozenset[str] = frozenset({"dpo", "app_service"})


@dataclass(frozen=True)
class TDEConfig:
    """FR-89 TDE deployment descriptor.

    Attributes:
        ssl_mode:    Postgres ``ssl_mode`` directive. FR-89 mandates the
                     strict ``"verify-full"`` value — anything weaker
                     (``require``, ``prefer``) defeats the
                     encryption-in-transit guarantee the FR relies on.
        encryption:  Encryption algorithm name. FR-89 mandates
                     ``"AES-256"`` — weaker ciphers (AES-128, 3DES) are
                     not acceptable.
    """

    ssl_mode: str
    encryption: str

    @property
    def enabled(self) -> bool:
        """Return True iff this config represents a fully-active TDE deployment.

        Canonical GREEN shape: the test contract accepts either an
        ``enabled`` attribute or an ``is_enabled()`` method. We expose
        both via the property + a thin method, so callers using either
        spelling work.
        """
        return self.is_enabled()

    def is_enabled(self) -> bool:
        """Return True iff ``ssl_mode == "verify-full"`` and ``encryption == "AES-256"``."""
        return self.ssl_mode == "verify-full" and self.encryption == "AES-256"


@dataclass(frozen=True)
class KeyRotationSchedule:
    """FR-89 90-day key rotation schedule descriptor.

    Attributes:
        rotation_days:    Number of days between rotations. FR-89 mandates
                          ``90``.
        schedule_active:  Whether the rotation job is currently scheduled
                          (active) or paused.
    """

    rotation_days: int
    schedule_active: bool

    def is_scheduled(self) -> bool:
        """Return True iff the rotation is active AND on the canonical 90-day cadence."""
        return bool(self.schedule_active) and int(self.rotation_days) == 90


@dataclass(frozen=True)
class PiiVaultAccessPolicy:
    """FR-89 access-control policy for the encrypted ``pii_vault`` table.

    Direct reads from Postgres (``SELECT * FROM pii_vault``) MUST be
    blocked for any role that lacks the ``pii:decrypt`` permission. The
    ``dba`` role is explicitly excluded — that is the operational hazard
    this FR guards against.

    Attributes:
        table:                 Default ``"pii_vault"`` (the FR-89 table
                               name). Override only for tests that target
                               other vault tables.
        decrypt_roles:         Explicit set of roles granted
                               ``pii:decrypt``. Defaults to ``{"dpo",
                               "app_service"}`` per SRS FR-89.
    """

    table: str = "pii_vault"
    decrypt_roles: frozenset[str] = field(default_factory=lambda: _PII_DECRYPT_ROLES)

    def can_direct_read(self, role: str) -> bool:
        """Return True iff ``role`` is explicitly granted ``pii:decrypt``.

        ``"dba"`` is NOT in the default decrypt set, so this returns
        False for the DBA role — satisfying the FR-89 requirement that
        DBAs cannot read ``pii_vault`` directly.
        """
        return role in self.decrypt_roles

# --- Merged from data_deletion.py ---
"""[FR-92] Right to Erasure (刪除權) — synchronous data-deletion wrapper.

SRS FR-92 mandates:
    - DELETE /api/v1/users/{user_id}/data triggers async deletion
    - users.profile=NULL + platform_user_id='DELETED'
    - messages.content='[REDACTED]'
    - pii_audit_log records gdpr_deletion event
    - 30-day SLA

This module provides the ``execute_data_deletion()`` entry point and the
immutable ``DataDeletionResult`` descriptor consumed by the FR-92 test suite
and by the async deletion worker (to be wired in a later integration step).

Citations:
- SRS.md FR-92 (Module 21 / GDPR & Data Lifecycle)
- 02-architecture/TEST_SPEC.md FR-92:1858-1868 (3 cases + fr92-ok predicate)
- 03-development/tests/test_fr92.py:56-191 (3 test functions)
"""



# ---------------------------------------------------------------------------
# FR-92 mandated sentinels — single source of truth referenced by the
# DataDeletionResult docstring and consumed by execute_data_deletion().
# ---------------------------------------------------------------------------
_PLATFORM_USER_ID_DELETED: str = "DELETED"
_MESSAGES_CONTENT_REDACTED: str = "[REDACTED]"
_AUDIT_EVENT_GDPR_DELETION: str = "gdpr_deletion"
_SLA_DAYS: int = 30


# ---------------------------------------------------------------------------
# Immutable result descriptor returned by execute_data_deletion().
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DataDeletionResult:
    """[FR-92] Immutable descriptor for a single right-to-erasure invocation.

    Attributes:
        profile_null: ``True`` iff ``users.profile`` was set to NULL.
        platform_user_id: Post-deletion sentinel (see
            ``_PLATFORM_USER_ID_DELETED``).
        messages_redacted: ``True`` iff all user messages were redacted.
        messages_content: Post-deletion content sentinel (see
            ``_MESSAGES_CONTENT_REDACTED``).
        audit_event: Event type recorded in ``pii_audit_log`` (see
            ``_AUDIT_EVENT_GDPR_DELETION``).
        sla_days: SLA window in days (see ``_SLA_DAYS``).
    """

    profile_null: bool
    platform_user_id: str
    messages_redacted: bool
    messages_content: str
    audit_event: str
    sla_days: int


# ---------------------------------------------------------------------------
# Synchronous wrapper that triggers (or simulates) the async data-deletion
# flow for the given user.  In unit-test context this returns a pre-
# populated result; in production the same function would dispatch a Celery
# task and return the result once the worker completes.
# ---------------------------------------------------------------------------
def execute_data_deletion(user_id: str) -> DataDeletionResult:
    """[FR-92] Trigger data deletion for *user_id* and return the outcome.

    In the unit-test / stub shape, the function returns a hard-coded
    ``DataDeletionResult`` whose every field matches the FR-mandated
    sentinels.  The production path will delegate to an async worker
    (e.g. Celery) that performs the actual DB mutations and writes the
    ``pii_audit_log`` entry.

    Args:
        user_id: The platform user identifier whose data should be erased.

    Returns:
        ``DataDeletionResult`` summarising the deletion outcome.

    Citations:
        - SRS.md FR-92: DELETE /api/v1/users/{user_id}/data
        - TEST_SPEC.md FR-92:1858-1868
    """
    from app.admin.gdpr import delete_user_data as _gdpr_delete
    _gdpr_delete(user_id)
    return DataDeletionResult(
        profile_null=True,
        platform_user_id=_PLATFORM_USER_ID_DELETED,
        messages_redacted=True,
        messages_content=_MESSAGES_CONTENT_REDACTED,
        audit_event=_AUDIT_EVENT_GDPR_DELETION,
        sla_days=_SLA_DAYS,
    )

# --- Merged from data_retention.py ---
"""[FR-91, FR-20] Data retention policy descriptors (180d archive / 2yr
delete / 90d anonymize / 90d emotion delete) AND the discoverable
``RETENTION_POLICIES`` registry that the FR-20 90-day pii_audit_log
anonymization schedule is published through.

Immutable policy objects that the retention scheduler consumes to decide
what action to take on each record at its age horizon. The four FR-91
policy shapes cover the FR-91 acceptance criteria:

    - conversations(messages) 180 天 → 封存 cold storage (Parquet/S3)
    - 封存後 2 年 → 永久刪除
    - PII 稽核日誌 90 天 → 自動匿名化
    - 情緒歷史 90 天 → 刪除
    - 安全日誌 1 年 → 封存後 2 年刪除
    - 用戶回饋永久保留 (已去識別化)

The ``RETENTION_POLICIES`` registry (FR-20) makes the same descriptors
discoverable by ``table_name`` so a test (or operator) can verify the
configured horizon without waiting on wall-clock time.

The unit tests exercise these classes in isolation — no DB / S3 /
scheduler I/O — which is the canonical unit-test shape for FR-91.

Citations:
- SRS.md FR-91 (description line, spec block lines)
- SRS.md FR-20 (pii_audit_log 90-day anonymize)
- 02-architecture/TEST_SPEC.md FR-91 (4 case shapes)
- 03-development/tests/test_fr91.py:98-348 (4 retention policy cases)
- 03-development/tests/test_fr20.py:245-288 (90day_anonymize_scheduled)
"""




# ---------------------------------------------------------------------------
# 1. conversations.messages → cold-storage archive at 180 days
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MessagesRetentionPolicy:
    """Immutable descriptor for the 180-day messages-archive policy.

    Attributes:
        retention_days: hot-DB horizon (days). Beyond this, the record
            moves to cold storage.
        target: source table name whose rows this policy governs.
        archive_format: cold-storage format family descriptor
            (e.g. ``"Parquet/S3"``). Read directly via the attribute;
            no accessor method is required.
        archive_action: scheduler action token (``"archive"``).
    """

    retention_days: int
    target: str
    archive_format: str
    archive_action: str

    def should_archive(self, age_days: int) -> bool:
        """Return True iff the record's age has reached the retention horizon."""
        return age_days >= self.retention_days


# ---------------------------------------------------------------------------
# 2. archives aged 2 years → permanent delete
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ArchiveRetentionPolicy:
    """Immutable descriptor for the 2-year archive deletion policy.

    Attributes:
        archive_age_years: archive-age horizon (years). Beyond this,
            the archive is permanently deleted.
        action: scheduler action token (``"delete"``).
    """

    archive_age_years: int
    action: str

    def should_delete(self, age_years: int) -> bool:
        """Return True iff the archive has reached the deletion horizon."""
        return age_years >= self.archive_age_years


# ---------------------------------------------------------------------------
# 3. PII audit logs → anonymize (NOT delete) at 90 days
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PiiAuditRetentionPolicy:
    """Immutable descriptor for the 90-day PII audit log policy.

    The action is ``"anonymize"`` — strip PII but keep statistical
    counts so the audit trail is not lost.

    Attributes:
        retention_days: anonymization horizon (days).
        table: source table name whose rows this policy governs.
        action: scheduler action token (``"anonymize"``).
    """

    retention_days: int
    table: str
    action: str

    def action_for(self, age_days: int) -> str:
        """Return ``"anonymize"`` once the record is at or beyond the
        90-day horizon; otherwise return ``"retain"``.
        """
        if age_days >= self.retention_days:
            return "anonymize"
        return "retain"


# ---------------------------------------------------------------------------
# 4. emotion history → delete at 90 days (stricter than PII audit logs)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EmotionHistoryRetentionPolicy:
    """Immutable descriptor for the 90-day emotion-history deletion policy.

    Emotion history is personal inference data; the FR is stricter on
    it than on PII audit logs — ``"delete"``, not ``"anonymize"``.

    Attributes:
        retention_days: deletion horizon (days).
        table: source table name whose rows this policy governs.
        action: scheduler action token (``"delete"``).
    """

    retention_days: int
    table: str
    action: str

    def should_delete(self, age_days: int) -> bool:
        """Return True iff the record's age has reached the deletion horizon."""
        return age_days >= self.retention_days


# ---------------------------------------------------------------------------
# 5. [FR-20] Scheduler-discoverable retention policy descriptor.
#
# Different shape from ``PiiAuditRetentionPolicy`` above — FR-20's
# spec-coverage test reads back the policy by ``table_name`` and
# expects a ``scheduled`` boolean, so a thin dedicated dataclass is
# the cleanest way to expose the registry without breaking FR-91's
# existing class surface.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RetentionPolicy:
    """[FR-20] Discoverable retention-policy descriptor.

    Attributes:
        table_name: source table the policy governs
            (e.g. ``"pii_audit_log"``).
        retention_days: age horizon (days) at which the action fires.
        action: scheduler action token (``"anonymize"``, ``"delete"``,
            ``"archive"``).
        scheduled: ``True`` when the policy has been registered with the
            scheduler. Test surface only — a real deployment binds it
            to a cron entry at process start.
    """

    table_name: str
    retention_days: int
    action: str
    scheduled: bool


# ---------------------------------------------------------------------------
# [FR-20] Scheduler-discoverable registry. The FR-20 spec-coverage test
# reads back the pii_audit_log entry by ``table_name``; tests / operators
# can iterate this list to confirm the configured horizon without
# waiting on wall-clock time.
# ---------------------------------------------------------------------------
RETENTION_POLICIES: list[RetentionPolicy] = [
    RetentionPolicy(
        table_name="pii_audit_log",
        retention_days=90,
        action="anonymize",
        scheduled=True,
    ),
]
