"""Markdown transcript generation for meeting audio."""

from importlib.metadata import PackageNotFoundError, version

from meetdown.api import transcribe_file
from meetdown.constants import APP_NAME
from meetdown.json_types import JsonObject
from meetdown.limits import ChunkPlan, plan_auto_chunk, request_limit_seconds
from meetdown.markdown import render_markdown, write_markdown
from meetdown.notion import (
    NotionUploadConfig,
    NotionUploadError,
    notion_upload_status,
    notion_upload_url,
    resolve_notion_upload_config,
    upload_markdown_to_notion,
)
from meetdown.providers import (
    ProviderConfig,
    ProviderError,
    ProviderLimitError,
    ProviderSelectionError,
    default_provider_from_env,
    infer_provider_from_credentials,
    resolve_provider_config,
    transcribe_with_provider,
)
from meetdown.quality import QualityReport, assess_transcript

__all__ = [
    "ChunkPlan",
    "JsonObject",
    "NotionUploadConfig",
    "NotionUploadError",
    "ProviderConfig",
    "ProviderError",
    "ProviderLimitError",
    "ProviderSelectionError",
    "QualityReport",
    "__version__",
    "assess_transcript",
    "default_provider_from_env",
    "infer_provider_from_credentials",
    "notion_upload_status",
    "notion_upload_url",
    "plan_auto_chunk",
    "render_markdown",
    "request_limit_seconds",
    "resolve_notion_upload_config",
    "resolve_provider_config",
    "transcribe_file",
    "transcribe_with_provider",
    "upload_markdown_to_notion",
    "write_markdown",
]

try:
    __version__ = version(APP_NAME)
except PackageNotFoundError:
    __version__ = "0+unknown"
