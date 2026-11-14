"""
Media publishing helpers for pitch reels.

Primary path:
- upload generated MP4s to Supabase Storage and serve the resulting public URL
- optionally package and upload an HLS ladder when a compatible ffmpeg binary is available

Fallback:
- callers can fall back to DB-backed video bytes when storage is unavailable
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from app.utils.logger import logger

DEFAULT_STORAGE_BUCKET = "pitch-reels"
DEFAULT_VIDEO_PREFIX = "videos"
DEFAULT_HLS_PREFIX = "hls"

_verified_buckets: set[str] = set()


@dataclass(frozen=True)
class PublishedPitchReelMedia:
    playback_url: str
    storage_path: str
    hls_manifest_url: str | None = None
    hls_manifest_path: str | None = None


def storage_is_configured() -> bool:
    return bool(_storage_base_url() and _storage_api_key())


def hls_is_enabled() -> bool:
    return os.getenv("PITCH_REEL_ENABLE_HLS", "").strip().lower() in {"1", "true", "yes", "on"}


def publish_reel_video_bytes(reel_id: str, video_bytes: bytes) -> PublishedPitchReelMedia | None:
    if not storage_is_configured():
        return None

    bucket = _storage_bucket()
    video_path = f"{_video_prefix().strip('/')}/{reel_id}.mp4"

    with tempfile.TemporaryDirectory(prefix=f"pitch-reel-{reel_id[:8]}-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        source_video = tmp_dir / f"{reel_id}.mp4"
        source_video.write_bytes(video_bytes)

        hls_media = _publish_hls_package_if_available(
            reel_id=reel_id, source_video=source_video, bucket=bucket
        )
        if hls_media is not None:
            # Keep the MP4 in storage as a durable fallback for clients that do not use HLS.
            _upload_object(bucket, video_path, video_bytes, content_type="video/mp4")
            return hls_media

    mp4_url = _upload_object(bucket, video_path, video_bytes, content_type="video/mp4")
    return PublishedPitchReelMedia(playback_url=mp4_url, storage_path=video_path)


def _publish_hls_package_if_available(
    *,
    reel_id: str,
    source_video: Path,
    bucket: str,
) -> PublishedPitchReelMedia | None:
    if not hls_is_enabled():
        return None

    ffmpeg_binary = _resolve_ffmpeg_binary()
    if not ffmpeg_binary:
        logger.warning(
            "[PitchReelMedia] HLS requested for %s but no ffmpeg binary is available.", reel_id
        )
        return None

    with tempfile.TemporaryDirectory(prefix=f"pitch-reel-hls-{reel_id[:8]}-") as hls_dir_name:
        hls_root = Path(hls_dir_name)
        try:
            _build_hls_ladder(
                ffmpeg_binary=ffmpeg_binary, source_video=source_video, output_root=hls_root
            )
        except Exception as exc:
            logger.warning("[PitchReelMedia] HLS packaging failed for %s: %s", reel_id, exc)
            return None

        storage_root = f"{_hls_prefix().strip('/')}/{reel_id}"
        master_storage_path = f"{storage_root}/master.m3u8"

        for asset_path in hls_root.rglob("*"):
            if not asset_path.is_file():
                continue
            relative_path = asset_path.relative_to(hls_root).as_posix()
            _upload_object(
                bucket,
                f"{storage_root}/{relative_path}",
                asset_path.read_bytes(),
                content_type=_content_type_for_path(asset_path),
            )

        master_url = _public_object_url(bucket, master_storage_path)
        return PublishedPitchReelMedia(
            playback_url=master_url,
            storage_path=master_storage_path,
            hls_manifest_url=master_url,
            hls_manifest_path=master_storage_path,
        )


def _build_hls_ladder(*, ffmpeg_binary: str, source_video: Path, output_root: Path) -> None:
    variants = [
        {"name": "720p", "width": 1280, "bitrate_kbps": 2400},
        {"name": "540p", "width": 960, "bitrate_kbps": 1500},
        {"name": "360p", "width": 640, "bitrate_kbps": 900},
    ]

    for variant in variants:
        variant_dir = output_root / variant["name"]
        variant_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = variant_dir / "index.m3u8"
        segment_pattern = variant_dir / "segment_%03d.ts"
        bitrate_kbps = int(variant["bitrate_kbps"])
        maxrate_kbps = int(bitrate_kbps * 1.15)
        bufsize_kbps = int(bitrate_kbps * 2)

        command = [
            ffmpeg_binary,
            "-y",
            "-i",
            str(source_video),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            f"scale=w={variant['width']}:h=-2:force_original_aspect_ratio=decrease",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-profile:v",
            "main",
            "-crf",
            "21",
            "-sc_threshold",
            "0",
            "-g",
            "48",
            "-keyint_min",
            "48",
            "-b:v",
            f"{bitrate_kbps}k",
            "-maxrate",
            f"{maxrate_kbps}k",
            "-bufsize",
            f"{bufsize_kbps}k",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(segment_pattern),
            str(playlist_path),
        ]

        subprocess.run(command, check=True, capture_output=True, text=True)

    master_manifest = output_root / "master.m3u8"
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    bandwidth_mappings = {
        "720p": 2800000,
        "540p": 1750000,
        "360p": 1050000,
    }
    resolution_mappings = {
        "720p": "1280x720",
        "540p": "960x540",
        "360p": "640x360",
    }
    for variant in variants:
        name = str(variant["name"])
        lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth_mappings[name]},RESOLUTION={resolution_mappings[name]}"
        )
        lines.append(f"{name}/index.m3u8")
    master_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_ffmpeg_binary() -> str | None:
    env_binary = os.getenv("PITCH_REEL_FFMPEG_PATH", "").strip()
    if env_binary:
        return env_binary

    system_binary = shutil.which("ffmpeg")
    if system_binary:
        return system_binary

    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _storage_base_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _storage_api_key() -> str:
    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_KEY", "").strip()
    )


def _storage_bucket() -> str:
    return (
        os.getenv("PITCH_REEL_STORAGE_BUCKET", DEFAULT_STORAGE_BUCKET).strip()
        or DEFAULT_STORAGE_BUCKET
    )


def _video_prefix() -> str:
    return (
        os.getenv("PITCH_REEL_STORAGE_VIDEO_PREFIX", DEFAULT_VIDEO_PREFIX).strip()
        or DEFAULT_VIDEO_PREFIX
    )


def _hls_prefix() -> str:
    return (
        os.getenv("PITCH_REEL_STORAGE_HLS_PREFIX", DEFAULT_HLS_PREFIX).strip() or DEFAULT_HLS_PREFIX
    )


def _request_headers(*, content_type: str | None = None, upsert: bool = False) -> dict[str, str]:
    headers = {
        "apikey": _storage_api_key(),
        "Authorization": f"Bearer {_storage_api_key()}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if upsert:
        headers["x-upsert"] = "true"
    return headers


def _ensure_bucket_exists(bucket: str) -> None:
    if bucket in _verified_buckets:
        return

    base_url = _storage_base_url()
    if not base_url:
        raise RuntimeError("SUPABASE_URL is not configured")

    bucket_url = f"{base_url}/storage/v1/bucket/{quote(bucket, safe='')}"
    response = requests.get(bucket_url, headers=_request_headers(), timeout=20)
    if response.status_code == 200:
        _verified_buckets.add(bucket)
        return
    if response.status_code not in {404, 400}:
        response.raise_for_status()

    create_response = requests.post(
        f"{base_url}/storage/v1/bucket",
        headers={**_request_headers(), "Content-Type": "application/json"},
        json={"id": bucket, "name": bucket, "public": True},
        timeout=20,
    )
    if create_response.status_code not in {200, 201, 409}:
        create_response.raise_for_status()
    _verified_buckets.add(bucket)


def _upload_object(bucket: str, storage_path: str, payload: bytes, *, content_type: str) -> str:
    _ensure_bucket_exists(bucket)
    base_url = _storage_base_url()
    object_url = (
        f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(storage_path, safe='/')}"
    )
    response = requests.post(
        object_url,
        headers=_request_headers(content_type=content_type, upsert=True),
        data=payload,
        timeout=120,
    )
    if response.status_code not in {200, 201}:
        response.raise_for_status()
    return _public_object_url(bucket, storage_path)


def _public_object_url(bucket: str, storage_path: str) -> str:
    public_base = os.getenv("PITCH_REEL_STORAGE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    encoded_path = quote(storage_path, safe="/")
    if public_base:
        return f"{public_base}/{encoded_path}"
    return f"{_storage_base_url()}/storage/v1/object/public/{quote(bucket, safe='')}/{encoded_path}"


def _content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".m3u8":
        return "application/vnd.apple.mpegurl"
    if suffix == ".ts":
        return "video/mp2t"
    if suffix == ".mp4":
        return "video/mp4"
    return "application/octet-stream"
