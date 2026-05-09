from datetime import datetime
from pathlib import Path

from meetdown.json_types import JsonObject, as_json_object, as_number, as_object_list


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
        return "true" if value else "false"
    if value is None:
        return "not set"
    return str(value)


def render_markdown(
    response: JsonObject,
    *,
    title: str,
    source_path: str | Path | None = None,
    language: str = "ko-KR",
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
        "## 메타데이터",
        "",
    ]

    if source:
        lines.append(f"- 원본 파일: `{source}`")
    lines.extend(
        [
            f"- 생성일시: `{created.isoformat(timespec='seconds')}`",
            f"- 인식 언어: `{language}`",
        ]
    )
    if confidence is not None:
        lines.append(f"- 전체 정확도: `{confidence}`")

    if processing_options:
        lines.extend(["", "## 처리 옵션", ""])
        for key, value in processing_options.items():
            if key == "replay_command":
                continue
            lines.append(f"- {key}: `{_option_text(value)}`")

        replay_command = processing_options.get("replay_command")
        if replay_command:
            lines.extend(
                [
                    "",
                    "재실행 커맨드:",
                    "",
                    "```powershell",
                    str(replay_command),
                    "```",
                    "",
                    "`<...>` placeholder values must be replaced before running this command.",
                ]
            )

    lines.extend(
        [
            "",
            "## 전체 텍스트",
            "",
            full_text or "_전체 텍스트 없음_",
            "",
            "## 발화 기록",
            "",
        ]
    )

    if not segments:
        lines.append("_발화 구간 없음_")
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
                text or "_내용 없음_",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_markdown(path: str | Path, content: str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
