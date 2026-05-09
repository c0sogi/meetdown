import copy
import importlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, cast

from meetdown.json_types import JsonObject, as_json_object, as_number, as_object_list


class ChunkingError(RuntimeError):
    """Raised when media chunking fails before transcription."""


@dataclass(frozen=True)
class MediaChunk:
    path: Path
    offset_ms: int


class _ImageioFfmpegModule(Protocol):
    def get_ffmpeg_exe(self) -> str: ...


_DURATION_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>s|m|h)?$")
_CHUNK_FORMATS: dict[str, tuple[str, list[str]]] = {
    "flac": (".flac", ["-acodec", "flac", "-compression_level", "8"]),
    "mp3": (".mp3", ["-acodec", "libmp3lame", "-b:a", "64k"]),
    "wav": (".wav", ["-acodec", "pcm_s16le"]),
}
_FFMPEG_DURATION_RE = re.compile(
    r"Duration:\s*(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+(?:\.\d+)?)"
)


def parse_time_seconds(value: str) -> float:
    text = value.strip().lower()
    if ":" in text:
        parts = text.split(":")
        if len(parts) not in (2, 3):
            raise ValueError("time must look like 600, 10m, 01:23, or 01:02:03")

        try:
            numbers = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError(
                "time must look like 600, 10m, 01:23, or 01:02:03"
            ) from exc

        if any(number < 0 for number in numbers):
            raise ValueError("time must not be negative")
        if any(number >= 60 for number in numbers[1:]):
            raise ValueError("minute and second fields must be less than 60")

        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes * 60 + seconds

        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds

    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError("time must look like 600, 600s, 10m, 01:23, or 01:02:03")

    amount = float(match.group("value"))
    unit = match.group("unit") or "s"
    multiplier = {"s": 1, "m": 60, "h": 3600}[unit]
    seconds = amount * multiplier
    if seconds < 0:
        raise ValueError("time must not be negative")
    return seconds


def parse_duration_seconds(value: str) -> float:
    seconds = parse_time_seconds(value)
    if seconds <= 0:
        raise ValueError("duration must be greater than zero")
    return seconds


def normalize_chunk_format(value: str) -> str:
    chunk_format = value.strip().lower()
    if chunk_format not in _CHUNK_FORMATS:
        supported = ", ".join(sorted(_CHUNK_FORMATS))
        raise ValueError(f"chunk format must be one of: {supported}")
    return chunk_format


def chunk_extension(chunk_format: str) -> str:
    normalized_format = normalize_chunk_format(chunk_format)
    extension, _ = _CHUNK_FORMATS[normalized_format]
    return extension


def validate_time_range(start_seconds: float, end_seconds: float | None) -> None:
    if start_seconds < 0:
        raise ValueError("start time must not be negative")
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("end time must be greater than start time")


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        imageio_ffmpeg = cast(
            _ImageioFfmpegModule,
            importlib.import_module("imageio_ffmpeg"),
        )
    except ImportError as exc:
        raise ChunkingError(
            "ffmpeg is required for media extraction. Install ffmpeg or install "
            "meetdown with the imageio-ffmpeg dependency."
        ) from exc

    return imageio_ffmpeg.get_ffmpeg_exe()


def ffprobe_executable() -> str | None:
    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe

    ffmpeg_path = Path(ffmpeg_executable())
    for candidate in (
        ffmpeg_path.with_name("ffprobe.exe"),
        ffmpeg_path.with_name("ffprobe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _run_ffmpeg(command: list[str], *, action: str) -> None:
    command = [ffmpeg_executable(), *command]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise ChunkingError(f"ffmpeg failed to start for {action}: {exc}") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown ffmpeg error"
        raise ChunkingError(f"ffmpeg failed to {action}: {stderr}")


def _parse_ffmpeg_duration(stderr: str) -> float:
    match = _FFMPEG_DURATION_RE.search(stderr)
    if not match:
        raise ChunkingError("ffmpeg could not read media duration")

    hours = float(match.group("hours"))
    minutes = float(match.group("minutes"))
    seconds = float(match.group("seconds"))
    duration = hours * 3600 + minutes * 60 + seconds
    if duration <= 0:
        raise ChunkingError("media duration must be greater than zero")
    return duration


def _probe_media_duration_with_ffmpeg(source: Path) -> float:
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-i",
        str(source),
        "-t",
        "0.001",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise ChunkingError(
            f"ffmpeg failed to start for duration probing: {exc}"
        ) from exc

    return _parse_ffmpeg_duration(completed.stderr)


def probe_media_duration_seconds(input_path: str | Path) -> float:
    source = Path(input_path)
    ffprobe = ffprobe_executable()
    if ffprobe is None:
        return _probe_media_duration_with_ffmpeg(source)

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(source),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError:
        return _probe_media_duration_with_ffmpeg(source)

    if completed.returncode != 0:
        return _probe_media_duration_with_ffmpeg(source)

    try:
        duration = float(completed.stdout.strip())
    except ValueError as exc:
        raise ChunkingError("ffprobe could not read media duration") from exc

    if duration <= 0:
        raise ChunkingError("media duration must be greater than zero")
    return duration


def _input_args(source: Path, start_seconds: float) -> list[str]:
    args: list[str] = []
    if start_seconds:
        args.extend(["-ss", str(start_seconds)])
    args.extend(["-i", str(source)])
    return args


def _duration_args(start_seconds: float, end_seconds: float | None) -> list[str]:
    if end_seconds is None:
        return []
    return ["-t", str(end_seconds - start_seconds)]


def extract_media(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start_seconds: float = 0,
    end_seconds: float | None = None,
    chunk_format: str = "flac",
) -> MediaChunk:
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"audio file not found: {source}")

    validate_time_range(start_seconds, end_seconds)
    normalized_format = normalize_chunk_format(chunk_format)
    _, codec_args = _CHUNK_FORMATS[normalized_format]

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *_input_args(source, start_seconds),
        "-vn",
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        *codec_args,
        *_duration_args(start_seconds, end_seconds),
        str(destination),
    ]
    _run_ffmpeg(command, action="extract selected media")
    return MediaChunk(path=destination, offset_ms=int(round(start_seconds * 1000)))


def split_media(
    input_path: str | Path,
    output_dir: str | Path,
    chunk_seconds: float,
    *,
    chunk_format: str = "flac",
    start_seconds: float = 0,
    end_seconds: float | None = None,
) -> list[MediaChunk]:
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"audio file not found: {source}")

    validate_time_range(start_seconds, end_seconds)
    normalized_format = normalize_chunk_format(chunk_format)
    extension, _ = _CHUNK_FORMATS[normalized_format]
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    base_offset_seconds = start_seconds
    segment_source = source
    if start_seconds or end_seconds is not None:
        selected_path = destination / f"selected{extension}"
        extract_media(
            source,
            selected_path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            chunk_format=chunk_format,
        )
        segment_source = selected_path

    duration = probe_media_duration_seconds(segment_source)
    chunks: list[MediaChunk] = []
    local_start = 0.0
    index = 0
    while local_start < duration - 0.001:
        local_end = min(local_start + chunk_seconds, duration)
        chunk_path = destination / f"chunk_{index:05d}{extension}"
        extract_media(
            segment_source,
            chunk_path,
            start_seconds=local_start,
            end_seconds=local_end,
            chunk_format=normalized_format,
        )
        chunks.append(
            MediaChunk(
                path=chunk_path,
                offset_ms=int(round((base_offset_seconds + local_start) * 1000)),
            )
        )
        local_start += chunk_seconds
        index += 1

    if not chunks:
        raise ChunkingError("ffmpeg did not create any chunks")
    return chunks


def _offset_numeric_field(mapping: JsonObject, key: str, offset_ms: int) -> None:
    value = as_number(mapping.get(key))
    if value is not None:
        mapping[key] = value + offset_ms


def offset_response_times(response: JsonObject, offset_ms: int) -> JsonObject:
    adjusted = copy.deepcopy(response)

    for item in as_object_list(adjusted.get("segments")) or []:
        segment = as_json_object(item)
        if segment is None:
            continue
        for key in ("start", "end"):
            _offset_numeric_field(segment, key, offset_ms)
        for word_item in as_object_list(segment.get("words")) or []:
            word = as_object_list(word_item)
            if word is None or len(word) < 2:
                continue
            start = as_number(word[0])
            end = as_number(word[1])
            if start is not None:
                word[0] = start + offset_ms
            if end is not None:
                word[1] = end + offset_ms

    for item in as_object_list(adjusted.get("events")) or []:
        event = as_json_object(item)
        if event is None:
            continue
        for key in ("start", "end"):
            _offset_numeric_field(event, key, offset_ms)

    return adjusted


def merge_responses(responses: list[JsonObject]) -> JsonObject:
    adjusted_segments: list[object] = []
    adjusted_events: list[object] = []
    texts: list[str] = []
    confidences: list[float] = []

    for response in responses:
        text = str(response.get("text") or "").strip()
        if text:
            texts.append(text)

        segments = as_object_list(response.get("segments"))
        if segments is not None:
            adjusted_segments.extend(segments)

        events = as_object_list(response.get("events"))
        if events is not None:
            adjusted_events.extend(events)

        confidence = as_number(response.get("confidence"))
        if confidence is not None:
            confidences.append(float(confidence))

    merged: JsonObject = {
        "result": "COMPLETED",
        "message": "Merged chunked transcription",
        "text": " ".join(texts),
        "segments": adjusted_segments,
    }
    if adjusted_events:
        merged["events"] = adjusted_events
    if confidences:
        merged["confidence"] = sum(confidences) / len(confidences)
    return merged
