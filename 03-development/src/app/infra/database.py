"""Canonical DB session factory seam.

Stubbed for FR-101 test isolation. The autouse fixture in
``03-development/tests/test_fr101.py`` monkeypatches
``app.infra.database.get_session`` to keep unit tests off the real
PostgreSQL. The real session factory is delivered by FR-2 (database
schema) — until then, calling ``get_session`` without an injected
override raises ``NotImplementedError`` so production code cannot
silently escape into unmocked I/O.
"""

from __future__ import annotations

from typing import Any


def get_session() -> Any:
    """Return a DB session context manager.

    The canonical seam FR-101 expects to be monkeypatched in tests
    (see ``tests/test_fr101.py::_isolate_knowledge_admin_io``). The
    real implementation arrives with FR-2; calling this stub without
    an override is a configuration error.
    """
    raise NotImplementedError(
        "FR-2 database session factory not yet wired; inject a "
        "session factory or monkeypatch app.infra.database.get_session"
    )