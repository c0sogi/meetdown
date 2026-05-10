from pathlib import Path

from meetdown.constants import (
    DEFAULT_DIARIZATION,
    DEFAULT_LANGUAGE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WORD_ALIGNMENT,
)
from meetdown.json_types import JsonObject
from meetdown.providers import resolve_provider_config, transcribe_with_provider


def transcribe_file(
    audio_path: str | Path,
    *,
    provider: str | None = None,
    language: str = DEFAULT_LANGUAGE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    word_alignment: bool = DEFAULT_WORD_ALIGNMENT,
    diarization: bool = DEFAULT_DIARIZATION,
    api_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    clova_invoke_url: str | None = None,
    clova_secret_key: str | None = None,
) -> JsonObject:
    """Transcribe one file with the same provider resolution used by the CLI."""
    config = resolve_provider_config(
        provider=provider,
        language=language,
        timeout_seconds=timeout_seconds,
        word_alignment=word_alignment,
        diarization=diarization,
        api_url=api_url,
        api_key=api_key,
        model=model,
        clova_invoke_url=clova_invoke_url,
        clova_secret_key=clova_secret_key,
    )
    return transcribe_with_provider(audio_path, config)
