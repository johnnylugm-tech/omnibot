"""[FR-28] Parent-Child Chunking (500-token parent / 150-token child).

Spec source: 02-architecture/TEST_SPEC.md (FR-28)
SRS source : SRS.md FR-28

FR-28 -- Parent-Child Chunking:
    Parent = 500 tokens (100 token overlap), Child = 150 tokens;
    Only Child Chunks build a vector index; vector hit on Child ->
    trace back to the corresponding Parent for LLM input.

This module exposes the SRS-mandated numeric constants plus three small
classes — :class:`ChunkSpec`, :class:`Chunker`, :class:`ParentChildIndex`
— that wire the parent/child relationship together. Tokenisation here
captures both word runs and whitespace runs (``re.findall(r"\\S+|\\s+", text)``)
so chunk content round-trips through tokenise → join without losing
tabs, newlines, or runs of consecutive spaces; a real BPE/SentencePiece
splitter slots in behind the same interface in production.

Citations:
    - SRS.md FR-28 -- Parent = 500 tokens (100 token overlap), Child = 150
      tokens (line 107).
    - SRS.md FR-28 -- Only Child Chunks build a vector index (line 108).
    - SRS.md FR-28 -- Vector hit on Child -> trace back to corresponding
      Parent for LLM input (line 109).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SRS-mandated numeric constants. The wiring layer reads these directly so
# they MUST agree with the :class:`ChunkSpec` defaults below.
# ---------------------------------------------------------------------------
PARENT_TOKEN_SIZE: int = 500
CHILD_TOKEN_SIZE: int = 150
OVERLAP_TOKENS: int = 100


@dataclass(frozen=True)
class ChunkSpec:
    """[FR-28] Chunking parameters — defaults match the SRS constants.

    ``parent_size`` (500) and ``child_size`` (150) are the two chunk
    sizes SRS FR-28 mandates; ``parent_child_overlap`` (100) is the
    sliding-window overlap that lets adjacent parent chunks share a
    tail so a child chunk does not straddle an arbitrary parent
    boundary.

    Citations:
        - SRS.md FR-28 -- Parent = 500 tokens (100 token overlap).
    """

    parent_size: int = PARENT_TOKEN_SIZE
    child_size: int = CHILD_TOKEN_SIZE
    parent_child_overlap: int = OVERLAP_TOKENS


@dataclass(frozen=True)
class Chunk:
    """[FR-28] A single parent or child chunk returned by :class:`Chunker`.

    ``chunk_type`` is one of ``"parent"`` / ``"child"``; parent chunks
    carry ``parent_id=None`` while child chunks carry the ``chunk_id``
    of the parent they belong to (the FK the vector-hit-walks-parent
    path follows).

    Citations:
        - SRS.md FR-28 — Child 追索對應 Parent 送 LLM.
    """

    chunk_id: str
    content: str
    chunk_type: str  # "parent" | "child"
    parent_id: str | None
    token_count: int


def _tokenize(text: str) -> list[str]:
    """Whitespace-aware tokenisation that preserves original spacing (M-08).

    Captures both word runs (``\\S+``) and whitespace runs (``\\s+``) as
    separate tokens, so ``"".join(tokens)`` round-trips to the original
    text. Pure ``str.split()`` collapses consecutive whitespace and loses
    tabs, newlines, and indentation — those are part of the document's
    surface form and must survive chunking.
    """
    return re.findall(r"\S+|\s+", text)


def _slice_tokens(
    tokens: list[str],
    size: int,
    *,
    prefix: str,
    chunk_type: str,
    parent_id_for: Callable[[int, int], str | None],
    overlap: int = 0,
) -> list[Chunk]:
    """Slice ``tokens`` into fixed-size windows and wrap each as a :class:`Chunk`.

    ``overlap`` is the number of tokens shared between adjacent windows
    (``step = size - overlap``). With ``overlap=0`` the windows tile the
    stream with no shared tokens; with ``overlap=parent_child_overlap``
    (100 by default) parent windows form a sliding window so a child
    chunk straddling the boundary can be resolved against either parent
    via the child→parent FK.

    ``parent_id_for(idx, start)`` resolves the parent FK for the chunk at
    position ``idx`` whose first token sits at ``start``; parents pass a
    callable that returns ``None``.
    """
    if not tokens or not "".join(tokens).strip():
        # L-04: signal that empty/whitespace input was silently dropped
        # before it can mislead a downstream RAG caller.
        raise ValueError(
            "chunking._slice_tokens: empty/whitespace-only input produced 0 chunks; "
            "check that the source text contains non-whitespace characters"
        )
    if size <= 0:
        raise ValueError(f"_slice_tokens size must be positive; got {size}")
    if overlap < 0 or overlap >= size:
        raise ValueError(
            f"_slice_tokens overlap must satisfy 0 <= overlap < size; "
            f"got overlap={overlap}, size={size}"
        )

    step = size - overlap
    chunks: list[Chunk] = []
    for idx, start in enumerate(range(0, len(tokens), step)):
        piece = tokens[start : start + size]
        if not piece:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{prefix}-{idx}",
                content="".join(piece),
                chunk_type=chunk_type,
                parent_id=parent_id_for(idx, start),
                token_count=len(piece),
            )
        )
    return chunks


class Chunker:
    """[FR-28] Slices text into 500-token parents and 150-token children.

    The chunker is stateless apart from its :class:`ChunkSpec`; pass a
    custom spec to override sizes for tests. ``split_children`` derives
    each child's ``parent_id`` from its token offset against the parent
    boundary so the child→parent walk works without an external DB.

    Citations:
        - SRS.md FR-28 -- Parent = 500 tokens; Child = 150 tokens.
    """

    def __init__(self, spec: ChunkSpec | None = None) -> None:
        self._spec = spec or ChunkSpec()

    def split_parents(self, text: str) -> list[Chunk]:
        """[FR-28] Slice ``text`` into 500-token parent chunks with 100-token overlap (H-16).

        ``parent_child_overlap`` (100 by default) makes adjacent parents
        share a 100-token tail so a child chunk straddling the boundary
        can be resolved against either parent. The child→parent FK
        ``f"parent-{start // parent_size}"`` picks the parent whose
        window starts at or before the child's first token, which is a
        valid covering parent for any child that uses it.
        """
        return _slice_tokens(
            _tokenize(text),
            self._spec.parent_size,
            prefix="parent",
            chunk_type="parent",
            parent_id_for=lambda _idx, _start: None,
            overlap=self._spec.parent_child_overlap,
        )

    def split_children(self, text: str) -> list[Chunk]:
        """[FR-28] Slice ``text`` into 150-token child chunks (no overlap).

        Each child is annotated with the ``parent_id`` of the parent it
        belongs to (computed from the token offset against
        ``spec.parent_size``) so the retrieval path can walk a vector hit
        on a child back to its parent context block.

        Citations:
            - SRS.md FR-28 -- Child = 150 tokens; trace back Parent for LLM.
        """
        parent_size = self._spec.parent_size

        def parent_id(_idx: int, start: int) -> str:
            return f"parent-{start // parent_size}" if parent_size > 0 else "parent-0"

        return _slice_tokens(
            _tokenize(text),
            self._spec.child_size,
            prefix="child",
            chunk_type="child",
            parent_id_for=parent_id,
        )


class ParentChildIndex:
    """[FR-28] In-memory child→parent wiring for vector-hit-walks-parent.

    The production implementation reads from the ``knowledge_chunks``
    table; this in-memory variant exists so unit tests can wire a
    ``child_id`` → ``parent_id`` mapping without standing up PostgreSQL.
    Only child chunks are vector-indexed — parents are reached by walking
    the child hit's FK, never by similarity search.

    Parents are NEVER seeded with empty content. ``add_link`` requires
    the caller to supply real ``parent_content`` (or to register the
    parent via :meth:`add_parent` first); ``retrieve_parent`` rejects
    empty content rather than handing an empty string to the LLM (H-17).

    Citations:
        - SRS.md FR-28 — 僅 Child Chunks 建向量索引;向量命中 Child 追索
          對應 Parent.
    """

    def __init__(self) -> None:
        self._links: dict[str, str] = {}
        self._parents: dict[str, Chunk] = {}

    def add_link(
        self,
        child_id: str,
        parent_id: str,
        parent_content: str,
    ) -> None:
        """[FR-28] Wire ``child_id`` → ``parent_id`` and seed the parent with real content (H-17).

        ``parent_content`` MUST be non-empty. An empty string would
        propagate to the LLM as the parent context and silently disable
        the RAG retrieval path's main signal. Use :meth:`add_parent` to
        register a parent :class:`Chunk` with richer metadata (actual
        ``token_count``, etc.).
        """
        if not parent_content:
            raise ValueError(
                f"add_link requires non-empty parent_content for "
                f"parent_id={parent_id!r}; empty content would propagate "
                f"to the LLM (H-17). Use add_parent() to register a "
                f"parent chunk with real content."
            )
        self._links[child_id] = parent_id
        self._parents[parent_id] = Chunk(
            chunk_id=parent_id,
            content=parent_content,
            chunk_type="parent",
            parent_id=None,
            token_count=PARENT_TOKEN_SIZE,
        )

    def add_parent(self, parent: Chunk) -> None:
        """[FR-28] Register a parent :class:`Chunk` with real content (H-17).

        Raises ``ValueError`` if ``parent.chunk_type`` is not ``"parent"``
        or if ``parent.content`` is empty — the LLM must never receive
        an empty string as parent context.
        """
        if parent.chunk_type != "parent":
            raise ValueError(
                f"add_parent requires chunk_type='parent'; "
                f"got chunk_type={parent.chunk_type!r}"
            )
        if not parent.content:
            raise ValueError(
                "add_parent requires non-empty content; "
                "LLM must not receive empty string as parent context (H-17)"
            )
        self._parents[parent.chunk_id] = parent

    def is_vector_indexed(self, chunk: Chunk) -> bool:
        """[FR-28] Return True iff ``chunk`` is a child chunk.

        Parents are never vector-indexed; only children populate the
        HNSW index. Returning the decision as a deterministic ``bool``
        lets callers use the value directly in conditional branches.

        Citations:
            - SRS.md FR-28 — 僅 Child Chunks 建向量索引.
        """
        return chunk.chunk_type == "child"

    def retrieve_parent(self, child_id: str) -> Chunk | None:
        """[FR-28] Walk ``child_id`` → ``parent_id`` → parent Chunk (H-17).

        Returns the parent :class:`Chunk` the LLM (Tier 3) actually
        consumes, or ``None`` if the child has no registered parent or
        the registered parent has empty content (refused to avoid
        handing the LLM an empty string). The returned chunk's
        ``chunk_id`` is the parent identifier, not the ``child_id`` we
        queried with.

        Citations:
            - SRS.md FR-28 — 向量命中 Child → 追索對應 Parent 送 LLM.
        """
        parent_id = self._links.get(child_id)
        if parent_id is None:
            return None
        parent = self._parents.get(parent_id)
        if parent is None or not parent.content:
            return None
        return parent
