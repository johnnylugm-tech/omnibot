"""[FR-29] HNSW vector index specification for ``knowledge_chunks``.

The HNSW DDL and the row-level "is this row included by the partial WHERE?"
check both live behind one typed object, so unit tests can verify the
index definition (m / ef_construction / ops class / partial WHERE clause)
without spinning up pgvector.

[FR-29] ``knowledge_chunks`` table MUST build an HNSW index using
       ``vector_cosine_ops`` with ``m=16`` and ``ef_construction=64``.
       A Partial Index (WHERE embedding IS NOT NULL) keeps NULL embeddings
       out of the index so pgvector never has to validate them and the
       index does not pay maintenance cost on empty vectors.

Citations:
- SRS.md FR-29 (description line 65, spec block lines 621-626)
- SRS.md NFR-28 (Recall@3 ≥ 92%, line 102)
- 02-architecture/TEST_SPEC.md FR-29 (HNSW m=16 / ef=64 / partial WHERE)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HNSWIndexSpec:
    """[FR-29] HNSW vector index specification.

    Attributes:
        m: HNSW max-connections per node per layer. SRS FR-29 mandates 16.
        ef_construction: HNSW candidate-list size during build. SRS FR-29
            mandates 64.
        ops: pgvector ops class. SRS FR-29 mandates ``vector_cosine_ops``.
        partial_where: SQL fragment for the Partial Index predicate.
            SRS FR-29 mandates a clause referencing ``IS NOT NULL`` on the
            embedding column so rows whose embedding has not yet been
            computed are excluded from the index.
    """

    m: int
    ef_construction: int
    ops: str
    partial_where: str

    def should_index_row(self, row: Mapping[str, Any]) -> bool:
        """[FR-29] Partial index row predicate.

        Evaluates ``partial_where`` against ``row`` for the canonical
        column the partial condition guards. The column name is fixed to
        ``embedding`` (matches ``knowledge_chunks.embedding`` in SRS FR-28).

        Returns:
            True iff ``row["embedding"]`` is not None — i.e. the row is
            included in the partial index. A row whose embedding is None
            (still in-flight from the SAQ EmbeddingJob, for example) is
            excluded so pgvector never has to validate an empty vector
            and the index pays no maintenance cost on it.
        """
        return row.get("embedding") is not None