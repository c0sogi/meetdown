from dataclasses import replace
from decimal import Decimal
from typing import cast

from meetdown.constants import PROVIDER_USAGES_KEY, ProviderName
from meetdown.json_types import JsonObject
from meetdown.pricing import estimate_transcription_cost
from meetdown.providers import ProviderConfig


def provider_config(
    provider: str,
    *,
    api_url: str | None = None,
    model: str | None = None,
    diarization: bool = True,
) -> ProviderConfig:
    config = ProviderConfig(
        provider=cast(ProviderName, provider),
        language="ko-KR",
        timeout_seconds=60,
        word_alignment=False,
        diarization=diarization,
        api_url=api_url,
        api_key="test-key",
    )
    if provider == "openai" and model is not None:
        return replace(config, openai_model=model)
    if provider == "gemini" and model is not None:
        return replace(config, gemini_model=model)
    return config


def test_openai_uses_reported_token_usage() -> None:
    response: JsonObject = {
        PROVIDER_USAGES_KEY: [
            {"type": "tokens", "input_tokens": 100_000, "output_tokens": 10_000}
        ]
    }

    estimate = estimate_transcription_cost(provider_config("openai"), response)

    assert estimate.amount == Decimal("0.35")
    assert estimate.display_amount() == "$0.35 USD"
    assert estimate.input_tokens == 100_000
    assert estimate.output_tokens == 10_000


def test_openai_duration_model_uses_reported_seconds() -> None:
    response: JsonObject = {PROVIDER_USAGES_KEY: [{"type": "duration", "seconds": 120}]}

    estimate = estimate_transcription_cost(
        provider_config("openai", model="gpt-transcribe", diarization=False),
        response,
    )

    assert estimate.amount == Decimal("0.0090")
    assert estimate.display_amount() == "$0.009 USD"
    assert estimate.billable_audio_seconds == 120


def test_gemini_uses_modality_and_output_tokens() -> None:
    response: JsonObject = {
        PROVIDER_USAGES_KEY: [
            {
                "promptTokenCount": 33_000,
                "promptTokensDetails": [
                    {"modality": "AUDIO", "tokenCount": 32_000},
                    {"modality": "TEXT", "tokenCount": 1_000},
                ],
                "candidatesTokenCount": 2_000,
                "thoughtsTokenCount": 500,
            }
        ]
    }

    estimate = estimate_transcription_cost(provider_config("gemini"), response)

    assert estimate.amount == Decimal("0.04000")
    assert estimate.display_amount() == "$0.04 USD"
    assert estimate.input_tokens == 33_000
    assert estimate.output_tokens == 2_500


def test_clova_rounds_each_request_to_fifteen_seconds() -> None:
    estimate = estimate_transcription_cost(
        provider_config("clova"),
        {},
        request_durations_seconds=[10, 32],
    )

    assert estimate.amount == Decimal(20)
    assert estimate.display_amount() == "₩20 KRW"
    assert estimate.billable_audio_seconds == 60
    assert "speaker diarization" in estimate.note


def test_custom_model_and_endpoint_are_not_assigned_official_prices() -> None:
    usage: JsonObject = {
        PROVIDER_USAGES_KEY: [{"input_tokens": 1_000, "output_tokens": 1_000}]
    }

    custom_model = estimate_transcription_cost(
        provider_config("openai", model="custom-model"), usage
    )
    custom_endpoint = estimate_transcription_cost(
        provider_config(
            "openai", api_url="https://proxy.example.com/v1", model="gpt-transcribe"
        ),
        usage,
        request_durations_seconds=[60],
    )

    assert not custom_model.available
    assert not custom_endpoint.available
    assert custom_model.display_amount() == "unavailable"
