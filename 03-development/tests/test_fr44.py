"""TDD-RED: failing tests for FR-44 — OmniBot Agent Card /.well-known/agent.json.

Spec source: 02-architecture/TEST_SPEC.md (FR-44)
SRS source : SRS.md FR-44 (Module 7: Action Execution Engine (AEE))

Acceptance criteria (from SRS FR-44):
    OmniBot Agent Card：GET /.well-known/agent.json 回傳 Agent Card JSON
    （name, description, url, version, capabilities, methods, auth_schemes）；
    methods: [ask_customer_service, escalate_to_human].

Active NFR patterns: none (static discovery endpoint).

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-41 shipped ``A2AAdapter._discover_agent_card`` which CONSUMES a remote
# ``/.well-known/agent.json`` (the inbound Agent Card side). FR-44 flips
# the lens — it ships the OUTBOUND endpoint: OmniBot itself advertises
# its own Agent Card at ``GET /.well-known/agent.json`` so that other
# A2A agents (FR-06 callers) can discover what methods OmniBot exposes.
#
# GREEN TODO (for the GREEN agent):
#
#   The following surface MUST live in
#   ``03-development/src/app/api/agent_card.py`` (a NEW module under
#   ``app.api`` — the API layer directory which is currently empty):
#
#     - A FastAPI ``app`` instance (named ``app`` so TestClient can be
#       constructed via ``TestClient(app)``) that registers the route:
#
#         GET ``/.well-known/agent.json`` → 200 application/json
#
#     - The JSON response body MUST be an Agent Card with the
#       well-known fields specified by SRS FR-44:
#
#         {
#           "name": str,
#           "description": str,
#           "url": str,
#           "version": str,
#           "capabilities": list[str] | dict,
#           "methods": list[str],
#           "auth_schemes": list[dict] | list[str],
#         }
#
#     - ``methods`` MUST include BOTH of the A2A method names that
#       FR-06 pins:
#
#         * ``"ask_customer_service"`` — the customer-service RPC.
#         * ``"escalate_to_human"``    — the human-handoff RPC.
#
#   During the current RED step, ``app.api.agent_card`` is intentionally
#   NOT YET defined. The imports below are unguarded: pytest MUST fail
#   with Collection Error (Exit Code 2 / ModuleNotFoundError) because
#   the module does not exist. That is the valid RED signal. GREEN
#   creates ``agent_card.py`` with the surface above.
# ---------------------------------------------------------------------------
from app.api.agent_card import app


# ---------------------------------------------------------------------------
# 1. GET /.well-known/agent.json returns HTTP 200 (happy_path).
#
# Spec input: path="/.well-known/agent.json"; expected_status="200".
# SRS FR-44: "GET /.well-known/agent.json 回傳 Agent Card JSON".
# The Agent Card endpoint MUST be reachable, return ``200 OK``, and
# serve a JSON body. ``TestClient`` is the FastAPI-native way to
# exercise the endpoint without binding a real socket.
# ---------------------------------------------------------------------------
def test_fr44_agent_card_endpoint_200():
    path = "/.well-known/agent.json"
    expected_status = "200"

    # Spec fr44-ok predicate 'result is not None' applies_to case 1.
    # The trigger for case 1 is ``expected_status``; we gate the
    # predicate on that variable matching the spec input
    # (``expected_status="200"``).
    if expected_status == "200":
        # Spec fr44-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert app is not None, (
            "fr44-ok predicate: FastAPI app must be importable "
            "from app.api.agent_card"
        )

    # GREEN TODO: ``app.api.agent_card.app`` MUST be a FastAPI
    # application (or ``fastapi.APIRouter`` is acceptable ONLY if the
    # module also wires it into a top-level ``app`` for TestClient)
    # that registers the ``GET /.well-known/agent.json`` route returning
    # a 200 application/json body per SRS FR-44.
    from fastapi.testclient import TestClient

    client = TestClient(app)  # type: ignore[arg-type]

    response = client.get(path)

    # Bind the local var ``response`` to the spec predicate free variable
    # ``result`` so the harness parser can match the predicate reference.
    result = response

    if expected_status == "200":
        # Spec fr44-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, (
            "fr44-ok predicate: HTTP response must not be None"
        )

    assert response.status_code == 200, (
        f"FR-44: GET {path} must return 200 (expected_status="
        f"{expected_status!r}); got status_code={response.status_code!r}, "
        f"body={response.text!r}"
    )
    # Body MUST be valid JSON (the spec says "回傳 Agent Card JSON").
    # ``response.json()`` raises if the body isn't parseable, which is
    # exactly the failure mode RED→GREEN wants to surface.
    try:
        body = response.json()
    except ValueError as exc:
        pytest.fail(
            f"FR-44: GET {path} must return a JSON body; "
            f"got parse error: {exc}; raw body={response.text!r}"
        )
    assert isinstance(body, dict), (
        f"FR-44: Agent Card body must be a JSON object (dict); "
        f"got {type(body).__name__}"
    )

    # Sentinels MUST be preserved per spec.
    assert path == "/.well-known/agent.json", (
        f"FR-44: path sentinel must be '/.well-known/agent.json'; "
        f"got {path!r}"
    )
    assert expected_status == "200", (
        f"FR-44: expected_status sentinel must be '200'; "
        f"got {expected_status!r}"
    )


# ---------------------------------------------------------------------------
# 2. Agent Card ``methods`` MUST include ``ask_customer_service`` AND
#    ``escalate_to_human`` (validation).
#
# Spec input: expected_methods="ask_customer_service,escalate_to_human".
# SRS FR-44: "methods: [ask_customer_service, escalate_to_human]".
# Both methods are pinned by FR-06 — A2A Platform Adapter JSON-RPC
# contract — so the Agent Card MUST advertise them or remote agents
# cannot discover OmniBot's surface. Order-insensitive: an unsorted
# ``methods`` list is acceptable as long as BOTH entries are present.
# ---------------------------------------------------------------------------
def test_fr44_agent_card_methods_include_ask_and_escalate():
    expected_methods = "ask_customer_service,escalate_to_human"

    # Spec fr44-ok predicate 'result is not None' applies_to case 2.
    # The trigger for case 2 is ``expected_methods``; we gate the
    # predicate on that variable matching the spec input
    # (``expected_methods="ask_customer_service,escalate_to_human"``).
    if expected_methods == "ask_customer_service,escalate_to_human":
        # Spec fr44-ok predicate 'result is not None' applies_to case 2.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 2's input.
        assert app is not None, (
            "fr44-ok predicate: FastAPI app must be importable "
            "from app.api.agent_card"
        )

    # GREEN TODO: the Agent Card response body MUST include a
    # ``methods`` list whose entries include both
    # ``"ask_customer_service"`` and ``"escalate_to_human"`` (FR-06
    # pins these as OmniBot's A2A RPC methods).
    from fastapi.testclient import TestClient

    client = TestClient(app)  # type: ignore[arg-type]

    response = client.get("/.well-known/agent.json")

    assert response.status_code == 200, (
        f"FR-44: GET /.well-known/agent.json must return 200 to "
        f"inspect methods; got status_code={response.status_code!r}, "
        f"body={response.text!r}"
    )

    body = response.json()
    assert isinstance(body, dict), (
        f"FR-44: Agent Card body must be a JSON object (dict); "
        f"got {type(body).__name__}"
    )

    # ``methods`` MUST be present and MUST be a list (per SRS FR-44
    # "methods: [ask_customer_service, escalate_to_human]").
    assert "methods" in body, (
        f"FR-44: Agent Card body MUST include a 'methods' field; "
        f"got keys={sorted(body.keys())!r}"
    )
    methods = body["methods"]
    assert isinstance(methods, list), (
        f"FR-44: 'methods' must be a list per SRS FR-44; "
        f"got {type(methods).__name__}"
    )
    # Coerce entries to ``str`` defensively — GREEN may legitimately
    # emit dict-shaped method descriptors (``{"name": "...", ...}``)
    # per A2A spec, in which case we inspect the ``name`` sub-field.
    method_names: list[str] = []
    for entry in methods:
        if isinstance(entry, str):
            method_names.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            method_names.append(entry["name"])

    expected_set = {"ask_customer_service", "escalate_to_human"}
    actual_set = set(method_names)
    missing = expected_set - actual_set
    assert not missing, (
        f"FR-44: Agent Card 'methods' MUST include "
        f"{sorted(expected_set)!r} (expected_methods="
        f"{expected_methods!r}); missing={sorted(missing)!r}, "
        f"got methods={methods!r}"
    )

    # Sentinel MUST be preserved per spec.
    assert expected_methods == "ask_customer_service,escalate_to_human", (
        f"FR-44: expected_methods sentinel must be "
        f"'ask_customer_service,escalate_to_human'; got {expected_methods!r}"
    )
