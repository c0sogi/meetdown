"""Provider request limits and automatic chunk planning."""

import math
from dataclasses import dataclass

from meetdown import text as ui_text
from meetdown.constants import (
    AUTO_CHUNK_SAFETY_RATIO,
    GEMINI_INLINE_LIMIT_BYTES,
    GEMINI_PREFERRED_CHUNK_SECONDS,
    MIN_AUTO_CHUNK_SECONDS,
    OPENAI_MAX_AUDIO_SECONDS,
    OPENAI_MAX_UPLOAD_BYTES,
    OPENAI_PREFERRED_CHUNK_SECONDS,
    OPENAI_WHISPER_MODEL,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    UPLOAD_BYTES_PER_SECOND,
)
from meetdown.providers import ProviderConfig


@dataclass(frozen=True)
class ChunkPlan:
    """How to split media so each request stays under the provider limit."""

    chunk_seconds: float
    request_limit_seconds: float
    reason: str


def _format_bytes_per_second(upload_format: str) -> float:
    return float(
        UPLOAD_BYTES_PER_SECOND.get(
            upload_format, max(UPLOAD_BYTES_PER_SECOND.values())
        )
    )


def request_limit_seconds(
    config: ProviderConfig,
    upload_format: str,
    *,
    bytes_per_second: float | None = None,
) -> float | None:
    """Return the longest media one request can carry, or None if unknown.

    ``bytes_per_second`` overrides the estimate for ``upload_format``, which is
    useful when the original file is uploaded without re-encoding.
    """
    rate = bytes_per_second or _format_bytes_per_second(upload_format)
    if config.provider == PROVIDER_OPENAI:
        limit = OPENAI_MAX_UPLOAD_BYTES / rate
        if config.openai_model != OPENAI_WHISPER_MODEL:
            limit = min(limit, OPENAI_MAX_AUDIO_SECONDS)
        return limit
    if config.provider == PROVIDER_GEMINI:
        return GEMINI_INLINE_LIMIT_BYTES / rate
    return None


def _preferred_chunk_seconds(config: ProviderConfig) -> float:
    if config.provider == PROVIDER_GEMINI:
        return GEMINI_PREFERRED_CHUNK_SECONDS
    return OPENAI_PREFERRED_CHUNK_SECONDS


def plan_auto_chunk(
    config: ProviderConfig,
    *,
    duration_seconds: float | None,
    upload_format: str,
    source_bytes: int | None = None,
) -> ChunkPlan | None:
    """Plan chunking when the selected media would exceed one request.

    ``source_bytes`` is the size of the file that would be uploaded as-is; when
    it is omitted the upload size is estimated from ``upload_format``. Chunks are
    always re-encoded to ``upload_format``.
    """
    if duration_seconds is None or duration_seconds <= 0:
        return None

    measured_rate = source_bytes / duration_seconds if source_bytes else None
    limit = request_limit_seconds(config, upload_format, bytes_per_second=measured_rate)
    if limit is None:
        return None
    # Providers measure duration and size slightly differently, so keep a margin.
    threshold = limit * AUTO_CHUNK_SAFETY_RATIO
    if duration_seconds <= threshold:
        return None

    chunk_limit = request_limit_seconds(config, upload_format) or limit
    safe_chunk = math.floor(chunk_limit * AUTO_CHUNK_SAFETY_RATIO / 60) * 60
    chunk_seconds = max(
        MIN_AUTO_CHUNK_SECONDS, min(_preferred_chunk_seconds(config), safe_chunk)
    )
    return ChunkPlan(
        chunk_seconds=chunk_seconds,
        request_limit_seconds=limit,
        reason=ui_text.auto_chunk_reason(
            config.provider, limit, threshold, duration_seconds
        ),
    )


def format_duration_option(seconds: float) -> str:
    """Format seconds the way --chunk-duration accepts them, such as 10m."""
    if seconds >= 60 and seconds % 60 == 0:
        return f"{int(seconds // 60)}m"
    return f"{seconds:g}s"
