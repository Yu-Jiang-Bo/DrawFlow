"""Resolve installed fonts by their embedded OpenType names."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import struct
from typing import Any, Iterable


FONT_EXTENSIONS = {".otc", ".otf", ".ttc", ".ttf"}
NAME_IDS = {1, 4, 6, 16, 17}


def default_font_dirs() -> list[Path]:
    configured = os.environ.get("DRAWFLOW_FONT_DIRS", "")
    if configured:
        return [Path(item.strip()) for item in configured.split(";") if item.strip()]
    directories = [Path("C:/Windows/Fonts")]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        directories.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
    return directories


def missing_required_fonts(required: Any, font_dirs: list[Path] | None = None) -> list[str]:
    wanted = _string_list(required)
    if not wanted:
        return []
    installed = installed_font_names(default_font_dirs() if font_dirs is None else font_dirs)
    return [font for font in wanted if normalize_font_name(font) not in installed]


def installed_font_names(font_dirs: Iterable[Path]) -> frozenset[str]:
    snapshot: list[tuple[str, int, int]] = []
    for directory in font_dirs:
        try:
            candidates = list(Path(directory).iterdir())
        except OSError:
            continue
        for path in candidates:
            try:
                if path.is_file() and path.suffix.casefold() in FONT_EXTENSIONS:
                    stat = path.stat()
                    snapshot.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
            except OSError:
                continue
    return _names_for_snapshot(tuple(sorted(snapshot)))


@lru_cache(maxsize=8)
def _names_for_snapshot(snapshot: tuple[tuple[str, int, int], ...]) -> frozenset[str]:
    names: set[str] = set()
    for raw_path, _size, _modified in snapshot:
        path = Path(raw_path)
        names.add(normalize_font_name(path.stem))
        try:
            names.update(normalize_font_name(name) for name in font_names_from_file(path))
        except (OSError, ValueError, struct.error):
            continue
    names.discard("")
    return frozenset(names)


def font_names_from_file(path: Path | str) -> set[str]:
    payload = Path(path).read_bytes()
    offsets = _font_offsets(payload)
    names: set[str] = set()
    for offset in offsets:
        names.update(_font_names_at(payload, offset))
    return names


def normalize_font_name(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _font_offsets(payload: bytes) -> list[int]:
    if payload[:4] != b"ttcf":
        return [0]
    if len(payload) < 12:
        raise ValueError("invalid TrueType collection")
    count = _u32(payload, 8)
    if count <= 0 or count > 1024 or 12 + count * 4 > len(payload):
        raise ValueError("invalid TrueType collection")
    return [_u32(payload, 12 + index * 4) for index in range(count)]


def _font_names_at(payload: bytes, font_offset: int) -> set[str]:
    if font_offset < 0 or font_offset + 12 > len(payload):
        raise ValueError("invalid font offset")
    table_count = _u16(payload, font_offset + 4)
    records_start = font_offset + 12
    if table_count > 4096 or records_start + table_count * 16 > len(payload):
        raise ValueError("invalid font directory")
    name_offset = -1
    name_length = 0
    for index in range(table_count):
        record = records_start + index * 16
        if payload[record : record + 4] == b"name":
            name_offset = _u32(payload, record + 8)
            name_length = _u32(payload, record + 12)
            break
    if name_offset < 0 or name_offset + name_length > len(payload):
        return set()
    return _read_name_table(payload, name_offset, name_length)


def _read_name_table(payload: bytes, offset: int, length: int) -> set[str]:
    if length < 6:
        return set()
    count = _u16(payload, offset + 2)
    strings = offset + _u16(payload, offset + 4)
    records = offset + 6
    if count > 65535 or records + count * 12 > offset + length:
        raise ValueError("invalid font name table")
    names: set[str] = set()
    for index in range(count):
        record = records + index * 12
        platform = _u16(payload, record)
        name_id = _u16(payload, record + 6)
        size = _u16(payload, record + 8)
        relative = _u16(payload, record + 10)
        start = strings + relative
        end = start + size
        if name_id not in NAME_IDS or start < strings or end > offset + length:
            continue
        decoded = _decode_name(payload[start:end], platform).strip("\x00 \t\r\n")
        if decoded:
            names.add(decoded)
    return names


def _decode_name(payload: bytes, platform: int) -> str:
    encoding = "utf-16-be" if platform in {0, 3} else "mac_roman" if platform == 1 else "latin-1"
    return payload.decode(encoding, errors="ignore")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _u16(payload: bytes, offset: int) -> int:
    return struct.unpack_from(">H", payload, offset)[0]


def _u32(payload: bytes, offset: int) -> int:
    return struct.unpack_from(">I", payload, offset)[0]


__all__ = [
    "default_font_dirs",
    "font_names_from_file",
    "installed_font_names",
    "missing_required_fonts",
    "normalize_font_name",
]
