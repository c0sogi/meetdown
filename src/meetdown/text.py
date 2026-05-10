from __future__ import annotations

from collections.abc import Iterable

from meetdown.constants import (
    APP_NAME,
    AUTO_DETECT_API_KEY_ENV_NAMES,
    CLOVA_MODEL_DESCRIPTION,
    CLOVA_SPEECH_SECRET_KEY_ENV,
    CLOVA_SPEECH_INVOKE_URL_ENV,
    GEMINI_API_KEY_ENV,
    GEMINI_DEFAULT_MODEL,
    GOOGLE_API_KEY_ENV,
    MEETDOWN_API_KEY_ENV,
    OPENAI_API_KEY_ENV,
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_NO_DIARIZATION_MODEL,
    LANGUAGE_AUTO,
)

HELP_DESCRIPTION = """\
Turn a meeting recording into a Markdown transcript.

meetdown can use CLOVA Speech, OpenAI, or Gemini. When --provider is omitted,
it auto-detects the provider from configured provider-specific credentials.
Common inputs include m4a, mp3, wav, flac, and mp4 files.
meetdown extracts audio and prepares a provider-friendly upload copy before transcription.
"""

ARG_AUDIO_PATH_HELP = (
    "Local audio or video file to transcribe, such as m4a, mp3, wav, flac, or mp4."
)
ARG_PROVIDER_GROUP = "provider and credentials"
ARG_PROVIDER_HELP = (
    "Speech provider to use. Auto-detected from provider-specific credentials "
    "when omitted."
)
ARG_API_KEY_HELP = "Generic provider API key. Uses provider-specific environment variables when omitted."
ARG_API_URL_HELP = (
    "Provider API URL. For CLOVA, use the CLOVA Speech Invoke URL; "
    "/recognizer/upload is optional."
)
ARG_MODEL_HELP = "Provider model override. Used by OpenAI and Gemini only."
ARG_OUTPUT_GROUP = "output"
ARG_OUTPUT_HELP = "Markdown output path."
ARG_TITLE_HELP = "Markdown document title."
ARG_FROM_JSON_HELP = (
    "Convert an existing normalized provider JSON response instead of calling the API."
)
ARG_SAVE_JSON_HELP = "Save the normalized transcription JSON to this path."
ARG_MEDIA_GROUP = "media selection and upload size"
ARG_CHUNK_DURATION_HELP = (
    "Split media before upload. Accepts seconds or s/m/h suffixes, "
    "such as 600, 10m, or 1h."
)
ARG_CHUNK_FORMAT_HELP = "Exact temporary upload format. Overrides --compress."
ARG_COMPRESS_HELP = "Upload compression preset."
ARG_START_HELP = (
    "Only transcribe media after this time. Accepts 600, 10m, 01:23, or 01:02:03."
)
ARG_END_HELP = (
    "Stop transcription at this source-media time. Accepts 600, 10m, 01:23, "
    "or 01:02:03."
)
ARG_RECOGNITION_GROUP = "recognition"
ARG_LANGUAGE_HELP = "Recognition language."
ARG_WORD_ALIGNMENT_HELP = "Request word-level alignment when the provider supports it."
ARG_NO_DIARIZATION_HELP = "Disable speaker diarization when the provider supports it."
ARG_ADVANCED_GROUP = "advanced"
ARG_TIMEOUT_HELP = "HTTP timeout in seconds for provider upload."

MARKDOWN_METADATA_HEADING = "## Metadata"
MARKDOWN_SOURCE_FILE_LABEL = "Source file"
MARKDOWN_CREATED_AT_LABEL = "Created at"
MARKDOWN_LANGUAGE_LABEL = "Recognition language"
MARKDOWN_CONFIDENCE_LABEL = "Overall confidence"
MARKDOWN_PROCESSING_HEADING = "## Processing options"
MARKDOWN_REPLAY_COMMAND_LABEL = "Replay command:"
MARKDOWN_PLACEHOLDER_NOTE = (
    "`<...>` placeholder values must be replaced before running this command."
)
MARKDOWN_FULL_TEXT_HEADING = "## Full text"
MARKDOWN_NO_FULL_TEXT = "_No full text._"
MARKDOWN_TRANSCRIPT_HEADING = "## Transcript"
MARKDOWN_NO_SEGMENTS = "_No transcript segments._"
MARKDOWN_NO_CONTENT = "_No content._"

OPTION_NOT_CONFIGURED = "not configured"
OPTION_NOT_SET = "not set"
OPTION_TRUE = "true"
OPTION_FALSE = "false"
PROCESSING_NOT_USED = "not used"
PROCESSING_NOT_CHUNKED = "not chunked"
PROCESSING_START_OF_FILE = "start of file"
PROCESSING_END_OF_FILE = "end of file"
PROCESSING_CONFIGURED = "configured"
PROCESSING_PROVIDER_DEFAULT = "provider default"
PREPROCESSING_SOURCE_FILE = "source file"
PREPROCESSING_CHUNKED = "chunked"
PREPROCESSING_SELECTED_RANGE = "selected range"
PREPROCESSING_COMPRESSED_UPLOAD = "compressed upload"


def comma_list(values: Iterable[str]) -> str:
    return ", ".join(values)


def help_epilog() -> str:
    return f"""\
Quick start:
  CLOVA:
    uvx {APP_NAME} meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>"

  OpenAI with {OPENAI_API_KEY_ENV} set:
    uvx {APP_NAME} meeting.m4a -o meeting.md

  Gemini with {GEMINI_API_KEY_ENV} set:
    uvx {APP_NAME} meeting.m4a -o meeting.md --chunk-duration 10m

Common workflows:
  Long recording:
    uvx {APP_NAME} meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --chunk-duration 10m

  Only transcribe a section:
    uvx {APP_NAME} meeting.mp4 -o section.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --start 00:10:00 --end 00:45:00

  Save normalized provider JSON as well as Markdown:
    uvx {APP_NAME} meeting.m4a -o meeting.md --api-url "<CLOVA Invoke URL>" --api-key "<CLOVA Secret Key>" --save-json meeting.json

  Convert a saved normalized JSON response without calling an API:
    uvx {APP_NAME} --from-json meeting.json -o meeting.md

Compression presets:
  --compress smallest  -> MP3 64 kbps upload, usually cheapest
  --compress lossless  -> FLAC upload, larger but lossless
  --compress none      -> Upload the original file unless chunking/range extraction is needed

Provider models:
  clova  -> {CLOVA_MODEL_DESCRIPTION}
  openai -> {OPENAI_DEFAULT_MODEL}
            {OPENAI_DEFAULT_NO_DIARIZATION_MODEL} when --no-diarization is used
  gemini -> {GEMINI_DEFAULT_MODEL}

Provider credentials:
  If --provider is omitted, exactly one provider-specific API key must be configured.
  clova  needs --api-url and --api-key. /recognizer/upload is optional in --api-url.
  openai needs --api-key or {OPENAI_API_KEY_ENV}.
  gemini needs --api-key, {GEMINI_API_KEY_ENV}, or {GOOGLE_API_KEY_ENV}. Use --chunk-duration for large files.

Advanced:
  You may store keys in environment variables instead of typing --api-key every time.
  Supported names include CLOVA_SPEECH_SECRET_KEY, {OPENAI_API_KEY_ENV}, {GEMINI_API_KEY_ENV},
  {GOOGLE_API_KEY_ENV}, and {MEETDOWN_API_KEY_ENV}.
"""


def provider_must_be_supported() -> str:
    return "provider must be one of: clova, openai, gemini"


def provider_is_ambiguous(configured: Iterable[str]) -> str:
    return (
        "provider is ambiguous because multiple provider API keys are configured: "
        f"{comma_list(configured)}. Pass --provider explicitly."
    )


def provider_generic_key_is_ambiguous() -> str:
    return (
        "provider could not be inferred from a generic API key alone. "
        "Pass --provider or set exactly one provider-specific API key environment variable."
    )


def provider_could_not_be_inferred() -> str:
    return (
        "provider could not be inferred. Pass --provider or set exactly one of "
        f"{comma_list(AUTO_DETECT_API_KEY_ENV_NAMES)}."
    )


def clova_model_not_supported() -> str:
    return "--model is not supported for clova"


def clova_missing_api_url() -> str:
    return f"--api-url or {CLOVA_SPEECH_INVOKE_URL_ENV} is required for clova"


def clova_missing_api_key() -> str:
    return f"--api-key or {CLOVA_SPEECH_SECRET_KEY_ENV} is required for clova"


def openai_missing_api_key() -> str:
    return f"--api-key or {OPENAI_API_KEY_ENV} is required for openai"


def gemini_missing_api_key() -> str:
    return (
        f"--api-key, {GEMINI_API_KEY_ENV}, or {GOOGLE_API_KEY_ENV} "
        "is required for gemini"
    )


def missing_provider_config(provider: str) -> str:
    return f"{provider} provider is missing API URL or API key"


def missing_api_key(provider: str) -> str:
    return f"{provider} provider is missing API key"


def unsupported_provider(provider: str) -> str:
    return f"unsupported provider: {provider}"


def audio_file_not_found(path: object) -> str:
    return f"audio file not found: {path}"


FROM_JSON_MUST_CONTAIN_OBJECT = "--from-json must contain a JSON object"
AUDIO_PATH_REQUIRED = "audio_path is required unless --from-json is used"
INVOKE_URL_MUST_NOT_BE_EMPTY = "invoke_url must not be empty"


def transcribing_chunk(index: int, total: int, name: str, size_kib: float) -> str:
    return f"Transcribing chunk {index}/{total}: {name} ({size_kib:.1f} KiB)"


def transcribing_selected_range(name: str, size_kib: float) -> str:
    return f"Transcribing selected range: {name} ({size_kib:.1f} KiB)"


def transcribing_compressed_upload(name: str, size_kib: float) -> str:
    return f"Transcribing compressed upload: {name} ({size_kib:.1f} KiB)"


def wrote_file(path: object) -> str:
    return f"Wrote {path}"


DEFAULTS_TITLE = "Current defaults"
DEFAULTS_RUNTIME_SECTION = "Runtime"
DEFAULTS_OUTPUT_SECTION = "Output"
DEFAULTS_MEDIA_SECTION = "Media"
DEFAULTS_MODELS_SECTION = "Models"
DEFAULTS_CREDENTIALS_SECTION = "Credentials"
DEFAULTS_PROVIDER_AUTO = "auto-detect"
DEFAULTS_NOT_INFERRED = "not inferred"
DEFAULTS_OUTPUT_PATH = "<audio>.md, or <from-json>.md when --from-json is used"
DEFAULTS_TITLE_VALUE = "input file stem"
DEFAULTS_CHUNK_FORMAT_VALUE = "derived from --compress unless --chunk-format is set"
DEFAULTS_PROVIDER_LABEL = "Provider"
DEFAULTS_CURRENT_PROVIDER_LABEL = "Detected now"
DEFAULTS_LANGUAGE_LABEL = "Language"
DEFAULTS_OUTPUT_LABEL = "Markdown path"
DEFAULTS_TITLE_LABEL = "Title"
DEFAULTS_COMPRESS_LABEL = "Compression"
DEFAULTS_CHUNK_FORMAT_LABEL = "Chunk format"
DEFAULTS_UPLOAD_FORMAT_LABEL = "Upload format"
DEFAULTS_CHUNK_DURATION_LABEL = "Chunk duration"
DEFAULTS_START_LABEL = "Start"
DEFAULTS_END_LABEL = "End"
DEFAULTS_WORD_ALIGNMENT_LABEL = "Word alignment"
DEFAULTS_DIARIZATION_LABEL = "Diarization"
DEFAULTS_TIMEOUT_SECONDS_LABEL = "Timeout"
DEFAULTS_WITHOUT_DIARIZATION_LABEL = "without diarization"
DEFAULTS_API_URL_LABEL = "API URL"
DEFAULTS_API_KEY_LABEL = "API key"


def defaults_section(title: str) -> str:
    return f"{title}:"


def defaults_provider_setting(provider: str, setting: str) -> str:
    return f"{provider} {setting}"


def defaults_provider_inference_error(_error: object) -> str:
    return DEFAULTS_NOT_INFERRED


TIME_FORMAT_HELP = "time must look like 600, 10m, 01:23, or 01:02:03"
TIME_FORMAT_WITH_SECONDS_SUFFIX_HELP = (
    "time must look like 600, 600s, 10m, 01:23, or 01:02:03"
)
TIME_MUST_NOT_BE_NEGATIVE = "time must not be negative"
START_TIME_MUST_NOT_BE_NEGATIVE = "start time must not be negative"
END_TIME_MUST_BE_AFTER_START = "end time must be greater than start time"
TIME_FIELDS_MUST_BE_UNDER_60 = "minute and second fields must be less than 60"
DURATION_MUST_BE_POSITIVE = "duration must be greater than zero"
MEDIA_DURATION_MUST_BE_POSITIVE = "media duration must be greater than zero"
FFMPEG_DURATION_UNREADABLE = "ffmpeg could not read media duration"
FFPROBE_DURATION_UNREADABLE = "ffprobe could not read media duration"
FFMPEG_NO_CHUNKS = "ffmpeg did not create any chunks"
UNKNOWN_FFMPEG_ERROR = "unknown ffmpeg error"
MERGED_CHUNKED_TRANSCRIPTION = "Merged chunked transcription"


def chunk_format_must_be_supported(supported: str) -> str:
    return f"chunk format must be one of: {supported}"


def ffmpeg_required() -> str:
    return (
        "ffmpeg is required for media extraction. Install ffmpeg or install "
        "meetdown with the imageio-ffmpeg dependency."
    )


def ffmpeg_failed_to_start(action: str, error: object) -> str:
    return f"ffmpeg failed to start for {action}: {error}"


def ffmpeg_failed(action: str, stderr: str) -> str:
    return f"ffmpeg failed to {action}: {stderr}"


def provider_http_failed(provider: str, status_code: int, body: str) -> str:
    return f"{provider} transcription failed with HTTP {status_code}: {body}"


def clova_http_failed(status_code: int, body: str) -> str:
    return f"CLOVA Speech request failed with HTTP {status_code}: {body}"


def provider_returned_non_json(provider: str, body: str) -> str:
    return f"{provider} returned non-JSON response: {body}"


def clova_returned_non_json(body: str) -> str:
    return f"CLOVA Speech returned non-JSON response: {body}"


def provider_returned_non_object(provider: str) -> str:
    return f"{provider} returned a JSON value that is not an object"


CLOVA_RETURNED_NON_OBJECT = "CLOVA Speech returned a JSON value that is not an object"
GEMINI_INLINE_LIMIT_EXCEEDED = (
    "Gemini inline audio requests are limited to about 20 MB. "
    "Use --chunk-duration or --compress smallest."
)
GEMINI_TRANSCRIPT_NOT_OBJECT = "Gemini transcript was not a JSON object"


GEMINI_DIARIZATION_INSTRUCTION = (
    "Include speaker labels when you can identify speaker changes."
)
GEMINI_NO_DIARIZATION_INSTRUCTION = "Do not invent speaker labels."
GEMINI_AUTO_LANGUAGE_INSTRUCTION = (
    "Detect the spoken language or languages automatically."
)


def gemini_transcription_prompt(language: str, diarization: bool) -> str:
    speaker_instruction = (
        GEMINI_DIARIZATION_INSTRUCTION
        if diarization
        else GEMINI_NO_DIARIZATION_INSTRUCTION
    )
    language_instruction = (
        GEMINI_AUTO_LANGUAGE_INSTRUCTION
        if language.strip().lower() == LANGUAGE_AUTO
        else f"The expected language is {language}."
    )
    return (
        "Transcribe this meeting audio. Return only JSON with this shape: "
        '{"text":"full transcript","segments":[{"start":0,"end":0,'
        '"text":"segment transcript","speaker":{"label":"1"}}]}. '
        "Use seconds for start and end. "
        f"{language_instruction} {speaker_instruction}"
    )
