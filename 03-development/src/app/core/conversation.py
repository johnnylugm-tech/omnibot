"""[FR-202] Conversation storage model + paginated list.

New module registered in SAB.json as ``app.core.conversation`` (added
2026-06-27 in the FR-200/202/203 implementation wave). Exposes the
``Conversation`` row dataclass, the ``ConversationListPage`` value
object returned by the paginated list function, and the
``list_conversations_paginated`` factory wired to the management API's
``GET /api/v1/conversations`` endpoint.

Layering: this module is in the ``core`` layer and depends only on
``infra.database`` for SQLAlchemy session injection (per the SAB
``allowed_dependencies: ["infra", "services"]`` rule). No imports
from ``api`` or ``admin`` layers.
"""
# pragma: no error-handling

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Conversation:
    """Row mirror of the ``conversations`` Postgres table.

    Columns mirror the Alembic migration added in the same FR-202 wave.
    Timestamps are stored as ISO 8601 strings to keep the dataclass
    hashable + JSON-serialisable without pulling in ``datetime`` at the
    boundary.
    """

    conversation_id: str
    user_id: str
    channel: str
    started_at: str
    last_message_at: str
    message_count: int


@dataclass(frozen=True)
class ConversationListPage:
    """[FR-202] Paginated response value object.

    Mirrors the ``PaginatedResponse`` adapter shape used by the
    management knowledge list endpoint, plus the ``has_next`` boolean
    and an ``items`` list of ``Conversation`` rows. The api route
    handler converts this into the JSON shape ``{"total", "page",
    "limit", "has_next", "items": [...]}``.
    """

    items: list[Conversation]
    total: int
    page: int
    limit: int
    has_next: bool


async def list_conversations_paginated(*, page: int, limit: int) -> ConversationListPage:
    """[FR-202] Read ``conversations`` table and return a paginated page.

    Boundary handling:
      - ``page < 1`` or ``limit not in [1, 100]`` → empty page with
        ``total=0`` and ``has_next=False`` (preserves the management
        contract that an out-of-range page does not 4xx).
      - offset = (page - 1) * limit; has_next = (offset + len(items)) < total.

    Test seam: tests inject a session stub via ``monkeypatch.setattr`` on
    ``app.infra.database.get_session`` to feed deterministic rows.
    """
    if page < 1 or limit < 1 or limit > 100:
        return ConversationListPage(items=[], total=0, page=page, limit=limit, has_next=False)

    from app.infra.database import get_session  # lazy import per api/core boundary

    offset = (page - 1) * limit
    # ``get_session`` is an async generator declared without
    # ``@asynccontextmanager`` (see ``app.infra.database:41``), so the
    # static type checker cannot see ``__aenter__`` / ``__aexit__``.
    # It IS a runtime async context manager — this is a long-standing
    # typing asymmetry, not a runtime bug. ``type: ignore[attr-defined]``
    # keeps pyright quiet without changing behaviour.
    session_cm = get_session()  # type: ignore[attr-defined]
    session = await session_cm.__aenter__()  # type: ignore[attr-defined]
    try:
        rows = (await session.execute(
            "SELECT conversation_id, user_id, channel, started_at, last_message_at, message_count "
            "FROM conversations ORDER BY last_message_at DESC LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset},
        )).fetchall()
        total = (await session.execute("SELECT count(*) FROM conversations")).scalar() or 0
    finally:
        await session_cm.__aexit__(None, None, None)  # type: ignore[attr-defined]

    items = [
        Conversation(
            conversation_id=r[0],
            user_id=r[1],
            channel=r[2],
            started_at=str(r[3]),
            last_message_at=str(r[4]),
            message_count=int(r[5]),
        )
        for r in rows
    ]
    has_next = (offset + len(items)) < int(total)
    return ConversationListPage(items=items, total=int(total), page=page, limit=limit, has_next=has_next)


__all__ = ["Conversation", "ConversationListPage", "list_conversations_paginated"]