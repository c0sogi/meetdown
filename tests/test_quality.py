from meetdown.json_types import JsonObject, as_object_list
from meetdown.quality import assess_transcript

KOREAN_LINES = (
    "이번 회의에서는 다음 달 현장 시연 일정과 준비 범위를 먼저 정리하겠습니다.",
    "시연은 정밀도보다 기능이 실제로 동작한다는 점을 보여주는 데 집중하면 좋겠습니다.",
    "출력 형식은 플랫폼 담당자와 따로 맞춰 보고 다음 주 수요일까지 공유하겠습니다.",
    "합성 데이터로 학습한 모델은 실제 데이터로 한 번 더 미세 조정할 계획입니다.",
)


def segment(start: float, end: float, text: str) -> JsonObject:
    return {
        "start": start * 1000,
        "end": end * 1000,
        "text": text,
        "speaker": {"label": "A"},
    }


def korean_response() -> JsonObject:
    segments: list[object] = [
        segment(index * 8, index * 8 + 7, line)
        for index, line in enumerate(KOREAN_LINES)
    ]
    return {"text": " ".join(KOREAN_LINES), "segments": segments}


def test_normal_korean_transcript_is_ok() -> None:
    report = assess_transcript(korean_response(), "ko-KR")

    assert report.status == "ok"
    assert report.warnings == ()
    assert report.to_json()["recommendations"] == []


def test_repetition_loop_with_impossible_speech_rate_is_poor() -> None:
    response = korean_response()
    segments = as_object_list(response["segments"])
    assert segments is not None
    segments.append(segment(40, 43, "twenty to thirty to " * 80))

    report = assess_transcript(response, "ko-KR")

    assert report.status == "poor"
    assert report.repetition == 1
    assert report.speech_rate == 1
    assert report.examples[0].reasons == (
        "repetition",
        "speech_rate",
        "language_mismatch",
    )
    assert "possible transcription hallucination" in report.warnings[0]


def test_english_output_for_korean_speech_is_flagged() -> None:
    english = [
        segment(
            index * 6,
            index * 6 + 5,
            "So we have to go through the whole process again.",
        )
        for index in range(6)
    ]
    response: JsonObject = {
        "text": "",
        "segments": [*english, segment(40, 47, KOREAN_LINES[0])],
    }

    report = assess_transcript(response, "ko-KR")

    assert report.status == "poor"
    assert report.language_mismatch == 6
    assert report.latin_ratio is not None and report.latin_ratio > 0.3
    assert any("Latin script" in warning for warning in report.warnings)


def test_language_check_is_skipped_when_language_is_auto() -> None:
    english = [
        segment(
            index * 6,
            index * 6 + 5,
            "So we have to go through the whole process again.",
        )
        for index in range(3)
    ]

    report = assess_transcript({"text": "", "segments": english}, "auto")

    assert report.status == "ok"
    assert report.latin_ratio is None


def test_full_text_without_segments_detects_loops() -> None:
    loop = "노타가 좀 더 나갈 수도 있긴 한데 여기 원디바이스 인공지능 모델입니다. " * 12
    response: JsonObject = {"text": " ".join(KOREAN_LINES) * 3 + loop, "segments": []}

    report = assess_transcript(response, "ko-KR")

    assert report.status in {"review", "poor"}
    assert report.repetitive_windows > 0


def test_report_json_includes_summary_and_counts() -> None:
    response = korean_response()
    segments = as_object_list(response["segments"])
    assert segments is not None
    segments.append(segment(40, 41, "just " * 200))

    payload = assess_transcript(response, "ko-KR").to_json()

    assert payload["status"] == "poor"
    assert str(payload["summary"]).startswith("poor: ")
    assert payload["counts"] == {
        "repetition": 1,
        "speech_rate": 1,
        "language_mismatch": 1,
    }
    assert payload["recommendations"]
