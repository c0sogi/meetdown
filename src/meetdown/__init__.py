"""Markdown transcript generation for meeting audio."""

from importlib.metadata import PackageNotFoundError, version

from meetdown.api import transcribe_file
from meetdown.constants import APP_NAME
from meetdown.json_types import JsonObject
from meetdown.markdown import render_markdown, write_markdown
from meetdown.notion import (
    NotionUploadConfig,
    NotionUploadError,
    resolve_notion_upload_config,
    upload_markdown_to_notion,
)
from meetdown.providers import (
    ProviderConfig,
    ProviderError,
    infer_provider_from_credentials,
    resolve_provider_config,
    transcribe_with_provider,
)

__all__ = [
    "JsonObject",
    "NotionUploadConfig",
    "NotionUploadError",
    "ProviderConfig",
    "ProviderError",
    "__version__",
    "infer_provider_from_credentials",
    "render_markdown",
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
