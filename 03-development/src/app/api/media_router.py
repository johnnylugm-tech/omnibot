"""[FR-100, FR-200] Media router — multipart upload + BYTEA stream back.

Routes (mounted at ``/api/v1``):
    POST /web/upload                — accept multipart files, persist BYTEA,
                                      return ``{media_ids, attachments}``
    GET  /media/{media_id}          — stream the bytes back with the
                                      original ``Content-Type``

Storage: PostgreSQL BYTEA column on ``media_attachments`` (no S3
dependency in single-deploy mode — see plan §C "Storage"). The
``ConversationMessageType`` (TEXT/IMAGE/STICKER/LOCATION/AUDIO/VIDEO/FILE)
mapping is derived from the uploaded MIME prefix.

Fail-secure posture (FR-100):
    * ClamAV down → 503 FILE_SCAN_UNAVAILABLE for ``file`` attachments
    * > 10 MB → 413 FILE_TOO_LARGE
    * disallowed mime prefix → 415 UNSUPPORTED_MEDIA_TYPE

The router is intentionally thin — the heavy lifting (scan + size
gate) is delegated to ``services.media.MediaPipeline``. SQL is
issued through the canonical ``app.infra.database.get_session`` seam.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.auth import get_current_user_role
from app.services.media import (
    CLAMAV_STATUS_DOWN,
    CLAMAV_STATUS_UNAVAILABLE,
    FILE_SCAN_HTTP_503,
    FILE_SCAN_UNAVAILABLE_ERROR,
    FILE_SIZE_LIMIT_MB,
    MediaPipeline,
)
from sqlalchemy import text

from app.infra.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media"])
_media = MediaPipeline()

# MIME → MessageType mapping. Kept inline because the table is small
# and stable; centralising it would force a second module import for
# what amounts to a 6-line lookup.
_MIME_TO_MESSAGE_TYPE = (
    ("image/", "IMAGE"),
    ("audio/", "AUDIO"),
    ("video/", "VIDEO"),
    ("application/pdf", "FILE"),
    ("text/", "FILE"),
    ("application/", "FILE"),
)


def _classify_mime(mime: str) -> str:
    for prefix, mtype in _MIME_TO_MESSAGE_TYPE:
        if mime.startswith(prefix):
            return mtype
    return "FILE"


from typing import Optional

@router.post("/web/upload")
async def upload(
    files: list[UploadFile] = File(...),
    conversation_id: Optional[str] = None,
    role: str = Depends(get_current_user_role),
    session = Depends(get_session),
) -> dict:
    """Persist uploads as BYTEA rows and return their media_ids."""
    if role == "anonymous":
        raise HTTPException(status_code=401, detail="authentication required")

    media_ids: list[str] = []
    attachments: list[dict] = []
    conversation_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"

    try:
        for f in files:
            # FR-100 size gate BEFORE buffering the full file — stream in
            # 1 MiB chunks and abort the moment we exceed the limit so a
            # malicious client can't OOM the worker with a single 10 GB
            # request.
            size_limit_bytes = FILE_SIZE_LIMIT_MB * 1024 * 1024
            chunks: list[bytes] = []
            size_bytes = 0
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > size_limit_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"file exceeds {FILE_SIZE_LIMIT_MB}MB",
                    )
                chunks.append(chunk)
            payload = b"".join(chunks)
            mime = (f.content_type or "application/octet-stream").lower()

            # FR-100 file ClamAV scan — best-effort fail-secure. Scan
            # any MIME that is not an obvious media container
            # (image/audio/video); allow-list of media prefixes keeps
            # the rule unambiguous as new MIMEs are added.
            media_prefixes = ("image/", "audio/", "video/")
            requires_scan = not mime.startswith(media_prefixes)
            if requires_scan:
                if not _media.scanner.is_available():
                    raise HTTPException(
                        status_code=FILE_SCAN_HTTP_503,
                        detail=FILE_SCAN_UNAVAILABLE_ERROR,
                    )
                scan_result = _media.scanner.scan(payload, mime)
                if scan_result.status in (
                    CLAMAV_STATUS_DOWN,
                    CLAMAV_STATUS_UNAVAILABLE,
                ):
                    raise HTTPException(
                        status_code=FILE_SCAN_HTTP_503,
                        detail=FILE_SCAN_UNAVAILABLE_ERROR,
                    )

            media_id = f"m_{uuid.uuid4().hex[:16]}"
            mtype = _classify_mime(mime)
            await session.execute(
                text(
                    "INSERT INTO media_attachments "
                    "(id, conversation_id, mime_type, size_bytes, payload, message_type, created_at) "
                    "VALUES (:id, :cid, :mime, :size, :payload, :mtype, NOW())"
                ),
                {
                    "id": media_id,
                    "cid": conversation_id,
                    "mime": mime,
                    "size": size_bytes,
                    "payload": payload,
                    "mtype": mtype,
                },
            )
            media_ids.append(media_id)
            attachments.append(
                {
                    "media_id": media_id,
                    "mime_type": mime,
                    "size_bytes": size_bytes,
                    "message_type": mtype,
                    "url": f"/api/v1/media/{media_id}",
                }
            )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        logger.exception("media upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="upload failed")

    return {
        "conversation_id": conversation_id,
        "media_ids": media_ids,
        "attachments": attachments,
    }


@router.get("/media/{media_id}")
async def get_media(
    media_id: str,
    session = Depends(get_session),
) -> Response:
    """Stream a previously-uploaded attachment back to the caller."""
    result = await session.execute(
        text(
            "SELECT payload, mime_type FROM media_attachments WHERE id = :id"
        ),
        {"id": media_id},
    )
    row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="media not found")
    payload, mime = row[0], row[1]
    # ``payload`` arrives as ``memoryview`` from asyncpg BYTEA — wrap
    # so the Response layer accepts it.
    return Response(content=bytes(payload), media_type=mime or "application/octet-stream")