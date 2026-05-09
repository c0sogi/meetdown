import json
from argparse import Namespace
from pathlib import Path

import pytest

from meetdown.cli import (
    build_parser,
    build_replay_command,
    choose_upload_format,
    mask_secret,
    run,
    should_prepare_whole_file_upload,
)
from meetdown.providers import ProviderConfig


def test_choose_upload_format_uses_compression_presets() -> None:
    assert choose_upload_format("smallest", None) == "mp3"
    assert choose_upload_format("lossless", None) == "flac"
    assert choose_upload_format("none", None) == "wav"
    assert choose_upload_format("smallest", "flac") == "flac"


def test_should_prepare_whole_file_upload_matches_compression_intent() -> None:
    assert should_prepare_whole_file_upload("smallest", None)
    assert should_prepare_whole_file_upload("lossless", None)
    assert should_prepare_whole_file_upload("none", "mp3")
    assert not should_prepare_whole_file_upload("none", None)


def test_mask_secret_shows_only_edges() -> None:
    assert mask_secret(None) == "not configured"
    assert mask_secret("abcd") == "****"
    assert mask_secret("secret-key") == "se******ey"
    assert mask_secret("sk-proj-1234567890") == "sk-p********7890"


def test_build_replay_command_is_powershell_copyable() -> None:
    args = Namespace(
        audio_path="C:\\Meetings\\weekly sync.m4a",
        title="Weekly Sync",
        compress="smallest",
        chunk_format=None,
        chunk_duration="10m",
        start="00:10:00",
        end=None,
        save_json="meeting.json",
    )
    config = ProviderConfig(
        provider="openai",
        language="ko-KR",
        timeout_seconds=3600,
        word_alignment=True,
        diarization=True,
        api_url="https://api.openai.com/v1",
        api_key="sk-proj-1234567890",
        openai_model="gpt-4o-transcribe-diarize",
    )

    command = build_replay_command(
        args=args,
        provider_config=config,
        output_path=Path("meeting.md"),
    )

    assert command.startswith("uvx meetdown 'C:\\Meetings\\weekly sync.m4a'")
    assert "--api-key '<OpenAI API key>'" in command
    assert "--chunk-duration 10m" in command
    assert "--word-alignment" in command


def test_help_includes_quick_start_and_provider_guidance() -> None:
    help_text = build_parser().format_help()

    assert "Quick start:" in help_text
    assert "CLOVA:" in help_text
    assert "uvx meetdown" in help_text
    assert "--api-url" in help_text
    assert "provider and credentials:" in help_text
    assert "Provider model defaults:" in help_text
    assert "gpt-4o-transcribe-diarize" in help_text
    assert "CLOVA Speech domain model" in help_text
    assert '--provider openai --api-key "<OpenAI API key>"' in help_text
    assert "/recognizer/upload is optional" in help_text
    assert "\n    meetdown " not in help_text
    assert "$env:" not in help_text


def test_cli_converts_existing_json(tmp_path: Path) -> None:
    source = tmp_path / "response.json"
    output = tmp_path / "meeting.md"
    source.write_text(
        json.dumps(
            {
                "text": "회의를 시작합니다.",
                "segments": [
                    {
                        "start": 0,
                        "end": 2000,
                        "text": "회의를 시작합니다.",
                        "speaker": {"label": "1"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = run(
        ["--from-json", str(source), "-o", str(output), "--title", "테스트 회의"]
    )

    assert exit_code == 0
    assert "테스트 회의" in output.read_text(encoding="utf-8")


def test_cli_reports_missing_audio_before_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.m4a"

    with pytest.raises(SystemExit) as exc_info:
        run([str(missing)])

    assert exc_info.value.code == 1
    assert "audio file not found" in capsys.readouterr().err
