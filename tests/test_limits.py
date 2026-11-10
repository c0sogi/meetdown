from meetdown.limits import (
    format_duration_option,
    plan_auto_chunk,
    request_limit_seconds,
)
from meetdown.providers import ProviderConfig


def make_config(provider: str, *, openai_model: str | None = None) -> ProviderConfig:
    if provider == "openai":
        return ProviderConfig(
            provider="openai",
            language="ko-KR",
            timeout_seconds=60,
            word_alignment=False,
            diarization=True,
            api_key="key",
            openai_model=openai_model or "gpt-4o-transcribe-diarize",
        )
    if provider == "gemini":
        return ProviderConfig(
            provider="gemini",
            language="ko-KR",
            timeout_seconds=60,
            word_alignment=False,
            diarization=True,
            api_key="key",
        )
    return ProviderConfig(
        provider="clova",
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=True,
        api_url="https://clova.example",
        api_key="key",
    )


def test_openai_diarization_model_splits_long_media_into_ten_minute_chunks() -> None:
    plan = plan_auto_chunk(
        make_config("openai"), duration_seconds=1926, upload_format="mp3"
    )

    assert plan is not None
    assert plan.chunk_seconds == 600
    assert plan.request_limit_seconds == 1400
    assert "openai accepts about 1400 s per request" in plan.reason


def test_media_within_the_request_limit_is_not_split() -> None:
    assert (
        plan_auto_chunk(
            make_config("openai"), duration_seconds=1200, upload_format="mp3"
        )
        is None
    )
    assert (
        plan_auto_chunk(
            make_config("openai"), duration_seconds=None, upload_format="mp3"
        )
        is None
    )


def test_whisper_is_limited_only_by_upload_size() -> None:
    whisper = make_config("openai", openai_model="whisper-1")

    assert plan_auto_chunk(whisper, duration_seconds=1926, upload_format="mp3") is None
    flac_plan = plan_auto_chunk(whisper, duration_seconds=1926, upload_format="flac")
    assert flac_plan is not None
    assert flac_plan.chunk_seconds == 600


def test_gemini_uses_the_inline_request_size_limit() -> None:
    gemini = make_config("gemini")

    mp3_plan = plan_auto_chunk(gemini, duration_seconds=2369, upload_format="mp3")
    assert mp3_plan is not None
    assert mp3_plan.chunk_seconds == 1200

    flac_plan = plan_auto_chunk(gemini, duration_seconds=1000, upload_format="flac")
    assert flac_plan is not None
    assert flac_plan.chunk_seconds == 540


def test_original_file_upload_uses_its_measured_bitrate() -> None:
    plan = plan_auto_chunk(
        make_config("openai", openai_model="whisper-1"),
        duration_seconds=1000,
        upload_format="wav",
        source_bytes=30_000_000,
    )

    assert plan is not None
    assert plan.request_limit_seconds < 1000
    assert plan.chunk_seconds == 600


def test_clova_has_no_client_side_request_limit() -> None:
    clova = make_config("clova")

    assert request_limit_seconds(clova, "mp3") is None
    assert plan_auto_chunk(clova, duration_seconds=7200, upload_format="mp3") is None


def test_format_duration_option_matches_chunk_duration_syntax() -> None:
    assert format_duration_option(600) == "10m"
    assert format_duration_option(1200) == "20m"
    assert format_duration_option(90) == "90s"
    assert format_duration_option(45.5) == "45.5s"
