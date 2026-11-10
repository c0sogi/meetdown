import json
import re
from pathlib import Path

import pytest

from meetdown.chunks import ChunkingError, MediaChunk
from meetdown.cli import build_defaults_report, default_cli_options, run
from meetdown.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MEETDOWN_PROVIDER_ENV,
    PROVIDER_ENV_NAMES,
)
from meetdown.json_types import JsonObject
from meetdown.providers import ProviderConfig, ProviderLimitError


def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def openai_config(**kwargs: object) -> ProviderConfig:
    del kwargs
    return ProviderConfig(
        provider="openai",
        language="ko-KR",
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        word_alignment=False,
        diarization=True,
        api_key="openai-key",
        provider_source="environment",
    )


def korean_response() -> JsonObject:
    return {
        "text": "회의를 시작하겠습니다.",
        "segments": [
            {
                "start": 0,
                "end": 2000,
                "text": "회의를 시작하겠습니다.",
                "speaker": {"label": "A"},
            }
        ],
    }


def fake_chunks(tmp_path: Path, count: int) -> list[MediaChunk]:
    chunks: list[MediaChunk] = []
    for index in range(count):
        path = tmp_path / f"chunk_{index:05d}.mp3"
        path.write_bytes(b"chunk")
        chunks.append(MediaChunk(path=path, offset_ms=index * 600_000))
    return chunks


def test_cli_splits_media_that_exceeds_the_provider_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio = tmp_path / "회의 녹음.m4a"
    output = tmp_path / "meeting.md"
    audio.write_bytes(b"fake audio")
    captured: dict[str, object] = {}

    def fake_split_media(
        input_path: object, output_dir: object, chunk_seconds: float, **kwargs: object
    ) -> list[MediaChunk]:
        captured["chunk_seconds"] = chunk_seconds
        captured["chunk_format"] = kwargs["chunk_format"]
        return fake_chunks(tmp_path, 4)

    def known_duration(path: object) -> float:
        return 1926.0

    def fake_transcribe(path: object, config: ProviderConfig) -> JsonObject:
        return korean_response()

    monkeypatch.setattr("meetdown.cli.resolve_provider_config", openai_config)
    monkeypatch.setattr("meetdown.cli.probe_media_duration_seconds", known_duration)
    monkeypatch.setattr("meetdown.cli.split_media", fake_split_media)
    monkeypatch.setattr("meetdown.cli.transcribe_with_provider", fake_transcribe)

    exit_code = run([str(audio), "-o", str(output), "--language", "ko-KR", "--json"])

    assert exit_code == 0
    streams = capsys.readouterr()
    assert streams.out.isascii(), "--json output must survive any console encoding"
    summary = json.loads(streams.out)
    assert summary["source"] == str(audio)
    assert captured == {"chunk_seconds": 600.0, "chunk_format": "mp3"}
    assert "Splitting media into 10m chunks" in streams.err
    assert summary["status"] == "ok"
    assert summary["provider"] == "openai"
    assert summary["provider_source"] == "environment"
    assert summary["media_duration_seconds"] == 1926.0
    assert summary["chunking"]["chunk_duration"] == "10m"
    assert summary["chunking"]["source"] == "auto"
    assert summary["chunking"]["chunk_count"] == 4
    assert summary["segment_count"] == 4
    assert summary["quality"]["status"] == "ok"
    assert any("speaker labels restart" in warning for warning in summary["warnings"])

    markdown = output.read_text(encoding="utf-8")
    assert "- chunk_duration: `10m`" in markdown
    assert "- chunking: `auto (openai accepts about 1400 s per request" in markdown
    assert "- api_key: `configured`" in markdown
    assert "--chunk-duration 10m" in markdown
    assert "- Quality check: `ok`" in markdown


def test_cli_retries_in_chunks_after_a_provider_limit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio = tmp_path / "meeting.m4a"
    output = tmp_path / "meeting.md"
    audio.write_bytes(b"fake audio")
    calls: list[str] = []

    def unknown_duration(path: object) -> float:
        raise ChunkingError("duration unknown")

    def fake_transcribe(path: object, config: ProviderConfig) -> JsonObject:
        calls.append(Path(str(path)).name)
        if len(calls) == 1:
            raise ProviderLimitError("OpenAI transcription failed with HTTP 413")
        return korean_response()

    monkeypatch.setattr("meetdown.cli.resolve_provider_config", openai_config)
    monkeypatch.setattr("meetdown.cli.probe_media_duration_seconds", unknown_duration)

    def two_chunks(*args: object, **kwargs: object) -> list[MediaChunk]:
        return fake_chunks(tmp_path, 2)

    monkeypatch.setattr("meetdown.cli.split_media", two_chunks)
    monkeypatch.setattr("meetdown.cli.transcribe_with_provider", fake_transcribe)

    exit_code = run([str(audio), "-o", str(output), "--compress", "none", "--json"])

    assert exit_code == 0
    streams = capsys.readouterr()
    summary = json.loads(streams.out)
    assert calls == ["meeting.m4a", "chunk_00000.mp3", "chunk_00001.mp3"]
    assert "Retrying in 10m chunks" in streams.err
    assert summary["chunking"]["source"] == "retry"
    assert summary["chunking"]["chunk_duration"] == "10m"


def test_cli_no_auto_chunk_reports_the_limit_error_as_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audio = tmp_path / "meeting.m4a"
    audio.write_bytes(b"fake audio")

    def too_long(path: object, config: ProviderConfig) -> JsonObject:
        raise ProviderLimitError("OpenAI transcription failed with HTTP 400")

    monkeypatch.setattr("meetdown.cli.resolve_provider_config", openai_config)
    monkeypatch.setattr("meetdown.cli.transcribe_with_provider", too_long)

    exit_code = run([str(audio), "--compress", "none", "--no-auto-chunk", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["code"] == "provider_limit"


def test_cli_json_error_lists_candidates_when_provider_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    audio = tmp_path / "meeting.m4a"
    audio.write_bytes(b"fake audio")

    exit_code = run([str(audio), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "provider_ambiguous"
    assert payload["candidates"] == ["openai", "gemini"]


def test_human_output_warns_about_poor_transcripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "response.json"
    output = tmp_path / "meeting.md"
    source.write_text(
        json.dumps(
            {
                "text": "",
                "segments": [
                    {"start": 0, "end": 1000, "text": "just " * 200},
                    {"start": 1000, "end": 6000, "text": "회의를 시작하겠습니다."},
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = run(
        ["--from-json", str(source), "-o", str(output), "--language", "ko-KR"]
    )

    assert exit_code == 0
    assert "Warning: possible transcription hallucination" in capsys.readouterr().err
    assert re.search(
        r"- Quality check: `poor: \d+% suspect", output.read_text(encoding="utf-8")
    )


def test_defaults_report_shows_the_environment_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv(MEETDOWN_PROVIDER_ENV, "openai")

    report = build_defaults_report(default_cli_options())

    assert re.search(r"Provider\s+openai \(MEETDOWN_PROVIDER\)", report)
    assert re.search(r"Detected now\s+openai", report)
