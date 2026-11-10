from typing import Final, Literal

ProviderName = Literal["clova", "openai", "gemini"]
ProviderSource = Literal["option", "environment", "credentials"]
NotionDuplicateStrategy = Literal[
    "ask", "timestamp", "counter", "create_anyway", "skip"
]

APP_NAME: Final = "meetdown"
LANGUAGE_AUTO: Final = "auto"
DEFAULT_LANGUAGE: Final = LANGUAGE_AUTO
DEFAULT_OUTPUT_PATH: Final = "meeting.md"
DEFAULT_TITLE: Final = "Meeting Transcript"
DEFAULT_TIMEOUT_SECONDS: Final = 3600.0
DEFAULT_WORD_ALIGNMENT: Final = False
DEFAULT_DIARIZATION: Final = True
DEFAULT_NOTION_DUPLICATE_STRATEGY: Final[NotionDuplicateStrategy] = "timestamp"
TEMP_DIR_PREFIX: Final = "meetdown-"

PROVIDER_CLOVA: Final[ProviderName] = "clova"
PROVIDER_OPENAI: Final[ProviderName] = "openai"
PROVIDER_GEMINI: Final[ProviderName] = "gemini"
SUPPORTED_PROVIDERS: Final[tuple[ProviderName, ...]] = (
    PROVIDER_CLOVA,
    PROVIDER_OPENAI,
    PROVIDER_GEMINI,
)

CLOVA_MODEL_DESCRIPTION: Final = (
    "CLOVA Speech domain model (not configurable by --model)"
)
OPENAI_DEFAULT_MODEL: Final = "gpt-4o-transcribe-diarize"
OPENAI_DEFAULT_NO_DIARIZATION_MODEL: Final = "gpt-transcribe"
OPENAI_DEFAULT_API_URL: Final = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_AUDIO_TRANSCRIPTIONS_PATH: Final = "/audio/transcriptions"
OPENAI_DIARIZATION_MODEL_MARKER: Final = "diarize"
OPENAI_WHISPER_MODEL: Final = "whisper-1"
GEMINI_DEFAULT_MODEL: Final = "gemini-3-flash-preview"
GEMINI_DEFAULT_API_URL: Final = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_GENERATE_CONTENT_SUFFIX: Final = ":generateContent"
GEMINI_INLINE_LIMIT_BYTES: Final = 19 * 1024 * 1024
OPENAI_MAX_UPLOAD_BYTES: Final = 25 * 1024 * 1024
# gpt-4o-transcribe-diarize rejects longer audio; whisper-1 only has the size limit.
OPENAI_MAX_AUDIO_SECONDS: Final = 1400.0
OPENAI_PREFERRED_CHUNK_SECONDS: Final = 600.0
GEMINI_PREFERRED_CHUNK_SECONDS: Final = 1200.0
LIMIT_RETRY_CHUNK_SECONDS: Final = 600.0
AUTO_CHUNK_SAFETY_RATIO: Final = 0.9
MIN_AUTO_CHUNK_SECONDS: Final = 60.0

CLOVA_SPEECH_INVOKE_URL_ENV: Final = "CLOVA_SPEECH_INVOKE_URL"
CLOVA_SPEECH_SECRET_KEY_ENV: Final = "CLOVA_SPEECH_SECRET_KEY"
OPENAI_API_KEY_ENV: Final = "OPENAI_API_KEY"
OPENAI_API_URL_ENV: Final = "OPENAI_API_URL"
OPENAI_BASE_URL_ENV: Final = "OPENAI_BASE_URL"
GEMINI_API_KEY_ENV: Final = "GEMINI_API_KEY"
GEMINI_API_URL_ENV: Final = "GEMINI_API_URL"
GOOGLE_API_KEY_ENV: Final = "GOOGLE_API_KEY"
GOOGLE_API_URL_ENV: Final = "GOOGLE_API_URL"
MEETDOWN_API_KEY_ENV: Final = "MEETDOWN_API_KEY"
MEETDOWN_API_URL_ENV: Final = "MEETDOWN_API_URL"
MEETDOWN_PROVIDER_ENV: Final = "MEETDOWN_PROVIDER"
NOTION_TOKEN_ENV: Final = "NOTION_TOKEN"
NOTION_PARENT_PAGE_ID_ENV: Final = "NOTION_PARENT_PAGE_ID"
PROVIDER_ENV_NAMES: Final[tuple[str, ...]] = (
    CLOVA_SPEECH_INVOKE_URL_ENV,
    CLOVA_SPEECH_SECRET_KEY_ENV,
    OPENAI_API_KEY_ENV,
    OPENAI_API_URL_ENV,
    OPENAI_BASE_URL_ENV,
    GEMINI_API_KEY_ENV,
    GEMINI_API_URL_ENV,
    GOOGLE_API_KEY_ENV,
    GOOGLE_API_URL_ENV,
    MEETDOWN_API_KEY_ENV,
    MEETDOWN_API_URL_ENV,
    MEETDOWN_PROVIDER_ENV,
)

CLOVA_AUTO_DETECT_API_KEY_ENV_NAMES: Final = (CLOVA_SPEECH_SECRET_KEY_ENV,)
OPENAI_AUTO_DETECT_API_KEY_ENV_NAMES: Final = (OPENAI_API_KEY_ENV,)
GEMINI_AUTO_DETECT_API_KEY_ENV_NAMES: Final = (
    GEMINI_API_KEY_ENV,
    GOOGLE_API_KEY_ENV,
)

CLOVA_API_KEY_ENV_NAMES: Final = (CLOVA_SPEECH_SECRET_KEY_ENV, MEETDOWN_API_KEY_ENV)
CLOVA_API_URL_ENV_NAMES: Final = (CLOVA_SPEECH_INVOKE_URL_ENV, MEETDOWN_API_URL_ENV)
OPENAI_API_KEY_ENV_NAMES: Final = (OPENAI_API_KEY_ENV, MEETDOWN_API_KEY_ENV)
OPENAI_API_URL_ENV_NAMES: Final = (
    OPENAI_API_URL_ENV,
    OPENAI_BASE_URL_ENV,
    MEETDOWN_API_URL_ENV,
)
GEMINI_API_KEY_ENV_NAMES: Final = (
    GEMINI_API_KEY_ENV,
    GOOGLE_API_KEY_ENV,
    MEETDOWN_API_KEY_ENV,
)
GEMINI_API_URL_ENV_NAMES: Final = (
    GEMINI_API_URL_ENV,
    GOOGLE_API_URL_ENV,
    MEETDOWN_API_URL_ENV,
)
AUTO_DETECT_API_KEY_ENV_NAMES: Final = (
    CLOVA_SPEECH_SECRET_KEY_ENV,
    OPENAI_API_KEY_ENV,
    GEMINI_API_KEY_ENV,
    GOOGLE_API_KEY_ENV,
)

CLOVA_UPLOAD_ENDPOINT: Final = "/recognizer/upload"
CLOVA_API_KEY_HEADER_NAME: Final = "X-CLOVASPEECH-API-KEY"
CLOVA_COMPLETION_SYNC: Final = "sync"
CLOVA_DEFAULT_LANGUAGE: Final = "ko-KR"
CLOVA_SUPPORTED_LANGUAGES: Final = ("ko-KR", "ja", "en-US", "enko", "zh-cn", "zh-tw")

COMPRESS_SMALLEST: Final = "smallest"
COMPRESS_LOSSLESS: Final = "lossless"
COMPRESS_NONE: Final = "none"
COMPRESSION_PRESETS: Final = (COMPRESS_SMALLEST, COMPRESS_LOSSLESS, COMPRESS_NONE)
DEFAULT_COMPRESS: Final = COMPRESS_SMALLEST
COMPRESSION_UPLOAD_FORMATS: Final[dict[str, str]] = {
    COMPRESS_SMALLEST: "mp3",
    COMPRESS_LOSSLESS: "flac",
    COMPRESS_NONE: "wav",
}

CHUNK_FORMAT_FLAC: Final = "flac"
CHUNK_FORMAT_MP3: Final = "mp3"
CHUNK_FORMAT_WAV: Final = "wav"
CHUNK_FORMAT_CHOICES: Final = (CHUNK_FORMAT_FLAC, CHUNK_FORMAT_MP3, CHUNK_FORMAT_WAV)
# Upper bounds for 16 kHz mono uploads: mp3 at 64 kbps, FLAC never above PCM, PCM WAV.
UPLOAD_BYTES_PER_SECOND: Final[dict[str, int]] = {
    CHUNK_FORMAT_MP3: 8_000,
    CHUNK_FORMAT_FLAC: 32_000,
    CHUNK_FORMAT_WAV: 32_000,
}

CHUNKING_SOURCE_OPTION: Final = "option"
CHUNKING_SOURCE_AUTO: Final = "auto"
CHUNKING_SOURCE_RETRY: Final = "retry"

ERROR_PROVIDER_AMBIGUOUS: Final = "provider_ambiguous"
ERROR_PROVIDER_NOT_CONFIGURED: Final = "provider_not_configured"
ERROR_PROVIDER_INVALID_DEFAULT: Final = "provider_invalid_default"
ERROR_PROVIDER_CREDENTIALS_MISSING: Final = "provider_credentials_missing"
ERROR_PROVIDER_LIMIT: Final = "provider_limit"
ERROR_PROVIDER_FAILED: Final = "provider_error"
ERROR_MEDIA: Final = "media_error"
ERROR_INPUT_NOT_FOUND: Final = "input_not_found"
ERROR_NOTION: Final = "notion_error"
ERROR_INVALID_OPTION: Final = "invalid_option"

NOTION_DUPLICATE_STRATEGIES: Final[tuple[NotionDuplicateStrategy, ...]] = (
    "ask",
    "timestamp",
    "counter",
    "create_anyway",
    "skip",
)

PROVIDER_API_KEY_PLACEHOLDERS: Final[dict[ProviderName, str]] = {
    PROVIDER_CLOVA: "<CLOVA Secret Key>",
    PROVIDER_OPENAI: "<OpenAI API key>",
    PROVIDER_GEMINI: "<Gemini API key>",
}
GENERIC_API_KEY_PLACEHOLDER: Final = "<API key>"

PROCESSING_REPLAY_COMMAND_KEY: Final = "replay_command"
PROVIDER_USAGES_KEY: Final = "provider_usages"

COLOR_ENV: Final = "MEETDOWN_COLOR"
NO_COLOR_ENV: Final = "NO_COLOR"
TERM_ENV: Final = "TERM"
TERM_DUMB_VALUE: Final = "dumb"
COLOR_ALWAYS_VALUES: Final = frozenset({"1", "always", "true", "yes", "on"})
COLOR_NEVER_VALUES: Final = frozenset({"0", "never", "false", "no", "off"})

ANSI_RESET: Final = "\033[0m"
ANSI_BOLD: Final = "\033[1m"
ANSI_DIM: Final = "\033[2m"
ANSI_GREEN: Final = "\033[32m"
ANSI_YELLOW: Final = "\033[33m"
ANSI_BLUE: Final = "\033[34m"
ANSI_MAGENTA: Final = "\033[35m"
ANSI_CYAN: Final = "\033[36m"
