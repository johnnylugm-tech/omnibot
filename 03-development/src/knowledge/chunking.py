"""[FR-27] Document chunking strategy.

Citations:
  SRS.md FR-27
"""
from __future__ import annotations


class ChunkingStrategy:
    """[FR-27] Splits documents into overlapping chunks for retrieval."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def split(self, text: str) -> list[str]:
        """Return list of text chunks."""
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunks.append(text[start:end])
            start += self._chunk_size - self._overlap
        return chunks
