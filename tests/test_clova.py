from meetdown.clova import DEFAULT_PARAMS, build_upload_url, merge_params
from meetdown.json_types import as_json_object


def test_build_upload_url_appends_endpoint() -> None:
    assert (
        build_upload_url("https://example.com")
        == "https://example.com/recognizer/upload"
    )


def test_build_upload_url_keeps_complete_endpoint() -> None:
    url = "https://example.com/recognizer/upload"
    assert build_upload_url(url) == url


def test_merge_params_preserves_nested_defaults() -> None:
    merged = merge_params(DEFAULT_PARAMS, {"diarization": {"enable": False}})

    assert merged["language"] == "ko-KR"
    assert merged["completion"] == "sync"
    diarization = as_json_object(merged["diarization"])
    assert diarization is not None
    assert diarization["enable"] is False
