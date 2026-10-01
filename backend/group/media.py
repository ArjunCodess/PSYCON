"""Video upload checks for a group recording.

The local audio demo remains limited to five minutes and 12 MB. Group
recordings use this validator instead.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MIN_DURATION_S = 60.0
MAX_DURATION_S = 3 * 60 * 60
MIN_WIDTH = 640
MIN_HEIGHT = 360
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
APPROVED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}
AUDIO_CODECS = {"aac", "opus", "mp3", "pcm_s16le", "vorbis"}
_CODEC_NAMES = {
    "avc1": "h264",
    "avc3": "h264",
    "hvc1": "hevc",
    "hev1": "hevc",
    "vp08": "vp8",
    "vp09": "vp9",
    "av01": "av1",
    "mp4a": "aac",
    "opus": "opus",
    "Opus": "opus",
    ".mp3": "mp3",
    "sowt": "pcm_s16le",
    "twos": "pcm_s16le",
    "raw ": "pcm_s16le",
    "vorb": "vorbis",
}
class MediaError(ValueError):
    pass


def validate_video(filename: str, data: bytes, probe=None, *, max_bytes: int = MAX_VIDEO_BYTES) -> dict:
    extension = Path(filename or "").suffix.lower()
    if extension not in APPROVED_EXTENSIONS:
        raise MediaError("approved video formats are mp4, mov, webm, and mkv")
    if not data:
        raise MediaError("video file is empty")
    if len(data) > max_bytes:
        raise MediaError("video file exceeds the 2 GB group-recording limit")
    _check_magic(extension, data)
    if probe is not None:
        info = dict(probe(data))
    elif extension in {".mp4", ".mov"}:
        info = inspect_mp4(data)
    else:
        info = probe_ffprobe(data, extension)
    return _check_streams(info)


def _check_magic(extension: str, data: bytes) -> None:
    if extension in {".mp4", ".mov"}:
        if b"ftyp" not in data[:64]:
            raise MediaError("file is not an mp4 or mov container")
        return
    if not data.startswith(b"\x1a\x45\xdf\xa3"):
        raise MediaError("file is not a webm or matroska container")


def _check_streams(info: dict) -> dict:
    try:
        duration = float(info["duration_s"])
        width = int(info["width"])
        height = int(info["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("video duration and dimensions could not be read") from exc
    if not info.get("timestamps_readable"):
        raise MediaError("video timestamps could not be read")
    if duration < MIN_DURATION_S or duration > MAX_DURATION_S:
        raise MediaError("video duration must be between 1 minute and 3 hours")
    if not info.get("has_audio"):
        raise MediaError("video must contain its original audio track")
    video_codec = str(info.get("video_codec") or "")
    audio_codec = str(info.get("audio_codec") or "")
    if video_codec not in VIDEO_CODECS:
        raise MediaError("video codec must be h264, hevc, vp8, vp9, or av1")
    if audio_codec not in AUDIO_CODECS:
        raise MediaError("audio codec must be aac, opus, mp3, pcm_s16le, or vorbis")
    if width < MIN_WIDTH or height < MIN_HEIGHT or width > MAX_WIDTH or height > MAX_HEIGHT:
        raise MediaError("video dimensions must be between 640x360 and 3840x2160")
    cleaned = dict(info)
    cleaned["duration_s"] = duration
    cleaned["width"] = width
    cleaned["height"] = height
    cleaned["video_codec"] = video_codec
    cleaned["audio_codec"] = audio_codec
    cleaned["has_audio"] = True
    cleaned["timestamps_readable"] = True
    return cleaned


def inspect_mp4(data: bytes) -> dict:
    moov = _find_payload(data, b"moov")
    if moov is None:
        raise MediaError("video timestamps could not be read")
    mvhd = _find_payload(moov, b"mvhd")
    duration = _mvhd_duration(mvhd) if mvhd is not None else None
    if duration is None:
        raise MediaError("video timestamps could not be read")
    video_codec = None
    audio_codec = None
    width = 0
    height = 0
    for track in _payloads(moov, b"trak"):
        handler = _handler(track)
        codec = _codec_name(_sample_codec(track))
        if handler == b"vide":
            video_codec = codec or video_codec
            dimensions = _track_dimensions(track)
            if dimensions is not None:
                width, height = dimensions
        elif handler == b"soun":
            audio_codec = codec or audio_codec
    return {
        "duration_s": duration,
        "width": width,
        "height": height,
        "has_audio": audio_codec is not None,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "timestamps_readable": True,
        "probe": "mp4_boxes_v1",
    }


def probe_ffprobe(data: bytes, extension: str) -> dict:
    executable = shutil.which("ffprobe")
    if executable is None:
        raise MediaError("ffprobe is required to validate this container")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / f"recording{extension}"
        path.write_bytes(data)
        completed = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
        )
    if completed.returncode != 0:
        raise MediaError("video timestamps could not be read")
    import json

    payload = json.loads(completed.stdout.decode("utf-8") or "{}")
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    try:
        duration = float((payload.get("format") or {}).get("duration"))
    except (TypeError, ValueError) as exc:
        raise MediaError("video timestamps could not be read") from exc
    return {
        "duration_s": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": bool(audio),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "timestamps_readable": duration > 0,
        "probe": "ffprobe",
    }


def _iter_boxes(data: bytes):
    offset = 0
    end = len(data)
    while offset + 8 <= end:
        size = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        header = 8
        if size == 1 and offset + 16 <= end:
            size = int.from_bytes(data[offset + 8 : offset + 16], "big")
            header = 16
        elif size == 0:
            size = end - offset
        if size < header or offset + size > end:
            break
        yield kind, data[offset + header : offset + size]
        offset += size


def _find_payload(data: bytes, kind: bytes) -> bytes | None:
    for box_kind, payload in _iter_boxes(data):
        if box_kind == kind:
            return payload
    return None


def _payloads(data: bytes, kind: bytes) -> list[bytes]:
    return [payload for box_kind, payload in _iter_boxes(data) if box_kind == kind]


def _mvhd_duration(payload: bytes) -> float | None:
    if not payload:
        return None
    version = payload[0]
    if version == 0 and len(payload) >= 20:
        timescale = int.from_bytes(payload[12:16], "big")
        duration = int.from_bytes(payload[16:20], "big")
    elif version == 1 and len(payload) >= 32:
        timescale = int.from_bytes(payload[20:24], "big")
        duration = int.from_bytes(payload[24:32], "big")
    else:
        return None
    if timescale <= 0 or duration <= 0:
        return None
    return duration / timescale


def _handler(track: bytes) -> bytes | None:
    mdia = _find_payload(track, b"mdia")
    if mdia is None:
        return None
    hdlr = _find_payload(mdia, b"hdlr")
    if hdlr is None or len(hdlr) < 12:
        return None
    return hdlr[8:12]


def _sample_codec(track: bytes) -> str | None:
    mdia = _find_payload(track, b"mdia")
    if mdia is None:
        return None
    minf = _find_payload(mdia, b"minf")
    if minf is None:
        return None
    stbl = _find_payload(minf, b"stbl")
    if stbl is None:
        return None
    stsd = _find_payload(stbl, b"stsd")
    if stsd is None or len(stsd) < 16:
        return None
    return stsd[12:16].decode("latin1")


def _codec_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _CODEC_NAMES.get(raw, raw)


def _track_dimensions(track: bytes) -> tuple[int, int] | None:
    tkhd = _find_payload(track, b"tkhd")
    if tkhd is None:
        return None
    base = 88 if tkhd[0] == 1 else 76
    if len(tkhd) < base + 8:
        return None
    width = int(int.from_bytes(tkhd[base : base + 4], "big") / 65536)
    height = int(int.from_bytes(tkhd[base + 4 : base + 8], "big") / 65536)
    if width <= 0 or height <= 0:
        return None
    return width, height
