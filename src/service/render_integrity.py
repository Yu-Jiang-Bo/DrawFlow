"""Deterministic comparison for Illustrator's internal PNG render previews."""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


class RenderIntegrityError(RuntimeError):
    """Raised when a render preview cannot be compared safely."""


@dataclass(frozen=True)
class PreviewDigest:
    path: str
    width: int
    height: int
    color_type: int
    pixel_hash: str


@dataclass(frozen=True)
class PreviewComparison:
    left: PreviewDigest
    right: PreviewDigest
    equal: bool
    differing_pixels: int

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def compare_png_previews(left_path: Path, right_path: Path) -> PreviewComparison:
    """Compare decoded 8-bit RGB/RGBA previews, never compressed PNG bytes."""

    left = _read_png(left_path)
    right = _read_png(right_path)
    left_digest = PreviewDigest(
        path=str(left_path),
        width=left.width,
        height=left.height,
        color_type=left.color_type,
        pixel_hash=hashlib.sha256(left.pixels).hexdigest(),
    )
    right_digest = PreviewDigest(
        path=str(right_path),
        width=right.width,
        height=right.height,
        color_type=right.color_type,
        pixel_hash=hashlib.sha256(right.pixels).hexdigest(),
    )
    if (left.width, left.height, left.color_type) != (right.width, right.height, right.color_type):
        return PreviewComparison(left_digest, right_digest, False, max(left.width * left.height, right.width * right.height))
    if left_digest.pixel_hash == right_digest.pixel_hash:
        return PreviewComparison(left_digest, right_digest, True, 0)

    channels = _channels(left.color_type)
    differing_pixels = sum(
        any(left.pixels[offset + channel] != right.pixels[offset + channel] for channel in range(channels))
        for offset in range(0, len(left.pixels), channels)
    )
    return PreviewComparison(left_digest, right_digest, False, differing_pixels)


@dataclass(frozen=True)
class _DecodedPng:
    width: int
    height: int
    color_type: int
    pixels: bytes


def _read_png(path: Path) -> _DecodedPng:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RenderIntegrityError(f"无法读取渲染预览：{path.name}") from exc
    if not data.startswith(PNG_SIGNATURE):
        raise RenderIntegrityError(f"渲染预览不是 PNG：{path.name}")

    width = height = bit_depth = color_type = interlace = None
    idat: list[bytes] = []
    for kind, payload in _png_chunks(data):
        if kind == b"IHDR":
            if len(payload) != 13:
                raise RenderIntegrityError(f"PNG 头损坏：{path.name}")
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filter_method != 0:
                raise RenderIntegrityError(f"PNG 编码不受支持：{path.name}")
        elif kind == b"IDAT":
            idat.append(payload)
    if not width or not height or bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise RenderIntegrityError(f"PNG 格式不受支持：{path.name}")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise RenderIntegrityError(f"PNG 像素数据损坏：{path.name}") from exc
    channels = _channels(color_type)
    stride = width * channels
    expected_length = (stride + 1) * height
    if len(raw) != expected_length:
        raise RenderIntegrityError(f"PNG 像素尺寸不匹配：{path.name}")
    return _DecodedPng(width, height, color_type, _unfilter(raw, stride, channels, height))


def _png_chunks(data: bytes) -> Iterable[tuple[bytes, bytes]]:
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        if offset + 12 > len(data):
            raise RenderIntegrityError("PNG 分块截断")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        end = offset + 8 + length
        if end + 4 > len(data):
            raise RenderIntegrityError("PNG 分块长度异常")
        yield kind, data[offset + 8 : end]
        offset = end + 4


def _channels(color_type: int) -> int:
    return 3 if color_type == 2 else 4


def _unfilter(raw: bytes, stride: int, channels: int, height: int) -> bytes:
    result = bytearray(stride * height)
    raw_offset = 0
    for row_index in range(height):
        filter_type = raw[raw_offset]
        raw_offset += 1
        row_start = row_index * stride
        previous_start = row_start - stride
        for column in range(stride):
            value = raw[raw_offset + column]
            left = result[row_start + column - channels] if column >= channels else 0
            up = result[previous_start + column] if row_index else 0
            upper_left = result[previous_start + column - channels] if row_index and column >= channels else 0
            if filter_type == 0:
                decoded = value
            elif filter_type == 1:
                decoded = (value + left) & 0xFF
            elif filter_type == 2:
                decoded = (value + up) & 0xFF
            elif filter_type == 3:
                decoded = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                decoded = (value + _paeth(left, up, upper_left)) & 0xFF
            else:
                raise RenderIntegrityError(f"PNG 使用未知过滤器：{filter_type}")
            result[row_start + column] = decoded
        raw_offset += stride
    return bytes(result)


def _paeth(left: int, up: int, upper_left: int) -> int:
    prediction = left + up - upper_left
    left_distance = abs(prediction - left)
    up_distance = abs(prediction - up)
    upper_left_distance = abs(prediction - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left
