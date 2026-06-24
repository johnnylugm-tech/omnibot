"""[FR-06] Unit tests for app/api/main.py pass-through collaborators.

Cover the non-pragma code paths inside ``main.py`` that aren't exercised
by the integration suite: ``_PassThroughPlatformAdapter.parse`` (every
supported platform name + the unknown branch) and
``_PassThroughRBAC.enforce`` (allow-by-default semantics). These keep
the ``--cov-fail-under=100`` budget honest for the production wiring in
``build_app`` (which carries ``pragma: no cover`` because it instantiates
the entire middleware chain + routers and only runs under uvicorn).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.main import (
    _PassThroughPlatformAdapter,
    _PassThroughRBAC,
)


# ---------------------------------------------------------------------------
# _PassThroughPlatformAdapter.parse — every supported platform + default.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path_segment",
    ["telegram", "line", "messenger", "whatsapp", "web"],
)
def test_pass_through_platform_adapter_parses_supported_platforms(path_segment: str) -> None:
    """parse() must surface each supported platform name from the URL path."""
    adapter = _PassThroughPlatformAdapter()
    request = SimpleNamespace(url=SimpleNamespace(path=f"/api/v1/webhooks/{path_segment}/incoming"))

    result = adapter.parse(request)

    assert result.platform == path_segment
    # user_id is hard-coded to "anonymous" — the pass-through collaborators
    # are test/dev only and don't claim to know who is calling.
    assert result.user_id == "anonymous"


def test_pass_through_platform_adapter_parses_a2a_when_no_web_substring() -> None:
    """``a2a`` is detected when the URL has no earlier substring match.

    The loop iterates ``("telegram", "line", "messenger", "whatsapp",
    "web", "a2a")`` and breaks on the FIRST substring hit. Because
    ``"/web"`` would shadow ``"/a2a"`` whenever the URL contains
    ``webhooks``, the A2A path is mounted at ``/.well-known/...`` per
    SAD.md — so the test below uses a ``.well-known/...`` style path
    that the pass-through adapter can disambiguate.
    """
    adapter = _PassThroughPlatformAdapter()
    request = SimpleNamespace(url=SimpleNamespace(path="/some/a2a/incoming/route"))

    result = adapter.parse(request)

    assert result.platform == "a2a"


def test_pass_through_platform_adapter_unknown_path_returns_unknown() -> None:
    """parse() must fall back to platform='unknown' when no known name matches."""
    adapter = _PassThroughPlatformAdapter()
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/some/other/route"))

    result = adapter.parse(request)

    assert result.platform == "unknown"
    assert result.user_id == "anonymous"


def test_pass_through_platform_adapter_first_match_wins() -> None:
    """When multiple substrings could match, the loop must break on the first hit."""
    adapter = _PassThroughPlatformAdapter()
    # "/telegram" appears before "/line" — declaration order in main.py
    # is telegram, line, messenger, whatsapp, web, a2a, so telegram wins.
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/telegram/line/whatsapp"))

    result = adapter.parse(request)

    assert result.platform == "telegram"


# ---------------------------------------------------------------------------
# _PassThroughRBAC.enforce — allow-by-default semantics.
# ---------------------------------------------------------------------------


def test_pass_through_rbac_enforce_returns_allowed_for_any_role() -> None:
    """Pass-through RBAC must permit every (user, resource, action) triple."""
    enforcer = _PassThroughRBAC()

    verdict = enforcer.enforce(user_id="any-user", resource="system", action="write")

    assert verdict.allowed is True
    assert verdict.user_id == "any-user"
    assert verdict.resource == "system"
    assert verdict.action == "write"


def test_pass_through_rbac_enforce_does_not_constrain_arguments() -> None:
    """The pass-through enforcer must NOT inspect / reject arguments.

    Real production deployments inject an RBAC adapter; the default
    here is intentionally permissive so unit tests can mount the app
    without seeding grants. This test pins that contract.
    """
    enforcer = _PassThroughRBAC()

    for role in ("", "system", "customer", "anonymous", "ghost"):
        verdict = enforcer.enforce(user_id=role, resource="anything", action="delete")

        assert verdict.allowed is True
        assert verdict.user_id == role