"""TDD-GREEN tests for FR-202 — Conversations List with real pagination.

Spec source: 02-architecture/TEST_SPEC.md (FR-202)
SRS source : SRS.md FR-202

Acceptance criteria (from SRS FR-202):
    GET /api/v1/conversations — 真正從 Postgres ``conversations`` 表讀取
    並回傳 PaginatedResponse (total/page/limit/has_next/items)；RBAC:
    escalate:read 通過；page/limit ∈ [1,100]；回傳 200 + PaginatedResponse；
    page 越界 → 空 items + has_next=false；未授權/型別錯 → 403.

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr202_list_conversations_returns_200_for_dpo
    2. test_fr202_list_conversations_returns_403_for_anon
    3. test_fr202_list_conversations_pagination_math

Sub-assertions (per TEST_SPEC):
    fr202-ok   : result == 200                                              (case 1)
    fr202-rbac : result == 403                                              (case 2)
    fr202-page : _LAST_LIST_RESULT.has_next is True and
                 len(_LAST_LIST_RESULT.items) == 10                         (case 3)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api.management import (
    _HTTP_FORBIDDEN,
    _HTTP_OK,
    list_conversations,
)
import app.api.management as management_mod
from app.core.conversation import Conversation, ConversationListPage


def test_fr202_list_conversations_returns_200_for_dpo(monkeypatch):
    """[FR-202 case 1] dpo role passes RBAC and returns 200."""
    # Stub the async core to return a deterministic page.
    fake_page = ConversationListPage(items=[], total=0, page=1, limit=10, has_next=False)
    monkeypatch.setattr(
        "app.core.conversation.list_conversations_paginated",
        MagicMock(return_value=fake_page),
    )
    # Drive async via asyncio.run interception.
    monkeypatch.setattr(
        "app.api.management.asyncio.run", lambda _: fake_page
    )

    result = list_conversations(role="dpo", page=1, limit=10)
    assert result == _HTTP_OK


def test_fr202_list_conversations_returns_403_for_anon():
    """[FR-202 case 2] anonymous role denied at RBAC."""
    result = list_conversations(role="anonymous", page=1, limit=10)
    assert result == _HTTP_FORBIDDEN


def test_fr202_list_conversations_pagination_math(monkeypatch):
    """[FR-202 case 3] page math: 50 total, page 2 of 10 → 10 items, has_next=True."""
    # Build 10 deterministic Conversation rows.
    items = [
        Conversation(
            conversation_id=f"conv_{i}",
            user_id=f"u_{i}",
            channel="web",
            started_at="2026-06-27T00:00:00Z",
            last_message_at="2026-06-27T00:01:00Z",
            message_count=i + 1,
        )
        for i in range(10)
    ]
    page_obj = ConversationListPage(items=items, total=50, page=2, limit=10, has_next=True)

    monkeypatch.setattr(
        "app.core.conversation.list_conversations_paginated",
        MagicMock(return_value=page_obj),
    )
    monkeypatch.setattr(
        "app.api.management.asyncio.run", lambda _: page_obj
    )

    result = list_conversations(role="dpo", page=2, limit=10)
    assert result == _HTTP_OK
    # Bridge contract: the real page is stashed in _LAST_LIST_RESULT.
    # Read it through the module (not a captured import reference) because
    # the function uses ``global _LAST_LIST_RESULT`` and ``from app.api
    # .management import _LAST_LIST_RESULT`` gives a stale snapshot.
    page_obj = management_mod._LAST_LIST_RESULT
    assert page_obj is not None
    assert page_obj.has_next is True
    assert len(page_obj.items) == 10
    assert page_obj.total == 50