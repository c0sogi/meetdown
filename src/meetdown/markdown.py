from datetime import datetime
from pathlib import Path

from meetdown.constants import DEFAULT_LANGUAGE, PROCESSING_REPLAY_COMMAND_KEY
from meetdown.json_types import JsonObject, as_json_object, as_number, as_object_list
from meetdown import text as ui_text


def speaker_token(label: object | None) -> str:
    raw = "" if label is None else str(label).strip()
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_").upper()
    return f"[[SPEAKER_{cleaned or 'UNKNOWN'}]]"


def format_time(milliseconds: int | float | None) -> str:
    if milliseconds is None:
        total_seconds = 0
    else:
        total_seconds = max(0, int(milliseconds) // 1000)

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def speaker_name(segment: JsonObject) -> str:
    speaker = as_json_object(segment.get("speaker")) or {}
    name = speaker.get("name")
    if name:
        return str(name)

    label = speaker.get("label")
    if label is not None and str(label) != "":
        return speaker_token(label)

    return speaker_token(None)


def _option_text(value: object) -> str:
    if isinstance(value, bool):
        return ui_text.OPTION_TRUE if value else ui_text.OPTION_FALSE
    if value is None:
        return ui_text.OPTION_NOT_SET
    return str(value)


def render_markdown(
    response: JsonObject,
    *,
    title: str,
    source_path: str | Path | None = None,
    language: str = DEFAULT_LANGUAGE,
    created_at: datetime | None = None,
) -> str:
    created = created_at or datetime.now().astimezone()
    source = str(source_path) if source_path else ""
    full_text = str(response.get("text") or "").strip()
    confidence = response.get("confidence")
    segments = as_object_list(response.get("segments"))
    processing_options = as_json_object(response.get("meetdown"))

    lines: list[str] = [
        f"# {title}",
        "",
        ui_text.MARKDOWN_METADATA_HEADING,
        "",
    ]

    if source:
        lines.append(f"- {ui_text.MARKDOWN_SOURCE_FILE_LABEL}: `{source}`")
    lines.extend(
        [
            f"- {ui_text.MARKDOWN_CREATED_AT_LABEL}: `{created.isoformat(timespec='seconds')}`",
            f"- {ui_text.MARKDOWN_LANGUAGE_LABEL}: `{language}`",
        ]
    )
    if confidence is not None:
        lines.append(f"- {ui_text.MARKDOWN_CONFIDENCE_LABEL}: `{confidence}`")

    if processing_options:
        lines.extend(["", ui_text.MARKDOWN_PROCESSING_HEADING, ""])
        for key, value in processing_options.items():
            if key == PROCESSING_REPLAY_COMMAND_KEY:
                continue
            lines.append(f"- {key}: `{_option_text(value)}`")

        replay_command = processing_options.get(PROCESSING_REPLAY_COMMAND_KEY)
        if replay_command:
            lines.extend(
                [
                    "",
                    ui_text.MARKDOWN_REPLAY_COMMAND_LABEL,
                    "",
                    "```powershell",
                    str(replay_command),
                    "```",
                    "",
                    ui_text.MARKDOWN_PLACEHOLDER_NOTE,
                ]
            )

    lines.extend(
        [
            "",
            ui_text.MARKDOWN_FULL_TEXT_HEADING,
            "",
            full_text or ui_text.MARKDOWN_NO_FULL_TEXT,
            "",
            ui_text.MARKDOWN_TRANSCRIPT_HEADING,
            "",
        ]
    )

    if not segments:
        lines.append(ui_text.MARKDOWN_NO_SEGMENTS)
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    for item in segments:
        segment = as_json_object(item)
        if segment is None:
            continue

        start = format_time(as_number(segment.get("start")))
        end = format_time(as_number(segment.get("end")))
        text = str(segment.get("text") or "").strip()
        speaker = speaker_name(segment)

        lines.extend(
            [
                f"### {start} - {end} / {speaker}",
                "",
                text or ui_text.MARKDOWN_NO_CONTENT,
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_markdown(path: str | Path, content: str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
