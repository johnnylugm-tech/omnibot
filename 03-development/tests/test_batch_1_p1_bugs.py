import asyncio
import contextlib
from collections import deque
from unittest.mock import patch

import pytest
from app.infra.rate_limit import RateLimiter, RateLimitResult
from app.infra.redis_streams import AsyncMessageProcessor, ParsedMessage


def test_id_rate_limit_01_a2a_platform():
    assert "a2a" in RateLimiter.LIMITS
    assert RateLimiter.LIMITS["a2a"] == 30

@pytest.mark.asyncio
async def test_id_rate_limit_08_aallow_await():
    limiter = RateLimiter()
    result = await limiter.aallow(platform="web", key="test")
    assert isinstance(result, RateLimitResult)

def test_id_rate_limit_10_buckets_size_bounded():
    limiter = RateLimiter()
    with patch("time.monotonic", return_value=100.0):
        for i in range(10005):
            limiter._buckets[("web", f"key{i}")] = deque([100.0])
        limiter._in_memory_check("web", "test", 10)
        assert len(limiter._buckets) <= 10001

@pytest.mark.asyncio
async def test_id_redis_streams_01_in_flight_dedup():
    class DummyMsg:
        def __init__(self, message_id):
            self.message_id = message_id
            self.fields = {"event_type": "test"}

    processor = AsyncMessageProcessor(None)

    async def mock_claim(c):
        return [DummyMsg("1-0")]
    async def mock_read(c):
        return []
    async def mock_ack(m):
        pass

    processor.claim_pending = mock_claim
    processor.read = mock_read
    processor.ack = mock_ack

    handled_count = 0
    async def handler(msg):
        nonlocal handled_count
        handled_count += 1
        await asyncio.sleep(0.1)

    async def run_loop():
        with contextlib.suppress(ZeroDivisionError):
            await processor.consume_loop("cons", handler)

    processor.read = mock_read # override temporarily

    # We will simulate the second task picking it up
    t1 = asyncio.create_task(handler(ParsedMessage("1-0", {})))
    processor._in_flight.add("1-0")

    # Run a consume loop that should ignore it
    processor.read = mock_read
    async def mock_claim_with_error(c):
        # Return the same msg, but also raise error to stop loop
        processor.read = lambda c: 1/0
        return [DummyMsg("1-0")]
    processor.claim_pending = mock_claim_with_error

    with contextlib.suppress(Exception):
        await processor.consume_loop("cons", handler)

    await t1
    assert handled_count == 1
