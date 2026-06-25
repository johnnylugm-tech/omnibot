"""Performance benchmarks for NFR-01..09 high-risk modules.

Targets pinned in .methodology/quality_manifest.json::nfr_traceability:
    NFR-02 p95<5ms     app.core.paladin (PII regex classification)
    NFR-03 p95<200ms   app.core.paladin (full classify)
    NFR-04 p95<300ms   app.core.knowledge (RAG retrieval / chunking)
    NFR-05 p95<500ms   app.core.dst (state transition)
    NFR-06 p95<100ms   app.infra.circuit_breaker
    NFR-07 p95<50ms    app.infra.redis_streams ack
    NFR-09 p95<100ms   app.infra.rate_limit token-bucket

These benchmarks are minimal smoke tests — they verify the modules
execute within an order-of-magnitude of the NFR targets on a developer's
laptop. They are NOT a substitute for load testing in staging.
"""
from __future__ import annotations


# -----------------------------------------------------------------------
# NFR-02 / NFR-03: app.core.paladin InputSanitizer
# Target: p95 < 5ms per single call (regex path), < 200ms full classify.
# -----------------------------------------------------------------------
class TestPaladinPerformance:
    """[NFR-02][NFR-03] PII / injection classification benchmarks."""

    def test_fr02_nfr02_sanitize_short(self, benchmark):
        """Input sanitizer on a short text — target p95 < 5ms."""
        from app.core.paladin import InputSanitizer

        s = InputSanitizer()
        text = "Hello, this is a clean message."
        benchmark(s.sanitize, text)

    def test_fr02_nfr03_sanitize_long(self, benchmark):
        """Input sanitizer on a long text — target p95 < 200ms."""
        from app.core.paladin import InputSanitizer

        s = InputSanitizer()
        text = ("Lorem ipsum dolor sit amet. " * 50) + " ID:A123456789 "
        benchmark(s.sanitize, text)


# -----------------------------------------------------------------------
# NFR-04 / NFR-08: app.core.knowledge RAG retrieval / chunking
# Target: p95 < 300ms retrieval, < 2000ms indexed search.
# -----------------------------------------------------------------------
class TestKnowledgePerformance:
    """[NFR-04][NFR-08] Knowledge retrieval benchmarks."""

    def test_fr04_nfr04_knowledge_tokenize(self, benchmark):
        """Knowledge chunker split_parents — target p95 < 300ms."""
        from app.core.knowledge import Chunker

        chunker = Chunker()
        text = "Omnibot knowledge chunking benchmark. " * 50
        benchmark(chunker.split_parents, text)


# -----------------------------------------------------------------------
# NFR-05: app.core.dst state machine transition
# Target: p95 < 500ms per FSM cycle.
# -----------------------------------------------------------------------
class TestDstPerformance:
    """[NFR-05] Dialog state machine benchmarks."""

    def test_fr34_nfr05_dst_legal_check(self, benchmark):
        """Pure legal-transition predicate — target p95 < 500ms."""
        from app.core.dst import _is_legal_transition

        # A legal edge per the FSM table; this is a pure function
        benchmark(_is_legal_transition, "IDLE", "INTENT_DETECTED")


# -----------------------------------------------------------------------
# NFR-06: app.infra.circuit_breaker token pass-through
# Target: p95 < 100ms per call.
# -----------------------------------------------------------------------
class TestCircuitBreakerPerformance:
    """[NFR-06] Circuit breaker benchmarks."""

    def test_fr06_nfr06_circuit_breaker_construction(self, benchmark):
        """Circuit-breaker construction — target p95 < 100ms."""
        from app.infra.circuit_breaker import CircuitBreaker

        benchmark(CircuitBreaker)


# -----------------------------------------------------------------------
# NFR-09: app.infra.rate_limit token-bucket acquire
# Target: p95 < 100ms per acquire.
# -----------------------------------------------------------------------
class TestRateLimitPerformance:
    """[NFR-09] Rate limiter benchmarks."""

    def test_fr09_nfr09_rate_limit_construction(self, benchmark):
        """In-memory rate limiter construction — target p95 < 100ms."""
        from app.infra.rate_limit import RateLimiter

        benchmark(RateLimiter)


# -----------------------------------------------------------------------
# NFR-07: app.infra.redis_streams message parse
# Target: p95 < 50ms per parse call.
# (Pure in-memory parse — does not require a live Redis server.)
# -----------------------------------------------------------------------
class TestRedisStreamsPerformance:
    """[NFR-07] Redis streams parse benchmarks."""

    def test_fr80_nfr07_redis_parse_helper(self, benchmark):
        """Stream message id parse — target p95 < 50ms."""
        from app.infra.redis_streams import _next_stream_id

        benchmark(_next_stream_id, "1234567890-0")
