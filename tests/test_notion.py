from pathlib import Path

import pytest

from meetdown.constants import (
    DEFAULT_NOTION_DUPLICATE_STRATEGY,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
)
from meetdown.notion import (
    NotionUploadConfig,
    NotionUploadError,
    resolve_notion_upload_config,
    upload_markdown_to_notion,
)


def test_resolve_notion_upload_config_requires_optional_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("meetdown.notion.notionit_available", lambda: False)

    with pytest.raises(NotionUploadError, match="optional notion extra"):
        resolve_notion_upload_config(parent_page_id="page-id")


def test_resolve_notion_upload_config_requires_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("meetdown.notion.notionit_available", lambda: True)
    monkeypatch.delenv(NOTION_TOKEN_ENV, raising=False)

    with pytest.raises(NotionUploadError, match=NOTION_TOKEN_ENV):
        resolve_notion_upload_config(parent_page_id="page-id")


def test_resolve_notion_upload_config_uses_environment_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("meetdown.notion.notionit_available", lambda: True)
    monkeypatch.setenv(NOTION_TOKEN_ENV, "secret")
    monkeypatch.setenv(NOTION_PARENT_PAGE_ID_ENV, "env-page")

    config = resolve_notion_upload_config()

    assert config == NotionUploadConfig(
        parent_page_id="env-page",
        duplicate_strategy=DEFAULT_NOTION_DUPLICATE_STRATEGY,
    )


def test_upload_markdown_to_notion_calls_quick_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown_path = tmp_path / "meeting.md"
    markdown_path.write_text("# Meeting\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeNotionIt:
        @staticmethod
        def quick_upload(*args: object, **kwargs: object) -> object:
            captured["args"] = args
            captured.update(kwargs)
            return {"ok": True}

    def fake_import_module(name: str) -> object:
        assert name == "notionit"
        return FakeNotionIt

    monkeypatch.setattr("meetdown.notion.import_module", fake_import_module)

    result = upload_markdown_to_notion(
        markdown_path,
        NotionUploadConfig(
            parent_page_id="page-id",
            page_title="Title",
            duplicate_strategy="skip",
        ),
    )

    assert result == {"ok": True}
    assert captured == {
        "args": (str(markdown_path),),
        "parent_page_id": "page-id",
        "page_title": "Title",
        "duplicate_strategy": "skip",
    }
