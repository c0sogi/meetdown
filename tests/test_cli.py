import json
import re
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from meetdown import text as ui_text
from meetdown.cli import (
    CliOptions,
    build_app,
    build_defaults_report,
    build_replay_command,
    choose_upload_format,
    default_cli_options,
    mask_secret,
    run,
    should_prepare_whole_file_upload,
    should_use_color,
)
from meetdown.constants import (
    ANSI_BLUE,
    ANSI_CYAN,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_YELLOW,
    COLOR_ENV,
    DEFAULT_COMPRESS,
    DEFAULT_DIARIZATION,
    DEFAULT_LANGUAGE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WORD_ALIGNMENT,
    NO_COLOR_ENV,
    PROVIDER_USAGES_KEY,
    PROVIDER_ENV_NAMES,
)
from meetdown.notion import NotionUploadConfig, NotionUploadError
from meetdown.providers import ProviderConfig

runner = CliRunner()


def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


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


def test_cli_parser_uses_shared_defaults() -> None:
    args = default_cli_options()

    assert args.compress == DEFAULT_COMPRESS
    assert args.language == DEFAULT_LANGUAGE
    assert args.timeout == DEFAULT_TIMEOUT_SECONDS
    assert args.word_alignment is DEFAULT_WORD_ALIGNMENT
    assert args.no_diarization is (not DEFAULT_DIARIZATION)


def test_mask_secret_shows_only_edges() -> None:
    assert mask_secret(None) == "not configured"
    assert mask_secret("abcd") == "****"
    assert mask_secret("secret-key") == "se******ey"
    assert mask_secret("sk-proj-1234567890") == "sk-p********7890"


def test_cli_version_uses_package_metadata(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run(["--version"])

    assert exit_code == 0
    assert f"meetdown {version('meetdown')}" in capsys.readouterr().out


def test_build_replay_command_is_powershell_copyable() -> None:
    args = CliOptions(
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
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
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


def test_root_help_lists_focused_subcommands() -> None:
    result = runner.invoke(build_app(color=False), ["--help"], prog_name="meetdown")
    help_text = result.stdout

    assert result.exit_code == 0
    assert "Usage: meetdown" in help_text
    assert "Commands" in help_text
    assert "transcribe" in help_text
    assert "quickstart" in help_text
    assert "defaults" in help_text
    assert "Current defaults" not in help_text
    assert "Provider recipes" not in help_text
    assert "--notion" not in help_text


def test_transcribe_help_includes_provider_and_notion_options() -> None:
    result = runner.invoke(
        build_app(color=False), ["transcribe", "--help"], prog_name="meetdown"
    )
    help_text = result.stdout
    compact_help = re.sub(r"\s+", " ", help_text)

    assert result.exit_code == 0
    assert "Usage: meetdown transcribe" in help_text
    assert "--api-url" in help_text
    assert "Provider" in help_text
    assert "Notion" in help_text
    assert "--notion" in help_text
    assert "--notion-parent-page" in help_text
    assert "meetdown quickstart" in compact_help
    assert "Defaults to ko-KR" not in help_text
    assert f"Defaults to {format(DEFAULT_TIMEOUT_SECONDS, 'g')}" not in help_text
    assert "--show-defaults" not in help_text
    assert "/recognizer/upload is optional" in compact_help
    assert "\n    meetdown " not in help_text
    assert "$env:" not in help_text


def test_cli_converts_existing_json(tmp_path: Path) -> None:
    source = tmp_path / "response.json"
    output = tmp_path / "meeting.md"
    source.write_text(
        json.dumps(
            {
                "text": "The meeting is starting.",
                "segments": [
                    {
                        "start": 0,
                        "end": 2000,
                        "text": "The meeting is starting.",
                        "speaker": {"label": "1"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = run(
        ["--from-json", str(source), "-o", str(output), "--title", "Test Meeting"]
    )

    assert exit_code == 0
    assert "Test Meeting" in output.read_text(encoding="utf-8")


def test_bare_cli_prints_clean_root_help_without_defaults(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_provider_env(monkeypatch)

    exit_code = run([])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Usage: meetdown" in output
    assert "transcribe" in output
    assert "quickstart" in output
    assert "defaults" in output
    assert "Current defaults" not in output
    assert "Provider recipes" not in output


def test_quickstart_command_prints_focused_rich_guide(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run(["quickstart"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Quickstart" in output
    assert "Provider recipes" in output
    assert "meetdown[notion]" in output
    assert "Current defaults" not in output


def test_defaults_command_prints_current_defaults(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_provider_env(monkeypatch)

    exit_code = run(["defaults"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Current defaults" in output
    assert "Runtime" in output
    assert "Notion" in output
    assert re.search(r"Provider\s+auto-detect", output)
    assert re.search(r"Detected now\s+not inferred", output)
    assert re.search(r"Language\s+auto", output)
    assert re.search(r"Compression\s+smallest", output)
    assert re.search(r"Upload format\s+mp3", output)
    assert "Quickstart" not in output


def test_defaults_report_shows_provider_inference_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")
    args = default_cli_options()

    output = build_defaults_report(args)

    assert re.search(r"Detected now\s+openai", output)
    assert re.search(r"openai API key\s+configured \(OPENAI_API_KEY\)", output)


def test_defaults_report_can_be_color_coded_by_section() -> None:
    args = default_cli_options()

    plain_output = build_defaults_report(args)
    color_output = build_defaults_report(args, color=True)

    assert "\033[" not in plain_output
    assert "\033[" in color_output
    assert (
        f"{ANSI_CYAN}{ui_text.defaults_section(ui_text.DEFAULTS_RUNTIME_SECTION)}"
        in color_output
    )
    assert (
        f"{ANSI_GREEN}{ui_text.defaults_section(ui_text.DEFAULTS_OUTPUT_SECTION)}"
        in color_output
    )
    assert (
        f"{ANSI_YELLOW}{ui_text.defaults_section(ui_text.DEFAULTS_MEDIA_SECTION)}"
        in color_output
    )
    assert (
        f"{ANSI_MAGENTA}{ui_text.defaults_section(ui_text.DEFAULTS_MODELS_SECTION)}"
        in color_output
    )
    assert (
        f"{ANSI_BLUE}{ui_text.defaults_section(ui_text.DEFAULTS_CREDENTIALS_SECTION)}"
        in color_output
    )


def test_color_detection_can_be_forced_or_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(COLOR_ENV, "always")
    monkeypatch.delenv(NO_COLOR_ENV, raising=False)
    assert should_use_color()

    monkeypatch.setenv(NO_COLOR_ENV, "1")
    assert not should_use_color()


def test_cli_passes_omitted_provider_as_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio = tmp_path / "meeting.m4a"
    output = tmp_path / "meeting.md"
    audio.write_bytes(b"fake audio")
    captured: dict[str, object] = {}

    def fake_resolve_provider_config(**kwargs: object) -> ProviderConfig:
        captured["provider"] = kwargs["provider"]
        return ProviderConfig(
            provider="openai",
            language="ko-KR",
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            word_alignment=False,
            diarization=True,
            api_key="openai-key",
        )

    def fake_transcribe_with_provider(
        audio_path: object, config: ProviderConfig
    ) -> dict[str, object]:
        return {
            "text": "Transcript",
            "segments": [],
            PROVIDER_USAGES_KEY: [
                {"type": "tokens", "input_tokens": 1_000, "output_tokens": 1_000}
            ],
        }

    monkeypatch.setattr(
        "meetdown.cli.resolve_provider_config", fake_resolve_provider_config
    )
    monkeypatch.setattr(
        "meetdown.cli.transcribe_with_provider", fake_transcribe_with_provider
    )

    exit_code = run([str(audio), "-o", str(output), "--compress", "none"])

    assert exit_code == 0
    assert captured["provider"] is None
    terminal_output = capsys.readouterr().out
    assert "Estimated API cost: $0.0125 USD" in terminal_output
    markdown = output.read_text(encoding="utf-8")
    assert "- estimated_cost: `$0.0125 USD`" in markdown
    assert "- input_tokens: `1000`" in markdown


def test_cli_reports_missing_audio_before_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.m4a"

    exit_code = run([str(missing)])

    assert exit_code == 1
    assert "audio file not found" in capsys.readouterr().err


def test_cli_prefights_notion_before_audio_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.m4a"
    called = False
    captured: dict[str, object] = {}

    def fake_resolve_notion_upload_config(**kwargs: object) -> NotionUploadConfig:
        nonlocal called
        called = True
        captured.update(kwargs)
        raise NotionUploadError("Notion is not configured")

    monkeypatch.setattr(
        "meetdown.cli.resolve_notion_upload_config", fake_resolve_notion_upload_config
    )

    exit_code = run([str(missing), "--title", "Weekly Sync", "--notion"])

    assert exit_code == 1
    assert called
    assert captured["page_title"] == "Weekly Sync"
    stderr = capsys.readouterr().err
    assert "Notion is not configured" in stderr
    assert "audio file not found" not in stderr


def test_cli_uploads_to_notion_after_markdown_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "response.json"
    output = tmp_path / "meeting.md"
    source.write_text(
        json.dumps({"text": "Transcript", "segments": []}),
        encoding="utf-8",
    )
    config = NotionUploadConfig(parent_page_id="page-id", page_title="Notion title")
    captured: dict[str, object] = {}

    def fake_resolve_notion_upload_config(**kwargs: object) -> NotionUploadConfig:
        captured["preflight"] = kwargs
        return config

    def fake_upload_markdown_to_notion(
        markdown_path: str | Path, notion_config: NotionUploadConfig
    ) -> object:
        captured["upload_path"] = markdown_path
        captured["upload_config"] = notion_config
        captured["markdown_exists_during_upload"] = Path(markdown_path).is_file()
        return [{"url": "https://notion.so/meeting"}]

    monkeypatch.setattr(
        "meetdown.cli.resolve_notion_upload_config", fake_resolve_notion_upload_config
    )
    monkeypatch.setattr(
        "meetdown.cli.upload_markdown_to_notion", fake_upload_markdown_to_notion
    )

    exit_code = run(
        [
            "--from-json",
            str(source),
            "-o",
            str(output),
            "--title",
            "Test Meeting",
            "--notion",
            "--notion-parent-page-id",
            "page-id",
            "--notion-title",
            "Notion title",
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    assert captured["preflight"] == {
        "parent_page_id": "page-id",
        "page_title": "Notion title",
        "duplicate_strategy": "timestamp",
    }
    assert captured["markdown_exists_during_upload"] is True
    assert captured["upload_path"] == output
    assert captured["upload_config"] == config
    assert (
        "Uploaded Markdown to Notion: https://notion.so/meeting"
        in capsys.readouterr().out
    )
