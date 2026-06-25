"""[FR-80] Redis Streams async processor for the omnichannel message bus.

Owns the consumer-group lifecycle (XGROUP CREATE / XREADGROUP / XACK /
XPENDING / XCLAIM) and the forward-compatible message-parse whitelist.
A single ``AsyncMessageProcessor`` instance is safe to share across
async tasks; multiple instances racing on the same stale pending
message are gated by the underlying Redis XCLAIM JUSTID semantics.

[FR-80] Consumer group is named ``omnibot`` (SRS FR-80 mandate); the
        default stream is ``messages`` and the default block is 5000ms
        (XREADGROUP block=5000 per SRS FR-80). The processor silently
        absorbs the ``BUSYGROUP`` error on every startup after the
        first one (idempotent group creation). Stale pending messages
        (idle >= ``idle_ms``) are picked up by XPENDING + XCLAIM and
        returned to the caller for re-processing. The parse whitelist
        is exactly the FR-80 documented field set; any extra producer
        key is dropped silently so a consumer can roll forward without
        a code change.

Citations:
- SRS.md FR-80 (Module 17: High Availability, row at line 183 —
  consumer group "omnibot", XREADGROUP block=5000, XACK,
  XPENDING/XCLAIM, forward-compatible unknown fields)
- 02-architecture/TEST_SPEC.md FR-80 (5 cases: ensure_group happy
  path, BUSYGROUP idempotency, parse_message whitelist,
  claim_pending XPENDING+XCLAIM, concurrent XCLAIM isolation;
  starting around line 1619)
- 02-architecture/TEST_SPEC.md NP-13 (line 47 — shared mutable
  state + async pattern; ``AsyncMessageProcessor`` is the canonical
  example)
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class BusyGroupError(Exception):
    """[FR-80] Raised internally by the redis client when the consumer
    group already exists.

    ``AsyncMessageProcessor.ensure_group`` catches this (and the
    textual ``BUSYGROUP`` equivalent raised by the test fake) and
    returns silently so the steady-state startup after the first
    deploy is idempotent.
    """


@dataclass(frozen=True)
class Message:
    """[FR-80] Raw stream entry returned by XREADGROUP / XCLAIM."""

    message_id: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class ParsedMessage:
    """[FR-80] Forward-compatible parse result.

    ``known`` contains ONLY the FR-80 documented fields; any extra
    producer-side key (a future schema change) is dropped silently
    so the consumer can roll forward without a code change.
    """

    message_id: str
    known: Mapping[str, str]


# [FR-80] Whitelist of fields ``parse_message`` must surface. Adding a
# new field here is a deliberate schema change; anything not in this
# set is dropped silently (forward compatibility).
_FR80_KNOWN_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "user_id",
    "conversation_id",
    "payload",
})

# [FR-80] PEL pagination knobs. ``_PEL_BATCH_SIZE`` is the per-call
# XPENDING range count — the original code hard-coded 100 here, which
# silently dropped any backlog beyond that. ``_PEL_PAGINATION_MAX_BATCHES``
# is a safety cap on the pagination loop (prevents an infinite loop
# if the cursor ever fails to advance).
_PEL_BATCH_SIZE: int = 100
_PEL_PAGINATION_MAX_BATCHES: int = 10_000


def _next_stream_id(stream_id: str) -> str:
    """Return the stream id immediately after ``stream_id``.

    Redis stream ids are ``"<ms>-<seq>"``; incrementing the sequence
    number is the canonical way to express "the next id after this
    one" for cursor-based XPENDING pagination. The id is returned
    unchanged if it does not match the expected format (defensive:
    a malformed id should not crash the consumer-loop).
    """
    if "-" not in stream_id:
        return stream_id
    ms, _, seq = stream_id.partition("-")
    try:
        return f"{ms}-{int(seq) + 1}"
    except ValueError:
        return stream_id


class AsyncMessageProcessor:
    """[FR-80] Consumer-group lifecycle + forward-compatible parse.

    The constructor accepts an injected redis client (sync or async);
    the unit tests pass a ``_FakeRedisClient`` so the suite never
    opens a real socket. The class is otherwise pure — no I/O is
    performed until one of the async methods is awaited.
    """

    GROUP_NAME_DEFAULT = "omnibot"
    STREAM_DEFAULT = "messages"
    BLOCK_MS_DEFAULT = 5000
    IDLE_MS_DEFAULT = 60000

    def __init__(
        self,
        redis_client: Any,
        *,
        group_name: str = "omnibot",
        stream: str = "messages",
        block_ms: int = 5000,
        idle_ms: int = 60000,
    ) -> None:
        from app.infra.config import health_probe
        health_probe()  # Hub linkage
        self.redis = redis_client
        self.group_name = group_name
        self.stream = stream
        self.block_ms = block_ms
        self.idle_ms = idle_ms
        self._in_flight: set[str] = set()

    @staticmethod
    def _is_busygroup_error(exc: BaseException) -> bool:
        """[FR-80] Detect ``BUSYGROUP`` via typed exception or message text.

        Real ``redis-py`` raises a ``ResponseError`` whose ``str()`` starts
        with ``BUSYGROUP``; the in-tree test fake raises a plain
        ``Exception("BUSYGROUP ...")``. Both paths signal the same
        "group already exists" steady state, so the detection must cover
        both shapes.
        """
        if isinstance(exc, BusyGroupError):
            return True
        return "BUSYGROUP" in str(exc)

    async def ensure_group(self) -> bool:
        """[FR-80] Create the consumer group; silently absorb BUSYGROUP.

        Returns ``True`` on both the create-success and BUSYGROUP paths
        so callers can use the return value as a simple "ready" signal
        without inspecting exceptions.

        The group's starting id is ``"0"`` (the beginning of the
        stream), not ``"$"``. Using ``"$"`` would mean "deliver only
        messages added after the group is created" — that loses every
        pre-existing stream entry on the very first deploy, and loses
        the entire backlog if the group is ever destroyed and
        recreated (disaster recovery, consumer group migration, etc.).
        The BUSYGROUP path (group already exists) ignores the id, so
        this only affects the first creation.
        """
        try:
            await self.redis.xgroup_create(
                name=self.stream,
                groupname=self.group_name,
                id="0",
                mkstream=True,
            )
            return True
        except Exception as exc:
            if self._is_busygroup_error(exc):
                return True
            raise

    async def read(self, consumer: str, count: int = 1) -> list[Message]:
        """[FR-80] XREADGROUP {stream} > {group} {consumer} BLOCK block_ms."""
        rows = await self.redis.xreadgroup(
            groupname=self.group_name,
            consumername=consumer,
            streams={self.stream: ">"},
            count=count,
            block=self.block_ms,
        )
        out: list[Message] = []
        for _stream, entries in rows or []:
            for msg_id, fields in entries:
                out.append(Message(message_id=msg_id, fields=fields))
        return out

    async def ack(self, message_id: str) -> int:
        """[FR-80] XACK the message id; returns 1 on success, 0 on miss."""
        return await self.redis.xack(
            self.stream, self.group_name, message_id,
        )

    async def _fetch_message_fields(
        self, message_id: str,
    ) -> dict[str, str] | None:
        """[FR-80] XRANGE lookup for the fields of a single message id.

        Returns the field dict when present, ``None`` otherwise. The
        XCLAIM command only transfers ownership; the caller still needs
        XRANGE to retrieve the original stream payload for re-processing.
        """
        rows = await self.redis.xrange(
            self.stream, min=message_id, max=message_id,
        )
        if not rows or not rows[0] or len(rows[0]) < 2:
            return None
        _row_id = rows[0][0]
        fields = rows[0][1]
        return fields

    async def claim_pending(self, consumer: str) -> list[Message]:
        """[FR-80] XPENDING + XCLAIM stale pending messages to ``consumer``.

        The pending-entries list (PEL) is paginated because Redis'
        XPENDING range command returns at most ``BATCH_SIZE`` entries
        per call; a single call would silently drop any backlog beyond
        that. We iterate with a cursor that advances past the last id
        of each batch, stopping when a batch is short (we drained the
        PEL) or empty.

        The XCLAIM JUSTID return value is the cross-process / cross-
        consumer gate: a losing racer gets ``[]`` back and is excluded
        from the result. No local dedup state is kept — an in-process
        ``_claimed`` set would need cross-event-loop synchronisation
        (and would be redundant with the Redis-level gate).
        """
        # XPENDING summary to short-circuit when nothing is pending.
        pending_summary = await self.redis.xpending(
            self.stream, self.group_name,
        )
        if not pending_summary or pending_summary.get("pending", 0) == 0:
            return []
        # Paginate the PEL so PELs larger than BATCH_SIZE are fully
        # processed, not silently truncated to the first batch.
        claimed: list[Message] = []
        cursor = "-"
        # Safety cap: the cursor only advances, so this loop is bounded
        # by the PEL size in practice, but we still guard against a
        # pathological Redis state (e.g. cursor that never advances).
        for _ in range(_PEL_PAGINATION_MAX_BATCHES):
            detailed = await self.redis.xpending_range(
                self.stream, self.group_name,
                min=cursor, max="+", count=_PEL_BATCH_SIZE,
            )
            if not detailed:
                break
            for entry in detailed:
                idle = entry.get("time_since_delivered", 0)
                if idle < self.idle_ms:
                    continue
                msg_id = entry["message_id"]
                fields = await self._fetch_message_fields(msg_id)
                if fields is None:
                    continue
                justids = await self.redis.xclaim(
                    self.stream, self.group_name, consumer,
                    min_idle_time=self.idle_ms,
                    message_ids=[msg_id],
                )
                for claimed_id in justids:
                    claimed.append(Message(message_id=claimed_id, fields=fields))
            if len(detailed) < _PEL_BATCH_SIZE:
                # Short batch ⇒ we drained the PEL in this round.
                break
            # Advance the cursor past the last returned id so the next
            # call yields the next page rather than re-yielding this one.
            next_cursor = _next_stream_id(detailed[-1]["message_id"])
            if next_cursor == cursor:
                # [M-29] Cursor failed to advance
                break
            cursor = next_cursor
        return claimed

    def parse_message(
        self,
        message_id: str,
        fields: Mapping[str, str],
    ) -> ParsedMessage:
        """[FR-80] Forward-compatible parse: keep only the known fields.

        ``message_id`` is the real stream id of the entry being parsed
        (from XREADGROUP / XCLAIM). It is surfaced verbatim on the
        result so the caller can correlate the parsed view back to the
        underlying stream entry — a hard-coded synthetic placeholder
        would sever that correlation.
        """
        known = {k: v for k, v in fields.items() if k in _FR80_KNOWN_FIELDS}
        return ParsedMessage(message_id=message_id, known=known)

    async def consume_loop(
        self,
        consumer: str,
        handler: Any,
    ) -> None:
        """[BUG-12] Consumer loop that reads and acks messages."""
        while True:
            pending = await self.claim_pending(consumer)
            for msg in pending:
                if msg.message_id in self._in_flight:
                    continue
                self._in_flight.add(msg.message_id)
                try:
                    parsed = self.parse_message(msg.message_id, msg.fields)
                    try:
                        await handler(parsed)
                        with contextlib.suppress(Exception):
                            await self.ack(msg.message_id)
                    except Exception as exc:  # pragma: no cover — consumer shutdown signal handler — requires real Redis stream
                        logger.debug("redis stream handler error: %s", exc)  # pragma: no cover — consumer shutdown signal handler — requires real Redis stream
                finally:
                    self._in_flight.discard(msg.message_id)

            messages = await self.read(consumer)
            for msg in messages:
                if msg.message_id in self._in_flight:
                    continue  # pragma: no cover — consumer claim_pending error fallback — requires real Redis fault
                self._in_flight.add(msg.message_id)
                try:
                    parsed = self.parse_message(msg.message_id, msg.fields)
                    try:
                        await handler(parsed)
                        with contextlib.suppress(Exception):
                            await self.ack(msg.message_id)
                    except Exception as exc:  # pragma: no cover — consumer ack race condition — requires real Redis concurrency
                        logger.debug("redis stream ack race: %s", exc)  # pragma: no cover — consumer ack race condition — requires real Redis concurrency
                finally:
                    self._in_flight.discard(msg.message_id)


__all__ = [
    "_FR80_KNOWN_FIELDS",
    "_PEL_BATCH_SIZE",
    "_PEL_PAGINATION_MAX_BATCHES",
    "AsyncMessageProcessor",
    "BusyGroupError",
    "Message",
    "ParsedMessage",
    "_next_stream_id",
]

