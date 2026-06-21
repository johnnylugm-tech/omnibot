"""TDD-RED: failing tests for FR-104 — Agent Portal
(轉接收件匣 + WebSocket + 智慧接管面板).

Spec source: 02-architecture/TEST_SPEC.md (FR-104)
SRS source : SRS.md FR-104 (Module 25: Agent Portal UI)
            "Agent Portal：轉接收件匣（Unassigned/My Chats/Resolved）+
             WebSocket 即時連動；優先級色彩（urgent=紅/high=橙/normal=藍）；
             智慧接管面板（情緒歷史軌跡、對話時間軸、DST Slot 側邊欄、
             Grounding 知識背景高亮）；1 秒掌握背景"

Acceptance criteria (from SRS FR-104):
    - 佇列 WebSocket 即時更新
    - 優先級色彩正確
    - 接管面板數據完整

TEST_SPEC cases (function names MUST match exactly):
    1. test_fr104_inbox_ws_realtime_update
         Inputs: event="escalation.new"; expected_update_latency="<1s"
         Type  : happy_path
    2. test_fr104_priority_colors_correct
         Inputs: urgent_color="red"; high_color="orange"; normal_color="blue"
         Type  : validation
    3. test_fr104_takeover_shows_emotion_dst_context
         Inputs: escalation_id="esc-001"; expected_panels="emotion,dst_slots,grounding"
         Type  : happy_path

Sub-assertion (per TEST_SPEC):
    fr104-ok: result is not None   (applies_to case 1)
"""

from __future__ import annotations

import time
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Test isolation — AgentPortal receives WebSocket events via the
# ``/ws/agent`` channel and fetches DST/emotion/grounding context from
# backend services. The autouse fixture stubs these seams so tests fail
# because the portal feature logic is absent, not because of missing
# WebSocket / DB / emotion-analyzer infrastructure.
#
# GREEN must expose an injectable ``_on_ws_event(self, event: str,
# payload: dict)`` method on AgentPortal that receives escalation.new
# events; and a ``_fetch_takeover_context(self, escalation_id:
# str) -> dict`` seam for DST/emotion/grounding data.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_portal_io(monkeypatch):
    """Stub WebSocket and context-fetching seams to avoid real I/O."""

    def _stub_on_ws_event(self, event: str, payload: dict) -> None:
        """Record the event in the inbox rather than requiring a live WS."""
        section = payload.get("section", "Unassigned")
        if not hasattr(self, "_inbox_events"):
            self._inbox_events: list[dict[str, Any]] = []  # type: ignore[misc]
        self._inbox_events.append(
            {"event": event, "payload": dict(payload), "section": section}
        )

    def _stub_fetch_takeover_context(self, escalation_id: str) -> dict:
        """Return stub context data for takeover panel rendering."""
        return {
            "escalation_id": escalation_id,
            "emotion": {
                "current": "angry",
                "intensity": 0.85,
                "history": ["angry", "negative", "negative"],
            },
            "dst_slots": {
                "intent": "return_request",
                "order_id": "ORD-001",
                "reason": "damaged",
            },
            "grounding": {
                "source_texts": ["退貨政策: 30天內可退貨"],
                "cosine_score": 0.88,
                "grounded": True,
            },
            "conversation": [
                {"role": "user", "text": "我要退貨，商品有問題"},
                {"role": "bot", "text": "了解，請問訂單編號是？"},
            ],
        }

    monkeypatch.setattr(
        "app.admin.portal.AgentPortal._on_ws_event",
        _stub_on_ws_event,
        raising=False,
    )
    monkeypatch.setattr(
        "app.admin.portal.AgentPortal._fetch_takeover_context",
        _stub_fetch_takeover_context,
        raising=False,
    )
    yield


# ---------------------------------------------------------------------------
# Source under test — ``AgentPortal`` and its companion constants are
# intentionally NOT YET exported by ``app.admin.portal``. These imports
# are unguarded: pytest MUST fail with Collection Error (Exit Code 2 /
# ImportError). That is the valid RED signal.
#
# GREEN must add to ``app/admin/portal.py``:
#
#   Constants:
#       PRIORITY_URGENT_COLOR  = "red"       # SRS: urgent=紅
#       PRIORITY_HIGH_COLOR    = "orange"    # SRS: high=橙
#       PRIORITY_NORMAL_COLOR  = "blue"      # SRS: normal=藍
#       INBOX_SECTIONS         = ("Unassigned", "My Chats", "Resolved")
#       TAKEOVER_PANELS        = ("emotion", "dst_slots", "grounding")
#
#   AgentPortal:
#       __init__(self) — creates empty inbox sections.
#       _on_ws_event(self, event: str, payload: dict) -> None
#           Injectable seam (patched by autouse fixture). Receives
#           WebSocket events (escalation.new, etc.) and updates the
#           inbox. GREEN wires the real WS listener through this seam.
#       on_escalation_new(self, payload: dict) -> None
#           Called by the WS handler when an escalation.new event
#           arrives. MUST insert the escalation into the correct inbox
#           section (Unassigned by default).
#       get_inbox(self, section: str) -> list[dict]
#           Return the list of escalation payloads in the named section.
#       get_takeover_context(self, escalation_id: str) -> dict
#           Return the full takeover context for the given escalation:
#           emotion, dst_slots, grounding, and conversation timeline.
#           Delegates to _fetch_takeover_context (injectable seam).
#       _fetch_takeover_context(self, escalation_id: str) -> dict
#           Injectable seam for backend data queries.
# ---------------------------------------------------------------------------
from app.admin.portal import (  # noqa: E402
    INBOX_SECTIONS,
    PRIORITY_HIGH_COLOR,
    PRIORITY_NORMAL_COLOR,
    PRIORITY_URGENT_COLOR,
    TAKEOVER_PANELS,
    AgentPortal,
)


# ============================================================================
# 1. test_fr104_inbox_ws_realtime_update
# ============================================================================
# Spec input : event="escalation.new"; expected_update_latency="<1s"
# SRS FR-104 : "佇列 WebSocket 即時更新"; "1 秒掌握背景"
# Type       : happy_path (Q1 derivation)
#
# Behaviour  : When an ``escalation.new`` WebSocket event arrives at the
#              Agent Portal, the inbox MUST be updated within 1 second.
#              The new escalation MUST appear in the "Unassigned" section.
#              A regression that delays the update past 1 second, misses
#              the event entirely, or places the escalation in the wrong
#              section would break the agent's ability to respond
#              promptly.
# ---------------------------------------------------------------------------
def test_fr104_inbox_ws_realtime_update():
    # Spec input literals.
    event = "escalation.new"          # spec: event="escalation.new"
    expected_update_latency = "<1s"   # spec: expected_update_latency="<1s"

    if event == "escalation.new":
        # GREEN TODO: AgentPortal must have
        #   on_escalation_new(self, payload: dict) -> None
        #   which inserts the escalation into the "Unassigned" section
        #   of the inbox within 1 second.
        portal = AgentPortal()

        # Anchor: AgentPortal must expose ``on_escalation_new``.
        assert hasattr(portal, "on_escalation_new") and callable(
            portal.on_escalation_new
        ), (
            "FR-104 AgentPortal must expose "
            "``on_escalation_new(payload: dict) -> None`` "
            "so the WS handler can update the inbox."
        )

        # Anchor: INBOX_SECTIONS must include the three SRS-mandated sections.
        assert "Unassigned" in INBOX_SECTIONS, (
            f"FR-104 INBOX_SECTIONS must include 'Unassigned'; "
            f"got {INBOX_SECTIONS!r}. SRS: 'Unassigned/My Chats/Resolved'."
        )
        assert "My Chats" in INBOX_SECTIONS, (
            f"FR-104 INBOX_SECTIONS must include 'My Chats'; "
            f"got {INBOX_SECTIONS!r}."
        )
        assert "Resolved" in INBOX_SECTIONS, (
            f"FR-104 INBOX_SECTIONS must include 'Resolved'; "
            f"got {INBOX_SECTIONS!r}."
        )

        payload = {
            "escalation_id": "esc-001",
            "conversation_id": "conv-001",
            "priority": 2,  # urgent
            "reason": "emotion_trigger",
            "platform": "web",
            "queued_at": "2026-06-21T10:00:00Z",
            "preview": {
                "user_message": "我真的很生氣，這個問題拖了三個月！",
                "emotion": "angry",
            },
        }

        # Measure the update latency.
        t0 = time.monotonic()
        result = portal.on_escalation_new(payload)
        elapsed_s = time.monotonic() - t0

        # fr104-ok predicate: result is not None (applies_to case 1).
        assert result is not None, (
            "fr104-ok: on_escalation_new() must not return None; "
            "SRS FR-104 '佇列 WebSocket 即時更新'."
        )

        # Core assertion: the inbox MUST be updated within 1 second.
        # The SRS mandates "1 秒掌握背景" — the agent must see the new
        # escalation within 1 second of the WS event arriving.
        max_latency_s = 1.0
        assert elapsed_s < max_latency_s, (
            f"FR-104: inbox update latency must be < 1s per SRS "
            f"'1 秒掌握背景'; got {elapsed_s:.3f}s. "
            f"expected_update_latency='{expected_update_latency}'."
        )

        # Anchor: AgentPortal must expose ``get_inbox`` to query sections.
        assert hasattr(portal, "get_inbox") and callable(portal.get_inbox), (
            "FR-104 AgentPortal must expose "
            "``get_inbox(section: str) -> list[dict]`` "
            "so the UI can render inbox sections."
        )

        # Verify the escalation landed in the "Unassigned" section (the
        # default for newly arrived escalations).
        unassigned = portal.get_inbox("Unassigned")
        assert isinstance(unassigned, list), (
            f"FR-104 get_inbox('Unassigned') must return a list; "
            f"got {type(unassigned).__name__}."
        )

        escalation_ids = [
            e.get("escalation_id") for e in unassigned if isinstance(e, dict)
        ]
        assert payload["escalation_id"] in escalation_ids, (
            f"FR-104: new escalation {payload['escalation_id']!r} must "
            f"appear in 'Unassigned' inbox section after "
            f"on_escalation_new(); got {escalation_ids!r}. "
            f"SRS FR-104: '轉接收件匣（Unassigned/My Chats/Resolved）'."
        )

    # Sentinels MUST be preserved per spec.
    assert event == "escalation.new", (
        f"FR-104: event sentinel must be 'escalation.new'; got {event!r}"
    )
    assert expected_update_latency == "<1s", (
        f"FR-104: expected_update_latency sentinel must be '<1s'; "
        f"got {expected_update_latency!r}"
    )


# ============================================================================
# 2. test_fr104_priority_colors_correct
# ============================================================================
# Spec input : urgent_color="red"; high_color="orange"; normal_color="blue"
# SRS FR-104 : "優先級色彩（urgent=紅/high=橙/normal=藍）"
# Type       : validation (Q2 derivation)
#
# Behaviour  : The priority colour constants MUST match the SRS contract
#              exactly. A regression that uses "crimson" for urgent,
#              "amber" for high, or "skyblue" for normal would break the
#              visual contract the operations team relies on; a regression
#              that adds extra priority levels without updating the
#              constants would cause dashboard rendering errors.
# ---------------------------------------------------------------------------
def test_fr104_priority_colors_correct():
    # Spec input literals.
    urgent_color = "red"      # spec: urgent_color="red"
    high_color = "orange"     # spec: high_color="orange"
    normal_color = "blue"     # spec: normal_color="blue"

    # Anchor: PRIORITY_URGENT_COLOR MUST be "red" (SRS: urgent=紅).
    assert urgent_color == PRIORITY_URGENT_COLOR, (
        f"FR-104 PRIORITY_URGENT_COLOR must be '{urgent_color}' "
        f"(SRS: urgent=紅); got {PRIORITY_URGENT_COLOR!r}."
    )

    # Anchor: PRIORITY_HIGH_COLOR MUST be "orange" (SRS: high=橙).
    assert high_color == PRIORITY_HIGH_COLOR, (
        f"FR-104 PRIORITY_HIGH_COLOR must be '{high_color}' "
        f"(SRS: high=橙); got {PRIORITY_HIGH_COLOR!r}."
    )

    # Anchor: PRIORITY_NORMAL_COLOR MUST be "blue" (SRS: normal=藍).
    assert normal_color == PRIORITY_NORMAL_COLOR, (
        f"FR-104 PRIORITY_NORMAL_COLOR must be '{normal_color}' "
        f"(SRS: normal=藍); got {PRIORITY_NORMAL_COLOR!r}."
    )

    # Defence-in-depth: the three colours MUST be distinct so the agent
    # can visually distinguish priority levels at a glance.
    colors = {PRIORITY_URGENT_COLOR, PRIORITY_HIGH_COLOR, PRIORITY_NORMAL_COLOR}
    assert len(colors) == 3, (
        f"FR-104: priority colours must be three distinct values; "
        f"got {colors!r}. SRS: urgent=紅/high=橙/normal=藍."
    )

    # GREEN TODO: AgentPortal must expose
    #   get_priority_color(self, priority: int) -> str
    #   that maps priority 2 → PRIORITY_URGENT_COLOR,
    #   priority 1 → PRIORITY_HIGH_COLOR,
    #   priority 0 → PRIORITY_NORMAL_COLOR.
    portal = AgentPortal()
    assert hasattr(portal, "get_priority_color") and callable(
        portal.get_priority_color
    ), (
        "FR-104 AgentPortal must expose "
        "``get_priority_color(priority: int) -> str`` "
        "so the inbox can colour-code escalation rows."
    )

    # Priority 2 (urgent) → red.
    assert portal.get_priority_color(2) == PRIORITY_URGENT_COLOR, (
        f"FR-104: priority=2 (urgent) must map to "
        f"{PRIORITY_URGENT_COLOR!r}; got "
        f"{portal.get_priority_color(2)!r}."
    )

    # Priority 1 (high) → orange.
    assert portal.get_priority_color(1) == PRIORITY_HIGH_COLOR, (
        f"FR-104: priority=1 (high) must map to "
        f"{PRIORITY_HIGH_COLOR!r}; got "
        f"{portal.get_priority_color(1)!r}."
    )

    # Priority 0 (normal) → blue.
    assert portal.get_priority_color(0) == PRIORITY_NORMAL_COLOR, (
        f"FR-104: priority=0 (normal) must map to "
        f"{PRIORITY_NORMAL_COLOR!r}; got "
        f"{portal.get_priority_color(0)!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert urgent_color == "red", (
        f"FR-104: urgent_color sentinel must be 'red'; got {urgent_color!r}"
    )
    assert high_color == "orange", (
        f"FR-104: high_color sentinel must be 'orange'; got {high_color!r}"
    )
    assert normal_color == "blue", (
        f"FR-104: normal_color sentinel must be 'blue'; got {normal_color!r}"
    )


# ============================================================================
# 3. test_fr104_takeover_shows_emotion_dst_context
# ============================================================================
# Spec input : escalation_id="esc-001"; expected_panels="emotion,dst_slots,grounding"
# SRS FR-104 : "智慧接管面板（情緒歷史軌跡、對話時間軸、DST Slot 側邊欄、
#              Grounding 知識背景高亮）"
# Type       : happy_path (Q1 derivation)
#
# Behaviour  : When an agent opens the takeover panel for an escalation,
#              the portal MUST return context data for all three SRS-
#              mandated panels: emotion (情緒歷史軌跡), dst_slots
#              (DST Slot 側邊欄), and grounding (Grounding 知識背景高亮).
#              The conversation timeline (對話時間軸) MUST also be
#              present. A regression that omits any panel, returns empty
#              data, or conflates the panels would prevent the agent
#              from achieving the SRS "1 秒掌握背景" goal.
# ---------------------------------------------------------------------------
def test_fr104_takeover_shows_emotion_dst_context():
    # Spec input literals.
    escalation_id = "esc-001"                                # spec
    expected_panels = "emotion,dst_slots,grounding"           # spec

    # Parse expected panels from the spec input.
    required_panels = [
        p.strip() for p in expected_panels.split(",") if p.strip()
    ]
    assert required_panels == ["emotion", "dst_slots", "grounding"], (
        f"Test setup invariant: expected_panels must be "
        f"['emotion', 'dst_slots', 'grounding']; got {required_panels!r}."
    )

    # Anchor: TAKEOVER_PANELS MUST include all three SRS-mandated panels.
    for panel in required_panels:
        assert panel in TAKEOVER_PANELS, (
            f"FR-104 TAKEOVER_PANELS must include '{panel}'; "
            f"got {TAKEOVER_PANELS!r}. "
            f"SRS FR-104: '情緒歷史軌跡、DST Slot 側邊欄、Grounding 知識背景高亮'."
        )

    # Anchor: TAKEOVER_PANELS MUST also include "conversation" for the
    # 對話時間軸 (conversation timeline) mandated by SRS FR-104.
    assert "conversation" in TAKEOVER_PANELS, (
        f"FR-104 TAKEOVER_PANELS must include 'conversation' for the "
        f"對話時間軸 (SRS FR-104 '對話時間軸'); got {TAKEOVER_PANELS!r}."
    )

    if escalation_id == "esc-001":
        # GREEN TODO: AgentPortal must have
        #   get_takeover_context(self, escalation_id: str) -> dict
        #   that returns a dict with these keys:
        #       emotion, dst_slots, grounding, conversation, escalation_id
        #   The autouse fixture patches _fetch_takeover_context as the
        #   injectable data seam.
        portal = AgentPortal()

        # Anchor: portal must expose get_takeover_context.
        assert hasattr(portal, "get_takeover_context") and callable(
            portal.get_takeover_context
        ), (
            "FR-104 AgentPortal must expose "
            "``get_takeover_context(escalation_id: str) -> dict`` "
            "so the takeover panel can render context data."
        )

        result = portal.get_takeover_context(escalation_id)

        # fr104-ok predicate: result is not None.
        assert result is not None, (
            f"fr104-ok: get_takeover_context('{escalation_id}') must "
            f"return a non-None result. SRS FR-104: '接管面板數據完整'."
        )

        assert isinstance(result, dict), (
            f"FR-104: get_takeover_context must return a dict so the "
            f"takeover panel can index panels by key; got "
            f"{type(result).__name__}."
        )

        # Core assertion: every required panel MUST be present in the
        # takeover context. The SRS mandates four data dimensions:
        #   1. emotion  — 情緒歷史軌跡
        #   2. dst_slots — DST Slot 側邊欄
        #   3. grounding — Grounding 知識背景高亮
        #   4. conversation — 對話時間軸
        missing_panels = [
            p for p in [*required_panels, "conversation"] if p not in result
        ]
        assert not missing_panels, (
            f"FR-104: get_takeover_context result is missing panels "
            f"{missing_panels!r}; expected at least "
            f"{[*required_panels, 'conversation']!r}. "
            f"SRS FR-104: '情緒歷史軌跡、對話時間軸、DST Slot 側邊欄、"
            f"Grounding 知識背景高亮'. Got keys={sorted(result.keys())!r}."
        )

        # Panel data integrity — each panel value MUST be non-None and
        # non-empty so the UI has something to render.
        for panel in [*required_panels, "conversation"]:
            panel_data = result.get(panel)
            assert panel_data is not None, (
                f"FR-104: takeover panel '{panel}' data must not be None; "
                f"SRS FR-104 '接管面板數據完整'. A regression that "
                f"returns a key with None value would render an empty panel."
            )
            # Panel data must be a dict for structured rendering.
            if panel != "conversation":
                assert isinstance(panel_data, dict), (
                    f"FR-104: takeover panel '{panel}' must be a dict "
                    f"for structured rendering; got "
                    f"{type(panel_data).__name__}."
                )
                # Defence-in-depth: each panel dict must have at least
                # one key so the UI doesn't render an empty card.
                assert len(panel_data) > 0, (
                    f"FR-104: takeover panel '{panel}' must contain "
                    f"at least one data field; got empty dict. "
                    f"SRS FR-104: '接管面板數據完整'."
                )
            else:
                # Conversation is a list of {role, text} messages.
                assert isinstance(panel_data, list), (
                    f"FR-104: takeover panel 'conversation' must be a "
                    f"list of timeline messages; got "
                    f"{type(panel_data).__name__}."
                )
                assert len(panel_data) > 0, (
                    "FR-104: takeover 'conversation' timeline must "
                    "contain at least one message; got empty list."
                )

        # The result MUST echo the escalation_id so the UI can align
        # the takeover panel with the inbox row.
        assert result.get("escalation_id") == escalation_id, (
            f"FR-104: get_takeover_context result must echo "
            f"escalation_id={escalation_id!r} (spec sentinel); got "
            f"{result.get('escalation_id')!r}."
        )

    # Sentinels MUST be preserved per spec.
    assert escalation_id == "esc-001", (
        f"FR-104: escalation_id sentinel must be 'esc-001'; "
        f"got {escalation_id!r}"
    )
    assert expected_panels == "emotion,dst_slots,grounding", (
        f"FR-104: expected_panels sentinel must be "
        f"'emotion,dst_slots,grounding'; got {expected_panels!r}"
    )
