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
        self._default_store = _InMemoryStore()
        self._embedding_status_provider = (
            embedding_status_provider
            if embedding_status_provider is not None
            else EmbeddingStatusProvider()
        )

    # ---- internal helpers ------------------------------------------------

    def _store(self) -> _InMemoryStore:
        """Return the active store: injected session or in-memory default.

        The test-injected ``_FakeSession`` is a context manager whose
        ``__enter__`` returns a store with ``add/get/delete/commit``;
        honour that contract for compatibility.
        """
        if self._db_session is None:
            return self._default_store
        session = self._db_session()
        if hasattr(session, "__enter__"):
            return session.__enter__()
        return session

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

    @staticmethod
    def _crud_response(
        entry: Optional[KnowledgeEntry],
    ) -> Dict[str, Any]:
        """Build the canonical {status, entry, ok} dict for read/verb results."""
        return {
            "status": KNOWLEDGE_API_OK_STATUS,
            "entry": entry,
            "ok": entry is not None,
        }

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
            return self._crud_response(entry)
        if action == KNOWLEDGE_ACTION_READ:
            return self._crud_response(
                self.read_entry(kwargs.get("entry_id"))
            )
        if action == KNOWLEDGE_ACTION_UPDATE:
            return self._crud_response(
                self.update_entry(
                    kwargs.get("entry_id"), **kwargs.get("fields", {})
                )
            )
        if action == KNOWLEDGE_ACTION_DELETE:
            # Delete is the only verb whose ``ok`` follows the
            # affected-row count rather than entry-presence.
            deleted = self.delete_entry(kwargs.get("entry_id"))
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


# ===========================================================================
# [FR-102] RAGDebugger — 管理 WebUI RAG Debugger (Tier 1 ILIKE + Tier 2
# RAG/cosine + RRF k=60 Top-3 評分展示 + 相似度閾值滑桿沙盒).
#
# Spec source: 02-architecture/TEST_SPEC.md (FR-102)
# SRS source : SRS.md FR-102 (Module 25: 管理 WebUI)
#              "RAG Debugger：管理員輸入測試提問 → 展示 ILIKE 匹配結果+置信度、
#               Child Chunk 餘弦相似度分數、Parent Chunk 內容、RRF k=60 Top-3
#               評分；相似度閾值滑桿（預設 0.75，沙盒調整不寫入
#               platform_configs）"
# SAD source  : 02-architecture/SAD.md §2.4
#              "Module: webui.py — Knowledge CRUD + Markdown editor +
#               CSV/JSON import + embedding status + RAG Debugger
#               → FR-101 / FR-102"
#
# Public surface pinned by ``03-development/tests/test_fr102.py``:
#
#   - Constants (test_fr102.py:181-194, 217-272):
#       RAG_DEFAULT_THRESHOLD   = 0.75              # 滑桿預設值
#       RAG_RRF_K               = 60                # FR-27 RRF k=60
#       RAG_RRF_TOP_N           = 3                 # RRF Top-3 評分
#       RAG_SECTION_ILIKE       = "ilike_results"   # Tier 1 區段
#       RAG_SECTION_COSINE      = "cosine_scores"   # Tier 2 區段
#       RAG_SECTION_RRF_TOP3    = "rrf_top3"        # RRF 區段
#       RAG_REQUIRED_SECTIONS   = (the three names in display order)
#
#   - RAGDebugger (test_fr102.py:282-359):
#       Top-level dispatcher. ``__init__(config_store=None,
#       knowledge_provider=None)`` stores the injected seams. The
#       sandbox slider threshold lives on the instance only; the
#       persisted platform_configs row is NEVER touched by
#       ``set_slider_threshold``. ``debug(query, threshold)`` returns a
#       ``DebuggerResult`` whose ``sections`` is the canonical three
#       names in display order.
#
#   - DebuggerResult (test_fr102.py:131-141, 302-393):
#       ``query`` echoes the input; ``ilike_results``, ``cosine_scores``,
#       ``rrf_top3`` are list-like; ``sections`` carries the three
#       canonical section names.
#
#   - ILIKEMatch / CosineHit / RRFEntry (optional, but if present MUST
#     carry the canonical fields shown in test_fr102.py L156-175).
#
# Citations:
#     test_fr102.py L181-194 — canonical imports / public surface
#     test_fr102.py L211-393 — FR-102 happy path: three sections + query
#                              echo + list-shaped payloads
#     test_fr102.py L406-487 — FR-102 sandbox slider MUST NOT persist
#                              to platform_configs (multiple set +
#                              debug() calls leave the saved threshold
#                              at RAG_DEFAULT_THRESHOLD)
# ===========================================================================


# ---------------------------------------------------------------------------
# FR-102 canonical configuration constants.
# ---------------------------------------------------------------------------

#: Default 相似度閾值 — SRS FR-102 "相似度閾值滑桿（預設 0.75）".
RAG_DEFAULT_THRESHOLD: float = 0.75

#: RRF k=60 融合係數 — FR-27 (Reciprocal Rank Fusion) / SRS FR-102.
RAG_RRF_K: int = 60

#: RRF Top-N 截斷 — SRS FR-102 "RRF k=60 Top-3 評分".
RAG_RRF_TOP_N: int = 3

#: Tier 1 區段名稱 — ILIKE 匹配 + 置信度.
RAG_SECTION_ILIKE: str = "ilike_results"

#: Tier 2 區段名稱 — Child Chunk 餘弦相似度分數.
RAG_SECTION_COSINE: str = "cosine_scores"

#: RRF 區段名稱 — k=60 Top-3 評分 + Parent Chunk 內容.
RAG_SECTION_RRF_TOP3: str = "rrf_top3"

#: WebUI section-renderer 必須按此順序迭代的三個區段名稱.
RAG_REQUIRED_SECTIONS: tuple = (
    RAG_SECTION_ILIKE,
    RAG_SECTION_COSINE,
    RAG_SECTION_RRF_TOP3,
)


# ---------------------------------------------------------------------------
# FR-102 data containers — Tier 1 / Tier 2 / RRF payloads.
# ---------------------------------------------------------------------------

@dataclass
class ILIKEMatch:
    """Tier 1 ILIKE match row (PostgreSQL ``ILIKE`` on knowledge base).

    Attributes:
        row_id:     Row id in the knowledge base (synthetic for the
                    in-memory seam).
        content:    Matched content snippet (verbatim).
        confidence: Confidence score in [0, 1] derived from the ILIKE
                    match score (1.0 for exact substring hit).
    """

    row_id: int = 0
    content: str = ""
    confidence: float = 0.0


@dataclass
class CosineHit:
    """Tier 2 Child Chunk cosine similarity hit.

    Attributes:
        chunk_id: Child chunk identifier (string for embedding-key
                  compatibility; the production system uses UUIDs).
        score:    Cosine similarity in [-1, 1]; the Tier 2 cut-off
                  applies ``>= RAG_DEFAULT_THRESHOLD`` (or the sandbox
                  slider value) to filter hits.
    """

    chunk_id: str = ""
    score: float = 0.0


@dataclass
class RRFEntry:
    """RRF Top-N entry — fused rank + Parent Chunk content.

    Attributes:
        rank:      1-based rank within the Top-N list (1 = best).
        score:     RRF fused score using k=RAG_RRF_K.
        parent_id: Parent chunk id in the knowledge base.
        content:   Parent chunk content (verbatim Markdown).
    """

    rank: int = 0
    score: float = 0.0
    parent_id: int = 0
    content: str = ""


@dataclass
class DebuggerResult:
    """Result of a single RAG Debugger invocation.

    Attributes:
        query:         Echoes the input query so the WebUI can show
                       the user "what did I just search for?".
        ilike_results: Tier 1 ILIKE matches + confidence (list of
                       ``ILIKEMatch`` or any list-like).
        cosine_scores: Tier 2 child-chunk cosine scores (list of
                       ``CosineHit`` or any list-like).
        rrf_top3:      RRF k=RAG_RRF_K Top-N entries + Parent Chunk
                       content (list of ``RRFEntry`` or any list-like).
        sections:      The three canonical section names in display
                       order (``RAG_REQUIRED_SECTIONS``).
    """

    query: str = ""
    ilike_results: List[Any] = field(default_factory=list)
    cosine_scores: List[Any] = field(default_factory=list)
    rrf_top3: List[Any] = field(default_factory=list)
    sections: List[str] = field(
        default_factory=lambda: list(RAG_REQUIRED_SECTIONS)
    )


# ---------------------------------------------------------------------------
# FR-102 default in-memory knowledge provider — Tier 1 + Tier 2 + RRF seam.
# ---------------------------------------------------------------------------

class _InMemoryKnowledgeProvider:
    """Default seam for the Tier 1 ILIKE + Tier 2 cosine + RRF pipeline.

    Mirrors the contract GREEN needs to expose so the debugger can run
    without a live PostgreSQL / pgvector / Redis stack. Tests inject
    their own provider; this default returns empty result lists so
    ``debug()`` is observable end-to-end.
    """

    def ilike_search(self, query: str) -> List[ILIKEMatch]:
        """Tier 1 ILIKE search (default: no rows)."""
        return []

    def cosine_search(
        self, query: str, threshold: float
    ) -> List[CosineHit]:
        """Tier 2 cosine search (default: no rows)."""
        return []

    def rrf_fuse(
        self, ilike: List[ILIKEMatch], cosine: List[CosineHit]
    ) -> List[RRFEntry]:
        """RRF k=RAG_RRF_K fusion (default: empty Top-N)."""
        return []


# ---------------------------------------------------------------------------
# FR-102 RAGDebugger — top-level dispatcher.
# ---------------------------------------------------------------------------

class RAGDebugger:
    """Top-level dispatcher for the RAG Debugger WebUI panel.

    FR-102 contract:
        * ``__init__(config_store=None, knowledge_provider=None)``
          stores the injected seams (platform_configs reader/writer +
          Tier 1 ILIKE / Tier 2 cosine provider). Both default to
          ``None``; ``debug()`` falls back to the in-memory default
          provider when nothing is wired so unit tests can construct
          the debugger with no args.
        * ``debug(query, threshold)`` runs the Tier 1+2 pipeline with
          the sandbox threshold and returns a ``DebuggerResult`` whose
          ``sections`` field carries the three canonical section names
          in display order. The persisted platform_configs row is
          NEVER mutated by this call.
        * ``set_slider_threshold(threshold)`` is a sandbox-only
          mutation — it adjusts an in-memory slider value used by
          subsequent ``debug()`` calls but does NOT call the injected
          ``config_store.set(...)`` (which would persist to
          platform_configs). SRS FR-102: "沙盒調整不寫入
          platform_configs".
        * ``get_saved_threshold()`` reads the persisted threshold
          (default ``RAG_DEFAULT_THRESHOLD``). After any number of
          ``set_slider_threshold`` calls, this MUST still return
          ``RAG_DEFAULT_THRESHOLD``.
    """

    def __init__(
        self,
        config_store: Optional[Any] = None,
        knowledge_provider: Optional[Any] = None,
    ) -> None:
        self._config_store = config_store
        self._knowledge_provider = (
            knowledge_provider
            if knowledge_provider is not None
            else _InMemoryKnowledgeProvider()
        )
        # Sandbox-only slider value — never persisted. ``None`` means
        # "no slider adjustment has been made yet; use the threshold
        # passed to ``debug()``".
        self._sandbox_threshold: Optional[float] = None

    # ---- internal helpers ------------------------------------------------

    def _saved_threshold(self) -> float:
        """Read the persisted platform_configs threshold.

        Resolution order:
            1. Explicitly injected ``config_store`` (preferred for
               production wiring).
            2. The canonical ``app.infra.config_store.get_config_store``
               seam (monkeypatched by ``test_fr102.py``'s autouse
               fixture). Falls back silently when the seam is
               unavailable — the FR-102 test fixture uses
               ``raising=False`` precisely because the infra module is
               not always present.
            3. ``RAG_DEFAULT_THRESHOLD`` (the canonical default).
        """
        if self._config_store is not None:
            try:
                value = self._config_store.get(
                    "rag_cosine_threshold", RAG_DEFAULT_THRESHOLD
                )
                if value is not None:
                    return float(value)
            except Exception:  # noqa: BLE001 — defensive read
                pass
        try:
            from app.infra import config_store as _cs_mod  # type: ignore
            store = _cs_mod.get_config_store()
            value = store.get("rag_cosine_threshold", RAG_DEFAULT_THRESHOLD)
            return float(value)
        except Exception:  # noqa: BLE001 — seam unavailable
            return RAG_DEFAULT_THRESHOLD

    def _effective_threshold(self, requested: float) -> float:
        """Return the sandbox slider value if set; else the requested one.

        The sandbox value (set by ``set_slider_threshold``) shadows the
        threshold passed to ``debug()`` so the WebUI can preview a new
        cosine cut-off without persisting it.
        """
        if self._sandbox_threshold is not None:
            return float(self._sandbox_threshold)
        return float(requested)

    # ---- public surface --------------------------------------------------

    def debug(
        self,
        query: str,
        threshold: float = RAG_DEFAULT_THRESHOLD,
    ) -> DebuggerResult:
        """Run the Tier 1+2 pipeline with the sandbox threshold.

        Returns a ``DebuggerResult`` whose ``sections`` field carries
        the three canonical section names in display order. The
        persisted platform_configs row is NEVER mutated — only the
        in-memory sandbox threshold (if previously set) is consulted.
        """
        effective_threshold = self._effective_threshold(threshold)

        # Tier 1 — ILIKE match + confidence.
        ilike = self._knowledge_provider.ilike_search(query)

        # Tier 2 — child chunk cosine similarity at the sandbox cut-off.
        cosine = self._knowledge_provider.cosine_search(
            query, effective_threshold
        )

        # RRF fusion — k=RAG_RRF_K, Top-N=RAG_RRF_TOP_N.
        rrf = self._knowledge_provider.rrf_fuse(ilike, cosine)

        return DebuggerResult(
            query=query,
            ilike_results=list(ilike),
            cosine_scores=list(cosine),
            rrf_top3=list(rrf[:RAG_RRF_TOP_N]),
            sections=list(RAG_REQUIRED_SECTIONS),
        )

    def set_slider_threshold(self, threshold: float) -> None:
        """Sandbox-only slider adjustment — MUST NOT persist.

        SRS FR-102: "沙盒調整不寫入 platform_configs". The slider value
        is stored on the instance only and shadows the threshold passed
        to subsequent ``debug()`` calls. The persisted
        platform_configs row is left untouched, so production queries
        are unaffected by debugger adjustments.
        """
        self._sandbox_threshold = float(threshold)

    def get_saved_threshold(self) -> float:
        """Return the persisted platform_configs threshold (default 0.75).

        After any number of ``set_slider_threshold`` calls this MUST
        still return ``RAG_DEFAULT_THRESHOLD`` — the sandbox slider is
        in-memory only.
        """
        return self._saved_threshold()
