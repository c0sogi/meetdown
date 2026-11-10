"""Heuristics that flag likely speech-recognition hallucinations.

Some speech models loop on a phrase, emit text far faster than anyone can speak,
or translate speech into English instead of transcribing it. These checks are
cheap, need no extra API calls, and were calibrated on real Korean meetings:
normal segments compressed at a 1.4-1.7 ratio while looping segments exceeded 3.
"""

import re
import zlib
from dataclasses import dataclass, replace
from typing import Literal

from meetdown import text as ui_text
from meetdown.json_types import JsonObject, as_json_object, as_number, as_object_list

QualityStatus = Literal["ok", "review", "poor"]
REASON_REPETITION = "repetition"
REASON_SPEECH_RATE = "speech_rate"
REASON_LANGUAGE_MISMATCH = "language_mismatch"

# Whisper drops windows above this zlib compression ratio as repetitive.
SEGMENT_REPETITION_RATIO = 2.4
SEGMENT_MIN_CHARS = 60
WINDOW_REPETITION_RATIO = 2.8
WINDOW_SIZE = 400
WINDOW_STEP = 200
MAX_CHARS_PER_SECOND = 25.0
ZERO_LENGTH_MAX_CHARS = 40
LATIN_DOMINANT_RATIO = 0.8
LATIN_MIN_LETTERS = 20
LATIN_OVERALL_POOR = 0.30
POOR_SHARE = 0.20
REVIEW_SHARE = 0.05
MAX_EXAMPLES = 8
PREVIEW_CHARS = 60

_LATIN_RE = re.compile(r"[A-Za-z]")
_HANGUL_RE = re.compile(r"[가-힣]")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FlaggedSegment:
    start_ms: float | None
    end_ms: float | None
    reasons: tuple[str, ...]
    preview: str

    def to_json(self) -> JsonObject:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "reasons": list(self.reasons),
            "preview": self.preview,
        }


@dataclass(frozen=True)
class QualityReport:
    status: QualityStatus
    suspect_share: float
    latin_ratio: float | None
    repetition: int
    speech_rate: int
    language_mismatch: int
    repetitive_windows: int
    examples: tuple[FlaggedSegment, ...]
    warnings: tuple[str, ...]

    def details(self) -> list[str]:
        details: list[str] = []
        repetition = self.repetition + self.repetitive_windows
        if repetition:
            details.append(ui_text.quality_detail_repetition(repetition))
        if self.speech_rate:
            details.append(ui_text.quality_detail_speech_rate(self.speech_rate))
        if self.language_mismatch:
            details.append(ui_text.quality_detail_language(self.language_mismatch))
        return details

    def summary(self) -> str:
        return ui_text.quality_summary(self.status, self.suspect_share, self.details())

    def to_json(self) -> JsonObject:
        return {
            "status": self.status,
            "summary": self.summary(),
            "suspect_share": round(self.suspect_share, 4),
            "latin_ratio": (
                round(self.latin_ratio, 4) if self.latin_ratio is not None else None
            ),
            "counts": {
                REASON_REPETITION: self.repetition + self.repetitive_windows,
                REASON_SPEECH_RATE: self.speech_rate,
                REASON_LANGUAGE_MISMATCH: self.language_mismatch,
            },
            "examples": [example.to_json() for example in self.examples],
            "warnings": list(self.warnings),
            "recommendations": (
                list(ui_text.QUALITY_RECOMMENDATIONS) if self.status != "ok" else []
            ),
        }


def compression_ratio(text: str) -> float:
    raw = text.encode("utf-8")
    return len(raw) / max(1, len(zlib.compress(raw, 9)))


def expects_korean(language: str) -> bool:
    return language.strip().lower().startswith("ko")


def _letters(text: str) -> tuple[int, int]:
    return len(_LATIN_RE.findall(text)), len(_HANGUL_RE.findall(text))


def _visible_chars(text: str) -> int:
    return len(_SPACE_RE.sub("", text))


def _preview(text: str) -> str:
    flat = _SPACE_RE.sub(" ", text).strip()
    if len(flat) <= PREVIEW_CHARS:
        return flat
    return flat[:PREVIEW_CHARS] + "..."


def _segment_reasons(
    text: str, start_ms: float | None, end_ms: float | None, korean: bool
) -> tuple[str, ...]:
    chars = _visible_chars(text)
    reasons: list[str] = []
    if (
        chars >= SEGMENT_MIN_CHARS
        and compression_ratio(text) > SEGMENT_REPETITION_RATIO
    ):
        reasons.append(REASON_REPETITION)
    if start_ms is not None and end_ms is not None:
        duration = (end_ms - start_ms) / 1000
        if duration >= 1.0:
            if chars / duration > MAX_CHARS_PER_SECOND:
                reasons.append(REASON_SPEECH_RATE)
        elif chars >= ZERO_LENGTH_MAX_CHARS:
            reasons.append(REASON_SPEECH_RATE)
    if korean:
        latin, hangul = _letters(text)
        if (
            latin >= LATIN_MIN_LETTERS
            and latin / max(1, latin + hangul) >= LATIN_DOMINANT_RATIO
        ):
            reasons.append(REASON_LANGUAGE_MISMATCH)
    return tuple(reasons)


def _full_text_windows(full_text: str) -> list[str]:
    starts = range(0, max(1, len(full_text) - WINDOW_SIZE + 1), WINDOW_STEP)
    windows = [full_text[index : index + WINDOW_SIZE] for index in starts]
    return [window for window in windows if _visible_chars(window) >= SEGMENT_MIN_CHARS]


def assess_transcript(response: JsonObject, language: str) -> QualityReport:
    """Score a normalized transcription response for likely hallucinations.

    ``status`` is ``poor`` when a large share of the text is suspect, ``review``
    when there are isolated problems, and ``ok`` otherwise.
    """
    korean = expects_korean(language)
    examples: list[FlaggedSegment] = []
    counts = {REASON_REPETITION: 0, REASON_SPEECH_RATE: 0, REASON_LANGUAGE_MISMATCH: 0}
    total_chars = 0
    suspect_chars = 0
    segment_texts: list[str] = []

    for item in as_object_list(response.get("segments")) or []:
        segment = as_json_object(item)
        if segment is None:
            continue
        text = str(segment.get("text") or "")
        start = as_number(segment.get("start"))
        end = as_number(segment.get("end"))
        start_ms = float(start) if start is not None else None
        end_ms = float(end) if end is not None else None
        chars = _visible_chars(text)
        total_chars += chars
        segment_texts.append(text)
        reasons = _segment_reasons(text, start_ms, end_ms, korean)
        if not reasons:
            continue
        suspect_chars += chars
        for reason in reasons:
            counts[reason] += 1
        if len(examples) < MAX_EXAMPLES:
            examples.append(FlaggedSegment(start_ms, end_ms, reasons, _preview(text)))

    full_text = str(response.get("text") or "")
    windows = [] if segment_texts else _full_text_windows(full_text)
    repetitive_windows = sum(
        1 for window in windows if compression_ratio(window) > WINDOW_REPETITION_RATIO
    )

    basis = " ".join(segment_texts) if segment_texts else full_text
    latin, hangul = _letters(basis)
    latin_ratio = latin / max(1, latin + hangul) if korean else None

    if segment_texts:
        suspect_share = suspect_chars / max(1, total_chars)
    else:
        suspect_share = repetitive_windows / max(1, len(windows))
    strong_signals = (
        counts[REASON_REPETITION] + counts[REASON_SPEECH_RATE] + repetitive_windows
    )

    status: QualityStatus
    if suspect_share >= POOR_SHARE or (
        latin_ratio is not None and latin_ratio >= LATIN_OVERALL_POOR
    ):
        status = "poor"
    elif strong_signals or suspect_share >= REVIEW_SHARE:
        status = "review"
    else:
        status = "ok"

    report = QualityReport(
        status=status,
        suspect_share=suspect_share,
        latin_ratio=latin_ratio,
        repetition=counts[REASON_REPETITION],
        speech_rate=counts[REASON_SPEECH_RATE],
        language_mismatch=counts[REASON_LANGUAGE_MISMATCH],
        repetitive_windows=repetitive_windows,
        examples=tuple(examples),
        warnings=(),
    )
    warnings: list[str] = []
    if status != "ok":
        warnings.append(ui_text.quality_warning(report.summary()))
    if latin_ratio is not None and latin_ratio >= LATIN_OVERALL_POOR:
        warnings.append(ui_text.latin_script_warning(latin_ratio))
    return replace(report, warnings=tuple(warnings))
