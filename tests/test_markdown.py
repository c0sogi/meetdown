from datetime import datetime, timezone

from meetdown.json_types import JsonObject
from meetdown.markdown import format_time, render_markdown, speaker_name


def test_format_time_uses_hh_mm_ss() -> None:
    assert format_time(0) == "00:00:00"
    assert format_time(3_723_999) == "01:02:03"


def test_speaker_name_prefers_name_then_label() -> None:
    assert speaker_name({"speaker": {"name": "Alice", "label": "1"}}) == "Alice"
    assert speaker_name({"speaker": {"label": "2"}}) == "[[SPEAKER_2]]"
    assert speaker_name({"speaker": {"label": "A-1"}}) == "[[SPEAKER_A_1]]"
    assert speaker_name({}) == "[[SPEAKER_UNKNOWN]]"


def test_render_markdown_uses_full_text_and_segments() -> None:
    response: JsonObject = {
        "text": "전체 텍스트입니다.",
        "confidence": 0.95,
        "meetdown": {
            "provider": "clova",
            "model": "CLOVA Speech domain model (not configurable by --model)",
            "compress": "smallest",
            "api_key": "se*****ey",
            "replay_command": 'uvx meetdown meeting.m4a -o meeting.md --api-key "<CLOVA Secret Key>"',
        },
        "segments": [
            {
                "start": 0,
                "end": 4100,
                "text": "첫 번째 발화입니다.",
                "speaker": {"name": "Alice", "label": "1"},
            },
            {
                "start": 5100,
                "end": 9000,
                "text": "두 번째 발화입니다.",
                "speaker": {"label": "2"},
            },
        ],
    }

    rendered = render_markdown(
        response,
        title="회의",
        source_path="meeting.m4a",
        created_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert "# 회의" in rendered
    assert "## 처리 옵션" in rendered
    assert "- provider: `clova`" in rendered
    assert "- api_key: `se*****ey`" in rendered
    assert "재실행 커맨드:" in rendered
    assert (
        'uvx meetdown meeting.m4a -o meeting.md --api-key "<CLOVA Secret Key>"'
        in rendered
    )
    assert "placeholder values must be replaced" in rendered
    assert "## 전체 텍스트" in rendered
    assert "전체 텍스트입니다." in rendered
    assert "### 00:00:00 - 00:00:04 / Alice" in rendered
    assert "### 00:00:05 - 00:00:09 / [[SPEAKER_2]]" in rendered
