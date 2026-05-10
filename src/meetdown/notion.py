import importlib.util
import os
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable, cast

from meetdown import text as ui_text
from meetdown.constants import (
    DEFAULT_NOTION_DUPLICATE_STRATEGY,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    NotionDuplicateStrategy,
)
from meetdown.json_types import as_json_object, as_object_list


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


def notion_upload_url(result: object) -> str | None:
    result_object = as_json_object(result)
    if result_object is not None:
        for key in ("url", "public_url"):
            value = result_object.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    result_items = as_object_list(result)
    if result_items is not None:
        for item in result_items:
            url = notion_upload_url(item)
            if url is not None:
                return url
    return None


def notion_upload_status(result: object) -> str | None:
    result_object = as_json_object(result)
    if result_object is not None:
        status = result_object.get("status")
        return status if isinstance(status, str) and status else None

    result_items = as_object_list(result)
    if result_items is not None:
        for item in result_items:
            status = notion_upload_status(item)
            if status is not None:
                return status
    return None
