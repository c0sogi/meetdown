from typing import cast

JsonObject = dict[str, object]


def as_json_object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        return None
    return cast(JsonObject, raw)


def require_json_object(value: object, message: str) -> JsonObject:
    result = as_json_object(value)
    if result is None:
        raise ValueError(message)
    return result


def as_object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def as_number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None
