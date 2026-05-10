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
        "text": "This is the full text.",
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
                "text": "This is the first utterance.",
                "speaker": {"name": "Alice", "label": "1"},
            },
            {
                "start": 5100,
                "end": 9000,
                "text": "This is the second utterance.",
                "speaker": {"label": "2"},
            },
        ],
    }

    rendered = render_markdown(
        response,
        title="Meeting",
        source_path="meeting.m4a",
        created_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert "# Meeting" in rendered
    assert "## Processing options" in rendered
    assert "- provider: `clova`" in rendered
    assert "- api_key: `se*****ey`" in rendered
    assert "Replay command:" in rendered
    assert (
        'uvx meetdown meeting.m4a -o meeting.md --api-key "<CLOVA Secret Key>"'
        in rendered
    )
    assert "placeholder values must be replaced" in rendered
    assert "## Full text" in rendered
    assert "This is the full text." in rendered
    assert "### 00:00:00 - 00:00:04 / Alice" in rendered
    assert "### 00:00:05 - 00:00:09 / [[SPEAKER_2]]" in rendered
