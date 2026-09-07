"""Shared V2 content-preset parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


_LETTER_RE = re.compile(r"^[A-Za-z]$")


@dataclass(frozen=True)
class InitialWithText:
    initial: str
    text: str


class V2ContentPresetError(ValueError):
    """Raised when order content cannot be resolved without guessing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_initial_with_text(
    *,
    asset_value: object,
    text_value: object,
    asset_field: str = "",
    text_field: str = "",
) -> InitialWithText:
    """Resolve one decorative initial plus body text.

    Separate asset/text fields use the asset value when present; otherwise the
    body text is parsed with the combined-field rules.
    """

    asset_text = _clean(asset_value)
    body_text = _clean(text_value)
    if asset_field and text_field and asset_field != text_field:
        if asset_text:
            if not _single_letter(asset_text):
                raise V2ContentPresetError("initial_asset_invalid", "首字母字段必须是单个英文字母。")
            if not body_text:
                raise V2ContentPresetError("initial_text_missing", "首字母素材加正文缺少正文内容。")
            return InitialWithText(asset_text.upper(), body_text)
        return _parse_combined_initial_text(body_text)
    return _parse_combined_initial_text(body_text or asset_text)


def resolve_multi_initials(values: Sequence[object], expected_count: int) -> list[str]:
    """Resolve ordered decorative initials for several asset slots."""

    if expected_count <= 0:
        raise V2ContentPresetError("multi_initial_count_invalid", "多首字母槽位数量无效。")
    cleaned = [_clean(value) for value in values]
    if len(cleaned) == 1:
        return _parse_multi_initial_value(cleaned[0], expected_count)
    if len(cleaned) != expected_count or any(not value for value in cleaned):
        raise V2ContentPresetError("multi_initial_count_mismatch", "多首字母内容数量与素材槽位数量不一致。")
    return [_initial_from_name(value) for value in cleaned]


def match_supported_asset_value(value: str, supported_values: Iterable[object]) -> str:
    """Return the exact supported asset key for a resolved initial."""

    requested = _clean(value).upper()
    supported = [_clean(item) for item in supported_values if _clean(item)]
    if not supported:
        raise V2ContentPresetError("asset_supported_values_missing", "素材库支持范围尚未确认。")
    by_upper = {item.upper(): item for item in supported}
    if requested not in by_upper:
        raise V2ContentPresetError("asset_value_missing", f"素材库缺少字母 {requested}。")
    return by_upper[requested]


def _parse_combined_initial_text(value: str) -> InitialWithText:
    if not value:
        raise V2ContentPresetError("initial_content_missing", "首字母素材加正文缺少内容。")
    if "|" not in value:
        return InitialWithText(_initial_from_name(value), value)
    parts = [_clean(part) for part in value.split("|")]
    parts = [part for part in parts if part]
    if len(parts) != 2:
        raise V2ContentPresetError("initial_content_part_count", "首字母素材加正文必须提供一个正文和一个首字母，或只提供正文。")
    single_indexes = [index for index, part in enumerate(parts) if _single_letter(part)]
    if len(single_indexes) != 1:
        raise V2ContentPresetError("initial_content_ambiguous", "首字母内容无法唯一判断，请只提供一个完整单字母段。")
    initial_index = single_indexes[0]
    body_index = 1 - initial_index
    body = parts[body_index]
    if _single_letter(body):
        raise V2ContentPresetError("initial_content_ambiguous", "首字母和正文均为单字母，无法唯一判断。")
    return InitialWithText(parts[initial_index].upper(), body)


def _parse_multi_initial_value(value: str, expected_count: int) -> list[str]:
    if not value:
        raise V2ContentPresetError("multi_initial_content_missing", "多首字母内容为空。")
    if "|" in value:
        parts = [_clean(part) for part in value.split("|")]
        if len(parts) != expected_count or any(not part for part in parts):
            raise V2ContentPresetError("multi_initial_count_mismatch", "多首字母内容数量与素材槽位数量不一致。")
        return [_initial_from_name(part) for part in parts]
    if len(value) == expected_count and value.upper() == value and value.isalpha():
        return [char.upper() for char in value]
    if expected_count == 1:
        return [_initial_from_name(value)]
    raise V2ContentPresetError("multi_initial_count_mismatch", "多首字母内容数量与素材槽位数量不一致。")


def _initial_from_name(value: str) -> str:
    text = _clean(value)
    if not text:
        raise V2ContentPresetError("initial_content_missing", "首字母内容为空。")
    for char in text:
        if char.isalpha():
            return char.upper()
    raise V2ContentPresetError("initial_content_invalid", "首字母内容必须包含英文字母。")


def _single_letter(value: str) -> bool:
    return bool(_LETTER_RE.match(_clean(value)))


def _clean(value: object) -> str:
    return str(value or "").strip()


__all__ = [
    "InitialWithText",
    "V2ContentPresetError",
    "match_supported_asset_value",
    "resolve_initial_with_text",
    "resolve_multi_initials",
]
