from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from meetdown.clova import ClovaSpeechError, transcribe_file as transcribe_clova_file
from meetdown.json_types import (
    JsonObject,
    as_json_object,
    as_number,
    as_object_list,
    require_json_object,
)

ProviderName = Literal["clova", "openai", "gemini"]

CLOVA_MODEL_DESCRIPTION = "CLOVA Speech domain model (not configurable by --model)"
OPENAI_DEFAULT_MODEL = "gpt-4o-transcribe-diarize"
OPENAI_DEFAULT_NO_DIARIZATION_MODEL = "gpt-4o-mini-transcribe"
OPENAI_DEFAULT_API_URL = "https://api.openai.com/v1/audio/transcriptions"
GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview"
GEMINI_DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_INLINE_LIMIT_BYTES = 19 * 1024 * 1024

_AUDIO_MIME_BY_SUFFIX = {
    ".aac": "audio/aac",
    ".aiff": "audio/aiff",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


class ProviderError(RuntimeError):
    """Raised when a speech provider rejects or cannot process a request."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: ProviderName
    language: str
    timeout_seconds: float
    word_alignment: bool
    diarization: bool
    api_url: str | None = None
    api_key: str | None = None
    openai_model: str = OPENAI_DEFAULT_MODEL
    gemini_model: str = GEMINI_DEFAULT_MODEL


def normalize_provider(value: str) -> ProviderName:
    provider = value.strip().lower()
    if provider == "clova":
        return "clova"
    if provider == "openai":
        return "openai"
    if provider == "gemini":
        return "gemini"
    raise ValueError("provider must be one of: clova, openai, gemini")


def provider_model(
    provider: ProviderName, model: str | None, *, diarization: bool = True
) -> str | None:
    if provider == "openai":
        if model:
            return model
        return (
            OPENAI_DEFAULT_MODEL if diarization else OPENAI_DEFAULT_NO_DIARIZATION_MODEL
        )
    if provider == "gemini":
        return model or GEMINI_DEFAULT_MODEL
    return model


def provider_display_model(config: ProviderConfig) -> str:
    if config.provider == "clova":
        return CLOVA_MODEL_DESCRIPTION
    if config.provider == "openai":
        return config.openai_model
    return config.gemini_model


def _first_value(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def openai_transcriptions_url(api_url: str | None) -> str:
    if not api_url:
        return OPENAI_DEFAULT_API_URL
    normalized = api_url.rstrip("/")
    if normalized.endswith("/audio/transcriptions"):
        return normalized
    return f"{normalized}/audio/transcriptions"


def gemini_generate_content_url(api_url: str | None, model: str) -> str:
    if not api_url:
        return f"{GEMINI_DEFAULT_API_URL}/models/{model}:generateContent"
    normalized = api_url.rstrip("/")
    if "{model}" in normalized:
        return normalized.format(model=model)
    if normalized.endswith(":generateContent"):
        return normalized
    return f"{normalized}/models/{model}:generateContent"


def resolve_provider_config(
    *,
    provider: str,
    language: str,
    timeout_seconds: float,
    word_alignment: bool,
    diarization: bool,
    api_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    clova_invoke_url: str | None = None,
    clova_secret_key: str | None = None,
) -> ProviderConfig:
    normalized = normalize_provider(provider)
    resolved_model = provider_model(normalized, model, diarization=diarization)

    if normalized == "clova":
        if model:
            raise ValueError("--model is not supported for clova")
        resolved_url = _first_value(
            api_url,
            clova_invoke_url,
            os.getenv("CLOVA_SPEECH_INVOKE_URL"),
            os.getenv("MEETDOWN_API_URL"),
        )
        resolved_key = _first_value(
            api_key,
            clova_secret_key,
            os.getenv("CLOVA_SPEECH_SECRET_KEY"),
            os.getenv("MEETDOWN_API_KEY"),
        )
        if not resolved_url:
            raise ValueError(
                "--api-url or CLOVA_SPEECH_INVOKE_URL is required for clova"
            )
        if not resolved_key:
            raise ValueError(
                "--api-key or CLOVA_SPEECH_SECRET_KEY is required for clova"
            )
        return ProviderConfig(
            provider=normalized,
            language=language,
            timeout_seconds=timeout_seconds,
            word_alignment=word_alignment,
            diarization=diarization,
            api_url=resolved_url,
            api_key=resolved_key,
        )

    if normalized == "openai":
        openai_key = _first_value(
            api_key, os.getenv("OPENAI_API_KEY"), os.getenv("MEETDOWN_API_KEY")
        )
        if not openai_key:
            raise ValueError("--api-key or OPENAI_API_KEY is required for openai")
        return ProviderConfig(
            provider=normalized,
            language=language,
            timeout_seconds=timeout_seconds,
            word_alignment=word_alignment,
            diarization=diarization,
            api_url=_first_value(
                api_url,
                os.getenv("OPENAI_API_URL"),
                os.getenv("OPENAI_BASE_URL"),
                os.getenv("MEETDOWN_API_URL"),
            ),
            api_key=openai_key,
            openai_model=resolved_model or OPENAI_DEFAULT_MODEL,
        )

    gemini_key = _first_value(
        api_key,
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
        os.getenv("MEETDOWN_API_KEY"),
    )
    if not gemini_key:
        raise ValueError(
            "--api-key, GEMINI_API_KEY, or GOOGLE_API_KEY is required for gemini"
        )
    return ProviderConfig(
        provider=normalized,
        language=language,
        timeout_seconds=timeout_seconds,
        word_alignment=word_alignment,
        diarization=diarization,
        api_url=_first_value(
            api_url,
            os.getenv("GEMINI_API_URL"),
            os.getenv("GOOGLE_API_URL"),
            os.getenv("MEETDOWN_API_URL"),
        ),
        api_key=gemini_key,
        gemini_model=resolved_model or GEMINI_DEFAULT_MODEL,
    )


def transcribe_with_provider(
    audio_path: str | Path, config: ProviderConfig
) -> JsonObject:
    if config.provider == "clova":
        if config.api_url is None or config.api_key is None:
            raise ProviderError("clova provider is missing API URL or API key")
        params: JsonObject = {
            "language": config.language,
            "completion": "sync",
            "fullText": True,
            "wordAlignment": config.word_alignment,
            "diarization": {"enable": config.diarization},
        }
        try:
            return transcribe_clova_file(
                audio_path,
                invoke_url=config.api_url,
                secret_key=config.api_key,
                params=params,
                timeout_seconds=config.timeout_seconds,
            )
        except ClovaSpeechError as exc:
            raise ProviderError(str(exc)) from exc

    if config.provider == "openai":
        return transcribe_openai_file(audio_path, config)
    if config.provider == "gemini":
        return transcribe_gemini_file(audio_path, config)
    raise ProviderError(f"unsupported provider: {config.provider}")


def _iso_639_language(language: str) -> str:
    return language.split("-", 1)[0].lower()


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _AUDIO_MIME_BY_SUFFIX:
        return _AUDIO_MIME_BY_SUFFIX[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _coerce_ms(value: object) -> int | float | None:
    number = as_number(value)
    if number is None:
        return None
    return number * 1000


def _segment_from_object(item: object) -> JsonObject | None:
    source = as_json_object(item)
    if source is None:
        return None

    segment: JsonObject = {}
    text = source.get("text") or source.get("content") or source.get("transcript")
    if text is not None:
        segment["text"] = str(text)

    start_ms = _coerce_ms(source.get("start"))
    end_ms = _coerce_ms(source.get("end"))
    if start_ms is not None:
        segment["start"] = start_ms
    if end_ms is not None:
        segment["end"] = end_ms

    speaker_value = source.get("speaker")
    speaker = as_json_object(speaker_value)
    if speaker is not None:
        segment["speaker"] = speaker
    elif speaker_value is not None:
        segment["speaker"] = {"label": str(speaker_value)}

    return segment


def _normalize_provider_response(
    result: JsonObject, fallback_text: str = ""
) -> JsonObject:
    text = str(result.get("text") or fallback_text).strip()
    normalized_segments: list[object] = []
    source_segments = as_object_list(result.get("segments"))
    if source_segments is None:
        source_segments = as_object_list(result.get("speaker_segments"))
    for item in source_segments or []:
        segment = _segment_from_object(item)
        if segment is not None:
            normalized_segments.append(segment)

    normalized: JsonObject = {"text": text, "segments": normalized_segments}
    confidence = as_number(result.get("confidence"))
    if confidence is not None:
        normalized["confidence"] = confidence
    return normalized


def transcribe_openai_file(
    audio_path: str | Path, config: ProviderConfig
) -> JsonObject:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path}")
    if config.api_key is None:
        raise ProviderError("openai provider is missing API key")

    data: dict[str, str] = {
        "model": config.openai_model,
        "language": _iso_639_language(config.language),
    }
    if "diarize" in config.openai_model:
        data["response_format"] = "diarized_json"
        data["chunking_strategy"] = "auto"
    elif config.openai_model == "whisper-1":
        data["response_format"] = "verbose_json"
    else:
        data["response_format"] = "json"

    headers = {"Authorization": f"Bearer {config.api_key}"}
    with path.open("rb") as media:
        files = {"file": (path.name, media, _mime_type(path))}
        response = httpx.post(
            openai_transcriptions_url(config.api_url),
            headers=headers,
            data=data,
            files=files,
            timeout=config.timeout_seconds,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ProviderError(
            f"OpenAI transcription failed with HTTP {response.status_code}: {response.text[:1000]}"
        ) from exc

    try:
        loaded: object = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"OpenAI returned non-JSON response: {response.text[:1000]}"
        ) from exc

    return _normalize_provider_response(
        require_json_object(
            loaded, "OpenAI returned a JSON value that is not an object"
        )
    )


def _gemini_prompt(language: str, diarization: bool) -> str:
    speaker_instruction = (
        "Include speaker labels when you can identify speaker changes."
        if diarization
        else "Do not invent speaker labels."
    )
    return (
        "Transcribe this meeting audio. Return only JSON with this shape: "
        '{"text":"full transcript","segments":[{"start":0,"end":0,'
        '"text":"segment transcript","speaker":{"label":"1"}}]}. '
        "Use seconds for start and end. "
        f"The expected language is {language}. {speaker_instruction}"
    )


def _gemini_text(response: JsonObject) -> str:
    candidates = as_object_list(response.get("candidates")) or []
    texts: list[str] = []
    for candidate_item in candidates:
        candidate = as_json_object(candidate_item)
        if candidate is None:
            continue
        content = as_json_object(candidate.get("content"))
        if content is None:
            continue
        for part_item in as_object_list(content.get("parts")) or []:
            part = as_json_object(part_item)
            if part is None:
                continue
            text = part.get("text")
            if text is not None:
                texts.append(str(text))
    return "\n".join(texts).strip()


def transcribe_gemini_file(
    audio_path: str | Path, config: ProviderConfig
) -> JsonObject:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path}")
    if config.api_key is None:
        raise ProviderError("gemini provider is missing API key")
    if path.stat().st_size > GEMINI_INLINE_LIMIT_BYTES:
        raise ProviderError(
            "Gemini inline audio requests are limited to about 20 MB. "
            "Use --chunk-duration or --compress smallest."
        )

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    body: JsonObject = {
        "contents": [
            {
                "parts": [
                    {"text": _gemini_prompt(config.language, config.diarization)},
                    {"inline_data": {"mime_type": _mime_type(path), "data": encoded}},
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    response = httpx.post(
        gemini_generate_content_url(config.api_url, config.gemini_model),
        params={"key": config.api_key},
        json=body,
        timeout=config.timeout_seconds,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ProviderError(
            f"Gemini transcription failed with HTTP {response.status_code}: {response.text[:1000]}"
        ) from exc

    try:
        loaded: object = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"Gemini returned non-JSON response: {response.text[:1000]}"
        ) from exc

    response_json = require_json_object(
        loaded, "Gemini returned a JSON value that is not an object"
    )
    text = _gemini_text(response_json)
    try:
        model_json = require_json_object(
            json.loads(text), "Gemini transcript was not a JSON object"
        )
    except (json.JSONDecodeError, ValueError):
        return {"text": text, "segments": []}
    return _normalize_provider_response(model_json, fallback_text=text)
