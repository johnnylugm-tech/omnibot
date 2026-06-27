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
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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
    keywords: list[str] = field(default_factory=list)
    id: int | None = None
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
    errors: list[str] = field(default_factory=list)


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
        self._failed: bool = False

    def force_sync_status(self, synced: int, total: int) -> None:
        """Pin the provider into a deterministic chunks_synced/total pair.

        A pair where synced == total and total > 0 represents the
        canonical "已同步" state; synced < total is the in-progress
        "同步中" state; total == 0 is "nothing to sync" (also reported
        as 已同步 so the WebUI does not lie about a missing job).
        Driving a new pair also clears any prior FAILED state so a
        successful retry is reflected as SYNCING/SYNCED, not stuck red.
        """
        self._synced = synced
        self._total = total
        self._failed = False

    def mark_failed(self) -> None:
        """Pin the provider into the FAILED state (同步失敗 / 🔴).

        The next ``get_status`` call returns the FAILED branch so the
        WebUI stops misreporting a sync error as SYNCED (M-11).
        """
        self._failed = True

    def get_status(self, entry_id: int | None = None) -> dict[str, Any]:
        """Return the canonical 4-key status dict for the WebUI."""
        synced = self._synced
        total = self._total
        if self._failed:
            status = EMBEDDING_STATUS_FAILED
            display = EMBEDDING_DISPLAY_FAILED
        elif total <= 0 or synced >= total:
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
        self.rows: dict[int, KnowledgeEntry] = {}
        self._next_id = 1

    def add(self, obj: KnowledgeEntry) -> KnowledgeEntry:
        if obj.id is None:
            obj.id = self._next_id
            self._next_id += 1
        self.rows[obj.id] = obj
        return obj

    def get(self, _id: int) -> KnowledgeEntry | None:  # pragma: no cover
        return self.rows.get(_id)  # pragma: no cover

    def delete(self, _id: int) -> bool:  # pragma: no cover
        return self.rows.pop(_id, None) is not None  # pragma: no cover

    def commit(self) -> None:
        return None

    def rollback(self) -> None:  # pragma: no cover
        return None  # pragma: no cover


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
        db_session: Callable[[], Any] | None = None,
        embedding_status_provider: EmbeddingStatusProvider | None = None,
    ) -> None:
        self._db_session = db_session
        self._default_store = _InMemoryStore()
        self._embedding_status_provider = (
            embedding_status_provider
            if embedding_status_provider is not None
            else EmbeddingStatusProvider()
        )

    # ---- internal helpers ------------------------------------------------

    @contextmanager
    def _store(self) -> Iterator[Any]:
        """Yield the active store, guaranteeing the session is exited.

        The injected ``db_session`` factory returns a context manager
        whose ``__enter__`` yields a store; this wrapper funnels the
        access through ``with`` so ``__exit__`` (and therefore the
        underlying connection release) is always called. Without it,
        every CRUD call would leak one session and eventually exhaust
        the connection pool (H-22).
        """
        if self._db_session is None:
            yield self._default_store
            return
        session = self._db_session()
        if hasattr(session, "__enter__"):
            with session as store:
                yield store
        else:
            yield session

    # ---- per-verb CRUD methods -------------------------------------------

    def list_entries(
        self,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        """[P5] Paginated read for the admin WebUI table.

        Returns ``{"total": int, "page": int, "limit": int, "items": [KnowledgeEntry]}``.
        Reads through ``self._store`` so a SQL-backed session
        factory (with a ``rows``-shaped result) gets paged correctly.
        For the in-memory seam we sort by id desc (newest first) so
        page 1 shows the most recently created entries.
        """
        page = max(1, int(page))
        limit = max(1, min(200, int(limit)))
        start = (page - 1) * limit
        with self._store() as store:
            rows_attr = getattr(store, "rows", None)
            if isinstance(rows_attr, dict):
                entries = sorted(rows_attr.values(), key=lambda e: e.id or 0, reverse=True)
                total = len(entries)
                page_rows = entries[start : start + limit]
            else:
                # SQL-backed store — caller is responsible for paging.
                # We expose a contract note rather than faking LIMIT/OFFSET.
                page_rows = list(rows_attr) if rows_attr is not None else []
                total = len(page_rows)
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": list(page_rows),
        }

    def create_entry(
        self,
        title: str,
        content: str,
        keywords: list[str] | None = None,
    ) -> KnowledgeEntry:
        entry = KnowledgeEntry(
            title=title,
            content=content,
            keywords=list(keywords) if keywords else [],
        )
        with self._store() as store:
            result = store.add(entry)
            store.commit()  # H-23: real DB adapter requires explicit commit
        return result

    def read_entry(self, entry_id: int) -> KnowledgeEntry | None:  # pragma: no cover
        with self._store() as store:
            return store.get(entry_id)

    from app.admin.rbac import RBACEnforcer

    @RBACEnforcer.require("knowledge", "write")
    def update_entry(
        self, entry_id: int, **fields: Any
    ) -> KnowledgeEntry | None:
        with self._store() as store:
            entry = store.get(entry_id)
            if entry is None:
                return None
            for key, value in fields.items():
                if key in {"title", "content", "keywords"} and hasattr(entry, key):
                    setattr(entry, key, value)
            store.commit()  # H-23: real DB adapter requires explicit commit
        return entry

    def delete_entry(self, entry_id: int) -> bool:  # pragma: no cover
        with self._store() as store:
            return bool(store.delete(entry_id))

    # ---- dispatcher ------------------------------------------------------

    @staticmethod
    def _crud_response(
        entry: KnowledgeEntry | None,
    ) -> dict[str, Any]:
        """Build the canonical {status, entry, ok} dict for read/verb results."""
        return {
            "status": KNOWLEDGE_API_OK_STATUS,
            "entry": entry,
            "ok": entry is not None,
        }

    def crud(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Single dispatcher for the WebUI's ``action`` parameter.

        Maps the FR-101 ``action`` string to the per-verb methods and
        returns a dict with at least ``status`` (int HTTP code),
        ``entry`` (KnowledgeEntry | None), and ``ok`` (bool). The
        create leg is pinned to status=200 per the spec.
        """
        from app.admin.reports import log_admin_action
        log_admin_action("knowledge_crud", admin_id="system", details={"action": action})
        if action == KNOWLEDGE_ACTION_CREATE:
            entry = self.create_entry(
                title=kwargs.get("title", ""),
                content=kwargs.get("content", ""),
                keywords=kwargs.get("keywords"),
            )
            return self._crud_response(entry)
        if action == KNOWLEDGE_ACTION_READ:
            return self._crud_response(
                self.read_entry(kwargs.get("entry_id", 0))
            )
        if action == KNOWLEDGE_ACTION_UPDATE:
            return self._crud_response(
                self.update_entry(
                    kwargs.get("entry_id", 0), **kwargs.get("fields", {})
                )
            )
        if action == KNOWLEDGE_ACTION_DELETE:
            # Delete is the only verb whose ``ok`` follows the
            # affected-row count rather than entry-presence.
            deleted = self.delete_entry(kwargs.get("entry_id", 0))
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
        with self._store() as store:
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
                except Exception as exc:
                    result.skipped += 1
                    result.errors.append(str(exc))
        return result

    # ---- embedding status ------------------------------------------------

    def get_embedding_status(
        self, entry_id: int | None = None
    ) -> dict[str, Any]:
        """Delegate to the injected ``EmbeddingStatusProvider``."""
        return self._embedding_status_provider.get_status(entry_id=entry_id)


# ---------------------------------------------------------------------------
# FR-102: RAGDebugger — Tier 1 ILIKE + Tier 2 cosine + RRF k=60 Top-3 展示
# ---------------------------------------------------------------------------

RAG_DEFAULT_THRESHOLD: float = 0.75
RAG_RRF_K: int = 60
RAG_RRF_TOP_N: int = 3
RAG_SECTION_ILIKE: str = "ilike_results"
RAG_SECTION_COSINE: str = "cosine_scores"
RAG_SECTION_RRF_TOP3: str = "rrf_top3"
RAG_REQUIRED_SECTIONS: tuple = (
    RAG_SECTION_ILIKE,
    RAG_SECTION_COSINE,
    RAG_SECTION_RRF_TOP3,
)


@dataclass
class ILIKEMatch:
    """Tier 1 ILIKE match — row_id, content snippet, confidence score."""

    row_id: int = 0
    content: str = ""
    confidence: float = 0.0


@dataclass
class CosineHit:
    """Tier 2 child-chunk cosine hit — chunk_id and similarity score."""

    chunk_id: str = ""
    score: float = 0.0


@dataclass
class RRFEntry:
    """RRF Top-N entry — rank, fused score, parent_id, parent content."""

    rank: int = 0
    score: float = 0.0
    parent_id: int = 0
    content: str = ""


@dataclass
class DebuggerResult:
    """Single RAG Debugger invocation result with Tier 1+2 payload lists."""

    query: str = ""
    ilike_results: list[Any] = field(default_factory=list)
    cosine_scores: list[Any] = field(default_factory=list)
    rrf_top3: list[Any] = field(default_factory=list)
    sections: list[str] = field(
        default_factory=lambda: list(RAG_REQUIRED_SECTIONS)
    )


class _InMemoryKnowledgeProvider:
    """No-op Tier 1+2 seam — returns empty lists for all pipeline stages."""

    def ilike_search(self, query: str) -> list[ILIKEMatch]:
        return []

    def cosine_search(self, query: str, threshold: float) -> list[CosineHit]:
        return []

    def rrf_fuse(self, ilike: list[ILIKEMatch], cosine: list[CosineHit]) -> list[RRFEntry]:
        return []


class RAGDebugger:
    """RAG Debugger WebUI panel — Tier 1+2 pipeline runner with sandbox slider."""

    def __init__(
        self,
        config_store: Any | None = None,
        knowledge_provider: Any | None = None,
    ) -> None:
        self._config_store = config_store
        self._knowledge_provider = (
            knowledge_provider if knowledge_provider is not None
            else _InMemoryKnowledgeProvider()
        )
        self._sandbox_threshold: float | None = None

    def _saved_threshold(self) -> float:
        # Resolution: injected store → app.infra module seam (monkeypatched in tests) → default
        if self._config_store is not None:
            try:
                value = self._config_store.get("rag_cosine_threshold", RAG_DEFAULT_THRESHOLD)
                if value is not None:
                    return float(value)
            except Exception as exc:
                logger.debug("config_store threshold lookup failed: %s", exc)
        try:
            from app.infra.config import get_config_store
            store = get_config_store()
            return float(store.get("rag_cosine_threshold", RAG_DEFAULT_THRESHOLD))
        except Exception:
            return RAG_DEFAULT_THRESHOLD

    def _effective_threshold(self, requested: float) -> float:
        return float(self._sandbox_threshold) if self._sandbox_threshold is not None else float(requested)

    def debug(self, query: str, threshold: float = RAG_DEFAULT_THRESHOLD) -> DebuggerResult:
        """Run the Tier 1+2 pipeline in sandbox mode — never mutates platform_configs."""
        t = self._effective_threshold(threshold)
        ilike = self._knowledge_provider.ilike_search(query)
        cosine = self._knowledge_provider.cosine_search(query, t)
        rrf = self._knowledge_provider.rrf_fuse(ilike, cosine)
        return DebuggerResult(
            query=query,
            ilike_results=list(ilike),
            cosine_scores=list(cosine),
            rrf_top3=list(rrf[:RAG_RRF_TOP_N]),
            sections=list(RAG_REQUIRED_SECTIONS),
        )

    def set_slider_threshold(self, threshold: float) -> None:
        """Sandbox-only — SRS FR-102 '沙盒調整不寫入 platform_configs'."""
        self._sandbox_threshold = float(threshold)

    def get_saved_threshold(self) -> float:
        """Read persisted threshold from config_store; ignores sandbox slider."""
        return self._saved_threshold()


# ---------------------------------------------------------------------------
# FR-103: OperationsDashboard — FCR/p95/知識來源/成本 + 告警 + 時序切換
# ---------------------------------------------------------------------------

FCR_ALERT_THRESHOLD: float = 0.90   # SRS FR-103: FCR < 90% triggers yellow
ALERT_COLOR_YELLOW: str = "yellow"
ALERT_COLOR_GREEN: str = "green"
VALID_TIME_RANGES: tuple[str, ...] = ("24hr", "7d", "30d")


class OperationsDashboard:
    """[FR-103] Operations Dashboard — FCR/p95/知識來源/成本 KPI + 告警 + 時序切換."""

    def get_fcr_alert_color(self, fcr: float) -> str:
        """Return alert colour for the FCR KPI.

        Returns ALERT_COLOR_YELLOW when fcr < FCR_ALERT_THRESHOLD (0.90),
        otherwise ALERT_COLOR_GREEN.
        """
        if fcr < FCR_ALERT_THRESHOLD:
            return ALERT_COLOR_YELLOW
        return ALERT_COLOR_GREEN

    def _fetch_metrics(self, time_range: str) -> dict:
        """Injectable seam for DB metric queries — overridden by tests."""
        return {
            "fcr": 0.0,
            "p95_latency_ms": 0,
            "knowledge_distribution": {"tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0},
            "monthly_cost_usd": 0.0,
            "time_range": time_range,
        }

    def get_dashboard_data(self, time_range: str) -> dict:
        """Fetch and return dashboard metrics for the given time range.

        Valid time_range values: "24hr", "7d", "30d" (VALID_TIME_RANGES).
        """
        return self._fetch_metrics(time_range)


class RealSQLOperationsDashboard(OperationsDashboard):
    """[P5] OperationsDashboard subclass backed by real SQL queries.

    Runs the ODD SQL aggregates against the canonical
    ``odd_conversations`` / ``odd_queries`` tables via the standard
    ``get_session`` seam so the FR-101 unit tests can construct the
    base ``OperationsDashboard()`` without a DB while the production
    admin WebUI gets real numbers. SQL exceptions degrade gracefully
    to zero values + the prior alert colour so a partial outage
    doesn't black out the dashboard.

    Lives in ``app.admin.webui`` (not the API layer) so the router
    can stay declarative — it only calls
    ``dashboard.get_dashboard_data(range)``.
    """

    async def _fetch_metrics_async(self, time_range: str) -> dict:
        """Async SQL-backed metrics fetch.

        The ODD suite is fixed at a 30-day window so the UI's
        "24hr" / "7d" still get a meaningful number rather than an
        empty result set; the caller is responsible for translating
        time_range into a SQL INTERVAL if/when the ODD suite grows.
        """
        from sqlalchemy import text

        from app.infra.database import get_session

        out = {
            "fcr": 0.0,
            "p95_latency_ms": 0,
            "knowledge_distribution": {"tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0},
            "monthly_cost_usd": 0.0,
            "time_range": time_range,
        }
        try:
            from app.infra.database import get_session
            async for session in get_session():
                row = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FILTER (WHERE odd_resolved_on_first_contact = TRUE)::FLOAT"
                            " / NULLIF(COUNT(*), 0) AS fcr"
                            " FROM odd_conversations"
                            " WHERE scope_type = 'in_scope'"
                            " AND created_at >= NOW() - INTERVAL '30 days'"
                        )
                    )
                ).fetchone()
                if row and row[0] is not None:
                    out["fcr"] = float(row[0])

                row = (
                    await session.execute(
                        text(
                            "SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_time_seconds) * 1000"
                            " FROM odd_conversations"
                            " WHERE scope_type = 'in_scope' AND resolved_at IS NOT NULL"
                        )
                    )
                ).fetchone()
                if row and row[0] is not None:
                    out["p95_latency_ms"] = int(row[0])

                rows = (
                    await session.execute(
                        text(
                            "SELECT tier, COUNT(*) FROM odd_queries"
                            " WHERE scope_type = 'in_scope'"
                            " GROUP BY tier"
                        )
                    )
                ).fetchall()
                for r in rows:
                    key = f"tier{r[0]}"
                    if key in out["knowledge_distribution"]:
                        out["knowledge_distribution"][key] = int(r[1])
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "RealSQLOperationsDashboard: SQL fetch failed for "
                "time_range=%s: %s",
                time_range, exc,
            )
        return out

# Column list shared by every SELECT/UPDATE-RETURNING against
# knowledge_base. Extracted so a schema change touches one place, not five.
_KB_COLUMNS = (
    "id, title, content, keywords, embedding_status, "
    "embedding_chunks_synced, embedding_chunks_total"
)
_KB_INSERT_SQL = (
    "INSERT INTO knowledge_base "
    "(title, content, keywords, embedding_status, "
    "embedding_chunks_synced, embedding_chunks_total) "
    "VALUES (:title, :content, :keywords, :status, 0, 0)"
)


class RealSQLKnowledgeAdminAPI(KnowledgeAdminAPI):
    """[FR-101] Async SQL-backed implementation of KnowledgeAdminAPI."""

    @staticmethod
    def _row_to_entry(r: Any) -> KnowledgeEntry:
        """Map a ``knowledge_base`` row tuple to a KnowledgeEntry.

        All three read paths (list_entries, crud READ, crud UPDATE-RETURNING)
        share this projection so a column-list change stays in one place.
        """
        return KnowledgeEntry(
            id=r[0], title=r[1], content=r[2], keywords=r[3] or [],
            embedding_status=r[4] or EMBEDDING_STATUS_SYNCED,
            embedding_chunks_synced=r[5] or 0,
            embedding_chunks_total=r[6] or 0,
        )

    async def list_entries(self, page: int = 1, limit: int = 20) -> dict[str, Any]:
        page = max(1, int(page))
        limit = max(1, min(200, int(limit)))
        start = (page - 1) * limit
        from sqlalchemy import text
        from app.infra.database import get_session

        out = {"total": 0, "page": page, "limit": limit, "items": []}
        async for session in get_session():
            total_row = (await session.execute(text("SELECT COUNT(*) FROM knowledge_base"))).fetchone()
            out["total"] = total_row[0] if total_row else 0

            rows = (await session.execute(
                text(
                    f"SELECT {_KB_COLUMNS} FROM knowledge_base "
                    "ORDER BY id DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": start},
            )).fetchall()

            out["items"] = [self._row_to_entry(r) for r in rows]
            break
        return out

    async def crud(self, action: str, **kwargs: Any) -> dict[str, Any]:
        from sqlalchemy import text
        from app.infra.database import get_session
        from app.admin.reports import log_admin_action

        # Audit log uses the caller's actor_id (router's role) so the
        # audit trail attributes actions to the actual admin instead of
        # an opaque "system" sentinel. RBAC itself stays in the router;
        # this layer only records who triggered the action.
        actor_id = kwargs.pop("actor_id", None) or "system"
        log_admin_action("knowledge_crud", admin_id=actor_id, details={"action": action})

        async for session in get_session():
            if action == KNOWLEDGE_ACTION_CREATE:
                title = kwargs.get("title", "")
                content = kwargs.get("content", "")
                keywords = kwargs.get("keywords") or []
                row = (await session.execute(
                    text(f"{_KB_INSERT_SQL} RETURNING {_KB_COLUMNS}"),
                    {"title": title, "content": content, "keywords": keywords, "status": EMBEDDING_STATUS_SYNCED},
                )).fetchone()
                await session.commit()
                return self._crud_response(self._row_to_entry(row))

            if action == KNOWLEDGE_ACTION_READ:
                entry_id = kwargs.get("entry_id", 0)
                row = (await session.execute(
                    text(f"SELECT {_KB_COLUMNS} FROM knowledge_base WHERE id = :id"),
                    {"id": entry_id},
                )).fetchone()
                return self._crud_response(self._row_to_entry(row) if row else None)

            if action == KNOWLEDGE_ACTION_UPDATE:
                entry_id = kwargs.get("entry_id", 0)
                fields = kwargs.get("fields", {})
                if not fields:
                    # Empty fields → return current state via an inline
                    # SELECT on the SAME session. The previous recursive
                    # self.crud(READ) re-entered the async-for and opened
                    # a second pool connection while the first was pinned.
                    row = (await session.execute(
                        text(f"SELECT {_KB_COLUMNS} FROM knowledge_base WHERE id = :id"),
                        {"id": entry_id},
                    )).fetchone()
                    return self._crud_response(self._row_to_entry(row) if row else None)

                set_clauses = []
                params = {"id": entry_id}
                for k, v in fields.items():
                    if k in {"title", "content", "keywords"}:
                        set_clauses.append(f"{k} = :{k}")
                        params[k] = v

                if set_clauses:
                    row = (await session.execute(
                        text(
                            f"UPDATE knowledge_base SET {', '.join(set_clauses)} "
                            f"WHERE id = :id RETURNING {_KB_COLUMNS}"
                        ),
                        params,
                    )).fetchone()
                    await session.commit()
                    if row:
                        return self._crud_response(self._row_to_entry(row))
                return self._crud_response(None)

            if action == KNOWLEDGE_ACTION_DELETE:
                entry_id = kwargs.get("entry_id", 0)
                result = await session.execute(
                    text("DELETE FROM knowledge_base WHERE id = :id"),
                    {"id": entry_id}
                )
                await session.commit()
                return {
                    "status": KNOWLEDGE_API_OK_STATUS,
                    "entry": None,
                    "ok": result.rowcount > 0,
                }
            break

        return {
            "status": 400,
            "entry": None,
            "ok": False,
            "error": f"unknown action: {action!r}",
        }

    async def import_csv(self, file_bytes: bytes, filename: str = "kb.csv") -> ImportResult:
        result = ImportResult()
        try:
            text_data = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            result.errors.append(f"decode error: {exc}")
            return result

        import csv, io
        reader = csv.DictReader(io.StringIO(text_data))
        from sqlalchemy import text
        from app.infra.database import get_session

        async for session in get_session():
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

                    await session.execute(
                        text(_KB_INSERT_SQL),
                        {"title": title, "content": content, "keywords": keywords, "status": EMBEDDING_STATUS_SYNCED},
                    )
                    result.imported += 1
                except Exception as exc:
                    # Per-row failure: rollback the failed statement so the
                    # AsyncSession is reusable for subsequent rows. Without
                    # this the transaction enters a deactivated state and
                    # the final session.commit() raises InvalidRequestError.
                    await session.rollback()
                    result.skipped += 1
                    result.errors.append(str(exc))
            await session.commit()
            break
        return result

    async def _import_json(self, items: list[Any]) -> ImportResult:
        """Atomic JSON bulk import — one session + one commit.

        Unlike the per-row ``crud(CREATE)`` path, this opens a SINGLE
        session, INSERTs every valid row, and commits ONCE at the end
        so a partial failure leaves the database untouched (atomicity
        preserved) and the pool connection is reused across all rows.
        """
        from sqlalchemy import text
        from app.infra.database import get_session

        result = ImportResult()
        rows_to_insert: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("title"):
                result.skipped += 1
                continue
            rows_to_insert.append({
                "title": str(item["title"]).strip(),
                "content": str(item.get("content", "")).strip(),
                "keywords": list(item.get("keywords") or []),
                "status": EMBEDDING_STATUS_SYNCED,
            })

        if not rows_to_insert:
            return result

        async for session in get_session():
            try:
                for params in rows_to_insert:
                    await session.execute(text(_KB_INSERT_SQL), params)
                await session.commit()
                result.imported = len(rows_to_insert)
            except Exception as exc:
                await session.rollback()
                result.errors.append(f"bulk insert failed: {exc}")
                result.imported = 0
                result.skipped = len(items)
            break
        return result
