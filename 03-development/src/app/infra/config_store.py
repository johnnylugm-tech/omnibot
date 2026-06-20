"""[FR-102] ``app.infra.config_store`` — platform_configs reader/writer seam.

SRS source : SRS.md FR-102 (Module 25: 管理 WebUI)
             "沙盒調整不寫入 platform_configs" — the slider is a
             sandbox operation; the persisted platform_configs row
             stays at the canonical default (``rag_cosine_threshold =
             0.75``) until a real admin persists it via the platform
             config UI.
SAD source  : 02-architecture/SAD.md §2.4 (webui.py module)

Public surface (pinned by ``tests/test_fr102.py``):

    - ``get_config_store()`` returns a config store object with at
      least:
          ``get(key, default=None) -> Any``  (read)
          ``set(key, value) -> value``        (write — platform
                                                persistence path)
          ``as_dict() -> dict``                (snapshot)

    The default implementation is an in-process dict wrapper seeded
    with the FR-102 canonical defaults. The RAGDebugger's
    ``set_slider_threshold`` MUST NOT call ``set()`` (per
    "沙盒調整不寫入 platform_configs"); it only mutates the debugger's
    own in-memory sandbox state.

Citations:
    test_fr102.py L84-110 — autouse fixture monkeypatches
        ``app.infra.config_store.get_config_store`` to return an
        ``_InMemoryConfigStore`` with ``rag_cosine_threshold=0.75``.
        GREEN exposes the seam (this module) so the fixture's
        ``monkeypatch.setattr`` resolves cleanly.
    test_fr102.py L417-487 — slider adjustment MUST NOT persist via
        ``set()``; the persisted row stays at
        ``RAG_DEFAULT_THRESHOLD`` (0.75).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# FR-102 canonical defaults — the platform_configs seed values.
# ---------------------------------------------------------------------------

#: Canonical default for the RAG cosine threshold. SRS FR-102: "相似度
#: 閾值滑桿 (預設 0.75)".
DEFAULT_RAG_COSINE_THRESHOLD: float = 0.75


class _DictConfigStore:
    """In-process dict-backed config store.

    The production wiring would back this with a PostgreSQL read of
    ``platform_configs`` (the canonical store); for the unit-test seam
    we keep it in-process so the FR-102 fixture's
    ``monkeypatch.setattr`` can swap the implementation without
    needing a live database.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})
        # Seed the FR-102 canonical default so a fresh
        # ``get_config_store()`` always reports the spec's 0.75
        # threshold even when no production wiring has populated it.
        self._data.setdefault("rag_cosine_threshold", DEFAULT_RAG_COSINE_THRESHOLD)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> Any:
        self._data[key] = value
        return value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


# Module-level singleton — the canonical seam the RAGDebugger reads.
_default_store: _DictConfigStore | None = None


def get_config_store() -> _DictConfigStore:
    """Return the process-wide config store instance.

    This is the read-side seam GREEN exposes so the RAGDebugger
    (and any other consumer) can read the persisted
    ``rag_cosine_threshold`` without coupling to PostgreSQL. Tests
    monkeypatch this function (e.g. ``test_fr102.py``'s autouse
    fixture) to inject an in-memory dict so the slider-adjustment
    "sandbox-only" guarantee can be observed in isolation.
    """
    global _default_store
    if _default_store is None:
        _default_store = _DictConfigStore()
    return _default_store
