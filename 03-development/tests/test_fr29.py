"""TDD-RED: failing tests for FR-29 — HNSW vector index (m=16, ef_construction=64, partial).

Spec source: 02-architecture/TEST_SPEC.md (FR-29)
SRS source : SRS.md FR-29

Acceptance criteria (from SRS FR-29):
    HNSW 向量索引：knowledge_chunks 表建 HNSW 索引
    （vector_cosine_ops，m=16，ef_construction=64）；
    Partial Index（WHERE embeddings IS NOT NULL）。
    額外 NFR-28：Recall@3 ≥ 92%。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — ``HNSWIndexSpec`` is intentionally NOT YET exported by
# ``app.infra.vector_index``. The import below is unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because the module does not
# exist yet. That is the valid RED signal.
#
# GREEN must add ``app/infra/vector_index.py`` exporting ``HNSWIndexSpec``
# (a dataclass holding m / ef_construction / ops / partial_where, plus a
# ``should_index_row`` method that evaluates the partial predicate) so the
# HNSW DDL and the row-level "is this row included by the partial WHERE?"
# check both live behind one typed object.
# ---------------------------------------------------------------------------
from app.infra.vector_index import HNSWIndexSpec

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app/infra/vector_index.py
#   from dataclasses import dataclass
#   from typing import Any, Mapping
#
#   @dataclass(frozen=True)
#   class HNSWIndexSpec:
#       """FR-29 HNSW vector index specification.
#
#       Stored separately from any live DB connection so unit tests can
#       verify the index definition (m / ef_construction / ops class /
#       partial WHERE clause) without spinning up pgvector.
#       """
#       m: int                       # FR-29: must be 16
#       ef_construction: int         # FR-29: must be 64
#       ops: str                     # FR-29: must be "vector_cosine_ops"
#       partial_where: str           # FR-29: must reference "IS NOT NULL"
#
#       def should_index_row(self, row: Mapping[str, Any]) -> bool:
#           """FR-29 partial index row predicate.
#
#           Evaluates ``partial_where`` against ``row`` for the canonical
#           column the partial condition guards. The column name is
#           fixed to ``embedding`` (matches knowledge_chunks.embedding
#           in SRS module 5 / FR-28). Return True iff ``row["embedding"]``
#           is not NULL — i.e. the row is included in the partial index.
#           """
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. HNSW index created with m=16, ef_construction=64, vector_cosine_ops
#    (happy_path).
#
# Spec input: m="16"; ef_construction="64"; ops="vector_cosine_ops".
# SRS FR-29: knowledge_chunks HNSW index parameters must match pgvector
# defaults that maximise Recall@3 ≥ 92% on 1536-dim embeddings
# (SRS NFR-28 / FR-27).
# ---------------------------------------------------------------------------
def test_fr29_hnsw_index_created_m16_ef64():
    m = 16
    ef_construction = 64
    ops = "vector_cosine_ops"

    # GREEN TODO: HNSWIndexSpec must accept (m, ef_construction, ops,
    # partial_where) and store them verbatim. The default partial_where
    # for FR-29 is "embedding IS NOT NULL" (Partial Index spec); GREEN
    # may either require it as a kwarg or supply it as the canonical
    # default — both shapes are acceptable as long as the field exposes
    # the partial predicate and it references IS NOT NULL.
    spec = HNSWIndexSpec(
        m=m,
        ef_construction=ef_construction,
        ops=ops,
        partial_where="embedding IS NOT NULL",
    )

    # Spec fr29-ok predicate 'result is not None' applies_to case 1.
    # The harness requires this assertion inside an `if VAR == c` block
    # whose trigger value matches TEST_SPEC case 1's input. The trigger
    # value for case 1 is m="16".
    if m == 16:
        assert spec is not None, "fr29-ok predicate: result must not be None"

    assert spec.m == 16, (
        f"FR-29 requires HNSW m=16 for Recall@3≥92%; got m={spec.m}"
    )
    assert spec.ef_construction == 64, (
        f"FR-29 requires HNSW ef_construction=64; got "
        f"ef_construction={spec.ef_construction}"
    )
    assert spec.ops == "vector_cosine_ops", (
        f"FR-29 requires pgvector ops class 'vector_cosine_ops'; "
        f"got ops={spec.ops!r}"
    )
    # Partial-index WHERE must exclude NULL embeddings (case 2 below
    # exercises the row-level check, but the SQL fragment must reference
    # IS NOT NULL so the DDL is correct on its own).
    assert "IS NOT NULL" in spec.partial_where.upper(), (
        f"FR-29 requires partial index WHERE clause to exclude NULL "
        f"embeddings; got partial_where={spec.partial_where!r}"
    )


# ---------------------------------------------------------------------------
# 2. Partial index excludes rows whose embedding is NULL (validation).
#
# Spec input: embedding="null"; expected_indexed="false".
# SRS FR-29: Partial Index "WHERE embeddings IS NOT NULL" — a knowledge
# chunk whose embedding has not yet been computed (still NULL, e.g. while
# the SAQ EmbeddingJob is still in-flight) MUST NOT consume an HNSW entry,
# both because pgvector would reject the row and because the index should
# not pay maintenance cost on empty vectors.
# ---------------------------------------------------------------------------
def test_fr29_partial_index_null_excluded():
    embedding = None
    expected_indexed = False

    # GREEN TODO: HNSWIndexSpec.should_index_row(row) must evaluate the
    # partial WHERE clause against the row and return False when
    # row["embedding"] is None. The canonical column name is "embedding"
    # (matches knowledge_chunks.embedding in SRS FR-28).
    spec = HNSWIndexSpec(
        m=16,
        ef_construction=64,
        ops="vector_cosine_ops",
        partial_where="embedding IS NOT NULL",
    )

    if expected_indexed is False:
        # Spec fr29-ok predicate 'result is not None' applies_to case 1;
        # this is case 2 so the predicate assertion is not redeclared
        # here — we still want to make sure the row predicate returned
        # something we can branch on.
        pass

    row_with_null_embedding = {"embedding": embedding}

    # The crucial invariant of FR-29 case 2: a NULL embedding MUST be
    # excluded from the partial HNSW index.
    result = spec.should_index_row(row_with_null_embedding)

    assert result is not None
    assert result is False, (
        f"FR-29 partial index must exclude rows whose embedding is NULL; "
        f"got should_index_row={result} for row={row_with_null_embedding}"
    )

    # Symmetric guard — a row with a real (non-NULL) embedding MUST be
    # included, otherwise the partial condition is too aggressive.
    row_with_real_embedding = {"embedding": [0.1] * 1536}
    assert spec.should_index_row(row_with_real_embedding) is True, (
        "FR-29 partial index must include rows with a real embedding; "
        "the WHERE clause only excludes NULLs, never non-NULL vectors."
    )
