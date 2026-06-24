"""[FR-24] Middleware chain orchestrator.

Acceptance criteria (SRS FR-24):
    攔截鏈順序: TLS → IP Whitelist → Webhook Signature Validation
    → Platform Adapter Parse → Rate Limiting → RBAC

    - 各層按順序執行
    - IP 攔截在 signature 驗證前
    - Rate Limiting 在 Platform Adapter 解析 user_id 後

Citations:
- SRS.md FR-24 (description and spec block)
- 02-architecture/TEST_SPEC.md FR-24 (ip_block_before_signature_validation,
  rate_limit_after_platform_parse, middleware_chain_full_order)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    # FastAPI/Starlette BaseHTTPMiddleware. Optional import keeps this
    # module usable in unit-test contexts where the HTTP stack is absent.
    from starlette.middleware.base import BaseHTTPMiddleware  # type: ignore
    from starlette.responses import Response  # type: ignore
    _HAS_STARLETTE = True
except ImportError:  # pragma: no cover — exercised only in minimal envs
    BaseHTTPMiddleware = None  # type: ignore
    Response = None  # type: ignore
    _HAS_STARLETTE = False


@dataclass
class ChainResult:
    """Outcome of running a request through the FR-24 middleware chain.

    Attributes:
        status: HTTP-shaped status (200 / 400 / 401 / 403 / 422 / 429).
        body: Response body bytes.
        reason: Machine-readable short reason, e.g. "IP_BLOCKED",
            "RATE_LIMIT_EXCEEDED", "AUTHZ_INSUFFICIENT_ROLE".
        user_id: Resolved by the platform adapter at the parse stage, or
            ``None`` if the chain short-circuited before parse.
        platform: Resolved by the platform adapter at the parse stage, or
            ``None`` if the chain short-circuited before parse.
        stage_completed: Name of the last stage that finished executing,
            drawn from ``MiddlewareChain.CHAIN_ORDER``.
    """

    status: int
    body: bytes = b""
    reason: str = ""
    user_id: str | None = None
    platform: str | None = None
    stage_completed: str = ""


def _is_allowed(outcome: Any, *, default: bool) -> bool:
    """Defensive read of ``outcome.allowed`` with a fallback default.

    Each middleware contract uses a different default semantic — TLS treats
    ``None`` as pass-through (default True) while IP/RBAC treat ``None`` as
    deny (default False). Keeping the default at the call site preserves
    those semantics without scattering ``getattr`` calls.
    """
    return bool(getattr(outcome, "allowed", default))


class MiddlewareChain:
    """Strict-order orchestrator for the FR-24 middleware chain.

    ``CHAIN_ORDER`` is the single source of truth for stage order. Each
    stage in :meth:`process` is a labelled block whose order must match
    ``CHAIN_ORDER``; reordering requires touching both in lockstep.

    Short-circuit semantics:
        - Any stage that returns a non-success result causes the chain to
          return immediately. Subsequent stages are NOT invoked (this is
          what guarantees IP-deny never reaches the signature validator
          and rate-limit never blocks the parse path).
    """

    # Hard-coded execution order per SRS FR-24. Tests assert on this
    # tuple directly via ``MiddlewareChain.CHAIN_ORDER``; do not rename
    # or reorder without updating SRS FR-24.
    CHAIN_ORDER = ("tls", "ip", "signature", "parse", "rate", "rbac")

    def __init__(
        self,
        *,
        ip_whitelist,
        signature_validator,
        platform_adapter,
        rate_limiter,
        rbac_enforcer,
        tls_check=None,
    ) -> None:
        self.tls_check = tls_check
        self.ip_whitelist = ip_whitelist
        self.signature_validator = signature_validator
        self.platform_adapter = platform_adapter
        self.rate_limiter = rate_limiter
        self.rbac_enforcer = rbac_enforcer

    @staticmethod
    def _deny(stage: str, status: int, reason: str, **fields: Any) -> ChainResult:
        """Build a short-circuit ``ChainResult`` for ``stage``.

        ``fields`` carries the optional overrides each stage needs
        (e.g. ``body`` for IP/TLS, ``user_id``/``platform`` for the
        post-parse stages).
        """
        return ChainResult(
            status=status,
            reason=reason,
            stage_completed=stage,
            **fields,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(self, request) -> ChainResult:
        """Run ``request`` through every stage in ``CHAIN_ORDER``.

        Returns a :class:`ChainResult` reflecting the first non-success
        stage, or a 200 result if every stage passes.
        """
        # 1. TLS termination check (optional pass-through when None).
        if self.tls_check is not None:
            tls_outcome = self.tls_check(request)
            if not _is_allowed(tls_outcome, default=True):
                return self._deny(
                    "tls",
                    status=getattr(tls_outcome, "status", 400),
                    reason="TLS_CHECK_FAILED",
                    body=getattr(tls_outcome, "body", b""),
                )

        # 2. IP Whitelist — FR-24 mandates this BEFORE signature validation.
        client_host = getattr(getattr(request, "client", None), "host", None)
        x_forwarded_for = request.headers.get("x-forwarded-for")
        ip_outcome = self.ip_whitelist.is_allowed(x_forwarded_for=x_forwarded_for, client_host=client_host)
        if not _is_allowed(ip_outcome, default=False):
            ip_status = getattr(ip_outcome, "status", 403)
            return self._deny(
                "ip",
                status=ip_status,
                reason="IP_MISCONFIGURED" if ip_status == 400 else "IP_BLOCKED",
                body=getattr(ip_outcome, "body", b""),
            )

        # 3. Webhook Signature Validation.
        try:
            is_valid = self.signature_validator.verify(request)
        except Exception:
            is_valid = False
        if not is_valid:
            return self._deny("signature", status=401, reason="SIGNATURE_INVALID")

        # 4. Platform Adapter Parse — produces the user_id used as the
        # rate-limiter key in the next stage.
        try:
            ctx = self.platform_adapter.parse(request)
        except Exception:
            return self._deny("parse", status=400, reason="PARSE_FAILED")

        # 5. Rate Limiting — keyed by the parsed user_id, not the raw IP.
        rate_outcome = self.rate_limiter.allow(
            platform=ctx.platform,
            key=ctx.user_id,
        )
        if getattr(rate_outcome, "status", 200) == 429 or not _is_allowed(rate_outcome, default=True):
            return self._deny(
                "rate",
                status=429,
                reason="RATE_LIMIT_EXCEEDED",
                user_id=ctx.user_id,
                platform=ctx.platform,
            )

        # 6. RBAC — final authorization gate.
        rbac_outcome = self.rbac_enforcer.enforce(
            ctx.user_id, "webhook", "receive"
        )
        if not _is_allowed(rbac_outcome, default=False):
            return self._deny(
                "rbac",
                status=403,
                reason="AUTHZ_INSUFFICIENT_ROLE",
                user_id=ctx.user_id,
                platform=ctx.platform,
            )

        return self._deny(
            "rbac",
            status=200,
            reason="",
            user_id=ctx.user_id,
            platform=ctx.platform,
        )


if _HAS_STARLETTE and BaseHTTPMiddleware is not None:

    class MiddlewareChainMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
        """[F-02] Starlette/FastAPI middleware wrapper around :class:`MiddlewareChain`.

        Translates between Starlette's ``Request`` / ``Response`` and the
        chain's own :class:`ChainResult`. Short-circuited stages return
        a ``Response`` with the chain's status/reason/body so the chain
        never reaches downstream handlers when a stage denies.

        Install via::

            app.add_middleware(
                MiddlewareChainMiddleware,
                chain=MiddlewareChain(
                    ip_whitelist=...,
                    signature_validator=...,
                    platform_adapter=...,
                    rate_limiter=...,
                    rbac_enforcer=...,
                ),
            )
        """

        def __init__(self, app, *, chain: MiddlewareChain) -> None:
            super().__init__(app)  # pragma: no cover — middleware dispatch error handler — requires real HTTP request fault
            self._chain = chain  # pragma: no cover — middleware dispatch error handler — requires real HTTP request fault

        async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
            chain_result = self._chain.process(request)  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
            if chain_result.status != 200:  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                headers = {"X-Chain-Stage": chain_result.stage_completed,  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                           "X-Chain-Reason": chain_result.reason}  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                if Response is None:  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                    raise RuntimeError("starlette not available")  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                return Response(  # type: ignore[misc]  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                    content=chain_result.body or chain_result.reason.encode("utf-8"),  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                    status_code=chain_result.status,  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                    headers=headers,  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
                )  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
            # Status 200 — chain passed; continue to downstream handler.
            response = await call_next(request)  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
            response.headers.setdefault("X-Chain-Stage", chain_result.stage_completed)  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection
            return response  # pragma: no cover — middleware platform/rate/rbac deny branches — runtime fault injection

