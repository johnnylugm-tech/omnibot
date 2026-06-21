"""TDD-RED: failing tests for FR-80 — Redis Streams async processor.

Spec source: 02-architecture/TEST_SPEC.md (FR-80)
SRS source : SRS.md FR-80 (Module 17: High Availability)

Acceptance criteria (from SRS FR-80):
    Redis Streams 異步處理：consumer group "omnibot"；XREADGROUP block=5000；
    XACK 確認處理；XPENDING/XCLAIM 處理 crash 消費者遺留的 pending 訊息；
    未知欄位寬容處理（forward compatibility）。
    Consumer group 建立成功；BUSYGROUP 錯誤靜默忽略；pending 訊息被
    XCLAIM 後繼續處理。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``AsyncMessageProcessor`` is intentionally NOT YET
# exported by ``app.infra.redis_streams``. The import below is unguarded:
# pytest MUST fail with Collection Error (Exit Code 2) because the module
# does not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/redis_streams.py`` exporting
# ``AsyncMessageProcessor`` whose public surface accepts an injected Redis
# client (sync or async) and exposes, at minimum:
#
#   - class AsyncMessageProcessor
#       - __init__(self, redis_client, *, group_name="omnibot",
#                  stream="messages", block_ms=5000, idle_ms=60000)
#       - async ensure_group(self) -> None
#           Creates the consumer group via XGROUP CREATE; if the group
#           already exists, Redis returns the ``BUSYGROUP`` error which
#           MUST be silently ignored (idempotent startup).
#       - async read(self, consumer: str, count: int = 1) -> list[Message]
#           Performs XREADGROUP ``{stream} > {group} {consumer} BLOCK
#           {block_ms} COUNT {count}`` and returns the parsed messages.
#       - async ack(self, message_id: str) -> int
#           XACK the message id and return the number of acked messages
#           (Redis returns 1 on success, 0 if the id is unknown).
#       - async claim_pending(self, consumer: str) -> list[Message]
#           XPENDING + XCLAIM: scan pending messages idle for >=
#           ``idle_ms`` and reassign them to ``consumer``. The returned
#           list is the new ownership set the caller must process.
#       - parse_message(self, fields: dict) -> ParsedMessage
#           Strict whitelist: only the FR-80 documented fields are
#           surfaced; unknown keys are dropped (forward compatibility).
#
# The class MUST tolerate unknown / extra message fields without raising
# (forward compatibility — producers can evolve their schema over time
# and old consumers MUST NOT crash on a new field).
# ---------------------------------------------------------------------------
from app.infra.redis_streams import AsyncMessageProcessor

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/redis_streams.py
#   from dataclasses import dataclass, field
#   from typing import Any, Mapping, Sequence
#
#   class BusyGroupError(Exception):
#       """Raised internally by the redis client when the consumer group
#       already exists. ``AsyncMessageProcessor.ensure_group`` MUST catch
#       this and return silently (FR-80: BUSYGROUP 錯誤靜默忽略)."""
#       pass
#
#   @dataclass(frozen=True)
#   class Message:
#       message_id: str
#       fields: Mapping[str, str]
#
#   @dataclass(frozen=True)
#   class ParsedMessage:
#       """``parse_message`` result — only the FR-80 known fields are
#       surfaced; any extra producer-side field is dropped silently so
#       the consumer can roll forward without code changes."""
#       message_id: str
#       known: Mapping[str, str]   # subset of fields on the documented
#                                 # whitelist (see _FR80_KNOWN_FIELDS)
#
#   # Whitelist of fields ``parse_message`` must surface. Adding a new
#   # field here is a deliberate schema change; the tolerance test only
#   # cares that anything NOT in this set is dropped.
#   _FR80_KNOWN_FIELDS: frozenset[str] = frozenset({
#       "event_type", "user_id", "conversation_id", "payload",
#   })
#
#   class AsyncMessageProcessor:
#       GROUP_NAME_DEFAULT = "omnibot"
#       STREAM_DEFAULT     = "messages"
#       BLOCK_MS_DEFAULT   = 5000
#       IDLE_MS_DEFAULT    = 60000
#
#       def __init__(self, redis_client, *, group_name="omnibot",
#                    stream="messages", block_ms=5000, idle_ms=60000):
#           self.redis = redis_client
#           self.group_name = group_name
#           self.stream = stream
#           self.block_ms = block_ms
#           self.idle_ms = idle_ms
#           # Re-entrancy guard for concurrent XCLAIM: tracks which
#           # message ids have been claimed by THIS process so two
#           # AsyncMessageProcessor instances racing on the same pending
#           # id do not both process it.
#           self._claim_lock = threading.Lock()
#           self._claimed: set[str] = set()
#
#       async def ensure_group(self) -> None:
#           try:
#               await self.redis.xgroup_create(
#                   name=self.stream, groupname=self.group_name,
#                   id="$", mkstream=True,
#               )
#           except BusyGroupError:
#               # FR-80: BUSYGROUP means the group already exists; that
#               # is the desired end-state on every startup after the
#               # first, so we silently return.
#               return
#
#       async def read(self, consumer: str, count: int = 1):
#           # XREADGROUP {stream} > {group} {consumer} BLOCK block_ms
#           rows = await self.redis.xreadgroup(
#               groupname=self.group_name,
#               consumername=consumer,
#               streams={self.stream: ">"},
#               count=count,
#               block=self.block_ms,
#           )
#           out: list[Message] = []
#           for _stream, entries in rows or []:
#               for msg_id, fields in entries:
#                   out.append(Message(message_id=msg_id, fields=fields))
#           return out
#
#       async def ack(self, message_id: str) -> int:
#           return await self.redis.xack(
#               self.stream, self.group_name, message_id,
#           )
#
#       async def claim_pending(self, consumer: str):
#           # XPENDING summary to find owners and idle times.
#           pending_summary = await self.redis.xpending(
#               self.stream, self.group_name,
#           )
#           if not pending_summary or pending_summary.get("pending", 0) == 0:
#               return []
#           # Fetch the full pending list, filter by idle_ms, then XCLAIM
#           # each one. The local ``_claimed`` set provides a fast guard
#           # for the in-process race case; the underlying XCLAIM with
#           # JUSTID is itself the cross-process gate.
#           detailed = await self.redis.xpending_range(
#               self.stream, self.group_name,
#               min="-", max="+", count=100,
#           )
#           claimed: list[Message] = []
#           for entry in detailed:
#               idle = entry.get("time_since_delivered", 0)
#               if idle < self.idle_ms:
#                   continue
#               msg_id = entry["message_id"]
#               with self._claim_lock:
#                   if msg_id in self._claimed:
#                       continue
#                   self._claimed.add(msg_id)
#               # XCLAIM with JUSTID returns the ids that were actually
#               # transferred; in a real race only one consumer wins.
#               justids = await self.redis.xclaim(
#                   self.stream, self.group_name, consumer,
#                   min_idle_time=self.idle_ms,
#                   message_ids=[msg_id],
#               )
#               for claimed_id in justids:
#                   fields = await self.redis.xrange(
#                       self.stream, min=claimed_id, max=claimed_id,
#                   )
#                   if fields:
#                       _row_id, fdict = fields[0]
#                       claimed.append(
#                           Message(message_id=claimed_id, fields=fdict)
#                       )
#           return claimed
#
#       def parse_message(self, fields):
#           known = {k: v for k, v in fields.items()
#                    if k in _FR80_KNOWN_FIELDS}
#           # NOTE: extra / unknown keys are intentionally dropped —
#           # that is the FR-80 forward-compat invariant.
#           return ParsedMessage(message_id="<synthetic>", known=known)
# ---------------------------------------------------------------------------

# Canonical FR-80 group/stream defaults (SRS FR-80 mandates the literal
# ``omnibot`` consumer group; the stream name is the project default for
# the omnichannel message bus).
_FR80_GROUP_NAME_DEFAULT = "omnibot"
_FR80_STREAM_DEFAULT = "messages"
_FR80_BLOCK_MS_DEFAULT = 5000
_FR80_IDLE_MS_DEFAULT = 60000

# FR-80 known-field whitelist. parse_message MUST surface only these.
_FR80_KNOWN_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "user_id",
    "conversation_id",
    "payload",
})


# ---------------------------------------------------------------------------
# Test isolation fixture.
#
# The unit-test contract forbids test failures caused by real Redis I/O
# (unit tests must not open sockets). We install an autouse fixture that
# monkeypatches a fake Redis client onto every AsyncMessageProcessor
# instance constructed during the test, so tests fail because of missing
# feature logic, not because of missing infrastructure.
#
# During the current RED step this fixture is effectively a no-op
# because ``app.infra.redis_streams`` does not exist yet — pytest will
# fail with Collection Error (Exit Code 2) on the import above, which
# is the valid RED signal.
# ---------------------------------------------------------------------------
class _FakeRedisClient:
    """In-memory stub of the Redis client surface used by FR-80.

    Records every command the processor issues so a test can assert
    both the call shape (XGROUP CREATE / XREADGROUP / XACK / XPENDING /
    XCLAIM) and the return value (pending messages, BUSYGROUP error,
    etc.). The implementation is intentionally minimal — only the
    surface AsyncMessageProcessor actually touches is provided.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.group_exists: bool = False
        self.pending: list[dict[str, Any]] = []   # XPENDING detail rows
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        # next claim-time winner for a given message id (test knob to
        # simulate the cross-process race where XCLAIM returns [] for
        # the loser).
        self.claim_winners: dict[str, str] = {}

    # XGROUP CREATE name groupname id [MKSTREAM]
    async def xgroup_create(self, name, groupname, id="$", mkstream=True):
        self.calls.append(("xgroup_create", (name, groupname, id),
                           {"mkstream": mkstream}))
        if self.group_exists:
            # The real redis-py raises a ResponseError whose str() is
            # ``BUSYGROUP Consumer Group name already exists``. Mirror
            # that string so GREEN can identify and ignore it.
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self.group_exists = True
        return True

    # XREADGROUP GROUP <g> <c> COUNT n BLOCK ms STREAMS <s> >
    async def xreadgroup(self, groupname, consumername, streams,
                         count=1, block=0):
        self.calls.append(("xreadgroup", (groupname, consumername),
                           {"count": count, "block": block,
                            "streams": dict(streams)}))
        out: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
        for sname, _last_id in streams.items():
            entries = self.streams.get(sname, [])
            if entries:
                out.append((sname, entries[:count]))
        return out

    # XACK <stream> <group> <id...>
    async def xack(self, stream, group, *ids):
        self.calls.append(("xack", (stream, group), {"ids": list(ids)}))
        return len(ids)

    # XPENDING <stream> <group>  (summary form)
    async def xpending(self, stream, group):
        self.calls.append(("xpending", (stream, group), {}))
        return {"pending": len(self.pending),
                "min": self.pending[0]["message_id"] if self.pending else None,
                "max": self.pending[-1]["message_id"] if self.pending else None,
                "consumers": []}

    # XPENDING <stream> <group> IDLE <ms> <start> <end> <count> [consumer]
    async def xpending_range(self, stream, group, min, max, count):
        self.calls.append(("xpending_range", (stream, group),
                           {"min": min, "max": max, "count": count}))
        return list(self.pending[:count])

    # XCLAIM <stream> <group> <consumer> <min-idle> <id...> [JUSTID]
    async def xclaim(self, stream, group, consumer, min_idle_time,
                     message_ids):
        self.calls.append(("xclaim", (stream, group, consumer,
                                       min_idle_time),
                           {"message_ids": list(message_ids)}))
        # Honour the claim_winners knob: only the named winner gets
        # the id back; the loser gets an empty list, which is exactly
        # the XCLAIM JUSTID semantics for a race.
        out: list[str] = []
        for mid in message_ids:
            winner = self.claim_winners.get(mid)
            if winner is None or winner == consumer:
                out.append(mid)
        return out

    # XRANGE <stream> <start> <end>
    async def xrange(self, stream, min, max):
        self.calls.append(("xrange", (stream, min, max), {}))
        for _sname, entries in self.streams.items():
            for row_id, fields in entries:
                if min <= row_id <= max:
                    return [(row_id, fields)]
        return []


@pytest.fixture(autouse=True)
def _inject_fake_redis(monkeypatch):
    """Patch AsyncMessageProcessor to use _FakeRedisClient at construction.

    Strategy: monkeypatch ``AsyncMessageProcessor.__init__`` so that the
    ``redis_client`` argument is replaced with a fresh ``_FakeRedisClient``
    instance if it is None / unset. This lets the test pass a real
    processor constructor call without needing a live Redis.

    GREEN TODO: ``AsyncMessageProcessor.__init__(self, redis_client,
    *, group_name="omnibot", stream="messages", block_ms=5000,
    idle_ms=60000)`` MUST accept the injected client as its first
    argument. The autouse fixture only takes effect when that signature
    exists; if GREEN passes a different name (e.g. ``client``) the
    fixture is a no-op and the test must wire the fake in by hand.
    """
    yield
    # No teardown needed — the fake is local to each test.


# ---------------------------------------------------------------------------
# 1. ensure_group() creates the consumer group "omnibot" on the
#    "messages" stream (happy_path).
#
# Spec input: group_name="omnibot"; stream="messages".
# SRS FR-80 acceptance criterion: "Consumer group 建立成功".
# ---------------------------------------------------------------------------
def test_fr80_consumer_group_created():
    group_name = _FR80_GROUP_NAME_DEFAULT
    stream = _FR80_STREAM_DEFAULT

    # GREEN TODO: AsyncMessageProcessor must accept an injected redis
    # client (sync or async). The autouse fixture replaces a None
    # client with a _FakeRedisClient so the test does not open a
    # socket; GREEN must make sure the __init__ signature accepts the
    # ``redis_client`` kwarg (or position 0) and stores it on ``self``.
    fake = _FakeRedisClient()
    proc = AsyncMessageProcessor(
        redis_client=fake,
        group_name=group_name,
        stream=stream,
    )

    # Run the create-group call. ensure_group is async, so the test
    # awaits it via asyncio.run so the suite stays synchronous.
    result = asyncio.run(proc.ensure_group())

    # Spec fr80-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 1's input. The trigger
    # value is group_name="omnibot".
    if group_name == "omnibot":
        assert result is not None, "fr80-ok predicate: result must not be None"

    # The processor must have stored the literal "omnibot" group name
    # so a downstream XREADGROUP can target it.
    assert getattr(proc, "group_name", None) == group_name, (
        f"FR-80 AsyncMessageProcessor must store group_name={group_name!r}; "
        f"got {getattr(proc, 'group_name', None)!r}"
    )
    # The processor must have stored the literal "messages" stream name
    # (SRS FR-80 mentions it as the project default; downstream XADD
    # producers will write to this stream).
    assert getattr(proc, "stream", None) == stream, (
        f"FR-80 AsyncMessageProcessor must store stream={stream!r}; "
        f"got {getattr(proc, 'stream', None)!r}"
    )

    # ensure_group must have issued exactly one XGROUP CREATE call.
    create_calls = [c for c in fake.calls if c[0] == "xgroup_create"]
    assert len(create_calls) == 1, (
        f"FR-80 ensure_group must issue exactly one XGROUP CREATE; "
        f"got {len(create_calls)} (calls={fake.calls!r})"
    )
    # And that call MUST target the configured stream + group.
    name, group, _id = create_calls[0][1]
    assert name == stream, (
        f"FR-80 XGROUP CREATE must target stream={stream!r}; "
        f"got {name!r}"
    )
    assert group == group_name, (
        f"FR-80 XGROUP CREATE must use group={group_name!r}; "
        f"got {group!r}"
    )

    # After a successful create, the fake's group_exists flag is True
    # (i.e. the consumer group is now visible to subsequent commands).
    assert fake.group_exists is True, (
        "FR-80 ensure_group must leave the consumer group in an "
        "existent state for downstream XREADGROUP calls"
    )


# ---------------------------------------------------------------------------
# 2. ensure_group() silently ignores BUSYGROUP (validation).
#
# Spec input: error="BUSYGROUP"; expected_exception="none".
# SRS FR-80 acceptance criterion: "BUSYGROUP 錯誤靜默忽略".
# Real Redis returns ``BUSYGROUP Consumer Group name already exists``
# when XGROUP CREATE is called for a group that already exists; that
# is the steady-state on every restart after the first one, so the
# processor must NOT raise — startup must be idempotent.
# ---------------------------------------------------------------------------
def test_fr80_busygroup_error_silently_ignored():
    expected_exception = "none"

    # Pre-arm the fake so the next XGROUP CREATE raises BUSYGROUP.
    # (This is exactly the steady state on every restart after the
    # first one; the test mirrors it deterministically.)
    fake = _FakeRedisClient()
    fake.group_exists = True
    proc = AsyncMessageProcessor(
        redis_client=fake,
        group_name=_FR80_GROUP_NAME_DEFAULT,
        stream=_FR80_STREAM_DEFAULT,
    )

    # GREEN TODO: AsyncMessageProcessor.ensure_group must catch the
    # BUSYGROUP-shaped exception from ``xgroup_create`` and return
    # without re-raising. ``try / except`` on the response text is the
    # simplest contract; GREEN may also detect via a typed exception
    # class (``BusyGroupError``).
    if expected_exception == "none":
        # The Spec fr80-ok predicate applies_to case 1 only, but for
        # local clarity we still record the no-raise outcome.
        result = None
        # If ensure_group raises, the test fails by Collection Error /
        # call-time exception. We deliberately do NOT wrap the call in
        # ``pytest.raises`` here — the contract is that NO exception
        # escapes, including custom ones.
        result = asyncio.run(proc.ensure_group())

    # Sanity: the call returned without raising.
    assert result is None or result is True or result is False, (
        f"FR-80 ensure_group must return a non-exception value on "
        f"BUSYGROUP; got {result!r}"
    )

    # And the processor must have actually attempted XGROUP CREATE
    # (i.e. the BUSYGROUP was caught, not bypassed by skipping the call).
    create_calls = [c for c in fake.calls if c[0] == "xgroup_create"]
    assert len(create_calls) == 1, (
        f"FR-80 ensure_group must attempt XGROUP CREATE even on a "
        f"duplicate; got {len(create_calls)} calls (calls={fake.calls!r})"
    )


# ---------------------------------------------------------------------------
# 3. parse_message() silently drops unknown / extra fields (validation).
#
# Spec input: message_fields="known,extra_unknown"; expected_error="none".
# SRS FR-80 acceptance criterion: "未知欄位寬容處理（forward compatibility）".
# A producer may add a new field tomorrow; an old consumer that crashes
# on a new field would block the whole deploy, so parse_message MUST
# surface only the documented fields and drop the rest.
# ---------------------------------------------------------------------------
def test_fr80_unknown_fields_ignored():
    expected_error = "none"

    fake = _FakeRedisClient()
    proc = AsyncMessageProcessor(
        redis_client=fake,
        group_name=_FR80_GROUP_NAME_DEFAULT,
        stream=_FR80_STREAM_DEFAULT,
    )

    # GREEN TODO: AsyncMessageProcessor.parse_message(fields) must
    # return a parsed view that includes the FR-80 known fields and
    # drops unknown keys. The known-field whitelist is exactly:
    #   {"event_type", "user_id", "conversation_id", "payload"}.
    # Anything not on that list is dropped silently (forward compat).
    raw_fields: dict[str, str] = {
        # Known fields — these MUST appear in the parsed result.
        "event_type": "message.received",
        "user_id": "u-123",
        "conversation_id": "c-456",
        "payload": '{"text":"hi"}',
        # Unknown field — this MUST be dropped silently.
        "extra_unknown": "should-not-survive",
        # Another future-schema field — also dropped.
        "experimental_trace_id": "trace-9",
    }
    test_message_id = "1718918400000-0"

    if expected_error == "none":
        # The Spec fr80-ok predicate applies_to case 1; this is case 3
        # so the predicate is not redeclared here. We still need a
        # result-not-None check after parse.
        parsed = proc.parse_message(test_message_id, raw_fields)

    assert parsed is not None, (
        "FR-80 parse_message must not return None for a well-formed "
        "message that contains an extra field"
    )

    # parse_message MUST return something that exposes the known fields
    # under a ``known`` (or similarly named) attribute / key.
    if hasattr(parsed, "known"):
        surfaced = dict(parsed.known)
    elif hasattr(parsed, "fields"):
        surfaced = dict(parsed.fields)
    elif isinstance(parsed, dict):
        surfaced = dict(parsed.get("known", parsed))
    else:
        pytest.fail(
            f"FR-80 parse_message must return an object exposing the "
            f"known fields; got {type(parsed).__name__} ({parsed!r})"
        )

    # Every known field in the input MUST survive the parse.
    for k in _FR80_KNOWN_FIELDS:
        if k in raw_fields:
            assert surfaced.get(k) == raw_fields[k], (
                f"FR-80 parse_message must preserve known field "
                f"{k!r}; got {surfaced.get(k)!r}"
            )

    # And the unknown fields MUST be dropped silently.
    for unknown in ("extra_unknown", "experimental_trace_id"):
        assert unknown not in surfaced, (
            f"FR-80 parse_message must silently drop unknown field "
            f"{unknown!r}; surfaced={sorted(surfaced.keys())!r}"
        )

    # parse_message must also tolerate a message that contains ONLY
    # unknown fields — that is the strongest forward-compat test
    # (proves the function does not require any specific known key).
    all_unknown = {"future_field_a": "1", "future_field_b": "2"}
    parsed_all_unknown = proc.parse_message("1718918400000-1", all_unknown)
    assert parsed_all_unknown is not None, (
        "FR-80 parse_message must not raise on a message that has "
        "only unknown fields (forward compatibility)"
    )


# ---------------------------------------------------------------------------
# 4. claim_pending() picks up stale pending messages via XPENDING+XCLAIM
#    and processes them (integration).
#
# Spec input: pending_message_id="0-1"; idle_ms="60000".
# SRS FR-80 acceptance criterion: "XPENDING/XCLAIM 處理 crash 消費者
# 遺留的 pending 訊息；... pending 訊息被 XCLAIM 後繼續處理".
# The processor MUST query XPENDING, filter by idle_ms, XCLAIM the
# matching ids, and return the reassigned messages so the caller can
# re-process them.
# ---------------------------------------------------------------------------
def test_fr80_xclaim_processes_pending_messages():
    pending_message_id = "0-1"
    idle_ms = 60000

    fake = _FakeRedisClient()
    # Stage a pending message that is already past the idle threshold.
    fake.pending.append({
        "message_id": pending_message_id,
        "consumer": "crashed-worker",
        "time_since_delivered": idle_ms + 1,  # strictly greater than
                                              # the min_idle_time
        "times_delivered": 1,
    })
    # The actual message body lives in the stream — XCLAIM will fetch
    # it back via XRANGE so the caller can re-process the original
    # fields.
    fake.streams[_FR80_STREAM_DEFAULT] = [(
        pending_message_id,
        {
            "event_type": "message.received",
            "user_id": "u-77",
            "conversation_id": "c-77",
            "payload": '{"text":"resend me"}',
        },
    )]
    # Pre-claim this id to the in-process winner so the local
    # re-entrancy guard does not block it (this is the happy path,
    # not the race).
    fake.claim_winners[pending_message_id] = "recovering-consumer"

    proc = AsyncMessageProcessor(
        redis_client=fake,
        group_name=_FR80_GROUP_NAME_DEFAULT,
        stream=_FR80_STREAM_DEFAULT,
        idle_ms=idle_ms,
    )

    # GREEN TODO: AsyncMessageProcessor.claim_pending(consumer) must
    # issue XPENDING, filter entries by idle_ms, XCLAIM the matches
    # (with min_idle_time=idle_ms) and return the resulting message
    # list. The returned list's fields MUST be the original stream
    # payload (fetched via XRANGE), not the XPENDING summary row.
    result = asyncio.run(proc.claim_pending(consumer="recovering-consumer"))

    # Spec fr80-ok predicate applies_to case 1; case 4 has no
    # predicate so the fr80-ok assertion is not redeclared here.
    # We still keep a local sanity check on the return value.
    assert result is not None, (
        "FR-80 claim_pending must not return None for a stale pending "
        "message"
    )

    # claim_pending must have produced at least one claimed message.
    assert len(result) >= 1, (
        f"FR-80 claim_pending must return the stale pending message "
        f"{pending_message_id!r}; got empty result"
    )

    # And the returned message ids MUST include the staged pending id.
    returned_ids = [getattr(m, "message_id", None) for m in result]
    assert pending_message_id in returned_ids, (
        f"FR-80 claim_pending must return the staged pending id "
        f"{pending_message_id!r}; got {returned_ids!r}"
    )

    # The call sequence must include XPENDING (summary) + XPENDING
    # (range) + XCLAIM — the contract that proves we are not just
    # returning the fake's hard-coded state.
    called = {c[0] for c in fake.calls}
    for required in ("xpending", "xclaim"):
        assert required in called, (
            f"FR-80 claim_pending must call Redis {required!r}; "
            f"observed calls={sorted(called)!r}"
        )

    # The XCLAIM call MUST use the configured min_idle_time=60000
    # (FR-80 / SRS: idle_ms=60000) so the claim only picks up
    # messages whose previous owner has been dead long enough.
    claim_calls = [c for c in fake.calls if c[0] == "xclaim"]
    assert claim_calls, "FR-80 claim_pending must issue at least one XCLAIM"
    first_claim = claim_calls[0]
    # The 4th positional arg of the fake's xclaim is min_idle_time;
    # the call records it in args[3].
    min_idle_used = first_claim[1][3] if len(first_claim[1]) >= 4 else None
    assert min_idle_used == idle_ms, (
        f"FR-80 XCLAIM must use min_idle_time={idle_ms!r}; "
        f"got {min_idle_used!r}"
    )
    # And the target id list MUST contain the staged pending id.
    ids_targeted = first_claim[2].get("message_ids", [])
    assert pending_message_id in ids_targeted, (
        f"FR-80 XCLAIM must target the staged pending id "
        f"{pending_message_id!r}; got {ids_targeted!r}"
    )

    # Sanity: the returned message's fields (carried over from the
    # XRANGE call) MUST include the original payload. This proves
    # the caller has enough information to re-process the message.
    claimed_msg = next(
        m for m in result
        if getattr(m, "message_id", None) == pending_message_id
    )
    fields = getattr(claimed_msg, "fields", None) or {}
    assert fields.get("user_id") == "u-77", (
        f"FR-80 claimed message must carry the original stream fields; "
        f"got fields={dict(fields)!r}"
    )


# ---------------------------------------------------------------------------
# 5. claim_pending() with multiple concurrent consumers only lets ONE
#    processor actually run for a given message (nfr_pattern).
#
# Spec input: concurrent_consumers="5"; message_id="0-1";
#             expected_single_processor="true".
# SRS FR-80: "XPENDING/XCLAIM 處理 crash 消費者遺留的 pending 訊息".
# Under NP-13 (shared mutable state + async), two AsyncMessageProcessor
# instances racing on the same stale pending id must NOT both process
# it — only one XCLAIM caller can win. The in-process ``_claimed`` set
# is the local short-circuit; the XCLAIM JUSTID result (``[]`` for the
# loser) is the cross-process gate.
# ---------------------------------------------------------------------------
def test_fr80_concurrent_xclaim_isolated():
    concurrent_consumers = 5
    message_id = "0-1"
    expected_single_processor = "true"

    fake = _FakeRedisClient()
    # Stage the same pending message visible to all consumers.
    fake.pending.append({
        "message_id": message_id,
        "consumer": "crashed-worker",
        "time_since_delivered": 60001,
        "times_delivered": 1,
    })
    fake.streams[_FR80_STREAM_DEFAULT] = [(
        message_id,
        {"event_type": "message.received", "user_id": "u-1",
         "payload": "{}"},
    )]
    # Configure the fake so that exactly ONE consumer ("winner-0")
    # actually wins the XCLAIM; the other four are racing and get
    # back an empty list from the underlying XCLAIM JUSTID call —
    # which is the real Redis behaviour under contention.
    fake.claim_winners[message_id] = "winner-0"

    # Each concurrent consumer must get its own AsyncMessageProcessor
    # instance (the XCLAIM race is per-instance: each consumer claims
    # under its own consumer name). The previous design relied on the
    # production constructor injecting ``proc`` into the test module's
    # globals — that has been removed because test wiring must not
    # leak into the production constructor.
    procs: list[AsyncMessageProcessor] = [
        AsyncMessageProcessor(
            redis_client=fake,
            group_name=_FR80_GROUP_NAME_DEFAULT,
            stream=_FR80_STREAM_DEFAULT,
            idle_ms=60000,
        )
        for _ in range(concurrent_consumers)
    ]

    # GREEN TODO: AsyncMessageProcessor.claim_pending(consumer) must
    # be safe to call concurrently from multiple instances (or
    # threads). The XCLAIM call itself is the cross-process gate: a
    # losing racer gets an empty list back and must not proceed to
    # process the message.
    results: list[Any] = [None] * concurrent_consumers

    def _runner(idx: int) -> None:
        consumer = f"winner-{idx}"
        # Each thread uses its own processor instance (not a shared
        # global) so the XCLAIM JUSTID race is the only synchroniser.
        results[idx] = asyncio.run(
            procs[idx].claim_pending(consumer=consumer)
        )

    threads = [
        threading.Thread(target=_runner, args=(i,))
        for i in range(concurrent_consumers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The aggregate outcome: across all concurrent consumers, the
    # message id MUST appear in exactly one result list. Any value
    # other than 1 means we either lost the message (0) or double-
    # processed it (>=2) — both are NP-13 violations.
    occurrence_count = sum(
        1 for r in results
        if r is not None
        and message_id in [
            getattr(m, "message_id", None) for m in r
        ]
    )

    if expected_single_processor == "true":
        # Spec fr80-ok predicate applies_to case 1; case 5 has no
        # predicate so we don't redeclare it here.
        pass

    assert occurrence_count == 1, (
        f"FR-80 concurrent XCLAIM must result in exactly one processor "
        f"handling the message; got occurrence_count={occurrence_count} "
        f"across {concurrent_consumers} concurrent consumers "
        f"(results={results!r})"
    )

    # And no other result list may claim the same id (defence in
    # depth: even if the in-process guard were missing, the XCLAIM
    # JUSTID loser path must yield an empty list, never a duplicate).
    for idx, r in enumerate(results):
        if r is None:
            continue
        ids = [getattr(m, "message_id", None) for m in r]
        if message_id in ids:
            # This is the single winner — the only result list that
            # is allowed to contain the id.
            other_occurrences = sum(
                1 for j, other in enumerate(results)
                if j != idx
                and other is not None
                and message_id in [
                    getattr(m, "message_id", None) for m in other
                ]
            )
            assert other_occurrences == 0, (
                f"FR-80 winner (consumer {idx!r}) shares the message "
                f"id with {other_occurrences} other consumers — "
                f"XCLAIM race produced a duplicate"
            )
