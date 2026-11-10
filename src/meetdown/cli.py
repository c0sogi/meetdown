import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Sequence, TextIO

import click
import typer
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from meetdown import __version__
from meetdown import text as ui_text
from meetdown.chunks import (
    ChunkingError,
    chunk_extension,
    extract_media,
    merge_responses,
    offset_response_times,
    parse_duration_seconds,
    parse_time_seconds,
    probe_media_duration_seconds,
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
    CHUNKING_SOURCE_AUTO,
    CHUNKING_SOURCE_OPTION,
    CHUNKING_SOURCE_RETRY,
    CLOVA_API_KEY_ENV_NAMES,
    CLOVA_API_URL_ENV_NAMES,
    COLOR_ALWAYS_VALUES,
    COLOR_ENV,
    COLOR_NEVER_VALUES,
    COMPRESS_NONE,
    COMPRESSION_UPLOAD_FORMATS,
    DEFAULT_COMPRESS,
    DEFAULT_DIARIZATION,
    DEFAULT_LANGUAGE,
    DEFAULT_NOTION_DUPLICATE_STRATEGY,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TITLE,
    DEFAULT_WORD_ALIGNMENT,
    ERROR_INPUT_NOT_FOUND,
    ERROR_INVALID_OPTION,
    ERROR_MEDIA,
    ERROR_NOTION,
    ERROR_PROVIDER_FAILED,
    ERROR_PROVIDER_LIMIT,
    GEMINI_API_KEY_ENV,
    GEMINI_API_KEY_ENV_NAMES,
    GEMINI_API_URL_ENV_NAMES,
    GENERIC_API_KEY_PLACEHOLDER,
    GOOGLE_API_KEY_ENV,
    LIMIT_RETRY_CHUNK_SECONDS,
    MEETDOWN_PROVIDER_ENV,
    NO_COLOR_ENV,
    NOTION_DUPLICATE_STRATEGIES,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    OPENAI_API_KEY_ENV,
    OPENAI_API_KEY_ENV_NAMES,
    OPENAI_API_URL_ENV_NAMES,
    PROCESSING_REPLAY_COMMAND_KEY,
    PROVIDER_API_KEY_PLACEHOLDERS,
    PROVIDER_CLOVA,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    SUPPORTED_PROVIDERS,
    TEMP_DIR_PREFIX,
    TERM_DUMB_VALUE,
    TERM_ENV,
    NotionDuplicateStrategy,
)
from meetdown.json_types import (
    JsonObject,
    as_json_object,
    as_object_list,
    require_json_object,
)
from meetdown.limits import (
    format_duration_option,
    plan_auto_chunk,
    request_limit_seconds,
)
from meetdown.markdown import render_markdown, write_markdown
from meetdown.notion import (
    NotionUploadConfig,
    NotionUploadError,
    notion_upload_status,
    notion_upload_url,
    notionit_available,
    resolve_notion_upload_config,
    upload_markdown_to_notion,
)
from meetdown.providers import (
    CLOVA_MODEL_DESCRIPTION,
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    ProviderConfig,
    ProviderError,
    ProviderLimitError,
    ProviderSelectionError,
    default_provider_from_env,
    infer_provider_from_credentials,
    provider_display_model,
    resolve_provider_config,
    transcribe_with_provider,
)
from meetdown.pricing import (
    CostEstimate,
    estimate_transcription_cost,
    needs_request_duration,
)
from meetdown.quality import QualityReport, assess_transcript

_DEFAULT_SECTION_STYLES = {
    ui_text.DEFAULTS_RUNTIME_SECTION: ANSI_CYAN,
    ui_text.DEFAULTS_OUTPUT_SECTION: ANSI_GREEN,
    ui_text.DEFAULTS_MEDIA_SECTION: ANSI_YELLOW,
    ui_text.DEFAULTS_MODELS_SECTION: ANSI_MAGENTA,
    ui_text.DEFAULTS_CREDENTIALS_SECTION: ANSI_BLUE,
    ui_text.DEFAULTS_NOTION_SECTION: ANSI_MAGENTA,
}
_RICH_SECTION_STYLES = {
    ui_text.DEFAULTS_RUNTIME_SECTION: "cyan",
    ui_text.DEFAULTS_OUTPUT_SECTION: "green",
    ui_text.DEFAULTS_MEDIA_SECTION: "yellow",
    ui_text.DEFAULTS_MODELS_SECTION: "magenta",
    ui_text.DEFAULTS_CREDENTIALS_SECTION: "blue",
    ui_text.DEFAULTS_NOTION_SECTION: "magenta",
}

PROVIDER_PANEL = "Provider"
OUTPUT_PANEL = "Output"
MEDIA_PANEL = "Media"
RECOGNITION_PANEL = "Recognition"
NOTION_PANEL = "Notion"
ADVANCED_PANEL = "Advanced"
ROOT_COMMANDS = frozenset({"defaults", "quickstart", "transcribe"})
ROOT_OPTIONS = frozenset({"--help", "-h", "--version"})


class ProviderChoice(str, Enum):
    clova = PROVIDER_CLOVA
    openai = PROVIDER_OPENAI
    gemini = PROVIDER_GEMINI


class CompressionChoice(str, Enum):
    smallest = "smallest"
    lossless = "lossless"
    none = "none"


class ChunkFormatChoice(str, Enum):
    flac = "flac"
    mp3 = "mp3"
    wav = "wav"


class DuplicateStrategyChoice(str, Enum):
    ask = "ask"
    timestamp = "timestamp"
    counter = "counter"
    create_anyway = "create_anyway"
    skip = "skip"


@dataclass(frozen=True)
class CliOptions:
    audio_path: str | None = None
    provider: str | None = None
    api_key: str | None = None
    api_url: str | None = None
    model: str | None = None
    output: str | None = None
    title: str | None = None
    from_json: str | None = None
    save_json: str | None = None
    chunk_duration: str | None = None
    chunk_format: str | None = None
    compress: str = DEFAULT_COMPRESS
    start: str | None = None
    end: str | None = None
    language: str = DEFAULT_LANGUAGE
    word_alignment: bool = DEFAULT_WORD_ALIGNMENT
    no_diarization: bool = not DEFAULT_DIARIZATION
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    notion: bool = False
    notion_parent_page_id: str | None = None
    notion_title: str | None = None
    notion_duplicate_strategy: NotionDuplicateStrategy = (
        DEFAULT_NOTION_DUPLICATE_STRATEGY
    )
    legacy_invoke_url: str | None = None
    legacy_secret_key: str | None = None
    auto_chunk: bool = True
    json_output: bool = False


@dataclass(frozen=True)
class ChunkingChoice:
    """Which chunk length a run used and why."""

    seconds: float | None = None
    label: str | None = None
    source: str | None = None
    reason: str | None = None

    def processing_value(self) -> str:
        if self.source is None:
            return ui_text.PROCESSING_NOT_USED
        return ui_text.processing_chunking(self.source, self.reason)


@dataclass(frozen=True)
class MediaRun:
    response: JsonObject
    preprocessing: str
    upload_format: str
    chunk_count: int | None


@dataclass(frozen=True)
class DefaultsSection:
    title: str
    rows: tuple[tuple[str, object], ...]
    style: str


def default_cli_options() -> CliOptions:
    return CliOptions()


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


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{APP_NAME} {__version__}")
        raise typer.Exit()


def _enum_value(value: Enum | str | None) -> str | None:
    if isinstance(value, Enum):
        return str(value.value)
    return value


def _duplicate_strategy_value(
    value: DuplicateStrategyChoice,
) -> NotionDuplicateStrategy:
    raw = value.value
    if raw in NOTION_DUPLICATE_STRATEGIES:
        return raw
    raise ValueError(ui_text.notion_duplicate_strategy_unsupported(raw))


def root_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help=ui_text.ARG_VERSION_HELP,
            is_eager=True,
        ),
    ] = False,
) -> None:
    del version


def build_app(*, color: bool | None = None) -> typer.Typer:
    use_color = should_use_color() if color is None else color
    app = typer.Typer(
        name=APP_NAME,
        help=ui_text.HELP_DESCRIPTION,
        add_completion=False,
        context_settings={
            "color": use_color,
            "help_option_names": ["--help", "-h"],
        },
        no_args_is_help=True,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )
    app.callback()(root_callback)
    app.command(
        "transcribe",
        help=ui_text.TRANSCRIBE_COMMAND_HELP,
        epilog=ui_text.HELP_EPILOG_SHORT,
    )(cli_command)
    app.command("quickstart", help=ui_text.QUICKSTART_COMMAND_HELP)(quickstart_command)
    app.command("defaults", help=ui_text.DEFAULTS_COMMAND_HELP)(defaults_command)
    return app


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


def _provider_setting(args: CliOptions) -> str:
    if args.provider:
        return str(args.provider)
    env_default = os.getenv(MEETDOWN_PROVIDER_ENV, "").strip()
    if env_default:
        return ui_text.defaults_provider_from_environment(env_default)
    return ui_text.DEFAULTS_PROVIDER_AUTO


def _current_provider_inference(args: CliOptions) -> str:
    if args.provider:
        return str(args.provider)
    try:
        env_default = default_provider_from_env()
        if env_default is not None:
            return env_default
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
    if (
        text == ui_text.OPTION_TRUE
        or text == ui_text.OPTION_AVAILABLE
        or text.startswith(ui_text.PROCESSING_CONFIGURED)
    ):
        return ANSI_GREEN
    if (
        text == ui_text.DEFAULTS_NOT_INFERRED
        or text == ui_text.OPTION_NOT_CONFIGURED
        or text == ui_text.OPTION_NOT_SET
        or text == ui_text.OPTION_NOT_INSTALLED
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


def _notion_library_status() -> str:
    return (
        ui_text.OPTION_AVAILABLE
        if notionit_available()
        else ui_text.OPTION_NOT_INSTALLED
    )


def _default_sections(args: CliOptions) -> list[DefaultsSection]:
    upload_format = choose_upload_format(args.compress, args.chunk_format)
    diarization = not bool(args.no_diarization)
    return [
        DefaultsSection(
            ui_text.DEFAULTS_RUNTIME_SECTION,
            (
                (ui_text.DEFAULTS_PROVIDER_LABEL, _provider_setting(args)),
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
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_RUNTIME_SECTION],
        ),
        DefaultsSection(
            ui_text.DEFAULTS_OUTPUT_SECTION,
            (
                (
                    ui_text.DEFAULTS_OUTPUT_LABEL,
                    args.output or ui_text.DEFAULTS_OUTPUT_PATH,
                ),
                (
                    ui_text.DEFAULTS_TITLE_LABEL,
                    args.title or ui_text.DEFAULTS_TITLE_VALUE,
                ),
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_OUTPUT_SECTION],
        ),
        DefaultsSection(
            ui_text.DEFAULTS_MEDIA_SECTION,
            (
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
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_MEDIA_SECTION],
        ),
        DefaultsSection(
            ui_text.DEFAULTS_MODELS_SECTION,
            (
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
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_MODELS_SECTION],
        ),
        DefaultsSection(
            ui_text.DEFAULTS_CREDENTIALS_SECTION,
            (
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
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_CREDENTIALS_SECTION],
        ),
        DefaultsSection(
            ui_text.DEFAULTS_NOTION_SECTION,
            (
                (
                    ui_text.DEFAULTS_NOTION_UPLOAD_LABEL,
                    ui_text.OPTION_TRUE if args.notion else ui_text.OPTION_FALSE,
                ),
                (
                    ui_text.DEFAULTS_NOTION_LIBRARY_LABEL,
                    _notion_library_status(),
                ),
                (
                    ui_text.DEFAULTS_NOTION_TOKEN_LABEL,
                    _env_status(NOTION_TOKEN_ENV),
                ),
                (
                    ui_text.DEFAULTS_NOTION_PARENT_PAGE_LABEL,
                    (
                        ui_text.PROCESSING_CONFIGURED
                        if args.notion_parent_page_id
                        else _env_status(NOTION_PARENT_PAGE_ID_ENV)
                    ),
                ),
                (
                    ui_text.DEFAULTS_NOTION_TITLE_LABEL,
                    args.notion_title or ui_text.DEFAULTS_NOTION_TITLE_VALUE,
                ),
                (
                    ui_text.DEFAULTS_NOTION_DUPLICATE_STRATEGY_LABEL,
                    args.notion_duplicate_strategy,
                ),
            ),
            _DEFAULT_SECTION_STYLES[ui_text.DEFAULTS_NOTION_SECTION],
        ),
    ]


def build_defaults_report(args: CliOptions, *, color: bool = False) -> str:
    lines = [
        _styled(ui_text.DEFAULTS_TITLE, color, ANSI_BOLD),
    ]
    for section in _default_sections(args):
        lines.extend(
            [
                "",
                *_default_section(
                    section.title,
                    list(section.rows),
                    color=color,
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def _rich_console(*, color: bool | None = None) -> Console:
    use_color = should_use_color() if color is None else color
    return Console(
        force_terminal=use_color,
        no_color=not use_color,
        highlight=False,
        soft_wrap=False,
    )


def _rich_value_style(value: object) -> str:
    text = str(value)
    if (
        text == ui_text.OPTION_TRUE
        or text == ui_text.OPTION_AVAILABLE
        or text.startswith(ui_text.PROCESSING_CONFIGURED)
    ):
        return "green"
    if (
        text == ui_text.DEFAULTS_NOT_INFERRED
        or text == ui_text.OPTION_NOT_CONFIGURED
        or text == ui_text.OPTION_NOT_SET
        or text == ui_text.OPTION_NOT_INSTALLED
    ):
        return "yellow"
    if text == ui_text.OPTION_FALSE:
        return "dim"
    return ""


def _default_section_panel(section: DefaultsSection) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    rich_style = _RICH_SECTION_STYLES[section.title]
    for label, value in section.rows:
        table.add_row(
            Text(label, style=f"bold {rich_style}"),
            Text(str(value), style=_rich_value_style(value)),
        )
    return Panel(
        table,
        title=Text(section.title, style=f"bold {rich_style}"),
        border_style=rich_style,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def build_defaults_renderable(args: CliOptions) -> Group:
    return Group(
        Panel(
            ui_text.DEFAULTS_SUMMARY,
            title=Text(ui_text.DEFAULTS_TITLE, style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        ),
        *[_default_section_panel(section) for section in _default_sections(args)],
    )


def build_quickstart_renderable() -> Group:
    def command(text: str) -> Text:
        return Text(text, style="green")

    provider_table = Table(
        title="Provider recipes",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
    )
    provider_table.add_column("Provider", style="bold", no_wrap=True)
    provider_table.add_column("Use when", style="white")
    provider_table.add_column("Command")
    provider_table.add_row(
        "CLOVA",
        "you have a CLOVA Speech Invoke URL and Secret Key",
        command(
            f"uvx {APP_NAME} meeting.m4a -o meeting.md "
            '--api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>"'
        ),
    )
    provider_table.add_row(
        "OpenAI",
        f"{OPENAI_API_KEY_ENV} is set",
        command(f"uvx {APP_NAME} meeting.m4a -o meeting.md"),
    )
    provider_table.add_row(
        "Gemini",
        f"{GEMINI_API_KEY_ENV} or {GOOGLE_API_KEY_ENV} is set",
        command(f"uvx {APP_NAME} meeting.m4a -o meeting.md --chunk-duration 10m"),
    )
    provider_table.add_row(
        "Notion",
        "you want the saved Markdown uploaded after transcription",
        command(
            f'uvx "{APP_NAME}[notion]" transcribe meeting.m4a -o meeting.md --notion'
        ),
    )

    workflow_table = Table(
        title="Common workflows",
        box=box.ROUNDED,
        border_style="magenta",
        header_style="bold magenta",
    )
    workflow_table.add_column("Goal", style="bold", no_wrap=True)
    workflow_table.add_column("Command")
    workflow_table.add_row(
        "Long recording",
        command(
            f"uvx {APP_NAME} meeting.m4a -o meeting.md "
            '--api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" '
            "--chunk-duration 10m"
        ),
    )
    workflow_table.add_row(
        "Selected range",
        command(
            f"uvx {APP_NAME} meeting.mp4 -o section.md "
            '--api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" '
            "--start 00:10:00 --end 00:45:00"
        ),
    )
    workflow_table.add_row(
        "Save JSON",
        command(
            f"uvx {APP_NAME} meeting.m4a -o meeting.md "
            '--api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" '
            "--save-json meeting.json"
        ),
    )
    workflow_table.add_row(
        "From JSON",
        command(f"uvx {APP_NAME} --from-json meeting.json -o meeting.md"),
    )

    notes = Table.grid(padding=(0, 1))
    notes.add_column(style="bold yellow", no_wrap=True)
    notes.add_column()
    notes.add_row(
        "Provider",
        "Omit --provider when exactly one provider-specific API key is configured.",
    )
    notes.add_row(
        "CLOVA URL",
        "/recognizer/upload is optional in --api-url.",
    )
    notes.add_row(
        "More",
        f"Run {APP_NAME} defaults for current settings or {APP_NAME} transcribe --help for every option.",
    )

    return Group(
        Panel(
            ui_text.QUICKSTART_SUMMARY,
            title=Text(ui_text.QUICKSTART_TITLE, style="bold cyan"),
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        ),
        provider_table,
        workflow_table,
        Panel(notes, title="Notes", border_style="yellow", box=box.ROUNDED),
    )


def print_defaults(*, color: bool | None = None) -> None:
    _rich_console(color=color).print(build_defaults_renderable(default_cli_options()))


def print_quickstart(*, color: bool | None = None) -> None:
    _rich_console(color=color).print(build_quickstart_renderable())


def _api_key_placeholder(provider: str) -> str:
    for supported_provider in SUPPORTED_PROVIDERS:
        if provider == supported_provider:
            return PROVIDER_API_KEY_PLACEHOLDERS[supported_provider]
    return GENERIC_API_KEY_PLACEHOLDER


def build_replay_command(
    *,
    args: CliOptions,
    provider_config: ProviderConfig,
    output_path: Path,
    chunk_duration: str | None = None,
) -> str:
    effective_chunk_duration = chunk_duration or args.chunk_duration
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
    if effective_chunk_duration:
        parts.extend(["--chunk-duration", effective_chunk_duration])
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
    args: CliOptions,
    provider_config: ProviderConfig,
    upload_format: str,
    preprocessing: str,
    chunk_count: int | None,
    output_path: Path,
    cost_estimate: CostEstimate,
    chunking: ChunkingChoice | None = None,
) -> JsonObject:
    if chunking is None:
        chunking = (
            ChunkingChoice(None, args.chunk_duration, CHUNKING_SOURCE_OPTION, None)
            if args.chunk_duration
            else ChunkingChoice()
        )
    options: JsonObject = {
        "provider": provider_config.provider,
        "provider_source": provider_config.provider_source,
        "model": provider_display_model(provider_config),
        "language": provider_config.language,
        "diarization": provider_config.diarization,
        "word_alignment": provider_config.word_alignment,
        "preprocessing": preprocessing,
        "compress": str(args.compress),
        "upload_format": upload_format,
        "chunk_duration": _option_or_default(
            chunking.label, ui_text.PROCESSING_NOT_USED
        ),
        "chunking": chunking.processing_value(),
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
        # Never write key fragments into a transcript that people share.
        "api_key": (
            ui_text.PROCESSING_CONFIGURED
            if provider_config.api_key
            else ui_text.OPTION_NOT_CONFIGURED
        ),
        PROCESSING_REPLAY_COMMAND_KEY: build_replay_command(
            args=args,
            provider_config=provider_config,
            output_path=output_path,
            chunk_duration=chunking.label,
        ),
    }
    options.update(cost_estimate.processing_options())
    return options


def _echo(message: str, *, err: bool = False) -> None:
    typer.echo(message, err=err)


def _selected_media_duration(
    audio_path: Path, start_seconds: float, end_seconds: float | None
) -> tuple[float | None, float | None]:
    """Return the full media duration and the selected range duration."""
    try:
        media_duration: float | None = probe_media_duration_seconds(audio_path)
    except ChunkingError:
        media_duration = None
    if media_duration is None:
        selected = end_seconds - start_seconds if end_seconds is not None else None
        return None, selected
    stop = (
        min(end_seconds, media_duration) if end_seconds is not None else media_duration
    )
    return media_duration, max(0.0, stop - start_seconds)


def _transcribe_media(
    args: CliOptions,
    audio_path: str,
    *,
    upload_format: str,
    start_seconds: float,
    end_seconds: float | None,
    chunk_seconds: float | None,
    transcribe_request: Callable[[str | Path], JsonObject],
) -> MediaRun:
    progress_err = args.json_output
    if chunk_seconds is not None:
        with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
            chunks = split_media(
                audio_path,
                chunk_dir,
                chunk_seconds,
                chunk_format=upload_format,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
            responses: list[JsonObject] = []
            for index, chunk in enumerate(chunks, start=1):
                size_kib = chunk.path.stat().st_size / 1024
                _echo(
                    ui_text.transcribing_chunk(
                        index, len(chunks), chunk.path.name, size_kib
                    ),
                    err=progress_err,
                )
                chunk_response = transcribe_request(chunk.path)
                responses.append(offset_response_times(chunk_response, chunk.offset_ms))
            return MediaRun(
                merge_responses(responses),
                ui_text.PREPROCESSING_CHUNKED,
                upload_format,
                len(chunks),
            )

    if args.start or args.end:
        with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
            clip_path = Path(chunk_dir) / f"selected{chunk_extension(upload_format)}"
            clip = extract_media(
                audio_path,
                clip_path,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                chunk_format=upload_format,
            )
            size_kib = clip.path.stat().st_size / 1024
            _echo(
                ui_text.transcribing_selected_range(clip.path.name, size_kib),
                err=progress_err,
            )
            clip_response = transcribe_request(clip.path)
            return MediaRun(
                offset_response_times(clip_response, clip.offset_ms),
                ui_text.PREPROCESSING_SELECTED_RANGE,
                upload_format,
                1,
            )

    if should_prepare_whole_file_upload(args.compress, args.chunk_format):
        with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as chunk_dir:
            upload_path = Path(chunk_dir) / f"upload{chunk_extension(upload_format)}"
            upload = extract_media(audio_path, upload_path, chunk_format=upload_format)
            size_kib = upload.path.stat().st_size / 1024
            _echo(
                ui_text.transcribing_compressed_upload(upload.path.name, size_kib),
                err=progress_err,
            )
            return MediaRun(
                transcribe_request(upload.path),
                ui_text.PREPROCESSING_COMPRESSED_UPLOAD,
                upload_format,
                None,
            )

    return MediaRun(
        transcribe_request(audio_path),
        ui_text.PREPROCESSING_SOURCE_FILE,
        ui_text.PREPROCESSING_SOURCE_FILE,
        None,
    )


def _plan_chunking(
    args: CliOptions,
    provider_config: ProviderConfig,
    audio_path: Path,
    *,
    upload_format: str,
    start_seconds: float,
    end_seconds: float | None,
) -> tuple[ChunkingChoice, float | None]:
    """Choose explicit or automatic chunking, and report the probed duration."""
    if args.chunk_duration:
        return (
            ChunkingChoice(
                parse_duration_seconds(args.chunk_duration),
                args.chunk_duration,
                CHUNKING_SOURCE_OPTION,
                None,
            ),
            None,
        )
    if (
        not args.auto_chunk
        or request_limit_seconds(provider_config, upload_format) is None
    ):
        return ChunkingChoice(), None

    media_duration, selected_duration = _selected_media_duration(
        audio_path, start_seconds, end_seconds
    )
    uploads_source_as_is = not (
        args.start or args.end
    ) and not should_prepare_whole_file_upload(args.compress, args.chunk_format)
    plan = plan_auto_chunk(
        provider_config,
        duration_seconds=selected_duration,
        upload_format=upload_format,
        source_bytes=audio_path.stat().st_size if uploads_source_as_is else None,
    )
    if plan is None:
        return ChunkingChoice(), media_duration
    label = format_duration_option(plan.chunk_seconds)
    _echo(ui_text.auto_chunking(label, plan.reason), err=args.json_output)
    return (
        ChunkingChoice(plan.chunk_seconds, label, CHUNKING_SOURCE_AUTO, plan.reason),
        media_duration,
    )


def _has_speaker_labels(segments: list[object]) -> bool:
    for item in segments:
        segment = as_json_object(item)
        speaker = as_json_object((segment or {}).get("speaker"))
        if speaker and (speaker.get("label") is not None or speaker.get("name")):
            return True
    return False


def _run_warnings(
    response: JsonObject, quality: QualityReport, chunk_count: int | None
) -> list[str]:
    warnings = list(quality.warnings)
    segments = as_object_list(response.get("segments")) or []
    if not segments and str(response.get("text") or "").strip():
        warnings.append(ui_text.NO_TIMESTAMPED_SEGMENTS)
    if (chunk_count or 0) > 1 and _has_speaker_labels(segments):
        warnings.append(ui_text.SPEAKER_LABELS_RESET_PER_CHUNK)
    return warnings


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderSelectionError):
        return exc.code
    if isinstance(exc, ProviderLimitError):
        return ERROR_PROVIDER_LIMIT
    if isinstance(exc, ProviderError):
        return ERROR_PROVIDER_FAILED
    if isinstance(exc, ChunkingError):
        return ERROR_MEDIA
    if isinstance(exc, FileNotFoundError):
        return ERROR_INPUT_NOT_FOUND
    if isinstance(exc, NotionUploadError):
        return ERROR_NOTION
    return ERROR_INVALID_OPTION


def json_output_text(payload: JsonObject) -> str:
    """Serialize --json output as ASCII so any console encoding can carry it."""
    return json.dumps(payload, ensure_ascii=True, indent=2)


def error_payload(exc: Exception) -> JsonObject:
    """Machine-readable form of a transcription failure for --json."""
    payload: JsonObject = {
        "status": "error",
        "code": _error_code(exc),
        "message": str(exc),
    }
    if isinstance(exc, ProviderSelectionError) and exc.candidates:
        payload["candidates"] = list(exc.candidates)
    return payload


def execute_options(args: CliOptions) -> int:
    output_path = infer_output_path(args.audio_path, args.from_json, args.output)
    title = infer_title(args.audio_path, args.from_json, args.title)
    progress_err = args.json_output

    notion_config: NotionUploadConfig | None = None
    if args.notion:
        notion_config = resolve_notion_upload_config(
            parent_page_id=args.notion_parent_page_id,
            page_title=args.notion_title or title,
            duplicate_strategy=args.notion_duplicate_strategy,
        )

    provider_config: ProviderConfig | None = None
    cost_estimate: CostEstimate | None = None
    media_duration: float | None = None
    chunking = ChunkingChoice()
    preprocessing: str | None = None
    chunk_count: int | None = None

    if args.from_json:
        response_path = Path(args.from_json)
        loaded_response: object = json.loads(response_path.read_text(encoding="utf-8"))
        response = require_json_object(
            loaded_response, ui_text.FROM_JSON_MUST_CONTAIN_OBJECT
        )
        source_path = args.audio_path
        processing = as_json_object(response.get("meetdown")) or {}
        quality = assess_transcript(
            response, str(processing.get("language") or args.language)
        )
        response["quality"] = quality.to_json()
    else:
        if not args.audio_path:
            raise ValueError(ui_text.AUDIO_PATH_REQUIRED)

        audio_path = Path(args.audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(ui_text.audio_file_not_found(audio_path))

        resolved_config = resolve_provider_config(
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
        provider_config = resolved_config
        request_durations_seconds: list[float] = []

        def transcribe_request(path: str | Path) -> JsonObject:
            if needs_request_duration(resolved_config):
                try:
                    duration = probe_media_duration_seconds(path)
                except ChunkingError:
                    pass
                else:
                    request_durations_seconds.append(duration)
            return transcribe_with_provider(path, resolved_config)

        start_seconds = parse_time_seconds(args.start) if args.start else 0
        end_seconds = parse_time_seconds(args.end) if args.end else None
        validate_time_range(start_seconds, end_seconds)
        upload_format = choose_upload_format(args.compress, args.chunk_format)
        chunking, media_duration = _plan_chunking(
            args,
            resolved_config,
            audio_path,
            upload_format=upload_format,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )

        def run_media(choice: ChunkingChoice) -> MediaRun:
            return _transcribe_media(
                args,
                str(audio_path),
                upload_format=upload_format,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                chunk_seconds=choice.seconds,
                transcribe_request=transcribe_request,
            )

        try:
            media_run = run_media(chunking)
        except ProviderLimitError:
            if chunking.seconds is not None or not args.auto_chunk:
                raise
            # The size or duration estimate missed; split once and try again.
            label = format_duration_option(LIMIT_RETRY_CHUNK_SECONDS)
            chunking = ChunkingChoice(
                LIMIT_RETRY_CHUNK_SECONDS,
                label,
                CHUNKING_SOURCE_RETRY,
                ui_text.LIMIT_RETRY_REASON,
            )
            request_durations_seconds.clear()
            _echo(ui_text.retrying_with_chunks(label), err=progress_err)
            media_run = run_media(chunking)

        response = media_run.response
        preprocessing = media_run.preprocessing
        chunk_count = media_run.chunk_count
        cost_estimate = estimate_transcription_cost(
            resolved_config,
            response,
            request_durations_seconds=request_durations_seconds,
        )
        response["meetdown"] = build_processing_options(
            args=args,
            provider_config=resolved_config,
            upload_format=media_run.upload_format,
            preprocessing=media_run.preprocessing,
            chunk_count=media_run.chunk_count,
            output_path=output_path,
            cost_estimate=cost_estimate,
            chunking=chunking,
        )
        quality = assess_transcript(response, resolved_config.language)
        response["quality"] = quality.to_json()
        _echo(
            ui_text.estimated_api_cost(
                cost_estimate.display_amount(), cost_estimate.basis
            ),
            err=progress_err,
        )

        if args.save_json:
            save_path = Path(args.save_json)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        source_path = args.audio_path

    warnings = _run_warnings(response, quality, chunk_count)
    if not args.json_output:
        for message in warnings:
            _echo(ui_text.warning(message), err=True)

    markdown = render_markdown(
        response,
        title=title,
        source_path=source_path,
        language=args.language,
    )
    written_path = write_markdown(output_path, markdown)
    _echo(ui_text.wrote_file(written_path), err=progress_err)

    notion: JsonObject | None = None
    if notion_config is not None:
        upload_result = upload_markdown_to_notion(written_path, notion_config)
        notion = {
            "url": notion_upload_url(upload_result),
            "status": notion_upload_status(upload_result),
        }
        _echo(
            ui_text.notion_upload_completed(
                url=notion_upload_url(upload_result),
                status=notion_upload_status(upload_result),
            ),
            err=progress_err,
        )

    if args.json_output:
        summary = build_run_summary(
            written_path=written_path,
            title=title,
            source_path=source_path,
            response=response,
            provider_config=provider_config,
            media_duration=media_duration,
            preprocessing=preprocessing,
            chunking=chunking,
            chunk_count=chunk_count,
            cost_estimate=cost_estimate,
            quality=quality,
            warnings=warnings,
            notion=notion,
        )
        typer.echo(json_output_text(summary))

    return 0


def build_run_summary(
    *,
    written_path: Path,
    title: str,
    source_path: str | None,
    response: JsonObject,
    provider_config: ProviderConfig | None,
    media_duration: float | None,
    preprocessing: str | None,
    chunking: ChunkingChoice,
    chunk_count: int | None,
    cost_estimate: CostEstimate | None,
    quality: QualityReport,
    warnings: list[str],
    notion: JsonObject | None,
) -> JsonObject:
    """Machine-readable result of one run for --json."""
    processing = as_json_object(response.get("meetdown")) or {}
    segments = as_object_list(response.get("segments")) or []
    return {
        "status": "ok",
        "meetdown_version": __version__,
        "output": str(written_path),
        "title": title,
        "source": source_path,
        "provider": processing.get("provider"),
        "provider_source": (
            provider_config.provider_source if provider_config is not None else None
        ),
        "model": processing.get("model"),
        "language": processing.get("language"),
        "diarization": processing.get("diarization"),
        "media_duration_seconds": (
            round(media_duration, 3) if media_duration is not None else None
        ),
        "preprocessing": preprocessing,
        "chunking": {
            "chunk_duration": chunking.label,
            "source": chunking.source,
            "reason": chunking.reason,
            "chunk_count": chunk_count,
        },
        "segment_count": len(segments),
        "full_text_characters": len(str(response.get("text") or "").strip()),
        "estimated_cost": (
            {"amount": cost_estimate.display_amount(), "basis": cost_estimate.basis}
            if cost_estimate is not None
            else None
        ),
        "quality": quality.to_json(),
        "warnings": list(warnings),
        "notion": notion,
    }


def _cli_options_from_values(
    *,
    audio_path: str | None,
    provider: ProviderChoice | None,
    api_key: str | None,
    api_url: str | None,
    model: str | None,
    output: str | None,
    title: str | None,
    from_json: str | None,
    save_json: str | None,
    chunk_duration: str | None,
    chunk_format: ChunkFormatChoice | None,
    compress: CompressionChoice,
    start: str | None,
    end: str | None,
    language: str,
    word_alignment: bool,
    no_diarization: bool,
    timeout: float,
    notion: bool,
    notion_parent_page_id: str | None,
    notion_title: str | None,
    notion_duplicate_strategy: DuplicateStrategyChoice,
    legacy_invoke_url: str | None,
    legacy_secret_key: str | None,
    no_auto_chunk: bool = False,
    json_output: bool = False,
) -> CliOptions:
    return CliOptions(
        audio_path=audio_path,
        provider=_enum_value(provider),
        api_key=api_key,
        api_url=api_url,
        model=model,
        output=output,
        title=title,
        from_json=from_json,
        save_json=save_json,
        chunk_duration=chunk_duration,
        chunk_format=_enum_value(chunk_format),
        compress=compress.value,
        start=start,
        end=end,
        language=language,
        word_alignment=word_alignment,
        no_diarization=no_diarization,
        timeout=timeout,
        notion=notion,
        notion_parent_page_id=notion_parent_page_id,
        notion_title=notion_title,
        notion_duplicate_strategy=_duplicate_strategy_value(notion_duplicate_strategy),
        legacy_invoke_url=legacy_invoke_url,
        legacy_secret_key=legacy_secret_key,
        auto_chunk=not no_auto_chunk,
        json_output=json_output,
    )


def cli_command(
    audio_path: Annotated[
        str | None,
        typer.Argument(help=ui_text.ARG_AUDIO_PATH_HELP, metavar="audio_path"),
    ] = None,
    provider: Annotated[
        ProviderChoice | None,
        typer.Option(
            "--provider",
            help=ui_text.ARG_PROVIDER_HELP,
            rich_help_panel=PROVIDER_PANEL,
            case_sensitive=False,
        ),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key", help=ui_text.ARG_API_KEY_HELP, rich_help_panel=PROVIDER_PANEL
        ),
    ] = None,
    api_url: Annotated[
        str | None,
        typer.Option(
            "--api-url", help=ui_text.ARG_API_URL_HELP, rich_help_panel=PROVIDER_PANEL
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model", help=ui_text.ARG_MODEL_HELP, rich_help_panel=PROVIDER_PANEL
        ),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            "-o", "--output", help=ui_text.ARG_OUTPUT_HELP, rich_help_panel=OUTPUT_PANEL
        ),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option(
            "--title", help=ui_text.ARG_TITLE_HELP, rich_help_panel=OUTPUT_PANEL
        ),
    ] = None,
    from_json: Annotated[
        str | None,
        typer.Option(
            "--from-json", help=ui_text.ARG_FROM_JSON_HELP, rich_help_panel=OUTPUT_PANEL
        ),
    ] = None,
    save_json: Annotated[
        str | None,
        typer.Option(
            "--save-json", help=ui_text.ARG_SAVE_JSON_HELP, rich_help_panel=OUTPUT_PANEL
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json", help=ui_text.ARG_JSON_HELP, rich_help_panel=OUTPUT_PANEL
        ),
    ] = False,
    chunk_duration: Annotated[
        str | None,
        typer.Option(
            "--chunk-duration",
            help=ui_text.ARG_CHUNK_DURATION_HELP,
            rich_help_panel=MEDIA_PANEL,
        ),
    ] = None,
    no_auto_chunk: Annotated[
        bool,
        typer.Option(
            "--no-auto-chunk",
            help=ui_text.ARG_NO_AUTO_CHUNK_HELP,
            rich_help_panel=MEDIA_PANEL,
        ),
    ] = False,
    chunk_format: Annotated[
        ChunkFormatChoice | None,
        typer.Option(
            "--chunk-format",
            help=ui_text.ARG_CHUNK_FORMAT_HELP,
            rich_help_panel=MEDIA_PANEL,
            case_sensitive=False,
        ),
    ] = None,
    compress: Annotated[
        CompressionChoice,
        typer.Option(
            "--compress",
            help=ui_text.ARG_COMPRESS_HELP,
            rich_help_panel=MEDIA_PANEL,
            case_sensitive=False,
        ),
    ] = CompressionChoice(DEFAULT_COMPRESS),
    start: Annotated[
        str | None,
        typer.Option(
            "--start", help=ui_text.ARG_START_HELP, rich_help_panel=MEDIA_PANEL
        ),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help=ui_text.ARG_END_HELP, rich_help_panel=MEDIA_PANEL),
    ] = None,
    language: Annotated[
        str,
        typer.Option(
            "--language",
            help=ui_text.ARG_LANGUAGE_HELP,
            rich_help_panel=RECOGNITION_PANEL,
        ),
    ] = DEFAULT_LANGUAGE,
    word_alignment: Annotated[
        bool,
        typer.Option(
            "--word-alignment",
            help=ui_text.ARG_WORD_ALIGNMENT_HELP,
            rich_help_panel=RECOGNITION_PANEL,
        ),
    ] = DEFAULT_WORD_ALIGNMENT,
    no_diarization: Annotated[
        bool,
        typer.Option(
            "--no-diarization",
            help=ui_text.ARG_NO_DIARIZATION_HELP,
            rich_help_panel=RECOGNITION_PANEL,
        ),
    ] = not DEFAULT_DIARIZATION,
    notion: Annotated[
        bool,
        typer.Option(
            "--notion", help=ui_text.ARG_NOTION_HELP, rich_help_panel=NOTION_PANEL
        ),
    ] = False,
    notion_parent_page_id: Annotated[
        str | None,
        typer.Option(
            "--notion-parent-page-id",
            help=ui_text.ARG_NOTION_PARENT_PAGE_ID_HELP,
            rich_help_panel=NOTION_PANEL,
        ),
    ] = None,
    notion_title: Annotated[
        str | None,
        typer.Option(
            "--notion-title",
            help=ui_text.ARG_NOTION_TITLE_HELP,
            rich_help_panel=NOTION_PANEL,
        ),
    ] = None,
    notion_duplicate_strategy: Annotated[
        DuplicateStrategyChoice,
        typer.Option(
            "--notion-duplicate-strategy",
            help=ui_text.ARG_NOTION_DUPLICATE_STRATEGY_HELP,
            rich_help_panel=NOTION_PANEL,
            case_sensitive=False,
        ),
    ] = DuplicateStrategyChoice(DEFAULT_NOTION_DUPLICATE_STRATEGY),
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout", help=ui_text.ARG_TIMEOUT_HELP, rich_help_panel=ADVANCED_PANEL
        ),
    ] = DEFAULT_TIMEOUT_SECONDS,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help=ui_text.ARG_VERSION_HELP,
            is_eager=True,
            rich_help_panel=ADVANCED_PANEL,
        ),
    ] = False,
    legacy_invoke_url: Annotated[
        str | None, typer.Option("--invoke-url", hidden=True)
    ] = None,
    legacy_secret_key: Annotated[
        str | None, typer.Option("--secret-key", hidden=True)
    ] = None,
) -> None:
    del version
    args = _cli_options_from_values(
        audio_path=audio_path,
        provider=provider,
        api_key=api_key,
        api_url=api_url,
        model=model,
        output=output,
        title=title,
        from_json=from_json,
        save_json=save_json,
        chunk_duration=chunk_duration,
        chunk_format=chunk_format,
        compress=compress,
        start=start,
        end=end,
        language=language,
        word_alignment=word_alignment,
        no_diarization=no_diarization,
        timeout=timeout,
        notion=notion,
        notion_parent_page_id=notion_parent_page_id,
        notion_title=notion_title,
        notion_duplicate_strategy=notion_duplicate_strategy,
        legacy_invoke_url=legacy_invoke_url,
        legacy_secret_key=legacy_secret_key,
        no_auto_chunk=no_auto_chunk,
        json_output=json_output,
    )
    try:
        execute_options(args)
    except (
        ChunkingError,
        FileNotFoundError,
        NotionUploadError,
        ProviderError,
        ValueError,
    ) as exc:
        if args.json_output:
            typer.echo(json_output_text(error_payload(exc)))
        else:
            _echo(f"{APP_NAME}: {exc}", err=True)
        raise typer.Exit(1) from exc


def quickstart_command() -> None:
    print_quickstart()


def defaults_command() -> None:
    print_defaults()


def _route_args(argv: list[str]) -> list[str]:
    if not argv:
        return ["--help"]
    first = argv[0]
    if first in ROOT_COMMANDS or first in ROOT_OPTIONS:
        return argv
    return ["transcribe", *argv]


def run(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    app = build_app()
    routed_argv = _route_args(effective_argv)
    try:
        result = app(args=routed_argv, prog_name=APP_NAME, standalone_mode=False)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.ClickException as exc:
        exc.show(file=sys.stderr)
        return int(exc.exit_code)
    if isinstance(result, int):
        return result
    return 0


def main() -> None:
    raise SystemExit(run())
