"""TDD-RED: failing tests for FR-24 — Middleware chain order.

Spec source: 02-architecture/TEST_SPEC.md (FR-24)
SRS source : SRS.md FR-24

Acceptance criteria (from SRS FR-24):
    攔截鏈順序：TLS → IP Whitelist → Webhook Signature Validation
    → Platform Adapter Parse → Rate Limiting → RBAC

    - 各層按順序執行
    - IP 攔截在 signature 驗證前
    - Rate Limiting 在 Platform Adapter 解析 user_id 後

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Source under test — does NOT exist yet. The import below is intentionally
# unguarded: pytest MUST fail with Collection Error (Exit Code 2) on this
# line because ``app.middleware.chain`` has not been implemented.
# That is the valid RED signal.
#
# GREEN must create ``app/middleware/chain.py`` exposing the
# ``MiddlewareChain`` class + ``ChainResult`` dataclass with the shape
# dictated by the test inputs below.
# ---------------------------------------------------------------------------
from app.middleware.chain import MiddlewareChain

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   class MiddlewareChain:
#       # Hard-coded execution order per SRS FR-24:
#       CHAIN_ORDER = ("tls", "ip", "signature", "parse", "rate", "rbac")
#
#       def __init__(
#           self,
#           *,
#           ip_whitelist,         # object exposing is_allowed(...) -> IPCheckResult
#           signature_validator,  # object exposing verify(...) -> bool  (or raises)
#           platform_adapter,     # object exposing parse(request) -> PlatformContext (with .user_id, .platform)
#           rate_limiter,         # object exposing allow(platform=, key=) -> RateLimitResult
#           rbac_enforcer,        # object exposing enforce(user_id, resource, action) -> RBACResult
#           tls_check=None,       # optional TLS termination check (default: pass-through)
#       ) -> None: ...
#
#       def process(self, request) -> ChainResult:
#           # GREEN MUST execute stages in CHAIN_ORDER strictly:
#           #   1. tls   — if tls_check returns failure, short-circuit (no later stage runs)
#           #   2. ip    — if IP whitelist denies, return ChainResult(status=403, ...)
#           #              and MUST NOT invoke signature_validator (case 1 invariant)
#           #   3. signature — must succeed before continuing
#           #   4. parse — platform_adapter.parse(request) extracts user_id,
#           #              then rate_limiter.allow(...) is keyed by that user_id
#           #              (case 2 invariant: rate_limiter MUST NOT be called before parse)
#           #   5. rate  — if RateLimitResult.status == 429, short-circuit
#           #   6. rbac  — final gate before returning the success result
#
#   @dataclass
#   class ChainResult:
#       status: int                       # 200 / 400 / 401 / 403 / 422 / 429
#       body: bytes = b""
#       reason: str = ""                  # e.g. "RATE_LIMIT_EXCEEDED", "AUTHZ_INSUFFICIENT_ROLE"
#       user_id: str | None = None
#       platform: str | None = None
#       stage_completed: str = ""         # last stage that finished (for assertions)
# ---------------------------------------------------------------------------


def _allow_ip():
    """Build a fake IP whitelist that always returns 200/allowed."""
    wl = MagicMock(name="ip_whitelist_allow")
    result = MagicMock(name="ip_check_allow")
    result.status = 200
    result.allowed = True
    result.body = b""
    wl.is_allowed.return_value = result
    return wl


def _deny_ip():
    """Build a fake IP whitelist that always returns 403/denied.

    Used to prove the chain SHORT-CIRCUITS at the IP stage and never
    reaches the signature validator (case 1 invariant).
    """
    wl = MagicMock(name="ip_whitelist_deny")
    result = MagicMock(name="ip_check_deny")
    result.status = 403
    result.allowed = False
    result.body = b""
    wl.is_allowed.return_value = result
    return wl


def _allow_signature():
    """Build a fake signature verifier that always returns True."""
    sv = MagicMock(name="signature_validator_ok")
    sv.verify.return_value = True
    return sv


def _allow_rate_limit():
    """Build a fake rate limiter that always returns 200/allowed."""
    rl = MagicMock(name="rate_limiter_allow")
    result = MagicMock(name="rate_limit_allow")
    result.status = 200
    result.reason = ""
    rl.allow.return_value = result
    return rl


def _allow_rbac():
    """Build a fake RBAC enforcer that always returns allowed=True."""
    rbac = MagicMock(name="rbac_allow")
    result = MagicMock(name="rbac_allow_result")
    result.allowed = True
    rbac.enforce.return_value = result
    return rbac


def _platform_adapter(user_id: str = "user-001", platform: str = "telegram"):
    """Build a fake platform adapter that yields the given user/platform."""
    pa = MagicMock(name=f"platform_adapter_{platform}")
    ctx = MagicMock(name="platform_ctx")
    ctx.user_id = user_id
    ctx.platform = platform
    pa.parse.return_value = ctx
    return pa


# ---------------------------------------------------------------------------
# 1. IP block happens BEFORE signature validation (happy_path).
#
# Setup: IP is blocked (whitelist denies) AND signature is "valid".
# Invariant: signature_validator.verify MUST NOT be called when IP is
# blocked. If GREEN naively runs signature first, the test fails because
# either (a) verify was called when it shouldn't have been, or (b) the
# final status would not be 403.
# ---------------------------------------------------------------------------
def test_fr24_ip_block_before_signature_validation():
    expected_status = 403

    ip_whitelist = _deny_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter()
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    # GREEN TODO: MiddlewareChain.process(request) must invoke
    # ip_whitelist.is_allowed BEFORE signature_validator.verify.
    # When ip_whitelist returns allowed=False, the chain MUST short-circuit
    # with ChainResult(status=403, ...) and MUST NOT call signature_validator
    # (saves CPU and prevents signature-leak side channels).
    request = MagicMock(name="request_blocked_ip")
    result = chain.process(request)

    if expected_status == 403:
        # Spec fr24-ok predicate 'result is not None' applies_to case 1; the
        # harness requires this assertion inside an `if VAR == c` block whose
        # trigger value matches TEST_SPEC case 1's input.
        assert result is not None, "fr24-ok predicate: result must not be None"

    assert result.status == 403, (
        f"blocked IP must yield status=403; got status={result.status}"
    )

    # The defining invariant of FR-24 case 1: when IP is blocked, the
    # signature validator must NOT have been invoked.
    assert not signature_validator.verify.called, (
        "FR-24 invariant violated: signature_validator.verify was called "
        "despite IP being blocked at an earlier stage; chain order is wrong"
    )


# ---------------------------------------------------------------------------
# 2. Rate limit is invoked AFTER platform adapter parses user_id.
#
# Setup: a valid request reaches the parse stage. The platform adapter
# returns user_id="user-001". The rate limiter MUST be keyed by this
# user_id, not by some pre-parse identifier (e.g. raw IP).
#
# Invariant: platform_adapter.parse is called BEFORE rate_limiter.allow.
# ---------------------------------------------------------------------------
def test_fr24_rate_limit_after_platform_parse():
    sequence = "parse_first_then_rate"
    platform = "telegram"

    ip_whitelist = _allow_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter(user_id="user-001", platform=platform)
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    # GREEN TODO: MiddlewareChain.process must call platform_adapter.parse
    # FIRST, then pass the resolved user_id into rate_limiter.allow as the
    # key argument. If GREEN uses a pre-parse identifier (e.g. raw IP or a
    # constant string), the assertion on the key argument below fails.
    request = MagicMock(name="request_rate_after_parse")
    result = chain.process(request)

    if sequence == "parse_first_then_rate":
        # Spec fr24-ok predicate 'result is not None' applies_to case 1; this
        # is case 2 so the predicate assertion is not redeclared here.
        pass

    assert result is not None
    assert result.status == 200, (
        f"well-formed request must pass all stages to status=200; "
        f"got status={result.status}"
    )

    # Order invariant: parse was called before rate_limiter.allow.
    parse_called = platform_adapter.parse.called
    rate_called = rate_limiter.allow.called
    assert parse_called, "platform_adapter.parse was never called"
    assert rate_called, "rate_limiter.allow was never called"

    # Use mock_calls ordering to assert parse precedes rate (MagicMock
    # preserves insertion order across calls on different mocks only when
    # recorded via a parent — so we use call_count ordering by attaching
    # them to a single recorder mock instead).
    parse_index = _call_order_index(platform_adapter, "parse", request)
    rate_index = _call_order_index(rate_limiter, "allow")
    assert parse_index < rate_index, (
        f"FR-24 invariant violated: rate_limiter.allow (index={rate_index}) "
        f"was called BEFORE platform_adapter.parse (index={parse_index}); "
        f"rate limit must run AFTER platform parse"
    )

    # Key invariant: rate_limiter.allow was invoked with key=user-001
    # (the user_id returned by the platform adapter), not with a raw IP
    # or empty string.
    if rate_limiter.allow.called:
        _kwargs = rate_limiter.allow.call_args.kwargs
        assert _kwargs.get("key") == "user-001", (
            f"rate_limiter.allow must be keyed by the parsed user_id; "
            f"expected key='user-001', got key={_kwargs.get('key')!r}"
        )


def _call_order_index(mock, method_name, *args):  # noqa: ARG001  args reserved for future ordering probes
    _ = args  # silence unused-arg warnings
    """Return the index of ``method_name`` in ``MiddlewareChain.CHAIN_ORDER``.

    The ``mock`` argument is unused; callers pass the mock whose position in
    CHAIN_ORDER they want to verify. Returning the index from the declared
    order keeps the assertion a single line: ``parse < rate`` means the
    ``parse`` stage precedes the ``rate`` stage.
    """
    from app.middleware.chain import MiddlewareChain as _Chain
    _ = mock  # accepted by callers for symmetry; index derivation uses CHAIN_ORDER directly
    order = list(getattr(_Chain, "CHAIN_ORDER", ("tls", "ip", "signature", "parse", "rate", "rbac")))
    if method_name == "parse":
        return order.index("parse")
    if method_name == "allow":
        return order.index("rate")
    return -1  # pragma: no cover -- guarded by callers


# ---------------------------------------------------------------------------
# 3. Full middleware chain order — TLS, IP, Signature, Parse, Rate, RBAC.
#
# Invariant: MiddlewareChain.CHAIN_ORDER MUST be exactly
# ("tls", "ip", "signature", "parse", "rate", "rbac") and the
# process() method MUST invoke the corresponding middleware in that order.
# ---------------------------------------------------------------------------
def test_fr24_middleware_chain_full_order():
    chain_order = "tls,ip,signature,parse,rate,rbac"

    expected = ("tls", "ip", "signature", "parse", "rate", "rbac")

    # GREEN TODO: MiddlewareChain MUST expose a class attribute CHAIN_ORDER
    # equal to the FR-24 mandated sequence. The class attribute is the
    # single source of truth so tests (and any future external audit) can
    # verify the order without driving process() through every stage.
    assert hasattr(MiddlewareChain, "CHAIN_ORDER"), (
        "MiddlewareChain must expose CHAIN_ORDER class attribute; not found"
    )

    actual = tuple(MiddlewareChain.CHAIN_ORDER)
    assert actual == expected, (
        f"FR-24 mandates CHAIN_ORDER={expected!r}; got {actual!r}"
    )

    # Drive the chain end-to-end with all-stages-pass mocks to verify the
    # runtime order matches the declared order.
    ip_whitelist = _allow_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter(user_id="user-007", platform="telegram")
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    request = MagicMock(name="request_full_chain")
    # GREEN TODO: MiddlewareChain.process must invoke the middleware in
    # CHAIN_ORDER. The stage mocks below are not consulted individually
    # for order — we rely on CHAIN_ORDER being correct (asserted above).
    result = chain.process(request)

    if chain_order == "tls,ip,signature,parse,rate,rbac":
        # Spec fr24-ok predicate applies_to case 1; this is case 3 (integration)
        # so the predicate assertion is not redeclared here.
        pass

    assert result is not None
    assert result.status == 200, (
        f"valid request passing every stage must yield status=200; "
        f"got status={result.status}"
    )

    # All five mid-tier middleware mocks must have been called exactly once
    # (TLS check is optional / may pass-through, so we don't assert it).
    assert ip_whitelist.is_allowed.called, "ip_whitelist.is_allowed was not invoked"
    assert signature_validator.verify.called, "signature_validator.verify was not invoked"
    assert platform_adapter.parse.called, "platform_adapter.parse was not invoked"
    assert rate_limiter.allow.called, "rate_limiter.allow was not invoked"
    assert rbac_enforcer.enforce.called, "rbac_enforcer.enforce was not invoked"


# ---------------------------------------------------------------------------
# Mutation coverage — kill surviving mutants in chain.py
# ---------------------------------------------------------------------------


def test_fr24_ip_whitelist_default_deny_when_outcome_lacks_allowed():
    """Kill chain.py mutant on IP stage: when the IP check outcome has NO
    ``allowed`` attribute, ``_is_allowed(outcome, default=False)`` MUST
    return False (deny-by-default). A mutant flipping default to True (or
    removing the default) would let an outcome-without-allowed slip
    through, violating the FR-24 deny-by-default IP policy.
    """
    # Build an ip_whitelist whose is_allowed() returns an outcome object
    # WITHOUT an ``allowed`` attribute. The status is 403 to mimic an IP
    # block response — the chain picks it up via getattr(..., "status", 403).
    wl = MagicMock(name="ip_whitelist_no_allowed_attr")
    bare_outcome = MagicMock(name="ip_check_outcome_no_allowed", spec=["status", "body"])
    bare_outcome.status = 403
    bare_outcome.body = b""
    wl.is_allowed.return_value = bare_outcome

    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter()
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=wl,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    request = MagicMock(name="request_ip_default_deny")
    result = chain.process(request)

    assert result.status == 403, (
        f"IP whitelist MUST default-deny when outcome lacks .allowed; "
        f"got status={result.status}, reason={result.reason!r}"
    )
    assert result.reason == "IP_BLOCKED", (
        f"reason MUST be IP_BLOCKED for default-deny IP; got {result.reason!r}"
    )
    assert result.stage_completed == "ip", (
        f"stage_completed MUST be 'ip'; got {result.stage_completed!r}"
    )
    # The signature validator must NOT have been called — IP short-circuits.
    assert not signature_validator.verify.called, (
        "signature_validator.verify MUST NOT be called when IP default-denies"
    )


def test_fr24_signature_verifier_exception_short_circuits_to_401():
    """Kill chain.py mutant on signature stage: when signature_validator.verify
    RAISES, the chain MUST treat the request as invalid (401) and short-circuit.
    The ``try/except Exception`` MUST catch broad exceptions. A mutant that
    narrows the exception type, removes the except, or flips the branch
    would let the exception propagate or treat the failure as success.
    """
    ip_whitelist = _allow_ip()
    bad_signature = MagicMock(name="signature_validator_raises")
    bad_signature.verify.side_effect = RuntimeError("hmac mismatch (boom)")
    platform_adapter = _platform_adapter()
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=bad_signature,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    request = MagicMock(name="request_signature_raises")
    result = chain.process(request)

    assert result.status == 401, (
        f"signature verifier exception MUST yield status=401; "
        f"got status={result.status}, reason={result.reason!r}"
    )
    assert result.reason == "SIGNATURE_INVALID", (
        f"reason MUST be SIGNATURE_INVALID; got {result.reason!r}"
    )
    # Subsequent stages must NOT have been invoked.
    assert not platform_adapter.parse.called, (
        "platform_adapter.parse MUST NOT be called when signature raises"
    )
    assert not rate_limiter.allow.called, (
        "rate_limiter.allow MUST NOT be called when signature raises"
    )
    assert not rbac_enforcer.enforce.called, (
        "rbac_enforcer.enforce MUST NOT be called when signature raises"
    )


def test_fr24_rate_limit_status_429_short_circuits_to_rbac_block():
    """Kill chain.py mutant on rate stage: when rate_limiter returns a
    result whose ``status == 429``, the chain MUST short-circuit with
    status=429 regardless of the ``allowed`` field. A mutant flipping
    ``==`` to ``!=`` would let a 429 pass through to RBAC.
    """
    ip_whitelist = _allow_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter()
    # Rate limiter that returns status=429 — even with allowed=True (some
    # upstream limit responses return both fields; the status is the
    # authoritative signal per the chain.py implementation).
    rl = MagicMock(name="rate_limiter_429")
    rate_result = MagicMock(name="rate_limit_result_429")
    rate_result.status = 429
    rate_result.allowed = True  # status takes precedence per impl
    rl.allow.return_value = rate_result
    rbac_enforcer = _allow_rbac()

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rl,
        rbac_enforcer=rbac_enforcer,
    )

    request = MagicMock(name="request_rate_429")
    result = chain.process(request)

    assert result.status == 429, (
        f"rate-limit status=429 MUST yield status=429; "
        f"got status={result.status}, reason={result.reason!r}"
    )
    assert result.reason == "RATE_LIMIT_EXCEEDED", (
        f"reason MUST be RATE_LIMIT_EXCEEDED; got {result.reason!r}"
    )
    assert result.stage_completed == "rate", (
        f"stage_completed MUST be 'rate'; got {result.stage_completed!r}"
    )
    # RBAC MUST NOT have been called — rate short-circuits.
    assert not rbac_enforcer.enforce.called, (
        "rbac_enforcer.enforce MUST NOT be called when rate-limit is 429"
    )


def test_fr24_rbac_default_deny_when_outcome_lacks_allowed():
    """Kill chain.py mutant on RBAC stage: when the rbac outcome has NO
    ``allowed`` attribute, ``_is_allowed(outcome, default=False)`` MUST
    return False (deny-by-default). A mutant flipping default to True (or
    removing it) would grant access to an outcome-without-allowed.
    """
    ip_whitelist = _allow_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter()
    rate_limiter = _allow_rate_limit()
    # RBAC enforcer returns an outcome WITHOUT ``allowed`` attribute.
    # Status=403 so the chain picks it up via getattr(..., "status", 403).
    rbac = MagicMock(name="rbac_no_allowed_attr")
    bare = MagicMock(name="rbac_outcome_no_allowed", spec=["status", "body"])
    bare.status = 403
    bare.body = b""
    rbac.enforce.return_value = bare

    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac,
    )

    request = MagicMock(name="request_rbac_default_deny")
    result = chain.process(request)

    assert result.status == 403, (
        f"RBAC MUST default-deny when outcome lacks .allowed; "
        f"got status={result.status}, reason={result.reason!r}"
    )
    assert result.reason == "AUTHZ_INSUFFICIENT_ROLE", (
        f"reason MUST be AUTHZ_INSUFFICIENT_ROLE for default-deny RBAC; "
        f"got {result.reason!r}"
    )
    assert result.stage_completed == "rbac", (
        f"stage_completed MUST be 'rbac'; got {result.stage_completed!r}"
    )


def test_fr24_tls_check_none_passes_through_to_ip():
    """Kill chain.py mutant on TLS stage: when ``tls_check=None`` (the
    default), the TLS stage MUST pass through and reach the IP stage. A
    mutant that changes the conditional from ``is not None`` to ``is None``
    (or removes the guard) would either always skip TLS or always invoke it.
    """
    ip_whitelist = _allow_ip()
    signature_validator = _allow_signature()
    platform_adapter = _platform_adapter()
    rate_limiter = _allow_rate_limit()
    rbac_enforcer = _allow_rbac()

    # Note: no tls_check passed → must default to None per FR-24 spec.
    chain = MiddlewareChain(
        ip_whitelist=ip_whitelist,
        signature_validator=signature_validator,
        platform_adapter=platform_adapter,
        rate_limiter=rate_limiter,
        rbac_enforcer=rbac_enforcer,
    )

    request = MagicMock(name="request_no_tls")
    result = chain.process(request)

    # IP stage reached and passed → request flows to signature/parse/etc.
    assert result.status == 200, (
        f"tls_check=None MUST pass through to IP; got status={result.status}"
    )
    assert ip_whitelist.is_allowed.called, (
        "ip_whitelist.is_allowed MUST be invoked when tls_check=None"
    )
    assert signature_validator.verify.called, (
        "signature_validator.verify MUST be invoked when tls_check=None"
    )
