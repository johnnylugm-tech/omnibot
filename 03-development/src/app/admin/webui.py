"""[FR-101] KnowledgeAdminAPI + EmbeddingStatusProvider — Knowledge 管理 WebUI.

Spec source: 02-architecture/TEST_SPEC.md (FR-101)
SRS source : SRS.md FR-101 (Module 25: 知識管理與後台工具)
SAD source : 02-architecture/SAD.md §2.4
             "Module: webui.py — Knowledge CRUD + Markdown editor +
              CSV/JSON import + embedding status (🟡🟢🔴) → FR-101"

Public surface pinned by ``03-development/tests/test_fr101.py``:

    - Constants (test_fr101.py:219-232): the 14 canonical values
      (KNOWLEDGE_API_OK_STATUS, KNOWLEDGE_ACTION_*,
       KNOWLEDGE_CSV_FILE_TYPE, KNOWLEDGE_JSON_FILE_TYPE,
       EMBEDDING_STATUS_*, EMBEDDING_DISPLAY_*,
       KNOWLEDGE_UI_RESPONSE_LIMIT_MS).

    - KnowledgeAdminAPI (test_fr101.py:283-297,373-377,510-516):
      Top-level dispatcher. ``__init__(db_session=None,
      embedding_status_provider=None)`` stores the injected
      dependencies (or a fresh in-memory store / default provider
      when omitted so unit tests can construct it with no args).
      ``crud(action, **kwargs)`` returns ``{status, entry, ok}``
      with status=200 for create; ``create_entry`` / ``read_entry``
      / ``update_entry`` / ``delete_entry`` are the dedicated
      per-verb entry points. ``import_csv`` parses the canonical
      title,content,keywords columns and returns an ``ImportResult``
      whose ``imported`` count equals the row count. ``
      get_embedding_status`` delegates to the injected provider and
      returns ``{chunks_synced, total, display, status}``.

    - ImportResult (test_fr101.py:177-181, 399-406):
      ``imported: int``, ``skipped: int``, ``errors: list``.

    - KnowledgeEntry (test_fr101.py:183-191, 326-334):
      Plain dataclass — ``id`` / ``title`` / ``content`` /
      ``keywords`` / ``embedding_status`` /
      ``embedding_chunks_synced`` / ``embedding_chunks_total``.

    - EmbeddingStatusProvider (test_fr101.py:193-204, 487-505,
      518-550): ``force_sync_status(synced, total)`` pins the
      provider into a deterministic state; ``get_status(entry_id)``
      returns the canonical 4-key dict. The in-progress branch
      (synced < total) maps to ``"syncing" / "同步中"``.

Citations:
    test_fr101.py L211-233 — canonical imports / public surface
    test_fr101.py L245-334 — FR-101 CRUD create returns status=200
    test_fr101.py L347-423 — FR-101 CSV import returns imported=int
    test_fr101.py L437-550 — FR-101 embedding status "同步中" (5/10)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration constants — FR-101 canonical values.
# ---------------------------------------------------------------------------

KNOWLEDGE_API_OK_STATUS = 200

KNOWLEDGE_ACTION_CREATE = "create"
KNOWLEDGE_ACTION_READ = "read"
KNOWLEDGE_ACTION_UPDATE = "update"
KNOWLEDGE_ACTION_DELETE = "delete"

KNOWLEDGE_CSV_FILE_TYPE = "csv"
KNOWLEDGE_JSON_FILE_TYPE = "json"

# Machine codes (FR-79 source-of-truth) — three-state sync machine.
EMBEDDING_STATUS_SYNCED = "synced"   # 🟢
EMBEDDING_STATUS_SYNCING = "syncing"  # 🟡
EMBEDDING_STATUS_FAILED = "failed"   # 🔴

# Human-readable Chinese labels for the WebUI status column.
EMBEDDING_DISPLAY_SYNCED = "已同步"
EMBEDDING_DISPLAY_SYNCING = "同步中"
EMBEDDING_DISPLAY_FAILED = "同步失敗"

# SRS FR-101: "UI 響應時間 < 1.5s".
KNOWLEDGE_UI_RESPONSE_LIMIT_MS = 1500


# ---------------------------------------------------------------------------
# Data containers.
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    """A single row in the knowledge base.

    Attributes:
        id:                     Row id; None until the entry is persisted
                                (assigned by the in-memory store on add()).
        title:                  Markdown title (verbatim — the WebUI list
                                view pins on this string).
        content:                Markdown body.
        keywords:               Tag list (pipe-delimited in CSV source).
        embedding_status:       One of the EMBEDDING_STATUS_* machine codes.
        embedding_chunks_synced: Chunks whose embeddings are in the index.
        embedding_chunks_total:  Total chunks derived from content.
    """

    title: str = ""
    content: str = ""
    keywords: List[str] = field(default_factory=list)
    id: Optional[int] = None
    embedding_status: str = EMBEDDING_STATUS_SYNCED
    embedding_chunks_synced: int = 0
    embedding_chunks_total: int = 0


@dataclass
class ImportResult:
    """Result of a batch CSV / JSON import.

    Attributes:
        imported: Rows successfully persisted.
        skipped:  Rows rejected for any reason (parse error, missing
                  required field, etc.).
        errors:   Per-row error messages — empty on a clean import.
    """

    imported: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Embedding-status provider — testable seam for FR-79 sync state.
# ---------------------------------------------------------------------------

class EmbeddingStatusProvider:
    """Read-side provider for the embedding sync state machine.

    FR-101 contract:
        * ``force_sync_status(synced, total)`` pins the provider into
          a deterministic pair so unit tests can drive the WebUI's
          "同步中 / 已同步 / 同步失敗" status column.
        * ``get_status(entry_id=None)`` returns
          ``{chunks_synced, total, display, status}`` where the
          ``display`` is the canonical Chinese label and ``status``
          is the machine code. The in-progress branch (synced < total)
          is the one the FR-101 spec pins to "同步中".
    """

    def __init__(self, default_synced: int = 0, default_total: int = 0) -> None:
        self._synced = default_synced
        self._total = default_total

    def force_sync_status(self, synced: int, total: int) -> None:
        """Pin the provider into a deterministic chunks_synced/total pair.

        A pair where synced == total and total > 0 represents the
        canonical "已同步" state; synced < total is the in-progress
        "同步中" state; total == 0 is "nothing to sync" (also reported
        as 已同步 so the WebUI does not lie about a missing job).
        """
        self._synced = synced
        self._total = total

    def get_status(self, entry_id: Optional[int] = None) -> Dict[str, Any]:
        """Return the canonical 4-key status dict for the WebUI."""
        synced = self._synced
        total = self._total
        if total <= 0 or synced >= total:
            status = EMBEDDING_STATUS_SYNCED
            display = EMBEDDING_DISPLAY_SYNCED
        else:
            status = EMBEDDING_STATUS_SYNCING
            display = EMBEDDING_DISPLAY_SYNCING
        return {
            "chunks_synced": synced,
            "total": total,
            "display": display,
            "status": status,
        }


# ---------------------------------------------------------------------------
# Default in-memory store — unit-test seam for the CRUD verbs.
# ---------------------------------------------------------------------------

class _InMemoryStore:
    """Backing store for ``KnowledgeAdminAPI`` when no real DB is wired.

    Mirrors the shape of the autouse fixture's ``_InMemoryStore`` so
    unit tests can construct ``KnowledgeAdminAPI()`` with no args and
    still exercise the CRUD verbs end-to-end.
    """

    def __init__(self) -> None:
        self.rows: Dict[int, KnowledgeEntry] = {}
        self._next_id = 1

    def add(self, obj: KnowledgeEntry) -> KnowledgeEntry:
        if obj.id is None:
            obj.id = self._next_id
            self._next_id += 1
        self.rows[obj.id] = obj
        return obj

    def get(self, _id: int) -> Optional[KnowledgeEntry]:
        return self.rows.get(_id)

    def delete(self, _id: int) -> bool:
        return self.rows.pop(_id, None) is not None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


# ---------------------------------------------------------------------------
# KnowledgeAdminAPI — top-level dispatcher.
# ---------------------------------------------------------------------------

class KnowledgeAdminAPI:
    """Top-level dispatcher for the Knowledge 管理 WebUI.

    FR-101 contract:
        * Accepts an injected ``db_session`` (context manager
          producing a store with ``add / get / delete / commit``) and
          an injected ``embedding_status_provider``. Both default to
          the in-memory seam so unit tests can construct the API
          with no args.
        * ``crud(action, **kwargs)`` is the single dispatcher the
          WebUI calls; it routes to the per-verb methods and returns
          ``{status, entry, ok}``. The create leg pins status=200 per
          the FR-101 spec.
        * ``import_csv`` parses the canonical (title, content,
          keywords) columns; the keyword column is pipe-delimited so
          a single row can carry multiple tags.
        * ``get_embedding_status`` delegates to the injected
          ``EmbeddingStatusProvider`` and returns its 4-key dict.
    """

    def __init__(
        self,
        db_session: Optional[Callable[[], Any]] = None,
        embedding_status_provider: Optional[EmbeddingStatusProvider] = None,
    ) -> None:
        self._db_session = db_session
        self._embedding_status_provider = (
            embedding_status_provider
            if embedding_status_provider is not None
            else EmbeddingStatusProvider()
        )

    # ---- internal helpers ------------------------------------------------

    def _store(self) -> _InMemoryStore:
        """Return the active store, falling back to the in-memory seam.

        When ``db_session`` is injected the test owns the store; when
        it is omitted we lazily create a fresh ``_InMemoryStore`` so
        unit tests can construct ``KnowledgeAdminAPI()`` with no args.
        """
        if self._db_session is None:
            return self._default_store
        # The test-injected ``_FakeSession`` is a context manager
        # whose ``__enter__`` returns a store with ``add/get/delete/
        # commit``; honour that contract for compatibility.
        session = self._db_session()
        if hasattr(session, "__enter__"):
            return session.__enter__()
        return session

    @property
    def _default_store(self) -> _InMemoryStore:
        if not hasattr(self, "_default_store_cache"):
            self._default_store_cache = _InMemoryStore()
        return self._default_store_cache

    # ---- per-verb CRUD methods -------------------------------------------

    def create_entry(
        self,
        title: str,
        content: str,
        keywords: Optional[List[str]] = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            title=title,
            content=content,
            keywords=list(keywords) if keywords else [],
        )
        return self._store().add(entry)

    def read_entry(self, entry_id: int) -> Optional[KnowledgeEntry]:
        return self._store().get(entry_id)

    def update_entry(
        self, entry_id: int, **fields: Any
    ) -> Optional[KnowledgeEntry]:
        store = self._store()
        entry = store.get(entry_id)
        if entry is None:
            return None
        for key, value in fields.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        return entry

    def delete_entry(self, entry_id: int) -> bool:
        return bool(self._store().delete(entry_id))

    # ---- dispatcher ------------------------------------------------------

    def crud(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """Single dispatcher for the WebUI's ``action`` parameter.

        Maps the FR-101 ``action`` string to the per-verb methods and
        returns a dict with at least ``status`` (int HTTP code),
        ``entry`` (KnowledgeEntry | None), and ``ok`` (bool). The
        create leg is pinned to status=200 per the spec.
        """
        if action == KNOWLEDGE_ACTION_CREATE:
            entry = self.create_entry(
                title=kwargs.get("title", ""),
                content=kwargs.get("content", ""),
                keywords=kwargs.get("keywords"),
            )
            return {
                "status": KNOWLEDGE_API_OK_STATUS,
                "entry": entry,
                "ok": True,
            }
        if action == KNOWLEDGE_ACTION_READ:
            entry = self.read_entry(kwargs.get("entry_id"))
            return {
                "status": KNOWLEDGE_API_OK_STATUS,
                "entry": entry,
                "ok": entry is not None,
            }
        if action == KNOWLEDGE_ACTION_UPDATE:
            entry_id = kwargs.get("entry_id")
            fields = kwargs.get("fields", {})
            entry = self.update_entry(entry_id, **fields)
            return {
                "status": KNOWLEDGE_API_OK_STATUS,
                "entry": entry,
                "ok": entry is not None,
            }
        if action == KNOWLEDGE_ACTION_DELETE:
            entry_id = kwargs.get("entry_id")
            deleted = self.delete_entry(entry_id)
            return {
                "status": KNOWLEDGE_API_OK_STATUS,
                "entry": None,
                "ok": deleted,
            }
        # Unknown action — return a structured error rather than raising
        # so the WebUI can render the message without crashing the
        # request.
        return {
            "status": 400,
            "entry": None,
            "ok": False,
            "error": f"unknown action: {action!r}",
        }

    # ---- CSV import ------------------------------------------------------

    def import_csv(
        self,
        file_bytes: bytes,
        filename: str = "kb.csv",
    ) -> ImportResult:
        """Parse the canonical ``title,content,keywords`` CSV.

        The keyword column is pipe-delimited (``kb|faq``) so a single
        row can carry multiple tags. Each row is persisted as a
        ``KnowledgeEntry``; the returned ``ImportResult.imported``
        count is the number of rows successfully written.
        """
        result = ImportResult()
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            result.errors.append(f"decode error: {exc}")
            return result

        reader = csv.DictReader(io.StringIO(text))
        store = self._store()
        for row in reader:
            try:
                title = (row.get("title") or "").strip()
                content = (row.get("content") or "").strip()
                kw_raw = (row.get("keywords") or "").strip()
                keywords = [k for k in kw_raw.split("|") if k]
                if not title:
                    result.skipped += 1
                    result.errors.append("missing title")
                    continue
                entry = KnowledgeEntry(
                    title=title,
                    content=content,
                    keywords=keywords,
                )
                store.add(entry)
                result.imported += 1
            except Exception as exc:  # noqa: BLE001 — per-row isolation
                result.skipped += 1
                result.errors.append(str(exc))
        return result

    # ---- embedding status ------------------------------------------------

    def get_embedding_status(
        self, entry_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Delegate to the injected ``EmbeddingStatusProvider``."""
        return self._embedding_status_provider.get_status(entry_id=entry_id)
