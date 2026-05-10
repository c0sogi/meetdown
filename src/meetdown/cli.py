import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence, TextIO

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
from meetdown.constants import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RESET,
    ANSI_YELLOW,
    APP_NAME,
    CHUNK_FORMAT_CHOICES,
    COLOR_ALWAYS_VALUES,
    COLOR_ENV,
    COLOR_NEVER_VALUES,
    COMPRESS_NONE,
    COMPRESSION_PRESETS,
    COMPRESSION_UPLOAD_FORMATS,
    CLOVA_API_KEY_ENV_NAMES,
    CLOVA_API_URL_ENV_NAMES,
    DEFAULT_COMPRESS,
    DEFAULT_DIARIZATION,
    DEFAULT_LANGUAGE,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TITLE,
    DEFAULT_WORD_ALIGNMENT,
    GEMINI_API_KEY_ENV_NAMES,
    GEMINI_API_URL_ENV_NAMES,
    GENERIC_API_KEY_PLACEHOLDER,
    OPENAI_API_KEY_ENV_NAMES,
    OPENAI_API_URL_ENV_NAMES,
    PROCESSING_REPLAY_COMMAND_KEY,
    PROVIDER_API_KEY_PLACEHOLDERS,
    PROVIDER_CLOVA,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    NO_COLOR_ENV,
    SUPPORTED_PROVIDERS,
    TEMP_DIR_PREFIX,
    TERM_DUMB_VALUE,
    TERM_ENV,
)
from meetdown import text as ui_text
from meetdown.json_types import JsonObject, require_json_object
from meetdown.markdown import render_markdown, write_markdown
from meetdown.providers import (
    CLOVA_MODEL_DESCRIPTION,
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    ProviderConfig,
    ProviderError,
    infer_provider_from_credentials,
    provider_display_model,
    resolve_provider_config,
    transcribe_with_provider,
)


_DEFAULT_SECTION_STYLES = {
    ui_text.DEFAULTS_RUNTIME_SECTION: ANSI_CYAN,
    ui_text.DEFAULTS_OUTPUT_SECTION: ANSI_GREEN,
    ui_text.DEFAULTS_MEDIA_SECTION: ANSI_YELLOW,
    ui_text.DEFAULTS_MODELS_SECTION: ANSI_MAGENTA,
    ui_text.DEFAULTS_CREDENTIALS_SECTION: ANSI_BLUE,
}


def should_use_color(stream: TextIO | None = None) -> bool:
    if os.environ.get(NO_COLOR_ENV) is not None:
        return False

    color_setting = os.environ.get(COLOR_ENV)
    if color_setting is not None:
        normalized = color_setting.strip().lower()
        if normalized in COLOR_ALWAYS_VALUES:
            return True
        if normalized in COLOR_NEVER_VALUES:
            return False

    target = stream or sys.stdout
    if os.environ.get(TERM_ENV) == TERM_DUMB_VALUE:
        return False
    return target.isatty()


def _styled(text: str, enabled: bool, *styles: str) -> str:
    if not enabled or not styles:
        return text
    return f"{''.join(styles)}{text}{ANSI_RESET}"


def build_parser(*, color: bool | None = None) -> argparse.ArgumentParser:
    use_color = should_use_color() if color is None else color
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=ui_text.HELP_DESCRIPTION,
        epilog=ui_text.help_epilog(),
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
        help=ui_text.ARG_AUDIO_PATH_HELP,
    )

    provider = parser.add_argument_group(ui_text.ARG_PROVIDER_GROUP)
    provider.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        help=ui_text.ARG_PROVIDER_HELP,
    )
    provider.add_argument(
        "--api-key",
        help=ui_text.ARG_API_KEY_HELP,
    )
    provider.add_argument(
        "--api-url",
        help=ui_text.ARG_API_URL_HELP,
    )
    provider.add_argument(
        "--model",
        help=ui_text.ARG_MODEL_HELP,
    )

    output = parser.add_argument_group(ui_text.ARG_OUTPUT_GROUP)
    output.add_argument("-o", "--output", help=ui_text.ARG_OUTPUT_HELP)
    output.add_argument("--title", help=ui_text.ARG_TITLE_HELP)
    output.add_argument(
        "--from-json",
        help=ui_text.ARG_FROM_JSON_HELP,
    )
    output.add_argument(
        "--save-json",
        help=ui_text.ARG_SAVE_JSON_HELP,
    )

    media = parser.add_argument_group(ui_text.ARG_MEDIA_GROUP)
    media.add_argument(
        "--chunk-duration",
        help=ui_text.ARG_CHUNK_DURATION_HELP,
    )
    media.add_argument(
        "--chunk-format",
        choices=CHUNK_FORMAT_CHOICES,
        help=ui_text.ARG_CHUNK_FORMAT_HELP,
    )
    media.add_argument(
        "--compress",
        default=DEFAULT_COMPRESS,
        choices=COMPRESSION_PRESETS,
        help=ui_text.ARG_COMPRESS_HELP,
    )
    media.add_argument(
        "--start",
        help=ui_text.ARG_START_HELP,
    )
    media.add_argument(
        "--end",
        help=ui_text.ARG_END_HELP,
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

    recognition = parser.add_argument_group(ui_text.ARG_RECOGNITION_GROUP)
    recognition.add_argument(
        "--language", default=DEFAULT_LANGUAGE, help=ui_text.ARG_LANGUAGE_HELP
    )
    recognition.add_argument(
        "--word-alignment",
        action="store_true",
        default=DEFAULT_WORD_ALIGNMENT,
        help=ui_text.ARG_WORD_ALIGNMENT_HELP,
    )
    recognition.add_argument(
        "--no-diarization",
        action="store_true",
        default=not DEFAULT_DIARIZATION,
        help=ui_text.ARG_NO_DIARIZATION_HELP,
    )

    advanced = parser.add_argument_group(ui_text.ARG_ADVANCED_GROUP)
    advanced.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=ui_text.ARG_TIMEOUT_HELP,
    )
    parser.epilog = build_help_epilog(parser.parse_args([]), color=use_color)
    return parser


def choose_upload_format(compress: str, chunk_format: str | None) -> str:
    if chunk_format:
        return chunk_format
    return COMPRESSION_UPLOAD_FORMATS[compress]


def should_prepare_whole_file_upload(compress: str, chunk_format: str | None) -> bool:
    return bool(chunk_format) or compress != COMPRESS_NONE


def infer_output_path(
    audio_path: str | None, from_json: str | None, output: str | None
) -> Path:
    if output:
        return Path(output)
    if audio_path:
        return Path(audio_path).with_suffix(".md")
    if from_json:
        return Path(from_json).with_suffix(".md")
    return Path(DEFAULT_OUTPUT_PATH)


def infer_title(
    audio_path: str | None, from_json: str | None, title: str | None
) -> str:
    if title:
        return title
    if audio_path:
        return Path(audio_path).stem
    if from_json:
        return Path(from_json).stem
    return DEFAULT_TITLE


def _option_or_default(value: object | None, default: str) -> object:
    if value is None or value == "":
        return default
    return value


def mask_secret(value: str | None) -> str:
    if not value:
        return ui_text.OPTION_NOT_CONFIGURED

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


def _env_status(*names: str) -> str:
    configured = [name for name in names if os.getenv(name)]
    if configured:
        return f"{ui_text.PROCESSING_CONFIGURED} ({ui_text.comma_list(configured)})"
    return ui_text.OPTION_NOT_CONFIGURED


def _current_provider_inference(args: argparse.Namespace) -> str:
    if args.provider:
        return str(args.provider)
    try:
        return infer_provider_from_credentials(
            api_url=args.api_url,
            api_key=args.api_key,
            clova_invoke_url=args.legacy_invoke_url,
            clova_secret_key=args.legacy_secret_key,
        )
    except ValueError as exc:
        return ui_text.defaults_provider_inference_error(exc)


def _default_value_style(value: object) -> str:
    text = str(value)
    if text == ui_text.OPTION_TRUE or text.startswith(ui_text.PROCESSING_CONFIGURED):
        return ANSI_GREEN
    if (
        text == ui_text.DEFAULTS_NOT_INFERRED
        or text == ui_text.OPTION_NOT_CONFIGURED
        or text == ui_text.OPTION_NOT_SET
    ):
        return ANSI_YELLOW
    if text == ui_text.OPTION_FALSE:
        return ANSI_DIM
    return ""


def _default_row(
    label: str,
    value: object,
    label_width: int,
    section_style: str,
    *,
    color: bool,
) -> str:
    label_text = f"{label:<{label_width}}"
    value_style = _default_value_style(value)
    return (
        f"  {_styled(label_text, color, section_style)} "
        f"{_styled(str(value), color, value_style)}"
    )


def _default_section(
    title: str, rows: list[tuple[str, object]], *, color: bool
) -> list[str]:
    label_width = max(len(label) for label, _ in rows) + 2
    section_style = _DEFAULT_SECTION_STYLES.get(title, ANSI_BOLD)
    return [
        _styled(ui_text.defaults_section(title), color, ANSI_BOLD, section_style),
        *[
            _default_row(label, value, label_width, section_style, color=color)
            for label, value in rows
        ],
    ]


def build_defaults_report(args: argparse.Namespace, *, color: bool = False) -> str:
    upload_format = choose_upload_format(args.compress, args.chunk_format)
    diarization = not bool(args.no_diarization)
    lines = [
        _styled(ui_text.DEFAULTS_TITLE, color, ANSI_BOLD),
        "",
        *_default_section(
            ui_text.DEFAULTS_RUNTIME_SECTION,
            [
                (
                    ui_text.DEFAULTS_PROVIDER_LABEL,
                    args.provider or ui_text.DEFAULTS_PROVIDER_AUTO,
                ),
                (
                    ui_text.DEFAULTS_CURRENT_PROVIDER_LABEL,
                    _current_provider_inference(args),
                ),
                (ui_text.DEFAULTS_LANGUAGE_LABEL, args.language),
                (
                    ui_text.DEFAULTS_WORD_ALIGNMENT_LABEL,
                    ui_text.OPTION_TRUE
                    if args.word_alignment
                    else ui_text.OPTION_FALSE,
                ),
                (
                    ui_text.DEFAULTS_DIARIZATION_LABEL,
                    ui_text.OPTION_TRUE if diarization else ui_text.OPTION_FALSE,
                ),
                (
                    ui_text.DEFAULTS_TIMEOUT_SECONDS_LABEL,
                    _format_seconds(float(args.timeout)),
                ),
            ],
            color=color,
        ),
        "",
        *_default_section(
            ui_text.DEFAULTS_OUTPUT_SECTION,
            [
                (
                    ui_text.DEFAULTS_OUTPUT_LABEL,
                    args.output or ui_text.DEFAULTS_OUTPUT_PATH,
                ),
                (
                    ui_text.DEFAULTS_TITLE_LABEL,
                    args.title or ui_text.DEFAULTS_TITLE_VALUE,
                ),
            ],
            color=color,
        ),
        "",
        *_default_section(
            ui_text.DEFAULTS_MEDIA_SECTION,
            [
                (ui_text.DEFAULTS_COMPRESS_LABEL, args.compress),
                (
                    ui_text.DEFAULTS_CHUNK_FORMAT_LABEL,
                    args.chunk_format or ui_text.DEFAULTS_CHUNK_FORMAT_VALUE,
                ),
                (ui_text.DEFAULTS_UPLOAD_FORMAT_LABEL, upload_format),
                (
                    ui_text.DEFAULTS_CHUNK_DURATION_LABEL,
                    args.chunk_duration or ui_text.PROCESSING_NOT_USED,
                ),
                (
                    ui_text.DEFAULTS_START_LABEL,
                    args.start or ui_text.PROCESSING_START_OF_FILE,
                ),
                (
                    ui_text.DEFAULTS_END_LABEL,
                    args.end or ui_text.PROCESSING_END_OF_FILE,
                ),
            ],
            color=color,
        ),
        "",
        *_default_section(
            ui_text.DEFAULTS_MODELS_SECTION,
            [
                (PROVIDER_CLOVA, CLOVA_MODEL_DESCRIPTION),
                (PROVIDER_OPENAI, OPENAI_DEFAULT_MODEL),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_OPENAI,
                        ui_text.DEFAULTS_WITHOUT_DIARIZATION_LABEL,
                    ),
                    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
                ),
                (PROVIDER_GEMINI, GEMINI_DEFAULT_MODEL),
            ],
            color=color,
        ),
        "",
        *_default_section(
            ui_text.DEFAULTS_CREDENTIALS_SECTION,
            [
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_CLOVA, ui_text.DEFAULTS_API_URL_LABEL
                    ),
                    _env_status(*CLOVA_API_URL_ENV_NAMES),
                ),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_CLOVA, ui_text.DEFAULTS_API_KEY_LABEL
                    ),
                    _env_status(*CLOVA_API_KEY_ENV_NAMES),
                ),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_OPENAI, ui_text.DEFAULTS_API_URL_LABEL
                    ),
                    _env_status(*OPENAI_API_URL_ENV_NAMES),
                ),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_OPENAI, ui_text.DEFAULTS_API_KEY_LABEL
                    ),
                    _env_status(*OPENAI_API_KEY_ENV_NAMES),
                ),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_GEMINI, ui_text.DEFAULTS_API_URL_LABEL
                    ),
                    _env_status(*GEMINI_API_URL_ENV_NAMES),
                ),
                (
                    ui_text.defaults_provider_setting(
                        PROVIDER_GEMINI, ui_text.DEFAULTS_API_KEY_LABEL
                    ),
                    _env_status(*GEMINI_API_KEY_ENV_NAMES),
                ),
            ],
            color=color,
        ),
    ]
    return "\n".join(lines) + "\n"


def build_help_epilog(default_args: argparse.Namespace, *, color: bool = False) -> str:
    return (
        f"{ui_text.help_epilog()}\n{build_defaults_report(default_args, color=color)}"
    )


def _api_key_placeholder(provider: str) -> str:
    for supported_provider in SUPPORTED_PROVIDERS:
        if provider == supported_provider:
            return PROVIDER_API_KEY_PLACEHOLDERS[supported_provider]
    return GENERIC_API_KEY_PLACEHOLDER


def build_replay_command(
    *,
    args: argparse.Namespace,
    provider_config: ProviderConfig,
    output_path: Path,
) -> str:
    parts: list[object] = ["uvx", APP_NAME]

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
    if provider_config.provider != PROVIDER_CLOVA:
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
        "chunk_duration": _option_or_default(
            args.chunk_duration, ui_text.PROCESSING_NOT_USED
        ),
        "chunk_count": (
            chunk_count if chunk_count is not None else ui_text.PROCESSING_NOT_CHUNKED
        ),
        "start": _option_or_default(args.start, ui_text.PROCESSING_START_OF_FILE),
        "end": _option_or_default(args.end, ui_text.PROCESSING_END_OF_FILE),
        "timeout_seconds": provider_config.timeout_seconds,
        "api_url": (
            ui_text.PROCESSING_CONFIGURED
            if provider_config.api_url
            else ui_text.PROCESSING_PROVIDER_DEFAULT
        ),
        "api_key": mask_secret(provider_config.api_key),
        PROCESSING_REPLAY_COMMAND_KEY: build_replay_command(
            args=args,
            provider_config=provider_config,
            output_path=output_path,
        ),
    }


def run(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(effective_argv)

    if not effective_argv:
        parser.print_help()
        return 0

    output_path = infer_output_path(args.audio_path, args.from_json, args.output)
    title = infer_title(args.audio_path, args.from_json, args.title)

    if args.from_json:
        response_path = Path(args.from_json)
        loaded_response: object = json.loads(response_path.read_text(encoding="utf-8"))
        response = require_json_object(
            loaded_response, ui_text.FROM_JSON_MUST_CONTAIN_OBJECT
        )
        source_path = args.audio_path
    else:
        if not args.audio_path:
            parser.error(ui_text.AUDIO_PATH_REQUIRED)

        try:
            audio_path = Path(args.audio_path)
            if not audio_path.is_file():
                raise FileNotFoundError(ui_text.audio_file_not_found(audio_path))

            provider_config = resolve_provider_config(
                provider=args.provider,
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
            preprocessing = ui_text.PREPROCESSING_SOURCE_FILE
            saved_upload_format = ui_text.PREPROCESSING_SOURCE_FILE
            chunk_count: int | None = None

            if args.chunk_duration:
                chunk_seconds = parse_duration_seconds(args.chunk_duration)
                with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
                    chunks = split_media(
                        args.audio_path,
                        chunk_dir,
                        chunk_seconds,
                        chunk_format=upload_format,
                        start_seconds=start_seconds,
                        end_seconds=end_seconds,
                    )
                    chunk_count = len(chunks)
                    preprocessing = ui_text.PREPROCESSING_CHUNKED
                    saved_upload_format = upload_format
                    responses: list[JsonObject] = []
                    for index, chunk in enumerate(chunks, start=1):
                        size_kib = chunk.path.stat().st_size / 1024
                        print(
                            ui_text.transcribing_chunk(
                                index, len(chunks), chunk.path.name, size_kib
                            )
                        )
                        chunk_response = transcribe_with_provider(
                            chunk.path, provider_config
                        )
                        responses.append(
                            offset_response_times(chunk_response, chunk.offset_ms)
                        )
                    response = merge_responses(responses)
            elif args.start or args.end:
                with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
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
                    preprocessing = ui_text.PREPROCESSING_SELECTED_RANGE
                    saved_upload_format = upload_format
                    size_kib = clip.path.stat().st_size / 1024
                    print(ui_text.transcribing_selected_range(clip.path.name, size_kib))
                    clip_response = transcribe_with_provider(clip.path, provider_config)
                    response = offset_response_times(clip_response, clip.offset_ms)
            elif should_prepare_whole_file_upload(args.compress, args.chunk_format):
                with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
                    upload_path = (
                        Path(chunk_dir) / f"upload{chunk_extension(upload_format)}"
                    )
                    upload = extract_media(
                        args.audio_path,
                        upload_path,
                        chunk_format=upload_format,
                    )
                    preprocessing = ui_text.PREPROCESSING_COMPRESSED_UPLOAD
                    saved_upload_format = upload_format
                    size_kib = upload.path.stat().st_size / 1024
                    print(
                        ui_text.transcribing_compressed_upload(
                            upload.path.name, size_kib
                        )
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
    print(ui_text.wrote_file(written_path))
    return 0


def main() -> None:
    raise SystemExit(run())
