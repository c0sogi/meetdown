from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable, cast

from meetdown.constants import (
    DEFAULT_NOTION_DUPLICATE_STRATEGY,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    NotionDuplicateStrategy,
)
from meetdown import text as ui_text


class NotionUploadError(RuntimeError):
    """Raised when optional Notion upload cannot be prepared or completed."""


@dataclass(frozen=True)
class NotionUploadConfig:
    parent_page_id: str
    page_title: str | None = None
    duplicate_strategy: NotionDuplicateStrategy = DEFAULT_NOTION_DUPLICATE_STRATEGY


def notionit_available() -> bool:
    return importlib.util.find_spec("notionit") is not None


def resolve_notion_upload_config(
    *,
    parent_page_id: str | None = None,
    page_title: str | None = None,
    duplicate_strategy: NotionDuplicateStrategy = DEFAULT_NOTION_DUPLICATE_STRATEGY,
) -> NotionUploadConfig:
    if not notionit_available():
        raise NotionUploadError(ui_text.notion_extra_missing())
    if not os.getenv(NOTION_TOKEN_ENV):
        raise NotionUploadError(ui_text.notion_missing_token())

    resolved_parent = parent_page_id or os.getenv(NOTION_PARENT_PAGE_ID_ENV)
    if not resolved_parent:
        raise NotionUploadError(ui_text.notion_missing_parent_page())

    return NotionUploadConfig(
        parent_page_id=resolved_parent,
        page_title=page_title,
        duplicate_strategy=duplicate_strategy,
    )


def upload_markdown_to_notion(
    markdown_path: str | Path, config: NotionUploadConfig
) -> object:
    try:
        notionit_module = import_module("notionit")
    except ImportError as exc:
        raise NotionUploadError(ui_text.notion_extra_missing()) from exc
    quick_upload = cast(Callable[..., object], getattr(notionit_module, "quick_upload"))

    try:
        return quick_upload(
            str(markdown_path),
            parent_page_id=config.parent_page_id,
            page_title=config.page_title,
            duplicate_strategy=config.duplicate_strategy,
        )
    except Exception as exc:
        raise NotionUploadError(ui_text.notion_upload_failed(exc)) from exc
