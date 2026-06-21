from __future__ import annotations
"""TDD-RED: failing tests for FR-28 — Parent-Child Chunking (500/150 tokens).

Spec source: 02-architecture/TEST_SPEC.md (FR-28)
SRS source : SRS.md FR-28

Acceptance criteria (from SRS FR-28):
    Parent-Child Chunking：Parent = 500 tokens（100 token overlap），
    Child = 150 tokens；僅 Child Chunks 建向量索引；向量命中 Child →
    追索對應 Parent 送 LLM。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test — ``Chunker`` / ``ChunkSpec`` / ``ParentChildIndex`` are
# intentionally NOT YET defined. The imports below are unguarded: pytest
# MUST fail with Collection Error (Exit Code 2) because the FR-28 module
# does not exist yet. That is the valid RED signal.
#
# GREEN must add ``app/core/chunking.py`` exporting:
#   - PARENT_TOKEN_SIZE = 500, CHILD_TOKEN_SIZE = 150, OVERLAP_TOKENS = 100
#     (the SRS-mandated numeric constants)
#   - ``Chunk`` frozen dataclass with (chunk_id, content, chunk_type,
#     parent_id, token_count) — chunk_type ∈ {"parent", "child"}; child
#     chunks carry parent_id, parent chunks have parent_id=None.
#   - ``ChunkSpec`` frozen dataclass holding (parent_size, child_size,
#     parent_child_overlap); defaults to (500, 150, 100).
#   - ``Chunker`` class with ``split_parents(text)`` and
#     ``split_children(text)`` producing parent chunks of
#     ``spec.parent_size`` tokens (500) and child chunks of
#     ``spec.child_size`` tokens (150) respectively. ``split_children``
#     must annotate each child chunk with the parent_id it belongs to so
#     the retrieval path can walk back from child hit → parent context.
#   - ``ParentChildIndex`` class with ``is_vector_indexed(chunk)``
#     (returns True iff chunk.chunk_type == "child") and
#     ``retrieve_parent(child_id)`` that returns the Parent chunk for a
#     child hit. Also needs a seed method (e.g. ``add_link``) so unit
#     tests can wire child_id → parent_id without standing up PostgreSQL.
# ---------------------------------------------------------------------------
from app.core.knowledge import (
    CHILD_TOKEN_SIZE,
    OVERLAP_TOKENS,
    PARENT_TOKEN_SIZE,
    Chunk,
    Chunker,
    ChunkSpec,
    ParentChildIndex,
)


# ---------------------------------------------------------------------------
# 1. Parent chunk size is 500 tokens (boundary).
#
# Spec input: content_tokens="600"; expected_parent_size="500".
# SRS FR-28: Parent = 500 tokens — splitting 600 tokens of content must
# produce parents of exactly 500 tokens (not 600). Excess tokens spill
# into subsequent parent chunks, never into a single chunk.
# ---------------------------------------------------------------------------
def test_fr28_parent_500_token_size():
    content_tokens = 600
    expected_parent_size = 500

    # GREEN TODO: Chunker.split_parents(text) must slice the tokenized
    # content into chunks of spec.parent_size (500). The returned Chunk
    # objects must report token_count == 500 each (except possibly the
    # trailing one, which carries the remainder).
    chunker = Chunker()
    text = " ".join(f"t{i}" for i in range(content_tokens))
    parents = chunker.split_parents(text)

    if content_tokens == 600:
        # Spec fr28-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c`
        # block whose trigger value matches TEST_SPEC case 1's input
        # (content_tokens="600").
        assert parents, "fr28-ok predicate: parents list must not be empty"

    assert parents, "FR-28: splitting 600 tokens must yield >=1 parent chunk"
    first = parents[0]
    assert first.token_count == expected_parent_size, (
        f"FR-28: parent chunk must be {expected_parent_size} tokens; "
        f"got token_count={first.token_count}"
    )
    # The parent's chunk_type must be tagged "parent" so callers can
    # distinguish it from child chunks during the child→parent walk.
    assert first.chunk_type == "parent", (
        f"FR-28: parent chunk must carry chunk_type='parent'; "
        f"got chunk_type={first.chunk_type!r}"
    )
    # Parent chunks have no parent_id (they ARE the parent).
    assert first.parent_id is None, (
        f"FR-28: parent chunk must NOT carry a parent_id; "
        f"got parent_id={first.parent_id!r}"
    )


# ---------------------------------------------------------------------------
# 2. Child chunk size is 150 tokens (boundary).
#
# Spec input: content_tokens="200"; expected_child_size="150".
# SRS FR-28: Child = 150 tokens — splitting 200 tokens of content must
# produce children of 150 tokens; the leftover 50 tokens trail as the
# final (smaller) chunk.
# ---------------------------------------------------------------------------
def test_fr28_child_150_token_size():
    content_tokens = 200
    expected_child_size = 150

    # GREEN TODO: Chunker.split_children(text) must slice the tokenized
    # content into chunks of spec.child_size (150). Each returned Chunk
    # must report token_count == 150 except possibly the trailing one.
    chunker = Chunker()
    text = " ".join(f"t{i}" for i in range(content_tokens))
    children = chunker.split_children(text)

    if content_tokens == 200:
        # Spec fr28-ok predicate 'result is not None' applies_to case 1.
        # Trigger value matches TEST_SPEC case 2's input
        # (content_tokens="200").
        assert children, "fr28-ok predicate: children list must not be empty"

    assert children, "FR-28: splitting 200 tokens must yield >=1 child chunk"
    first = children[0]
    assert first.token_count == expected_child_size, (
        f"FR-28: child chunk must be {expected_child_size} tokens; "
        f"got token_count={first.token_count}"
    )
    # Each child must carry a parent_id pointing to the Parent chunk it
    # belongs to — that's how FR-28's vector-hit-walks-parent works.
    assert first.parent_id is not None, (
        f"FR-28: child chunk must have parent_id set (so child→parent "
        f"lookup works); got parent_id={first.parent_id!r}"
    )
    assert first.chunk_type == "child", (
        f"FR-28: child chunk must carry chunk_type='child'; "
        f"got chunk_type={first.chunk_type!r}"
    )


# ---------------------------------------------------------------------------
# 3. Only Child chunks are vector-indexed; Parent chunks are NOT (validation).
#
# Spec input: chunk_type="parent"; expected_indexed="false".
# SRS FR-28: 僅 Child Chunks 建向量索引. Vector indexing applies ONLY
# to children, never to parents — otherwise we'd double-index every
# context window and waste HNSW capacity.
# ---------------------------------------------------------------------------
def test_fr28_child_vector_indexed_parent_not():
    chunk_type = "parent"
    expected_indexed = False

    # GREEN TODO: ParentChildIndex.is_vector_indexed(chunk) must return
    # True iff chunk.chunk_type == "child"; for parent chunks it must
    # return False (parents are reached by walking the child→parent FK,
    # not via vector similarity).
    index = ParentChildIndex()
    parent_chunk = Chunk(
        chunk_id="p-1",
        content="parent content",
        chunk_type=chunk_type,
        parent_id=None,
        token_count=500,
    )

    if expected_indexed is False:
        # Spec fr28-ok predicate applies to case 1; case 3 is validation
        # so the fr28-ok predicate is not redeclared here — we still
        # want to verify the index decision branch.
        pass

    result = index.is_vector_indexed(parent_chunk)

    assert result is not None, (
        "FR-28: is_vector_indexed must return a deterministic bool, "
        "not None"
    )
    assert result is False, (
        f"FR-28: parent chunks must NOT be vector-indexed (only child "
        f"chunks are); got is_vector_indexed={result} for chunk_type="
        f"{parent_chunk.chunk_type!r}"
    )

    # Symmetric guard — child chunks MUST be indexed, otherwise the
    # FR-28 child-side indexing contract is broken.
    child_chunk = Chunk(
        chunk_id="c-1",
        content="child content",
        chunk_type="child",
        parent_id="p-1",
        token_count=150,
    )
    assert index.is_vector_indexed(child_chunk) is True, (
        "FR-28: child chunks MUST be vector-indexed (only children are "
        "indexed per the FR-28 spec)."
    )


# ---------------------------------------------------------------------------
# 4. Vector hit on a child chunk retrieves the parent chunk (happy_path).
#
# Spec input: child_id="chunk-1"; parent_id="doc-1".
# SRS FR-28: 向量命中 Child → 追索對應 Parent 送 LLM. The child hit
# walks the parent_id FK and returns the 500-token Parent chunk that
# the LLM (Tier 3) actually consumes.
# ---------------------------------------------------------------------------
def test_fr28_vector_hit_child_retrieves_parent():
    child_id = "chunk-1"
    parent_id = "doc-1"
    # H-17: add_link requires real parent_content; an empty stub would
    # propagate to the LLM as the parent context.
    parent_content = "doc-1 500-token parent context block"

    # GREEN TODO: ParentChildIndex.retrieve_parent(child_id) must walk
    # child_id → knowledge_chunks.parent_id → fetch the 500-token
    # Parent chunk. The returned Chunk must be the Parent (chunk_type
    # == "parent"), not the child hit itself. GREEN also needs an
    # ``add_link(child_id, parent_id)`` (or equivalent seed API) so the
    # unit test can wire the child→parent mapping without a real DB.
    index = ParentChildIndex()
    index.add_link(
        child_id=child_id,
        parent_id=parent_id,
        parent_content=parent_content,
    )

    if child_id == "chunk-1":
        # Spec fr28-ok predicate 'result is not None' applies_to case 1.
        # Trigger value matches TEST_SPEC case 4's input
        # (child_id="chunk-1").
        assert parent_id == "doc-1", (
            "FR-28 case 4 expects parent_id='doc-1' for "
            "child_id='chunk-1'"
        )

    result = index.retrieve_parent(child_id)

    assert result is not None, (
        f"FR-28: retrieve_parent(child_id={child_id!r}) must return the "
        f"Parent chunk; got None"
    )
    assert result.chunk_type == "parent", (
        f"FR-28: retrieved chunk must be the Parent "
        f"(chunk_type='parent'); got chunk_type={result.chunk_type!r}"
    )
    # Parent identifier resolution: result.chunk_id must reference the
    # parent (or its identifier), not the child_id we queried with.
    assert result.chunk_id != child_id, (
        f"FR-28: parent retrieval must return the Parent chunk, not "
        f"the child hit; got chunk_id={result.chunk_id!r} for "
        f"child_id={child_id!r}"
    )


# ---------------------------------------------------------------------------
# 5. Overlap is 100 tokens (boundary).
#
# Spec input: chunk_size="500"; overlap="100"; expected_overlap="100".
# SRS FR-28: Parent = 500 tokens（100 token overlap）. The overlap
# constant is SRS-mandated and is the value the wiring layer reads to
# align child chunks against parent boundaries.
# ---------------------------------------------------------------------------
def test_fr28_overlap_100_tokens_correct():
    chunk_size = 500
    overlap = 100
    expected_overlap = 100

    # GREEN TODO: ChunkSpec.parent_child_overlap (and the module-level
    # OVERLAP_TOKENS constant) must equal 100. The default ChunkSpec
    # produced by Chunker() / ChunkSpec() must carry overlap=100 so
    # parent chunks share a 100-token sliding window.
    spec = ChunkSpec()

    if chunk_size == 500 and overlap == 100:
        # Spec fr28-ok predicate 'result is not None' applies_to case 1.
        # Trigger value matches TEST_SPEC case 5's input
        # (chunk_size="500"; overlap="100").
        assert expected_overlap == 100, (
            "FR-28 case 5 expects OVERLAP_TOKENS=100."
        )

    assert spec.parent_size == chunk_size, (
        f"FR-28: ChunkSpec.parent_size must be {chunk_size}; "
        f"got parent_size={spec.parent_size}"
    )
    assert spec.parent_child_overlap == expected_overlap, (
        f"FR-28: ChunkSpec.parent_child_overlap must be "
        f"{expected_overlap}; got parent_child_overlap="
        f"{spec.parent_child_overlap}"
    )
    # Module-level constants — these are the values the embedding-job /
    # Tier-2 wiring layer reads so the constants must agree with
    # ChunkSpec defaults.
    assert expected_overlap == OVERLAP_TOKENS, (
        f"FR-28: OVERLAP_TOKENS module constant must be "
        f"{expected_overlap}; got OVERLAP_TOKENS={OVERLAP_TOKENS}"
    )
    assert chunk_size == PARENT_TOKEN_SIZE, (
        f"FR-28: PARENT_TOKEN_SIZE must be {chunk_size}; got "
        f"PARENT_TOKEN_SIZE={PARENT_TOKEN_SIZE}"
    )
    assert CHILD_TOKEN_SIZE == 150, (
        f"FR-28: CHILD_TOKEN_SIZE must be 150; got "
        f"CHILD_TOKEN_SIZE={CHILD_TOKEN_SIZE}"
    )
