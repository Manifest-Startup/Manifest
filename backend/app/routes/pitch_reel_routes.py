"""
REST endpoints for pitch reel media.
GET /api/pitch-reels/{reel_id}/video  — stream the AI-generated video from the database.
"""

from __future__ import annotations

import re

from app.db.database import create_database_client
from app.services.pitch_reels.service import create_pitch_reel_service
from app.utils.logger import logger
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

router = APIRouter(prefix="/api/pitch-reels", tags=["pitch-reels"])


@router.get("/{reel_id}/video")
def stream_pitch_reel_video(
    reel_id: str, range_header: str | None = Header(default=None, alias="range")
) -> Response:
    """
    Stream the AI-generated MP4 video for a pitch reel directly from the database.
    Falls back to 404 when no video data is stored (e.g. placeholder reels).
    """
    db = create_database_client()
    service = create_pitch_reel_service(db)

    try:
        video_bytes = service.get_reel_video_data(reel_id)
    except Exception as exc:
        logger.error("[PitchReelRoutes] Error fetching video for reel %s: %s", reel_id, exc)
        raise HTTPException(status_code=500, detail="Could not retrieve video") from exc

    if not video_bytes:
        raise HTTPException(status_code=404, detail="No generated video found for this reel")

    total_size = len(video_bytes)
    base_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
    }

    if not isinstance(range_header, str) or not range_header:
        return Response(
            content=video_bytes,
            media_type="video/mp4",
            headers={
                **base_headers,
                "Content-Length": str(total_size),
            },
        )

    range_match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if not range_match:
        raise HTTPException(status_code=416, detail="Invalid range header")

    start_raw, end_raw = range_match.groups()
    if not start_raw and not end_raw:
        raise HTTPException(status_code=416, detail="Invalid range header")

    if not start_raw:
        suffix_length = int(end_raw)
        if suffix_length <= 0:
            raise HTTPException(status_code=416, detail="Invalid range header")
        start = max(total_size - suffix_length, 0)
        end = total_size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else total_size - 1
        if start < 0 or start >= total_size or end < start:
            raise HTTPException(status_code=416, detail="Requested range not satisfiable")
        end = min(end, total_size - 1)

    chunk = video_bytes[start : end + 1]
    return Response(
        content=chunk,
        status_code=206,
        media_type="video/mp4",
        headers={
            **base_headers,
            "Content-Length": str(len(chunk)),
            "Content-Range": f"bytes {start}-{end}/{total_size}",
        },
    )
