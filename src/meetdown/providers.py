import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from meetdown import text as ui_text
from meetdown.clova import ClovaSpeechError
from meetdown.clova import transcribe_file as transcribe_clova_file
from meetdown.constants import (
    CLOVA_API_KEY_ENV_NAMES,
    CLOVA_API_URL_ENV_NAMES,
    CLOVA_AUTO_DETECT_API_KEY_ENV_NAMES,
    CLOVA_COMPLETION_SYNC,
    CLOVA_DEFAULT_LANGUAGE,
    CLOVA_MODEL_DESCRIPTION,
    CLOVA_SUPPORTED_LANGUAGES,
    DEFAULT_DIARIZATION,
    GEMINI_API_KEY_ENV_NAMES,
    GEMINI_API_URL_ENV_NAMES,
    GEMINI_AUTO_DETECT_API_KEY_ENV_NAMES,
    GEMINI_DEFAULT_API_URL,
    GEMINI_DEFAULT_MODEL,
    GEMINI_GENERATE_CONTENT_SUFFIX,
    GEMINI_INLINE_LIMIT_BYTES,
    LANGUAGE_AUTO,
    MEETDOWN_API_KEY_ENV,
    OPENAI_API_KEY_ENV_NAMES,
    OPENAI_API_URL_ENV_NAMES,
    OPENAI_AUDIO_TRANSCRIPTIONS_PATH,
    OPENAI_AUTO_DETECT_API_KEY_ENV_NAMES,
    OPENAI_DEFAULT_API_URL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    OPENAI_DIARIZATION_MODEL_MARKER,
    OPENAI_WHISPER_MODEL,
    PROVIDER_CLOVA,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_USAGES_KEY,
    SUPPORTED_PROVIDERS,
    ProviderName,
)
from meetdown.json_types import (
    JsonObject,
    as_json_object,
    as_number,
    as_object_list,
    require_json_object,
)

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
    normalized = value.strip().lower()
    for provider in SUPPORTED_PROVIDERS:
        if normalized == provider:
            return provider
    raise ValueError(ui_text.provider_must_be_supported())


def normalize_clova_language(language: str) -> str:
    normalized = language.strip()
    lower = normalized.lower().replace("_", "-")
    if not normalized or lower == LANGUAGE_AUTO:
        return CLOVA_DEFAULT_LANGUAGE

    aliases = {
        "ko": CLOVA_DEFAULT_LANGUAGE,
        "ko-kr": CLOVA_DEFAULT_LANGUAGE,
        "kr": CLOVA_DEFAULT_LANGUAGE,
        "en": "en-US",
        "en-us": "en-US",
        "ja": "ja",
        "jp": "ja",
        "enko": "enko",
        "zh": "zh-cn",
        "zh-cn": "zh-cn",
        "zh-tw": "zh-tw",
    }
    if lower in aliases:
        return aliases[lower]

    for supported_language in CLOVA_SUPPORTED_LANGUAGES:
        if normalized == supported_language:
            return supported_language

    raise ValueError(
        ui_text.clova_language_must_be_supported(
            ui_text.comma_list(CLOVA_SUPPORTED_LANGUAGES)
        )
    )


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def infer_provider_from_credentials(
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    clova_invoke_url: str | None = None,
    clova_secret_key: str | None = None,
) -> ProviderName:
    if clova_secret_key or (api_key and (api_url or clova_invoke_url)):
        return PROVIDER_CLOVA

    candidates: list[ProviderName] = []

    clova_key = _first_value(
        clova_secret_key, _first_env(*CLOVA_AUTO_DETECT_API_KEY_ENV_NAMES)
    )
    clova_url = _first_value(
        api_url, clova_invoke_url, _first_env(*CLOVA_API_URL_ENV_NAMES)
    )
    if clova_key or (api_key and clova_url):
        candidates.append(PROVIDER_CLOVA)

    if _first_env(*OPENAI_AUTO_DETECT_API_KEY_ENV_NAMES):
        candidates.append(PROVIDER_OPENAI)

    if _first_env(*GEMINI_AUTO_DETECT_API_KEY_ENV_NAMES):
        candidates.append(PROVIDER_GEMINI)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        raise ValueError(ui_text.provider_is_ambiguous(candidates))

    generic_key = _first_value(api_key, _first_env(MEETDOWN_API_KEY_ENV))
    if generic_key:
        raise ValueError(ui_text.provider_generic_key_is_ambiguous())

    raise ValueError(ui_text.provider_could_not_be_inferred())


def provider_model(
    provider: ProviderName,
    model: str | None,
    *,
    diarization: bool = DEFAULT_DIARIZATION,
) -> str | None:
    if provider == PROVIDER_OPENAI:
        if model:
            return model
        return (
            OPENAI_DEFAULT_MODEL if diarization else OPENAI_DEFAULT_NO_DIARIZATION_MODEL
        )
    if provider == PROVIDER_GEMINI:
        return model or GEMINI_DEFAULT_MODEL
    return model


def provider_display_model(config: ProviderConfig) -> str:
    if config.provider == PROVIDER_CLOVA:
        return CLOVA_MODEL_DESCRIPTION
    if config.provider == PROVIDER_OPENAI:
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
    if normalized.endswith(OPENAI_AUDIO_TRANSCRIPTIONS_PATH):
        return normalized
    return f"{normalized}{OPENAI_AUDIO_TRANSCRIPTIONS_PATH}"


def gemini_generate_content_url(api_url: str | None, model: str) -> str:
    if not api_url:
        return (
            f"{GEMINI_DEFAULT_API_URL}/models/{model}{GEMINI_GENERATE_CONTENT_SUFFIX}"
        )
    normalized = api_url.rstrip("/")
    if "{model}" in normalized:
        return normalized.format(model=model)
    if normalized.endswith(GEMINI_GENERATE_CONTENT_SUFFIX):
        return normalized
    return f"{normalized}/models/{model}{GEMINI_GENERATE_CONTENT_SUFFIX}"


def resolve_provider_config(
    *,
    provider: str | None,
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
    normalized = (
        normalize_provider(provider)
        if provider
        else infer_provider_from_credentials(
            api_url=api_url,
            api_key=api_key,
            clova_invoke_url=clova_invoke_url,
            clova_secret_key=clova_secret_key,
        )
    )
    resolved_model = provider_model(normalized, model, diarization=diarization)

    if normalized == PROVIDER_CLOVA:
        if model:
            raise ValueError(ui_text.clova_model_not_supported())
        resolved_language = normalize_clova_language(language)
        resolved_url = _first_value(
            api_url,
            clova_invoke_url,
            _first_env(*CLOVA_API_URL_ENV_NAMES),
        )
        resolved_key = _first_value(
            api_key,
            clova_secret_key,
            _first_env(*CLOVA_API_KEY_ENV_NAMES),
        )
        if not resolved_url:
            raise ValueError(ui_text.clova_missing_api_url())
        if not resolved_key:
            raise ValueError(ui_text.clova_missing_api_key())
        return ProviderConfig(
            provider=normalized,
            language=resolved_language,
            timeout_seconds=timeout_seconds,
            word_alignment=word_alignment,
            diarization=diarization,
            api_url=resolved_url,
            api_key=resolved_key,
        )

    if normalized == PROVIDER_OPENAI:
        openai_key = _first_value(api_key, _first_env(*OPENAI_API_KEY_ENV_NAMES))
        if not openai_key:
            raise ValueError(ui_text.openai_missing_api_key())
        return ProviderConfig(
            provider=normalized,
            language=language,
            timeout_seconds=timeout_seconds,
            word_alignment=word_alignment,
            diarization=diarization,
            api_url=_first_value(
                api_url,
                _first_env(*OPENAI_API_URL_ENV_NAMES),
            ),
            api_key=openai_key,
            openai_model=resolved_model or OPENAI_DEFAULT_MODEL,
        )

    gemini_key = _first_value(
        api_key,
        _first_env(*GEMINI_API_KEY_ENV_NAMES),
    )
    if not gemini_key:
        raise ValueError(ui_text.gemini_missing_api_key())
    return ProviderConfig(
        provider=normalized,
        language=language,
        timeout_seconds=timeout_seconds,
        word_alignment=word_alignment,
        diarization=diarization,
        api_url=_first_value(
            api_url,
            _first_env(*GEMINI_API_URL_ENV_NAMES),
        ),
        api_key=gemini_key,
        gemini_model=resolved_model or GEMINI_DEFAULT_MODEL,
    )


def transcribe_with_provider(
    audio_path: str | Path, config: ProviderConfig
) -> JsonObject:
    if config.provider == PROVIDER_CLOVA:
        if config.api_url is None or config.api_key is None:
            raise ProviderError(ui_text.missing_provider_config(config.provider))
        language = normalize_clova_language(config.language)
        params: JsonObject = {
            "completion": CLOVA_COMPLETION_SYNC,
            "fullText": True,
            "wordAlignment": config.word_alignment,
            "diarization": {"enable": config.diarization},
            "language": language,
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

    if config.provider == PROVIDER_OPENAI:
        return transcribe_openai_file(audio_path, config)
    if config.provider == PROVIDER_GEMINI:
        return transcribe_gemini_file(audio_path, config)
    raise ProviderError(ui_text.unsupported_provider(config.provider))


def _iso_639_language(language: str) -> str:
    return language.split("-", 1)[0].lower()


def _is_auto_language(language: str) -> bool:
    return language.strip().lower() == LANGUAGE_AUTO


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


def _attach_provider_usage(
    normalized: JsonObject, provider_response: JsonObject, usage_key: str
) -> JsonObject:
    usage = as_json_object(provider_response.get(usage_key))
    if usage is not None:
        normalized[PROVIDER_USAGES_KEY] = [usage]
    return normalized


def transcribe_openai_file(
    audio_path: str | Path, config: ProviderConfig
) -> JsonObject:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(ui_text.audio_file_not_found(path))
    if config.api_key is None:
        raise ProviderError(ui_text.missing_api_key(config.provider))

    data: dict[str, str] = {
        "model": config.openai_model,
    }
    if not _is_auto_language(config.language):
        data["language"] = _iso_639_language(config.language)
    if OPENAI_DIARIZATION_MODEL_MARKER in config.openai_model:
        data["response_format"] = "diarized_json"
        data["chunking_strategy"] = "auto"
    elif config.openai_model == OPENAI_WHISPER_MODEL:
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
            ui_text.provider_http_failed(
                "OpenAI", response.status_code, response.text[:1000]
            )
        ) from exc

    try:
        loaded: object = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(
            ui_text.provider_returned_non_json("OpenAI", response.text[:1000])
        ) from exc

    result = require_json_object(loaded, ui_text.provider_returned_non_object("OpenAI"))
    return _attach_provider_usage(_normalize_provider_response(result), result, "usage")


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
        raise FileNotFoundError(ui_text.audio_file_not_found(path))
    if config.api_key is None:
        raise ProviderError(ui_text.missing_api_key(config.provider))
    if path.stat().st_size > GEMINI_INLINE_LIMIT_BYTES:
        raise ProviderError(ui_text.GEMINI_INLINE_LIMIT_EXCEEDED)

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    body: JsonObject = {
        "contents": [
            {
                "parts": [
                    {
                        "text": ui_text.gemini_transcription_prompt(
                            config.language, config.diarization
                        )
                    },
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
            ui_text.provider_http_failed(
                "Gemini", response.status_code, response.text[:1000]
            )
        ) from exc

    try:
        loaded: object = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(
            ui_text.provider_returned_non_json("Gemini", response.text[:1000])
        ) from exc

    response_json = require_json_object(
        loaded, ui_text.provider_returned_non_object("Gemini")
    )
    text = _gemini_text(response_json)
    try:
        model_json = require_json_object(
            json.loads(text), ui_text.GEMINI_TRANSCRIPT_NOT_OBJECT
        )
    except (json.JSONDecodeError, ValueError):
        normalized: JsonObject = {"text": text, "segments": []}
    else:
        normalized = _normalize_provider_response(model_json, fallback_text=text)
    return _attach_provider_usage(normalized, response_json, "usageMetadata")
