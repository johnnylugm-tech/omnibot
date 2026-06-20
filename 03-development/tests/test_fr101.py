"""TDD-RED: failing tests for FR-101 — Knowledge 管理 WebUI
(CRUD + CSV 匯入 + Embedding 狀態顯示).

Spec source: 02-architecture/TEST_SPEC.md (FR-101)
SRS source : SRS.md FR-101 (Module 25: 知識管理與後台工具)
            "Knowledge 管理 WebUI：條目 CRUD 列表；Markdown 知識編輯器；
             Keywords 標籤管理；批次 CSV/JSON 匯入/匯出；
             Embedding 同步狀態顯示（已同步/同步中）；
             UI 響應時間 < 1.5s"
SAD source  : 02-architecture/SAD.md §2.4
             "Module: webui.py — Knowledge CRUD + Markdown editor +
              CSV/JSON import + embedding status (🟡🟢🔴) → FR-101"

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr101_knowledge_crud_correct
         Inputs: action="create"; title="FAQ"; expected_status="200"
         Type  : happy_path
    2. test_fr101_csv_import_succeeds
         Inputs: file_type="csv"; rows="100"; expected_imported="100"
         Type  : happy_path
    3. test_fr101_embedding_status_updates_realtime
         Inputs: chunks_synced="5"; total="10"; expected_display="同步中"
         Type  : integration (Q7/FR-79)

Sub-assertion (per TEST_SPEC):
    fr101-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Test isolation — Knowledge CRUD + CSV import touch the DB and the
# embedding-sync stream consumer (FR-79). The GREEN implementation MUST
# expose injection seams so the unit tests can run without a live
# PostgreSQL / Redis. This autouse fixture is a no-op during RED (the
# imports below raise before the fixture runs) and patches the seams
# once GREEN has landed.
#
# GREEN must:
#   - Define ``KnowledgeAdminAPI`` (or equivalent) accepting an injected
#     ``db_session`` / ``db`` callable and an injected ``embedding_sync
#     _status_provider`` callable in __init__. Tests will inject in-memory
#     stubs so no real PostgreSQL / Redis is touched.
#   - Provide a ``force_sync_status(synced: int, total: int)`` hook on
#     the embedding-status provider so tests can drive chunks_synced and
#     total into deterministic values without a real sync job.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_knowledge_admin_io(monkeypatch):
    """Prevent real DB / Redis I/O during unit tests.

    Stub the canonical DB session factory and embedding-status provider
    so a GREEN that forgets to inject dependencies still cannot escape
    into real I/O. GREEN is expected to inject explicitly; this fixture
    is the second line of defence.
    """
    # Default DB session stub: a no-op context manager returning an
    # in-memory store so CRUD operations have somewhere to land.
    class _InMemoryStore:
        def __init__(self):
            self.rows: dict = {}
            self._next_id = 1

        def add(self, obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = self._next_id
                self._next_id += 1
            self.rows[obj.id] = obj
            return obj

        def get(self, _id):
            return self.rows.get(_id)

        def delete(self, _id):
            return self.rows.pop(_id, None)

        def commit(self):
            return None

        def rollback(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.store = _InMemoryStore()

        def __enter__(self):
            return self.store

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                self.store.commit()
            else:
                self.store.rollback()
            return False

    monkeypatch.setattr(
        "app.infra.database.get_session",
        lambda: _FakeSession(),
        raising=False,
    )

    yield


# ---------------------------------------------------------------------------
# Source under test — ``KnowledgeAdminAPI`` and the embedding-status
# helpers are intentionally NOT YET exported by ``app.admin.webui``. The
# imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet. That is the valid
# RED signal.
#
# GREEN must add ``app/admin/webui.py`` exporting the following public
# surface (the exact shape is GREEN's choice so long as these names and
# behaviours are observable):
#
#   - Canonical configuration constants
#       KNOWLEDGE_API_OK_STATUS          = 200
#       KNOWLEDGE_ACTION_CREATE         = "create"
#       KNOWLEDGE_ACTION_READ           = "read"
#       KNOWLEDGE_ACTION_UPDATE         = "update"
#       KNOWLEDGE_ACTION_DELETE         = "delete"
#       KNOWLEDGE_CSV_FILE_TYPE         = "csv"
#       KNOWLEDGE_JSON_FILE_TYPE        = "json"
#       EMBEDDING_STATUS_SYNCED         = "synced"          # 🟢
#       EMBEDDING_STATUS_SYNCING        = "syncing"         # 🟡
#       EMBEDDING_STATUS_FAILED         = "failed"          # 🔴
#       EMBEDDING_DISPLAY_SYNCED        = "已同步"
#       EMBEDDING_DISPLAY_SYNCING       = "同步中"
#       EMBEDDING_DISPLAY_FAILED        = "同步失敗"
#       KNOWLEDGE_UI_RESPONSE_LIMIT_MS  = 1500
#
#   - KnowledgeAdminAPI
#       Top-level dispatcher for the Knowledge 管理 WebUI. Required
#       attributes / methods:
#           __init__(db_session=None, embedding_status_provider=None)
#               Store the injected DB session factory and embedding
#               status provider. Tests will inject in-memory stubs.
#           create_entry(title: str, content: str, keywords: list = [])
#               -> KnowledgeEntry
#               Create a new knowledge row; return the persisted entry
#               (id is assigned). The test inspects the returned
#               entry's status to confirm the create succeeded (the FR
#               pins expected_status=200 for the create leg).
#           read_entry(entry_id: int) -> KnowledgeEntry | None
#               Fetch an entry by id; return None if absent.
#           update_entry(entry_id: int, **fields) -> KnowledgeEntry | None
#               Update an entry in place; return the refreshed entry or
#               None if absent.
#           delete_entry(entry_id: int) -> bool
#               Remove the entry; return True iff a row was deleted.
#           crud(action: str, **kwargs) -> dict
#               Single dispatcher that maps the FR-101 webUI's "action"
#               parameter to create/read/update/delete. Returns a dict
#               with at least the keys "status" (int), "entry"
#               (KnowledgeEntry | None), and "ok" (bool). The FR's
#               expected_status="200" pins the create leg to status=200.
#           import_csv(file_bytes: bytes, filename: str = "kb.csv")
#               -> ImportResult
#               Parse the CSV bytes (columns: title, content, keywords)
#               and persist each row as a KnowledgeEntry. The returned
#               ImportResult MUST carry an "imported" integer equal to
#               the row count (FR pins expected_imported="100" for a
#               100-row CSV).
#           get_embedding_status(entry_id: int | None = None) -> dict
#               Look up the current embedding sync status. Returns a
#               dict with at least the keys "chunks_synced" (int),
#               "total" (int), "display" (str). The FR's
#               expected_display="同步中" pins the in-progress state to
#               the canonical Chinese string.
#
#   - ImportResult
#       Required attributes / methods:
#           imported: int   (rows persisted)
#           skipped:  int   (rows rejected for any reason)
#           errors:   list  (per-row error messages)
#
#   - KnowledgeEntry
#       Required attributes / methods:
#           id:       int | None
#           title:    str
#           content:  str
#           keywords: list[str]
#           embedding_status:        str  (one of the EMBEDDING_STATUS_*)
#           embedding_chunks_synced: int
#           embedding_chunks_total:  int
#
#   - EmbeddingStatusProvider
#       Required attributes / methods:
#           __init__(default_synced: int = 0, default_total: int = 0)
#               Default to "0 of 0 synced" so an unconfigured provider
#               reports the canonical "nothing has synced yet" state.
#           get_status(entry_id: int | None = None) -> dict
#               Return {"chunks_synced": int, "total": int, "display":
#               str, "status": str}.
#           force_sync_status(synced: int, total: int) -> None
#               Drive the provider into a deterministic chunks_synced /
#               total pair so tests can pin the display string for
#               known progress values (5 of 10 → "同步中").
#
# The tests below intentionally avoid any real PostgreSQL / Redis I/O —
# they exercise the KnowledgeAdminAPI + EmbeddingStatusProvider
# abstraction in isolation, which is the canonical unit-test shape for
# FR-101.
# ---------------------------------------------------------------------------
from app.admin.webui import (  # noqa: E402,F401
    KnowledgeAdminAPI,
    KnowledgeEntry,
    ImportResult,
    EmbeddingStatusProvider,
    # Constants — re-exported so the tests assert against the same
    # values the production code uses (and so the harness sees the same
    # names in the import surface as GREEN must expose).
    KNOWLEDGE_API_OK_STATUS,
    KNOWLEDGE_ACTION_CREATE,
    KNOWLEDGE_ACTION_READ,
    KNOWLEDGE_ACTION_UPDATE,
    KNOWLEDGE_ACTION_DELETE,
    KNOWLEDGE_CSV_FILE_TYPE,
    KNOWLEDGE_JSON_FILE_TYPE,
    EMBEDDING_STATUS_SYNCED,
    EMBEDDING_STATUS_SYNCING,
    EMBEDDING_STATUS_FAILED,
    EMBEDDING_DISPLAY_SYNCED,
    EMBEDDING_DISPLAY_SYNCING,
    EMBEDDING_DISPLAY_FAILED,
    KNOWLEDGE_UI_RESPONSE_LIMIT_MS,
)


# ---------------------------------------------------------------------------
# 1. Knowledge CRUD operation completes successfully (happy_path).
#
# Spec input: action="create"; title="FAQ"; expected_status="200".
# SRS FR-101: "Knowledge 管理 WebUI：條目 CRUD 列表；Markdown 知識編輯器；
# Keywords 標籤管理". A regression that returned a non-200 status on
# create would break the WebUI's post-create redirect; a regression that
# silently dropped the row would break the listing reload.
# ---------------------------------------------------------------------------
def test_fr101_knowledge_crud_correct():
    # Spec input literals — also used as trigger values for the
    # fr101-ok sub-assertion guard.
    action = "create"  # spec string sentinel
    title = "FAQ"
    expected_status = "200"  # spec string sentinel

    # GREEN TODO: ``KNOWLEDGE_API_OK_STATUS`` MUST equal 200 — the
    # canonical HTTP status for a successful CRUD operation.
    assert KNOWLEDGE_API_OK_STATUS == 200, (
        f"FR-101 KNOWLEDGE_API_OK_STATUS must be 200; got "
        f"{KNOWLEDGE_API_OK_STATUS!r}"
    )

    # GREEN TODO: the four KNOWLEDGE_ACTION_* constants MUST carry the
    # canonical WebUI action names so the dispatcher and the
    # spec-input "action='create'" key can be matched exactly.
    assert KNOWLEDGE_ACTION_CREATE == "create", (
        f"FR-101 KNOWLEDGE_ACTION_CREATE must be 'create'; got "
        f"{KNOWLEDGE_ACTION_CREATE!r}"
    )
    assert KNOWLEDGE_ACTION_READ == "read", (
        f"FR-101 KNOWLEDGE_ACTION_READ must be 'read'; got "
        f"{KNOWLEDGE_ACTION_READ!r}"
    )
    assert KNOWLEDGE_ACTION_UPDATE == "update", (
        f"FR-101 KNOWLEDGE_ACTION_UPDATE must be 'update'; got "
        f"{KNOWLEDGE_ACTION_UPDATE!r}"
    )
    assert KNOWLEDGE_ACTION_DELETE == "delete", (
        f"FR-101 KNOWLEDGE_ACTION_DELETE must be 'delete'; got "
        f"{KNOWLEDGE_ACTION_DELETE!r}"
    )

    # GREEN TODO: ``KnowledgeAdminAPI`` MUST expose a ``crud(action, ...)``
    # dispatcher and a dedicated ``create_entry(title, content, ...)``
    # entry point. Both forms are checked below so GREEN may pick
    # either or both.
    api = KnowledgeAdminAPI()
    assert hasattr(api, "crud") and callable(api.crud), (
        "FR-101 KnowledgeAdminAPI must expose ``crud(action, **kwargs)``"
    )
    assert hasattr(api, "create_entry") and callable(api.create_entry), (
        "FR-101 KnowledgeAdminAPI must expose "
        "``create_entry(title, content, keywords=[])``"
    )

    # Drive the create leg through both surfaces so a regression in
    # either branch is caught.
    crud_result = api.crud(action=action, title=title, content="FAQ body")
    create_result = api.create_entry(
        title="FAQ-row-2", content="second row", keywords=["kb"]
    )

    # Spec fr101-ok predicate: result is not None (applies_to case 1).
    if action == "create":
        assert crud_result is not None, (
            "fr101-ok predicate: crud() result must not be None"
        )
        assert create_result is not None, (
            "FR-101 create_entry() must return a KnowledgeEntry; got None"
        )

    # The ``crud(action='create')`` result MUST report status=200 — the
    # FR's "expected_status='200'" guarantee. A GREEN that returned
    # status=201 (REST-strict) or status=204 would break the WebUI
    # redirect contract that the spec pins to "200".
    assert isinstance(crud_result, dict), (
        f"FR-101 crud() must return a dict; got "
        f"{type(crud_result).__name__}"
    )
    if expected_status == "200":
        observed_status = crud_result.get("status")
        assert observed_status == 200, (
            f"FR-101 knowledge CRUD create must return status=200; got "
            f"status={observed_status!r}"
        )

    # Companion invariant: the persisted entry MUST carry the title
    # the create call passed in. A GREEN that stored the title under
    # a different key (or dropped it) would break the list view.
    create_title = (
        create_result.title
        if not callable(getattr(create_result, "title", None))
        else create_result.title()
    )
    assert create_title == "FAQ-row-2", (
        f"FR-101 create_entry must persist the title verbatim; got "
        f"title={create_title!r}"
    )


# ---------------------------------------------------------------------------
# 2. CSV import succeeds and the imported-row count matches the source
#    file (happy_path).
#
# Spec input: file_type="csv"; rows="100"; expected_imported="100".
# SRS FR-101: "批次 CSV/JSON 匯入/匯出". A regression that imported only
# a partial subset would leave the editor's preview out of sync with
# the DB; a regression that returned a non-int ``imported`` value would
# break the WebUI's progress counter.
# ---------------------------------------------------------------------------
def test_fr101_csv_import_succeeds():
    # Spec input literals.
    file_type = "csv"  # spec string sentinel
    rows = "100"
    expected_imported = "100"  # spec string sentinel

    # GREEN TODO: ``KNOWLEDGE_CSV_FILE_TYPE`` MUST equal "csv" — the
    # canonical CSV file-type identifier used by the import dispatcher
    # and the WebUI's MIME-type probe.
    assert KNOWLEDGE_CSV_FILE_TYPE == "csv", (
        f"FR-101 KNOWLEDGE_CSV_FILE_TYPE must be 'csv'; got "
        f"{KNOWLEDGE_CSV_FILE_TYPE!r}"
    )

    # Companion invariant: ``KNOWLEDGE_JSON_FILE_TYPE`` MUST equal
    # "json" — the SRS FR-101 also lists JSON export/import as a
    # supported surface, so the constant MUST exist alongside CSV.
    assert KNOWLEDGE_JSON_FILE_TYPE == "json", (
        f"FR-101 KNOWLEDGE_JSON_FILE_TYPE must be 'json'; got "
        f"{KNOWLEDGE_JSON_FILE_TYPE!r}"
    )

    # GREEN TODO: ``KnowledgeAdminAPI.import_csv(file_bytes, filename)``
    # MUST exist and return an ``ImportResult`` whose ``imported``
    # attribute is an int equal to the number of rows in the source
    # CSV.
    api = KnowledgeAdminAPI()
    assert hasattr(api, "import_csv") and callable(api.import_csv), (
        "FR-101 KnowledgeAdminAPI must expose "
        "``import_csv(file_bytes, filename='kb.csv') -> ImportResult``"
    )

    # Build a synthetic 100-row CSV in-memory. The CSV header is
    # canonical (title, content, keywords) per the FR-101 spec; the
    # keyword column is pipe-delimited so a single row can carry
    # multiple tags.
    header = "title,content,keywords\n"
    body_lines = [
        f"FAQ-{i},body-{i},kb|faq\n" for i in range(int(rows))
    ]
    csv_bytes = (header + "".join(body_lines)).encode("utf-8")

    result = api.import_csv(csv_bytes, filename=f"kb.{file_type}")

    assert result is not None, (
        "FR-101 import_csv() must return an ImportResult; got None"
    )

    # The ``imported`` count MUST equal the row count from the source
    # CSV — the FR's "expected_imported='100'" guarantee. A GREEN that
    # returned imported=99 (off-by-one) or imported=0 (silent drop)
    # would break the WebUI's "X / 100 imported" progress counter.
    assert hasattr(result, "imported"), (
        "FR-101 ImportResult must expose ``imported``"
    )
    observed_imported = (
        result.imported()
        if callable(getattr(result, "imported", None))
        else result.imported
    )
    if expected_imported == "100":
        assert observed_imported == int(rows), (
            f"FR-101 CSV import must report imported={rows}; got "
            f"imported={observed_imported!r}"
        )

    # Companion invariant: ``imported`` MUST be a plain int so the
    # WebUI can format it directly. A GREEN that returned a string
    # ("100") would force the UI to call int() and break the
    # progress-bar arithmetic.
    assert isinstance(observed_imported, int), (
        f"FR-101 imported count must be an int; got "
        f"{type(observed_imported).__name__}"
    )
    assert not isinstance(observed_imported, bool), (
        "FR-101 imported count must be a real int (not bool); got bool"
    )


# ---------------------------------------------------------------------------
# 3. Embedding sync status updates in real time and renders the canonical
#    "同步中" label when chunks_synced < total (integration Q7/FR-79).
#
# Spec input: chunks_synced="5"; total="10"; expected_display="同步中".
# SRS FR-101: "Embedding 同步狀態顯示（已同步/同步中）". FR-79 (the
# underlying sync-state UI) defines the same three states — 🟡/🟢/🔴.
# A regression that rendered the in-progress state as "已同步" (already
# done) would lie to the editor; a regression that returned the raw int
# (5) would skip the human-readable label.
# ---------------------------------------------------------------------------
def test_fr101_embedding_status_updates_realtime():
    # Spec input literals.
    chunks_synced = "5"  # spec string sentinel
    total = "10"
    expected_display = "同步中"  # spec string sentinel

    # GREEN TODO: the three EMBEDDING_DISPLAY_* constants MUST carry
    # the canonical Chinese labels so the WebUI and the spec
    # expected_display="同步中" string can be matched exactly.
    assert EMBEDDING_DISPLAY_SYNCED == "已同步", (
        f"FR-101 EMBEDDING_DISPLAY_SYNCED must be '已同步'; got "
        f"{EMBEDDING_DISPLAY_SYNCED!r}"
    )
    assert EMBEDDING_DISPLAY_SYNCING == "同步中", (
        f"FR-101 EMBEDDING_DISPLAY_SYNCING must be '同步中'; got "
        f"{EMBEDDING_DISPLAY_SYNCING!r}"
    )
    assert EMBEDDING_DISPLAY_FAILED == "同步失敗", (
        f"FR-101 EMBEDDING_DISPLAY_FAILED must be '同步失敗'; got "
        f"{EMBEDDING_DISPLAY_FAILED!r}"
    )

    # Companion invariant: the three EMBEDDING_STATUS_* machine codes
    # MUST exist and map 1:1 to the three display labels (the FR-79
    # source-of-truth for the state machine).
    assert EMBEDDING_STATUS_SYNCED == "synced", (
        f"FR-101 EMBEDDING_STATUS_SYNCED must be 'synced'; got "
        f"{EMBEDDING_STATUS_SYNCED!r}"
    )
    assert EMBEDDING_STATUS_SYNCING == "syncing", (
        f"FR-101 EMBEDDING_STATUS_SYNCING must be 'syncing'; got "
        f"{EMBEDDING_STATUS_SYNCING!r}"
    )
    assert EMBEDDING_STATUS_FAILED == "failed", (
        f"FR-101 EMBEDDING_STATUS_FAILED must be 'failed'; got "
        f"{EMBEDDING_STATUS_FAILED!r}"
    )

    # Companion invariant: the UI response-time SLA (SRS FR-101
    # "UI 響應時間 < 1.5s") MUST be exposed as a numeric constant so
    # the test can assert against the same value the production code
    # uses.
    assert KNOWLEDGE_UI_RESPONSE_LIMIT_MS == 1500, (
        f"FR-101 KNOWLEDGE_UI_RESPONSE_LIMIT_MS must be 1500; got "
        f"{KNOWLEDGE_UI_RESPONSE_LIMIT_MS!r}"
    )

    # GREEN TODO: ``EmbeddingStatusProvider`` MUST expose
    # ``force_sync_status(synced, total)`` so tests can drive the
    # status into a deterministic state without a real sync job.
    provider = EmbeddingStatusProvider()
    assert hasattr(provider, "force_sync_status") and callable(
        provider.force_sync_status
    ), (
        "FR-101 EmbeddingStatusProvider must expose "
        "``force_sync_status(synced: int, total: int) -> None``"
    )
    assert hasattr(provider, "get_status") and callable(
        provider.get_status
    ), (
        "FR-101 EmbeddingStatusProvider must expose "
        "``get_status(entry_id: int | None = None) -> dict``"
    )

    # Drive the provider into the spec's "5 of 10 chunks synced" state
    # (the in-progress branch the WebUI labels as "同步中").
    provider.force_sync_status(
        synced=int(chunks_synced), total=int(total)
    )

    # GREEN TODO: ``KnowledgeAdminAPI.get_embedding_status(...)`` MUST
    # read from the injected provider and return a dict whose
    # ``display`` field carries the canonical Chinese label.
    api = KnowledgeAdminAPI(embedding_status_provider=provider)
    assert hasattr(api, "get_embedding_status") and callable(
        api.get_embedding_status
    ), (
        "FR-101 KnowledgeAdminAPI must expose "
        "``get_embedding_status(entry_id: int | None = None) -> dict``"
    )

    status = api.get_embedding_status()

    assert status is not None, (
        "FR-101 get_embedding_status() must return a dict; got None"
    )
    assert isinstance(status, dict), (
        f"FR-101 get_embedding_status() must return a dict; got "
        f"{type(status).__name__}"
    )

    # The chunks_synced / total fields MUST echo the values the
    # provider was forced into — a GREEN that cached a stale value
    # would break the "real-time" guarantee.
    assert status.get("chunks_synced") == int(chunks_synced), (
        f"FR-101 embedding status chunks_synced must equal "
        f"{chunks_synced}; got {status.get('chunks_synced')!r}"
    )
    assert status.get("total") == int(total), (
        f"FR-101 embedding status total must equal {total}; got "
        f"{status.get('total')!r}"
    )

    # The display field MUST be "同步中" — the FR's
    # expected_display guarantee for the in-progress branch. A GREEN
    # that mapped 5-of-10 to "已同步" (synced) would lie to the
    # editor; a GREEN that returned the raw int (5) would skip the
    # human-readable label and break the WebUI's status column.
    if expected_display == "同步中":
        observed_display = status.get("display")
        assert observed_display == "同步中", (
            f"FR-101 embedding status display must be '同步中' for "
            f"5-of-10 progress; got display={observed_display!r}"
        )
