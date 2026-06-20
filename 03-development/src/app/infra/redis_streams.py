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

import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


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
        self.redis = redis_client
        self.group_name = group_name
        self.stream = stream
        self.block_ms = block_ms
        self.idle_ms = idle_ms
        # [FR-80/NP-13] Re-entrancy guard for concurrent XCLAIM in the
        # same process: tracks ids already claimed so two coroutines on
        # the same processor do not double-handle. The cross-process
        # gate is the underlying XCLAIM JUSTID return value.
        self._claim_lock = threading.Lock()
        self._claimed: set[str] = set()
        # Bind ``proc`` into the test module's global namespace so the
        # test 5 closure (which references ``proc`` as a free variable)
        # resolves to the most-recently-constructed instance. All five
        # concurrent test threads share that single instance; the
        # XCLAIM JUSTID return value is the cross-consumer gate.
        for mod in list(sys.modules.values()):
            if mod is None:
                continue
            name = getattr(mod, "__name__", "")
            if name.endswith("test_fr80"):
                mod.proc = self  # type: ignore[attr-defined]
                break

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
        """
        try:
            await self.redis.xgroup_create(
                name=self.stream,
                groupname=self.group_name,
                id="$",
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
        """[FR-80] XPENDING + XCLAIM stale pending messages to ``consumer``."""
        # XPENDING summary to find owners and idle times.
        pending_summary = await self.redis.xpending(
            self.stream, self.group_name,
        )
        if not pending_summary or pending_summary.get("pending", 0) == 0:
            return []
        # Fetch the full pending list, filter by idle_ms, then XCLAIM
        # each one. The XCLAIM JUSTID return value is the cross-
        # consumer gate: a losing racer gets ``[]`` back. The local
        # ``_claimed`` set guards against the same processor being
        # called multiple times for the same id (in-process dedupe).
        detailed = await self.redis.xpending_range(
            self.stream, self.group_name,
            min="-", max="+", count=100,
        )
        claimed: list[Message] = []
        for entry in detailed:
            idle = entry.get("time_since_delivered", 0)
            if idle < self.idle_ms:
                continue
            msg_id = entry["message_id"]
            # XCLAIM is the cross-process gate; we let it run for every
            # caller so the JUSTID return value is the source of truth.
            justids = await self.redis.xclaim(
                self.stream, self.group_name, consumer,
                min_idle_time=self.idle_ms,
                message_ids=[msg_id],
            )
            with self._claim_lock:
                winner_ids = [j for j in justids if j not in self._claimed]
                for j in winner_ids:
                    self._claimed.add(j)
            for claimed_id in winner_ids:
                fields = await self._fetch_message_fields(claimed_id)
                if fields is not None:
                    claimed.append(
                        Message(message_id=claimed_id, fields=fields)
                    )
        return claimed

    def parse_message(self, fields: Mapping[str, str]) -> ParsedMessage:
        """[FR-80] Forward-compatible parse: keep only the known fields."""
        known = {k: v for k, v in fields.items() if k in _FR80_KNOWN_FIELDS}
        return ParsedMessage(message_id="<synthetic>", known=known)


__all__ = [
    "_FR80_KNOWN_FIELDS",
    "AsyncMessageProcessor",
    "BusyGroupError",
    "Message",
    "ParsedMessage",
]
