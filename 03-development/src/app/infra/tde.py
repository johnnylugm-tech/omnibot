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

from __future__ import annotations

from dataclasses import dataclass, field

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
