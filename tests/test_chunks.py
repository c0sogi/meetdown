import pytest

from meetdown.chunks import (
    ffmpeg_executable,
    merge_responses,
    normalize_chunk_format,
    offset_response_times,
    parse_duration_seconds,
    parse_time_seconds,
    validate_time_range,
)
from meetdown.json_types import JsonObject, as_json_object, as_object_list


def test_parse_duration_seconds_accepts_suffixes() -> None:
    assert parse_duration_seconds("600") == 600
    assert parse_duration_seconds("10m") == 600
    assert parse_duration_seconds("1h") == 3600
    assert parse_duration_seconds("1.5m") == 90
    assert parse_duration_seconds("01:30") == 90
    assert parse_duration_seconds("01:02:03") == 3723


def test_parse_time_seconds_accepts_zero_for_range_start() -> None:
    assert parse_time_seconds("0") == 0
    assert parse_time_seconds("00:00") == 0


def test_parse_time_seconds_rejects_invalid_colon_values() -> None:
    with pytest.raises(ValueError, match="less than 60"):
        parse_time_seconds("01:99")


def test_validate_time_range_requires_end_after_start() -> None:
    validate_time_range(10, 20)
    with pytest.raises(ValueError, match="greater than start"):
        validate_time_range(20, 10)


def test_ffmpeg_executable_is_available_from_system_or_dependency() -> None:
    assert ffmpeg_executable()


def test_normalize_chunk_format_accepts_supported_values() -> None:
    assert normalize_chunk_format(" FLAC ") == "flac"
    assert normalize_chunk_format("mp3") == "mp3"
    assert normalize_chunk_format("wav") == "wav"


def test_normalize_chunk_format_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="chunk format"):
        normalize_chunk_format("aac")


def test_offset_response_times_adjusts_segments_words_and_events() -> None:
    response: JsonObject = {
        "segments": [
            {
                "start": 1000,
                "end": 2000,
                "words": [[1000, 1200, "hello"]],
            }
        ],
        "events": [{"start": 3000, "end": 3500}],
    }

    adjusted = offset_response_times(response, 10_000)
    segments = as_object_list(adjusted["segments"])
    assert segments is not None
    first_segment = as_json_object(segments[0])
    assert first_segment is not None
    words = as_object_list(first_segment["words"])
    assert words is not None
    first_word = as_object_list(words[0])
    assert first_word is not None
    events = as_object_list(adjusted["events"])
    assert events is not None
    first_event = as_json_object(events[0])
    assert first_event is not None

    assert first_segment["start"] == 11_000
    assert first_segment["end"] == 12_000
    assert first_word[:2] == [11_000, 11_200]
    assert first_event["start"] == 13_000


def test_merge_responses_combines_text_segments_and_confidence() -> None:
    responses: list[JsonObject] = [
        {"text": "첫 번째", "confidence": 0.8, "segments": [{"text": "첫 번째"}]},
        {"text": "두 번째", "confidence": 1.0, "segments": [{"text": "두 번째"}]},
    ]
    merged = merge_responses(responses)
    segments = as_object_list(merged["segments"])
    assert segments is not None
    segment_texts = [
        segment["text"]
        for item in segments
        if (segment := as_json_object(item)) is not None
    ]

    assert merged["text"] == "첫 번째 두 번째"
    assert segment_texts == ["첫 번째", "두 번째"]
    assert merged["confidence"] == 0.9
