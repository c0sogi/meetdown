import pytest

from meetdown.providers import (
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    gemini_generate_content_url,
    normalize_provider,
    openai_transcriptions_url,
    provider_model,
    resolve_provider_config,
)


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
