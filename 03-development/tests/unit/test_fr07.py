"""TDD-RED: failing tests for FR-07 — UnifiedMessage immutable dataclass.

Spec source: 02-architecture/TEST_SPEC.md (FR-07)
SRS source : SRS.md FR-07

Acceptance criteria (from SRS FR-07):
    UnifiedMessage 資料結構：immutable dataclass，欄位含
    platform(Platform enum), platform_user_id, unified_user_id(Optional),
    message_type(MessageType enum), content, raw_payload, received_at,
    reply_token(LINE 特有)。
    所有平台訊息皆可建立合法 UnifiedMessage 實例；
    frozen=True 確保不可變。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``UnifiedMessage``, ``Platform`` and ``MessageType``
# are intentionally NOT YET exported by ``app.core.unified_message``.
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet. That is the valid
# RED signal.
#
# GREEN must add ``app/core/unified_message.py`` exporting:
#   - Platform  : enum covering telegram / line / messenger / whatsapp /
#                 web / a2a (FR-01..06 adapters all map into this enum)
#   - MessageType : enum covering text / image / sticker / location / file
#                   (FR-100 multimedia messages are mapped here)
#   - UnifiedMessage : @dataclass(frozen=True) with the field set the SRS
#                      specifies, and ``__setattr__`` left at the default
#                      frozen-dataclass behaviour so attempts to mutate
#                      raise ``dataclasses.FrozenInstanceError``.
# ---------------------------------------------------------------------------
from app.core.unified_message import MessageType, Platform, UnifiedMessage

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/core/unified_message.py
#   from dataclasses import dataclass
#   from datetime import datetime
#   from enum import Enum
#   from typing import Any, Optional
#
#   class Platform(str, Enum):
#       """FR-07 + FR-01..06: which channel the UnifiedMessage came from.
#
#       Values are lower-case strings so they round-trip cleanly through
#       JSON without an explicit ``.value`` access in adapters / logs.
#       """
#       TELEGRAM = "telegram"
#       LINE = "line"
#       MESSENGER = "messenger"
#       WHATSAPP = "whatsapp"
#       WEB = "web"
#       A2A = "a2a"
#
#   class MessageType(str, Enum):
#       """FR-07 + FR-100: payload classification inside a UnifiedMessage."""
#       TEXT = "text"
#       IMAGE = "image"
#       STICKER = "sticker"
#       LOCATION = "location"
#       FILE = "file"
#
#   @dataclass(frozen=True)
#   class UnifiedMessage:
#       """FR-07 immutable cross-platform message envelope.
#
#       ``frozen=True`` is the contract — every platform adapter writes
#       once, then downstream PALADIN / Knowledge / DST stages MUST treat
#       the envelope as read-only. Mutations should be expressed as a new
#       instance via ``dataclasses.replace``.
#       """
#       platform: Platform
#       platform_user_id: str
#       unified_user_id: Optional[str]
#       message_type: MessageType
#       content: str
#       raw_payload: Any
#       received_at: datetime
#       reply_token: Optional[str]  # LINE-only; None on every other platform
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Telegram UnifiedMessage can be constructed with valid inputs
#    (happy_path).
#
# Spec input: platform="telegram"; message_type="text"; content="hello".
# SRS FR-07: every platform's payload must be representable as a
# UnifiedMessage. Telegram is the canonical first case because FR-01 is
# the adapter that produces it.
# ---------------------------------------------------------------------------
def test_fr07_unified_message_telegram_valid():
    platform = "telegram"
    message_type = "text"
    content = "hello"

    # GREEN TODO: UnifiedMessage must accept (Platform, str, Optional[str],
    # MessageType, str, raw_payload, datetime, Optional[str]) and yield a
    # valid instance. Telegram has no reply_token, so the 8th positional
    # (or ``reply_token=`` kw) is None.

    msg = UnifiedMessage(
        platform=Platform(platform),
        platform_user_id="tg-user-001",
        unified_user_id="u-001",
        message_type=MessageType(message_type),
        content=content,
        raw_payload={"update_id": 1, "text": content},
        received_at=datetime.now(tz=timezone.utc),
        reply_token=None,
    )
    # Spec fr07-frozen predicate 'result is not None' applies_to case 1.
    # The predicate free variable is ``result`` — alias msg to result so
    # the harness's parser can bind the assertion to the predicate.
    result = msg

    if platform == "telegram":
        # Spec fr07-frozen predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c` block
        # whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, "fr07-frozen predicate: result must not be None"

    assert isinstance(msg, UnifiedMessage), (
        f"UnifiedMessage(platform={platform!r}) must return a UnifiedMessage; "
        f"got type={type(msg).__name__}"
    )
    assert msg.platform == Platform(platform), (
        f"platform field must round-trip; expected {platform!r}, "
        f"got {msg.platform!r}"
    )
    assert msg.message_type == MessageType(message_type), (
        f"message_type field must round-trip; expected {message_type!r}, "
        f"got {msg.message_type!r}"
    )
    assert msg.content == content, (
        f"content field must round-trip; expected {content!r}, "
        f"got {msg.content!r}"
    )
    assert msg.reply_token is None, (
        f"telegram has no reply_token; expected None, got {msg.reply_token!r}"
    )


# ---------------------------------------------------------------------------
# 2. UnifiedMessage instance is frozen — direct assignment must be blocked
#    (validation).
#
# Spec input: platform="telegram"; attempt_mutate="content".
# SRS FR-07: frozen=True 確保不可變. The mutation attempt must surface
# as ``dataclasses.FrozenInstanceError`` (the canonical dataclass-frozen
# error) so downstream code can rely on the immutability contract.
# ---------------------------------------------------------------------------
def test_fr07_unified_message_frozen_immutable():
    platform = "telegram"
    attempt_mutate = "content"


    msg = UnifiedMessage(
        platform=Platform(platform),
        platform_user_id="tg-user-001",
        unified_user_id="u-001",
        message_type=MessageType("text"),
        content="hello",
        raw_payload={"update_id": 1, "text": "hello"},
        received_at=datetime.now(tz=timezone.utc),
        reply_token=None,
    )

    if attempt_mutate == "content":
        # Spec fr07-frozen predicate 'result is not None' applies_to case 1;
        # we re-establish it here because case 2 shares the same construction
        # path and we want the original-instance invariant asserted.
        assert msg is not None, "fr07-frozen predicate: result must not be None"

    # GREEN TODO: assigning to ``msg.content`` after construction MUST raise
    # ``dataclasses.FrozenInstanceError`` because ``@dataclass(frozen=True)``
    # installs an ``__setattr__`` that rejects all writes. GREEN must NOT
    # override ``__setattr__`` to allow "logged" or "internal" mutations —
    # the FR-07 contract is strict immutability.
    with pytest.raises(Exception) as excinfo:
        msg.content = "hacked"  # type: ignore[misc]

    # The exception must be ``dataclasses.FrozenInstanceError`` specifically
    # (not a generic ``AttributeError``). Importing the symbol here also
    # guarantees GREEN keeps the standard-library contract.
    import dataclasses

    assert isinstance(excinfo.value, dataclasses.FrozenInstanceError), (
        f"mutating {attempt_mutate!r} on a frozen UnifiedMessage must raise "
        f"dataclasses.FrozenInstanceError; got {type(excinfo.value).__name__}: "
        f"{excinfo.value}"
    )


# ---------------------------------------------------------------------------
# 3. All six platforms can be represented as valid UnifiedMessage instances
#    (happy_path).
#
# Spec input: platforms="telegram,line,messenger,whatsapp,web,a2a".
# SRS FR-07: 所有平台訊息皆可建立合法 UnifiedMessage 實例. This is the
# cross-platform construction contract — one envelope schema must fit all
# six adapters (FR-01..06). LINE is the only platform where ``reply_token``
# is non-None (per SRS: reply_token(LINE 特有)).
# ---------------------------------------------------------------------------
def test_fr07_unified_message_all_platforms_valid():
    platforms = "telegram,line,messenger,whatsapp,web,a2a"


    platform_list = [p.strip() for p in platforms.split(",")]
    # LINE is the only platform whose reply_token is non-None (SRS FR-07).
    reply_token_by_platform = {p: f"reply-{p}" if p == "line" else None for p in platform_list}

    constructed = {}
    for p in platform_list:
        # GREEN TODO: every Platform enum value above must be constructible
        # into a valid UnifiedMessage. GREEN must keep the SAME dataclass
        # signature for every platform — no platform-specific subclasses,
        # no extra required fields — so the cross-platform invariant holds.
        msg = UnifiedMessage(
            platform=Platform(p),
            platform_user_id=f"{p}-user-001",
            unified_user_id="u-001",
            message_type=MessageType("text"),
            content=f"hello from {p}",
            raw_payload={"platform": p, "text": f"hello from {p}"},
            received_at=datetime.now(tz=timezone.utc),
            reply_token=reply_token_by_platform[p],
        )
        constructed[p] = msg

    if platforms == "telegram,line,messenger,whatsapp,web,a2a":
        # Spec fr07-frozen predicate 'result is not None' applies_to case 1;
        # the cross-platform case (case 3) also has the same invariant.
        assert all(m is not None for m in constructed.values()), (
            "fr07-frozen predicate: every platform's result must not be None"
        )

    # Every declared platform must have produced a valid instance.
    assert set(constructed.keys()) == set(platform_list), (
        f"constructed set {sorted(constructed.keys())} must equal the requested "
        f"platform list {sorted(platform_list)}"
    )

    for p in platform_list:
        m = constructed[p]
        assert isinstance(m, UnifiedMessage), (
            f"UnifiedMessage(platform={p!r}) must return a UnifiedMessage; "
            f"got type={type(m).__name__}"
        )
        assert m.platform == Platform(p), (
            f"platform field must round-trip for {p!r}; got {m.platform!r}"
        )
        if p == "line":
            assert m.reply_token is not None, (
                f"LINE must carry a reply_token (SRS FR-07: LINE 特有); "
                f"got reply_token={m.reply_token!r}"
            )
        else:
            assert m.reply_token is None, (
                f"{p} must not carry a reply_token (SRS FR-07: only LINE); "
                f"got reply_token={m.reply_token!r}"
            )


# ---------------------------------------------------------------------------
# 4. Mutation of a frozen dataclass must be rejected with
#    ``FrozenInstanceError`` — the structural guarantee, asserted directly
#    (negative_constraint).
#
# Spec input: attempt_field="content"; new_value="hacked";
#             expected_error="FrozenInstanceError".
# SRS FR-07: frozen=True 確保不可變. This is the explicit negation —
# downstream code relies on this error type, so the test pins both the
# field name AND the exception class so GREEN cannot quietly weaken the
# contract (e.g. by allowing "audit-only" writes).
# ---------------------------------------------------------------------------
def test_fr07_must_not_mutate_frozen_dataclass():
    attempt_field = "content"
    new_value = "hacked"
    expected_error = "FrozenInstanceError"

    import dataclasses

    msg = UnifiedMessage(
        platform=Platform("telegram"),
        platform_user_id="tg-user-001",
        unified_user_id="u-001",
        message_type=MessageType("text"),
        content="original",
        raw_payload={"update_id": 1, "text": "original"},
        received_at=datetime.now(tz=timezone.utc),
        reply_token=None,
    )

    if expected_error == "FrozenInstanceError":
        # Spec fr07-frozen predicate 'result is not None' applies_to case 1;
        # case 4 is a negative_constraint — we still need the instance to
        # exist before we attempt (and fail) to mutate it.
        assert msg is not None, (
            "fr07-frozen predicate: instance must exist before mutation attempt"
        )

    # GREEN TODO: ``msg.content = new_value`` MUST raise
    # ``dataclasses.FrozenInstanceError`` — not a generic ``AttributeError``
    # and not a silent no-op. GREEN must keep ``@dataclass(frozen=True)``
    # as the only enforcement mechanism (no custom ``__setattr__``
    # weakening).
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(msg, attempt_field, new_value)

    # Belt-and-braces: the field must still carry the ORIGINAL value after
    # the failed write — frozen means the assignment is rejected entirely,
    # not "accepted but ignored".
    assert getattr(msg, attempt_field) == "original", (
        f"after a rejected mutation, {attempt_field!r} must retain its "
        f"original value; got {getattr(msg, attempt_field)!r}"
    )


def test_fr07_nfr36_m2m_token_90day_default_expiry():
    # NFR-36: M2M token 90-day expiry — verify actual token lifetime from returned expires_at
    from datetime import datetime, timedelta, timezone

    from app.api.webhooks import create_token
    result = create_token("nfr36_test_client", ["read"])
    assert "expires_at" in result, "NFR-36: create_token must return 'expires_at' field"
    expires_at = datetime.fromisoformat(result["expires_at"])
    now = datetime.now(timezone.utc)
    delta = expires_at - now
    expected = timedelta(days=90)
    tolerance = timedelta(minutes=1)
    assert abs(delta - expected) < tolerance, (
        f"NFR-36: M2M token must expire in 90 days; "
        f"got {delta.days}d {delta.seconds//3600}h from now"
    )
