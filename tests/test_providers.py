from pathlib import Path

import pytest

from meetdown.constants import PROVIDER_ENV_NAMES
from meetdown.json_types import JsonObject
from meetdown.providers import (
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    ProviderConfig,
    gemini_generate_content_url,
    infer_provider_from_credentials,
    normalize_provider,
    openai_transcriptions_url,
    provider_model,
    resolve_provider_config,
    transcribe_with_provider,
)
from meetdown.text import gemini_transcription_prompt


def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_normalize_provider_accepts_supported_names() -> None:
    assert normalize_provider(" CLOVA ") == "clova"
    assert normalize_provider("openai") == "openai"
    assert normalize_provider("gemini") == "gemini"


def test_normalize_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="provider"):
        normalize_provider("unknown")


def test_provider_model_uses_provider_defaults() -> None:
    assert provider_model("openai", None) == OPENAI_DEFAULT_MODEL
    assert (
        provider_model("openai", None, diarization=False)
        == OPENAI_DEFAULT_NO_DIARIZATION_MODEL
    )
    assert provider_model("gemini", None) == GEMINI_DEFAULT_MODEL
    assert provider_model("clova", None) is None
    assert provider_model("openai", "custom-model") == "custom-model"


def test_provider_url_builders_accept_base_or_full_urls() -> None:
    assert (
        openai_transcriptions_url("https://example.com/v1")
        == "https://example.com/v1/audio/transcriptions"
    )
    assert (
        openai_transcriptions_url("https://example.com/v1/audio/transcriptions")
        == "https://example.com/v1/audio/transcriptions"
    )
    assert (
        gemini_generate_content_url("https://example.com/v1beta", "gemini-test")
        == "https://example.com/v1beta/models/gemini-test:generateContent"
    )
    assert (
        gemini_generate_content_url(
            "https://example.com/{model}:generateContent", "gemini-test"
        )
        == "https://example.com/gemini-test:generateContent"
    )


def test_auto_language_does_not_send_clova_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "meeting.m4a"
    audio.write_bytes(b"fake audio")
    captured: dict[str, JsonObject | None] = {}

    def fake_transcribe_clova_file(*args: object, **kwargs: object) -> JsonObject:
        params = kwargs.get("params")
        captured["params"] = params if isinstance(params, dict) else None
        return {"text": "Transcript", "segments": []}

    monkeypatch.setattr(
        "meetdown.providers.transcribe_clova_file", fake_transcribe_clova_file
    )

    transcribe_with_provider(
        audio,
        ProviderConfig(
            provider="clova",
            language="auto",
            timeout_seconds=60,
            word_alignment=False,
            diarization=True,
            api_url="https://clova.example.com",
            api_key="secret",
        ),
    )

    params = captured["params"]
    assert params is not None
    assert "language" not in params


def test_gemini_prompt_uses_auto_language_instruction() -> None:
    prompt = gemini_transcription_prompt("auto", diarization=True)

    assert "Detect the spoken language or languages automatically." in prompt
    assert "The expected language is auto" not in prompt


def test_infer_provider_from_provider_specific_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")

    assert infer_provider_from_credentials() == "openai"


def test_infer_provider_uses_clova_when_generic_key_has_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")

    assert (
        infer_provider_from_credentials(api_url="https://example.com", api_key="secret")
        == "clova"
    )


def test_infer_provider_rejects_ambiguous_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-env-key")

    with pytest.raises(ValueError, match="ambiguous"):
        infer_provider_from_credentials()


def test_infer_provider_rejects_generic_key_without_provider_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)

    with pytest.raises(ValueError, match="generic API key"):
        infer_provider_from_credentials(api_key="secret")


def test_resolve_provider_config_uses_generic_url_and_key_for_clova() -> None:
    config = resolve_provider_config(
        provider="clova",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        api_url="https://example.com",
        api_key="secret",
        model=None,
    )

    assert config.provider == "clova"
    assert config.api_url == "https://example.com"
    assert config.api_key == "secret"


def test_resolve_provider_config_auto_detects_openai_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")

    config = resolve_provider_config(
        provider=None,
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        model=None,
    )

    assert config.provider == "openai"
    assert config.api_key == "openai-env-key"


def test_resolve_provider_config_auto_detects_clova_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("CLOVA_SPEECH_INVOKE_URL", "https://clova.example.com")
    monkeypatch.setenv("CLOVA_SPEECH_SECRET_KEY", "clova-env-key")

    config = resolve_provider_config(
        provider=None,
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        model=None,
    )

    assert config.provider == "clova"
    assert config.api_url == "https://clova.example.com"
    assert config.api_key == "clova-env-key"


def test_resolve_provider_config_rejects_model_for_clova() -> None:
    with pytest.raises(ValueError, match="--model"):
        resolve_provider_config(
            provider="clova",
            language="ko-KR",
            timeout_seconds=60,
            word_alignment=False,
            diarization=True,
            api_url="https://example.com",
            api_key="secret",
            model="custom-model",
        )


def test_resolve_provider_config_keeps_legacy_clova_aliases() -> None:
    config = resolve_provider_config(
        provider="clova",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        model=None,
        clova_invoke_url="https://legacy.example.com",
        clova_secret_key="legacy-secret",
    )

    assert config.api_url == "https://legacy.example.com"
    assert config.api_key == "legacy-secret"


def test_resolve_provider_config_uses_generic_key_for_openai() -> None:
    config = resolve_provider_config(
        provider="openai",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        api_key="openai-key",
        model=None,
    )

    assert config.provider == "openai"
    assert config.api_key == "openai-key"
    assert config.openai_model == OPENAI_DEFAULT_MODEL


def test_resolve_provider_config_uses_generic_key_for_gemini() -> None:
    config = resolve_provider_config(
        provider="gemini",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        api_url="https://gemini.example.com/v1beta",
        api_key="gemini-key",
        model="gemini-custom",
    )

    assert config.provider == "gemini"
    assert config.api_url == "https://gemini.example.com/v1beta"
    assert config.api_key == "gemini-key"
    assert config.gemini_model == "gemini-custom"
