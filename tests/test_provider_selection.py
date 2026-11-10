from pathlib import Path

import httpx
import pytest

from meetdown.constants import (
    ERROR_PROVIDER_AMBIGUOUS,
    ERROR_PROVIDER_CREDENTIALS_MISSING,
    ERROR_PROVIDER_INVALID_DEFAULT,
    MEETDOWN_PROVIDER_ENV,
    PROVIDER_ENV_NAMES,
)
from meetdown.providers import (
    ProviderConfig,
    ProviderError,
    ProviderLimitError,
    ProviderSelectionError,
    default_provider_from_env,
    resolve_provider_config,
    transcribe_gemini_file,
    transcribe_openai_file,
)


def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def resolve(provider: str | None = None) -> ProviderConfig:
    return resolve_provider_config(
        provider=provider,
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
    )


class ErrorResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        request = httpx.Request("POST", "https://example.com")
        raise httpx.HTTPStatusError(
            "request failed",
            request=request,
            response=httpx.Response(self.status_code, request=request),
        )


def openai_config() -> ProviderConfig:
    return ProviderConfig(
        provider="openai",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        api_key="test-key",
    )


def test_meetdown_provider_picks_the_default_among_several_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv(MEETDOWN_PROVIDER_ENV, " Gemini ")

    config = resolve()

    assert config.provider == "gemini"
    assert config.provider_source == "environment"


def test_explicit_provider_wins_over_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv(MEETDOWN_PROVIDER_ENV, "gemini")

    config = resolve("openai")

    assert config.provider == "openai"
    assert config.provider_source == "option"


def test_single_configured_provider_is_inferred_from_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = resolve()

    assert config.provider == "openai"
    assert config.provider_source == "credentials"


def test_invalid_default_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv(MEETDOWN_PROVIDER_ENV, "whisper")

    with pytest.raises(ProviderSelectionError) as excinfo:
        default_provider_from_env()

    assert excinfo.value.code == ERROR_PROVIDER_INVALID_DEFAULT
    assert MEETDOWN_PROVIDER_ENV in str(excinfo.value)


def test_ambiguous_credentials_report_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("CLOVA_SPEECH_SECRET_KEY", "clova-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    with pytest.raises(ProviderSelectionError) as excinfo:
        resolve()

    assert excinfo.value.code == ERROR_PROVIDER_AMBIGUOUS
    assert excinfo.value.candidates == ("clova", "openai", "gemini")
    assert MEETDOWN_PROVIDER_ENV in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)


def test_missing_credentials_have_a_stable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)

    with pytest.raises(ProviderSelectionError) as excinfo:
        resolve("openai")

    assert excinfo.value.code == ERROR_PROVIDER_CREDENTIALS_MISSING


def test_openai_duration_limit_is_a_limit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake audio")
    body = (
        '{"error": {"message": "audio duration 1926.33 seconds is longer than '
        '1400 seconds which is the maximum for this model"}}'
    )

    def fake_post(*args: object, **kwargs: object) -> ErrorResponse:
        return ErrorResponse(400, body)

    monkeypatch.setattr("meetdown.providers.httpx.post", fake_post)

    with pytest.raises(ProviderLimitError, match="HTTP 400"):
        transcribe_openai_file(audio, openai_config())


def test_other_openai_http_errors_stay_provider_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"fake audio")

    def fake_post(*args: object, **kwargs: object) -> ErrorResponse:
        return ErrorResponse(401, '{"error": {"message": "Incorrect API key"}}')

    monkeypatch.setattr("meetdown.providers.httpx.post", fake_post)

    with pytest.raises(ProviderError) as excinfo:
        transcribe_openai_file(audio, openai_config())

    assert not isinstance(excinfo.value, ProviderLimitError)


def test_gemini_inline_size_limit_is_a_limit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"0123456789")
    monkeypatch.setattr("meetdown.providers.GEMINI_INLINE_LIMIT_BYTES", 4)

    with pytest.raises(ProviderLimitError):
        transcribe_gemini_file(
            audio,
            ProviderConfig(
                provider="gemini",
                language="ko-KR",
                timeout_seconds=60,
                word_alignment=False,
                diarization=True,
                api_key="test-key",
            ),
        )
