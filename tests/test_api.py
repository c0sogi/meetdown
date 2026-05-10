from pathlib import Path

import pytest

import meetdown
from meetdown import (
    NotionUploadConfig,
    ProviderConfig,
    notion_upload_url,
    render_markdown,
    transcribe_file,
    upload_markdown_to_notion,
    write_markdown,
)
from meetdown.constants import (
    DEFAULT_DIARIZATION,
    DEFAULT_LANGUAGE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WORD_ALIGNMENT,
)


def test_top_level_exports_public_api() -> None:
    assert meetdown.transcribe_file is transcribe_file
    assert callable(render_markdown)
    assert callable(write_markdown)
    assert meetdown.NotionUploadConfig is NotionUploadConfig
    assert meetdown.upload_markdown_to_notion is upload_markdown_to_notion
    assert meetdown.notion_upload_url is notion_upload_url


def test_transcribe_file_resolves_config_and_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"audio")
    captured: dict[str, object] = {}

    def fake_resolve_provider_config(**kwargs: object) -> ProviderConfig:
        captured["resolve_kwargs"] = kwargs
        timeout_seconds = kwargs["timeout_seconds"]
        if not isinstance(timeout_seconds, int | float):
            raise TypeError("timeout_seconds must be numeric")
        return ProviderConfig(
            provider="openai",
            language=str(kwargs["language"]),
            timeout_seconds=float(timeout_seconds),
            word_alignment=bool(kwargs["word_alignment"]),
            diarization=bool(kwargs["diarization"]),
            api_key="openai-key",
            openai_model=str(kwargs["model"]),
        )

    def fake_transcribe_with_provider(
        transcribe_path: str | Path, config: ProviderConfig
    ) -> dict[str, object]:
        captured["transcribe_path"] = transcribe_path
        captured["config"] = config
        return {"text": "Hello", "segments": []}

    monkeypatch.setattr(
        "meetdown.api.resolve_provider_config", fake_resolve_provider_config
    )
    monkeypatch.setattr(
        "meetdown.api.transcribe_with_provider", fake_transcribe_with_provider
    )

    result = transcribe_file(
        audio_path,
        provider="openai",
        language="auto",
        timeout_seconds=12,
        word_alignment=True,
        diarization=False,
        api_key="openai-key",
        model="whisper-1",
    )

    assert result == {"text": "Hello", "segments": []}
    assert captured["transcribe_path"] == audio_path
    assert captured["resolve_kwargs"] == {
        "provider": "openai",
        "language": "auto",
        "timeout_seconds": 12,
        "word_alignment": True,
        "diarization": False,
        "api_url": None,
        "api_key": "openai-key",
        "model": "whisper-1",
        "clova_invoke_url": None,
        "clova_secret_key": None,
    }


def test_transcribe_file_uses_shared_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"audio")
    captured: dict[str, object] = {}

    def fake_resolve_provider_config(**kwargs: object) -> ProviderConfig:
        captured["resolve_kwargs"] = kwargs
        return ProviderConfig(
            provider="openai",
            language=str(kwargs["language"]),
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            word_alignment=DEFAULT_WORD_ALIGNMENT,
            diarization=DEFAULT_DIARIZATION,
            api_key="openai-key",
        )

    def fake_transcribe_with_provider(
        transcribe_path: str | Path, config: ProviderConfig
    ) -> dict[str, object]:
        captured["transcribe_path"] = transcribe_path
        captured["config"] = config
        return {"text": "Hello", "segments": []}

    monkeypatch.setattr(
        "meetdown.api.resolve_provider_config", fake_resolve_provider_config
    )
    monkeypatch.setattr(
        "meetdown.api.transcribe_with_provider", fake_transcribe_with_provider
    )

    result = transcribe_file(audio_path)

    assert result == {"text": "Hello", "segments": []}
    assert captured["transcribe_path"] == audio_path
    assert captured["resolve_kwargs"] == {
        "provider": None,
        "language": DEFAULT_LANGUAGE,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "word_alignment": DEFAULT_WORD_ALIGNMENT,
        "diarization": DEFAULT_DIARIZATION,
        "api_url": None,
        "api_key": None,
        "model": None,
        "clova_invoke_url": None,
        "clova_secret_key": None,
    }
