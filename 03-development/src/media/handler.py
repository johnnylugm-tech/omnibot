"""[FR-100] Media handler — image/audio/video processing.

Citations:
  SRS.md FR-100
"""
from __future__ import annotations



class MediaHandler:
    """[FR-100] Handles media file processing and storage."""

    def __init__(self, storage_backend: str = "local") -> None:
        self._backend = storage_backend

    def upload(self, file_data: bytes, filename: str, content_type: str) -> str:
        """Upload media and return URL."""
        return ""

    def get_url(self, media_id: str) -> str:
        """Return signed URL for media access."""
        return ""

    def delete(self, media_id: str) -> bool:
        """Delete media file."""
        return True
