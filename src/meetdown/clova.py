import json
from pathlib import Path

import httpx

from meetdown.json_types import JsonObject, as_json_object


class ClovaSpeechError(RuntimeError):
    """Raised when CLOVA Speech rejects or fails a request."""


DEFAULT_PARAMS: JsonObject = {
    "language": "ko-KR",
    "completion": "sync",
    "fullText": True,
    "wordAlignment": False,
    "diarization": {"enable": True},
}


def _as_params_dict(value: object) -> JsonObject | None:
    return as_json_object(value)


def build_upload_url(invoke_url: str) -> str:
    base = invoke_url.strip().rstrip("/")
    if not base:
        raise ValueError("invoke_url must not be empty")
    if base.lower().endswith("/recognizer/upload"):
        return base
    return f"{base}/recognizer/upload"


def merge_params(base: JsonObject, overrides: JsonObject | None) -> JsonObject:
    if not overrides:
        return dict(base)

    merged = dict(base)
    for key, value in overrides.items():
        base_value = merged.get(key)
        nested_base = _as_params_dict(base_value)
        nested_override = _as_params_dict(value)
        if nested_override is not None and nested_base is not None:
            merged[key] = merge_params(nested_base, nested_override)
        else:
            merged[key] = value
    return merged


def transcribe_file(
    audio_path: str | Path,
    *,
    invoke_url: str,
    secret_key: str,
    params: JsonObject | None = None,
    timeout_seconds: float = 3600,
) -> JsonObject:
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path}")

    request_params = merge_params(DEFAULT_PARAMS, params)
    headers = {"X-CLOVASPEECH-API-KEY": secret_key}
    upload_url = build_upload_url(invoke_url)

    with path.open("rb") as media:
        files = {
            "media": (path.name, media),
            "params": (
                None,
                json.dumps(request_params, ensure_ascii=False),
                "application/json",
            ),
        }
        response = httpx.post(
            upload_url, headers=headers, files=files, timeout=timeout_seconds
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:1000]
        raise ClovaSpeechError(
            f"CLOVA Speech request failed with HTTP {response.status_code}: {body}"
        ) from exc

    try:
        result: object = response.json()
    except json.JSONDecodeError as exc:
        body = response.text[:1000]
        raise ClovaSpeechError(
            f"CLOVA Speech returned non-JSON response: {body}"
        ) from exc

    json_result = as_json_object(result)
    if json_result is None:
        raise ClovaSpeechError(
            "CLOVA Speech returned a JSON value that is not an object"
        )
    return json_result
