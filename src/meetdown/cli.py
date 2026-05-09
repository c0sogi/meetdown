import argparse
import json
import tempfile
from pathlib import Path
from typing import Sequence

from meetdown import __version__
from meetdown.chunks import (
    ChunkingError,
    chunk_extension,
    extract_media,
    merge_responses,
    offset_response_times,
    parse_duration_seconds,
    parse_time_seconds,
    split_media,
    validate_time_range,
)
from meetdown.json_types import JsonObject, require_json_object
from meetdown.markdown import render_markdown, write_markdown
from meetdown.providers import (
    CLOVA_MODEL_DESCRIPTION,
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    ProviderConfig,
    ProviderError,
    provider_display_model,
    resolve_provider_config,
    transcribe_with_provider,
)

_COMPRESS_FORMATS = {
    "smallest": "mp3",
    "lossless": "flac",
    "none": "wav",
}

_HELP_DESCRIPTION = """\
Turn a meeting recording into a Markdown transcript.

By default, meetdown uses CLOVA Speech. It can also use OpenAI or Gemini.
Common inputs include m4a, mp3, wav, flac, and mp4 files.
By default, meetdown extracts audio and uploads a small MP3 copy.
"""

_HELP_EPILOG = f"""\
Quick start:
  CLOVA:
    uvx meetdown meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>"

  OpenAI:
    uvx meetdown meeting.m4a -o meeting.md --provider openai --api-key "<OpenAI API key>"

  Gemini:
    uvx meetdown meeting.m4a -o meeting.md --provider gemini --api-key "<Gemini API key>" --chunk-duration 10m

Common workflows:
  Long recording:
    uvx meetdown meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --chunk-duration 10m

  Only transcribe a section:
    uvx meetdown meeting.mp4 -o section.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --start 00:10:00 --end 00:45:00

  Save normalized provider JSON as well as Markdown:
    uvx meetdown meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --save-json meeting.json

  Convert a saved normalized JSON response without calling an API:
    uvx meetdown --from-json meeting.json -o meeting.md

Compression:
  --compress smallest  -> MP3 64 kbps upload, default and usually cheapest
  --compress lossless  -> FLAC upload, larger but lossless
  --compress none      -> Upload the original file unless chunking/range extraction is needed

Provider model defaults:
  clova  -> {CLOVA_MODEL_DESCRIPTION}
  openai -> {OPENAI_DEFAULT_MODEL}
            {OPENAI_DEFAULT_NO_DIARIZATION_MODEL} when --no-diarization is used
  gemini -> {GEMINI_DEFAULT_MODEL}

Provider credentials:
  clova  needs --api-url and --api-key. /recognizer/upload is optional in --api-url.
  openai needs --api-key.
  gemini needs --api-key. Use --chunk-duration for large files.

Advanced:
  You may store keys in environment variables instead of typing --api-key every time.
  Supported names include CLOVA_SPEECH_SECRET_KEY, OPENAI_API_KEY, GEMINI_API_KEY,
  GOOGLE_API_KEY, and MEETDOWN_API_KEY.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meetdown",
        description=_HELP_DESCRIPTION,
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        metavar="audio_path",
        help="Local audio or video file to transcribe, such as m4a, mp3, wav, flac, or mp4.",
    )

    provider = parser.add_argument_group("provider and credentials")
    provider.add_argument(
        "--provider",
        default="clova",
        choices=["clova", "openai", "gemini"],
        help="Speech provider to use. Defaults to clova.",
    )
    provider.add_argument(
        "--api-key",
        help="Generic provider API key. Uses provider-specific environment variables when omitted.",
    )
    provider.add_argument(
        "--api-url",
        help="Provider API URL. For CLOVA, use the CLOVA Speech Invoke URL; /recognizer/upload is optional.",
    )
    provider.add_argument(
        "--model",
        help="Provider model override. Used by OpenAI and Gemini only.",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "-o", "--output", help="Markdown output path. Defaults to <audio>.md."
    )
    output.add_argument(
        "--title", help="Markdown document title. Defaults to the input file stem."
    )
    output.add_argument(
        "--from-json",
        help="Convert an existing normalized provider JSON response instead of calling the API.",
    )
    output.add_argument(
        "--save-json",
        help="Save the normalized transcription JSON to this path.",
    )

    media = parser.add_argument_group("media selection and upload size")
    media.add_argument(
        "--chunk-duration",
        help="Split media before upload. Accepts seconds or s/m/h suffixes, such as 600, 10m, or 1h.",
    )
    media.add_argument(
        "--chunk-format",
        choices=["flac", "mp3", "wav"],
        help="Exact temporary upload format. Overrides --compress.",
    )
    media.add_argument(
        "--compress",
        default="smallest",
        choices=["smallest", "lossless", "none"],
        help="Upload compression preset. Defaults to smallest, which uploads mp3.",
    )
    media.add_argument(
        "--start",
        help="Only transcribe media after this time. Accepts 600, 10m, 01:23, or 01:02:03.",
    )
    media.add_argument(
        "--end",
        help="Stop transcription at this source-media time. Accepts 600, 10m, 01:23, or 01:02:03.",
    )

    parser.add_argument(
        "--invoke-url",
        dest="legacy_invoke_url",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--secret-key",
        dest="legacy_secret_key",
        help=argparse.SUPPRESS,
    )

    recognition = parser.add_argument_group("recognition")
    recognition.add_argument(
        "--language", default="ko-KR", help="Recognition language. Defaults to ko-KR."
    )
    recognition.add_argument(
        "--word-alignment",
        action="store_true",
        help="Request word-level alignment when the provider supports it.",
    )
    recognition.add_argument(
        "--no-diarization",
        action="store_true",
        help="Disable speaker diarization when the provider supports it.",
    )

    advanced = parser.add_argument_group("advanced")
    advanced.add_argument(
        "--timeout",
        type=float,
        default=3600,
        help="HTTP timeout in seconds for provider upload. Defaults to 3600.",
    )
    return parser


def choose_upload_format(compress: str, chunk_format: str | None) -> str:
    if chunk_format:
        return chunk_format
    return _COMPRESS_FORMATS[compress]


def should_prepare_whole_file_upload(compress: str, chunk_format: str | None) -> bool:
    return bool(chunk_format) or compress != "none"


def infer_output_path(
    audio_path: str | None, from_json: str | None, output: str | None
) -> Path:
    if output:
        return Path(output)
    if audio_path:
        return Path(audio_path).with_suffix(".md")
    if from_json:
        return Path(from_json).with_suffix(".md")
    return Path("meeting.md")


def infer_title(
    audio_path: str | None, from_json: str | None, title: str | None
) -> str:
    if title:
        return title
    if audio_path:
        return Path(audio_path).stem
    if from_json:
        return Path(from_json).stem
    return "Meeting Transcript"


def _option_or_default(value: object | None, default: str) -> object:
    if value is None or value == "":
        return default
    return value


def mask_secret(value: str | None) -> str:
    if not value:
        return "not configured"

    if len(value) <= 4:
        return "*" * len(value)

    if len(value) <= 12:
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"

    return f"{value[:4]}{'*' * 8}{value[-4:]}"


def quote_command_arg(value: object) -> str:
    text = str(value)
    safe_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+-=.,:/\\@"
    )
    if text and all(ch in safe_chars for ch in text):
        return text
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _format_seconds(value: float) -> str:
    return format(value, "g")


def _api_key_placeholder(provider: str) -> str:
    if provider == "clova":
        return "<CLOVA Secret Key>"
    if provider == "openai":
        return "<OpenAI API key>"
    if provider == "gemini":
        return "<Gemini API key>"
    return "<API key>"


def build_replay_command(
    *,
    args: argparse.Namespace,
    provider_config: ProviderConfig,
    output_path: Path,
) -> str:
    parts: list[object] = ["uvx", "meetdown"]

    if args.audio_path:
        parts.append(args.audio_path)

    parts.extend(["-o", output_path])
    parts.extend(["--provider", provider_config.provider])

    if args.title:
        parts.extend(["--title", args.title])
    if provider_config.api_url:
        parts.extend(["--api-url", provider_config.api_url])
    if provider_config.api_key:
        parts.extend(["--api-key", _api_key_placeholder(provider_config.provider)])
    if provider_config.provider != "clova":
        parts.extend(["--model", provider_display_model(provider_config)])

    parts.extend(["--language", provider_config.language])
    parts.extend(["--compress", args.compress])
    if args.chunk_format:
        parts.extend(["--chunk-format", args.chunk_format])
    if args.chunk_duration:
        parts.extend(["--chunk-duration", args.chunk_duration])
    if args.start:
        parts.extend(["--start", args.start])
    if args.end:
        parts.extend(["--end", args.end])
    if provider_config.word_alignment:
        parts.append("--word-alignment")
    if not provider_config.diarization:
        parts.append("--no-diarization")
    if args.save_json:
        parts.extend(["--save-json", args.save_json])
    parts.extend(["--timeout", _format_seconds(provider_config.timeout_seconds)])

    return " ".join(quote_command_arg(part) for part in parts)


def build_processing_options(
    *,
    args: argparse.Namespace,
    provider_config: ProviderConfig,
    upload_format: str,
    preprocessing: str,
    chunk_count: int | None,
    output_path: Path,
) -> JsonObject:
    return {
        "provider": provider_config.provider,
        "model": provider_display_model(provider_config),
        "language": provider_config.language,
        "diarization": provider_config.diarization,
        "word_alignment": provider_config.word_alignment,
        "preprocessing": preprocessing,
        "compress": str(args.compress),
        "upload_format": upload_format,
        "chunk_duration": _option_or_default(args.chunk_duration, "not used"),
        "chunk_count": chunk_count if chunk_count is not None else "not chunked",
        "start": _option_or_default(args.start, "start of file"),
        "end": _option_or_default(args.end, "end of file"),
        "timeout_seconds": provider_config.timeout_seconds,
        "api_url": "configured" if provider_config.api_url else "provider default",
        "api_key": mask_secret(provider_config.api_key),
        "replay_command": build_replay_command(
            args=args,
            provider_config=provider_config,
            output_path=output_path,
        ),
    }


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_path = infer_output_path(args.audio_path, args.from_json, args.output)
    title = infer_title(args.audio_path, args.from_json, args.title)

    if args.from_json:
        response_path = Path(args.from_json)
        loaded_response: object = json.loads(response_path.read_text(encoding="utf-8"))
        response = require_json_object(
            loaded_response, "--from-json must contain a JSON object"
        )
        source_path = args.audio_path
    else:
        if not args.audio_path:
            parser.error("audio_path is required unless --from-json is used")

        try:
            audio_path = Path(args.audio_path)
            if not audio_path.is_file():
                raise FileNotFoundError(f"audio file not found: {audio_path}")

            provider_config = resolve_provider_config(
                provider=str(args.provider),
                language=str(args.language),
                timeout_seconds=float(args.timeout),
                word_alignment=bool(args.word_alignment),
                diarization=not bool(args.no_diarization),
                api_url=args.api_url,
                api_key=args.api_key,
                model=args.model,
                clova_invoke_url=args.legacy_invoke_url,
                clova_secret_key=args.legacy_secret_key,
            )
            start_seconds = parse_time_seconds(args.start) if args.start else 0
            end_seconds = parse_time_seconds(args.end) if args.end else None
            validate_time_range(start_seconds, end_seconds)
            upload_format = choose_upload_format(args.compress, args.chunk_format)
            preprocessing = "source file"
            saved_upload_format = "source file"
            chunk_count: int | None = None

            if args.chunk_duration:
                chunk_seconds = parse_duration_seconds(args.chunk_duration)
                with tempfile.TemporaryDirectory(prefix="meetdown-") as chunk_dir:
                    chunks = split_media(
                        args.audio_path,
                        chunk_dir,
                        chunk_seconds,
                        chunk_format=upload_format,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                    )
                    chunk_count = len(chunks)
                    preprocessing = "chunked"
                    saved_upload_format = upload_format
                    responses: list[JsonObject] = []
                    for index, chunk in enumerate(chunks, start=1):
                        size_kib = chunk.path.stat().st_size / 1024
                        print(
                            f"Transcribing chunk {index}/{len(chunks)}: {chunk.path.name} ({size_kib:.1f} KiB)"
                        )
                        chunk_response = transcribe_with_provider(
                            chunk.path, provider_config
                        )
                        responses.append(
                            offset_response_times(chunk_response, chunk.offset_ms)
                        )
                    response = merge_responses(responses)
            elif args.start or args.end:
                with tempfile.TemporaryDirectory(prefix="meetdown-") as chunk_dir:
                    clip_path = (
                        Path(chunk_dir) / f"selected{chunk_extension(upload_format)}"
                    )
                    clip = extract_media(
                        args.audio_path,
                        clip_path,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                        chunk_format=upload_format,
                    )
                    chunk_count = 1
                    preprocessing = "selected range"
                    saved_upload_format = upload_format
                    size_kib = clip.path.stat().st_size / 1024
                    print(
                        f"Transcribing selected range: {clip.path.name} ({size_kib:.1f} KiB)"
                    )
                    clip_response = transcribe_with_provider(clip.path, provider_config)
                    response = offset_response_times(clip_response, clip.offset_ms)
            elif should_prepare_whole_file_upload(args.compress, args.chunk_format):
                with tempfile.TemporaryDirectory(prefix="meetdown-") as chunk_dir:
                    upload_path = (
                        Path(chunk_dir) / f"upload{chunk_extension(upload_format)}"
                    )
                    upload = extract_media(
                        args.audio_path,
                        upload_path,
                        chunk_format=upload_format,
                    )
                    preprocessing = "compressed upload"
                    saved_upload_format = upload_format
                    size_kib = upload.path.stat().st_size / 1024
                    print(
                        f"Transcribing compressed upload: {upload.path.name} ({size_kib:.1f} KiB)"
                    )
                    response = transcribe_with_provider(upload.path, provider_config)
            else:
                response = transcribe_with_provider(args.audio_path, provider_config)
            response["meetdown"] = build_processing_options(
                args=args,
                provider_config=provider_config,
                upload_format=saved_upload_format,
                preprocessing=preprocessing,
                chunk_count=chunk_count,
                output_path=output_path,
            )
        except (ChunkingError, ProviderError, FileNotFoundError, ValueError) as exc:
            parser.exit(1, f"meetdown: {exc}\n")

        if args.save_json:
            save_path = Path(args.save_json)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        source_path = args.audio_path

    markdown = render_markdown(
        response,
        title=title,
        source_path=source_path,
        language=args.language,
    )
    written_path = write_markdown(output_path, markdown)
    print(f"Wrote {written_path}")
    return 0


def main() -> None:
    raise SystemExit(run())
