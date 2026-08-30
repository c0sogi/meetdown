from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from typing import Literal
from urllib.parse import urlparse

from meetdown.constants import (
    GEMINI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    PROVIDER_CLOVA,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_USAGES_KEY,
)
from meetdown.json_types import JsonObject, as_json_object, as_number, as_object_list
from meetdown.providers import ProviderConfig

Currency = Literal["USD", "KRW"]

PRICING_AS_OF = "2026-08-30"
OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
GEMINI_PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
CLOVA_PRICING_SOURCE = "https://www.ncloud.com/product/aiService/clovaSpeech"

_ONE_MILLION = Decimal(1_000_000)
_SECONDS_PER_MINUTE = Decimal(60)

# Standard list prices per one million tokens. Keep these model-specific so a
# custom or newly released model cannot silently inherit the wrong price.
_OPENAI_TOKEN_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-transcribe-diarize": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-transcribe": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini-transcribe": (Decimal("1.25"), Decimal("5.00")),
}
_OPENAI_MINUTE_RATES: dict[str, Decimal] = {
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL: Decimal("0.0045"),
    "gpt-4o-transcribe-diarize": Decimal("0.006"),
    "gpt-4o-transcribe": Decimal("0.006"),
    "gpt-4o-mini-transcribe": Decimal("0.003"),
}

_GEMINI_TEXT_INPUT_RATE = Decimal("0.50")
_GEMINI_AUDIO_INPUT_RATE = Decimal("1.00")
_GEMINI_OUTPUT_RATE = Decimal("3.00")

_CLOVA_UNIT_SECONDS = 15
_CLOVA_BASE_RATE_KRW = Decimal(5)

_COMMON_NOTE = (
    "Provider list-price estimate; excludes free-tier allowances, credits, taxes, "
    "and account-specific adjustments."
)
_CLOVA_NOTE = (
    "CLOVA base speech recognition only; excludes free-tier allowances, VAT, and "
    "optional feature charges such as speaker diarization."
)


@dataclass(frozen=True)
class CostEstimate:
    amount: Decimal | None
    currency: Currency | None
    basis: str
    pricing_source: str
    note: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    billable_audio_seconds: float | None = None

    @property
    def available(self) -> bool:
        return self.amount is not None and self.currency is not None

    def display_amount(self) -> str:
        if self.amount is None or self.currency is None:
            return "unavailable"
        if self.currency == "KRW":
            rounded = self.amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return f"₩{int(rounded):,} KRW"

        rounded = self.amount.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        amount_text = format(rounded, "f").rstrip("0").rstrip(".")
        return f"${amount_text or '0'} USD"

    def processing_options(self) -> JsonObject:
        options: JsonObject = {
            "estimated_cost": self.display_amount(),
            "estimate_basis": self.basis,
            "pricing_as_of": PRICING_AS_OF,
            "pricing_source": self.pricing_source,
            "pricing_note": self.note,
        }
        if self.input_tokens is not None:
            options["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            options["output_tokens"] = self.output_tokens
        if self.billable_audio_seconds is not None:
            options["billable_audio_seconds"] = self.billable_audio_seconds
        return options


def needs_request_duration(config: ProviderConfig) -> bool:
    if config.provider == PROVIDER_CLOVA:
        return True
    return (
        config.provider == PROVIDER_OPENAI
        and config.openai_model in _OPENAI_MINUTE_RATES
        and _uses_official_endpoint(config.api_url, "api.openai.com")
    )


def estimate_transcription_cost(
    config: ProviderConfig,
    response: JsonObject,
    *,
    request_durations_seconds: list[float] | None = None,
) -> CostEstimate:
    durations = request_durations_seconds or []
    if config.provider == PROVIDER_OPENAI:
        return _estimate_openai(config, response, durations)
    if config.provider == PROVIDER_GEMINI:
        return _estimate_gemini(config, response)
    return _estimate_clova(config, durations)


def _uses_official_endpoint(api_url: str | None, hostname: str) -> bool:
    if api_url is None:
        return True
    parsed = urlparse(api_url)
    return parsed.scheme == "https" and parsed.hostname == hostname


def _provider_usages(response: JsonObject) -> list[JsonObject]:
    usages: list[JsonObject] = []
    for value in as_object_list(response.get(PROVIDER_USAGES_KEY)) or []:
        usage = as_json_object(value)
        if usage is not None:
            usages.append(usage)
    return usages


def _nonnegative_int(value: object) -> int | None:
    number = as_number(value)
    if number is None or number < 0 or int(number) != number:
        return None
    return int(number)


def _sum_required_counts(usages: list[JsonObject], key: str) -> int | None:
    if not usages:
        return None
    total = 0
    for usage in usages:
        count = _nonnegative_int(usage.get(key))
        if count is None:
            return None
        total += count
    return total


def _valid_duration_total(values: list[float]) -> float | None:
    if not values or any(value <= 0 for value in values):
        return None
    return sum(values)


def _unavailable(
    basis: str, pricing_source: str, note: str = _COMMON_NOTE
) -> CostEstimate:
    return CostEstimate(
        amount=None,
        currency=None,
        basis=basis,
        pricing_source=pricing_source,
        note=note,
    )


def _openai_reported_duration(usages: list[JsonObject]) -> float | None:
    seconds: list[float] = []
    for usage in usages:
        value = as_number(usage.get("seconds"))
        if value is None or value <= 0:
            return None
        seconds.append(float(value))
    return _valid_duration_total(seconds)


def _estimate_openai(
    config: ProviderConfig,
    response: JsonObject,
    request_durations_seconds: list[float],
) -> CostEstimate:
    if not _uses_official_endpoint(config.api_url, "api.openai.com"):
        return _unavailable(
            "Custom OpenAI endpoint; provider list pricing was not applied",
            OPENAI_PRICING_SOURCE,
        )

    model = config.openai_model
    token_rates = _OPENAI_TOKEN_RATES.get(model)
    minute_rate = _OPENAI_MINUTE_RATES.get(model)
    if token_rates is None and minute_rate is None:
        return _unavailable(
            f"No maintained pricing for OpenAI model {model}",
            OPENAI_PRICING_SOURCE,
        )

    usages = _provider_usages(response)
    if token_rates is not None:
        input_tokens = _sum_required_counts(usages, "input_tokens")
        output_tokens = _sum_required_counts(usages, "output_tokens")
        if input_tokens is not None and output_tokens is not None:
            input_rate, output_rate = token_rates
            amount = (
                Decimal(input_tokens) * input_rate
                + Decimal(output_tokens) * output_rate
            ) / _ONE_MILLION
            return CostEstimate(
                amount=amount,
                currency="USD",
                basis="OpenAI provider-reported token usage",
                pricing_source=OPENAI_PRICING_SOURCE,
                note=_COMMON_NOTE,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

    if minute_rate is not None:
        duration = _openai_reported_duration(usages)
        basis = "OpenAI provider-reported audio duration"
        if duration is None:
            duration = _valid_duration_total(request_durations_seconds)
            basis = "Uploaded audio duration and OpenAI estimated minute rate"
        if duration is not None:
            amount = Decimal(str(duration)) / _SECONDS_PER_MINUTE * minute_rate
            return CostEstimate(
                amount=amount,
                currency="USD",
                basis=basis,
                pricing_source=OPENAI_PRICING_SOURCE,
                note=_COMMON_NOTE,
                billable_audio_seconds=duration,
            )

    return _unavailable(
        "OpenAI response did not include usable billing metadata",
        OPENAI_PRICING_SOURCE,
    )


def _gemini_usage_counts(
    usages: list[JsonObject],
) -> tuple[int, int, int] | None:
    if not usages:
        return None

    audio_input = 0
    other_input = 0
    output = 0
    for usage in usages:
        service_tier = usage.get("serviceTier")
        if service_tier is not None and str(service_tier).lower() != "standard":
            return None

        details = as_object_list(usage.get("promptTokensDetails"))
        if details is None:
            return None
        detailed_prompt_total = 0
        for value in details:
            detail = as_json_object(value)
            if detail is None:
                return None
            token_count = _nonnegative_int(detail.get("tokenCount"))
            if token_count is None:
                return None
            detailed_prompt_total += token_count
            if str(detail.get("modality") or "").upper() == "AUDIO":
                audio_input += token_count
            else:
                other_input += token_count

        prompt_total = _nonnegative_int(usage.get("promptTokenCount"))
        if prompt_total is None or detailed_prompt_total > prompt_total:
            return None
        other_input += prompt_total - detailed_prompt_total

        candidates = _nonnegative_int(usage.get("candidatesTokenCount"))
        thoughts = _nonnegative_int(usage.get("thoughtsTokenCount"))
        output += (candidates or 0) + (thoughts or 0)

    return audio_input, other_input, output


def _estimate_gemini(config: ProviderConfig, response: JsonObject) -> CostEstimate:
    if not _uses_official_endpoint(config.api_url, "generativelanguage.googleapis.com"):
        return _unavailable(
            "Custom Gemini endpoint; provider list pricing was not applied",
            GEMINI_PRICING_SOURCE,
        )
    if config.gemini_model != GEMINI_DEFAULT_MODEL:
        return _unavailable(
            f"No maintained pricing for Gemini model {config.gemini_model}",
            GEMINI_PRICING_SOURCE,
        )

    counts = _gemini_usage_counts(_provider_usages(response))
    if counts is None:
        return _unavailable(
            "Gemini response did not include standard-tier modality token usage",
            GEMINI_PRICING_SOURCE,
        )

    audio_input, other_input, output = counts
    amount = (
        Decimal(audio_input) * _GEMINI_AUDIO_INPUT_RATE
        + Decimal(other_input) * _GEMINI_TEXT_INPUT_RATE
        + Decimal(output) * _GEMINI_OUTPUT_RATE
    ) / _ONE_MILLION
    return CostEstimate(
        amount=amount,
        currency="USD",
        basis="Gemini provider-reported standard-tier modality token usage",
        pricing_source=GEMINI_PRICING_SOURCE,
        note=_COMMON_NOTE,
        input_tokens=audio_input + other_input,
        output_tokens=output,
    )


def _estimate_clova(
    config: ProviderConfig, request_durations_seconds: list[float]
) -> CostEstimate:
    if config.provider != PROVIDER_CLOVA:
        return _unavailable("Unsupported provider", CLOVA_PRICING_SOURCE)
    if not request_durations_seconds or any(
        duration <= 0 for duration in request_durations_seconds
    ):
        return _unavailable(
            "Uploaded audio duration was unavailable",
            CLOVA_PRICING_SOURCE,
            _CLOVA_NOTE,
        )

    billed_units = sum(
        ceil(duration / _CLOVA_UNIT_SECONDS) for duration in request_durations_seconds
    )
    billable_seconds = float(billed_units * _CLOVA_UNIT_SECONDS)
    return CostEstimate(
        amount=Decimal(billed_units) * _CLOVA_BASE_RATE_KRW,
        currency="KRW",
        basis=(
            "CLOVA base speech recognition; request duration rounded up in "
            "15-second units"
        ),
        pricing_source=CLOVA_PRICING_SOURCE,
        note=_CLOVA_NOTE,
        billable_audio_seconds=billable_seconds,
    )
