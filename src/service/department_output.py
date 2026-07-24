"""Resolve the production delivery required by a department and manufacturer.

The Excel requirement sheet is stored in ``config/department_rules.json``.  This
module is deliberately independent of a renderer so every pipeline makes the
same routing decision before it asks Illustrator to create a file.
"""

from __future__ import annotations

import json
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "department_rules.json"

_DEPARTMENT_KEYS = ("department", "production department", "生产部门", "部门")
_MANUFACTURER_KEYS = (
    "manufacturer",
    "factory",
    "supplier",
    "厂家",
    "厂商",
    "生产厂家",
    "供应商",
)
_ORDER_KEYS = ("order_no", "order", "order number", "内部订单号", "订单号")


class DepartmentOutputError(ValueError):
    """A production department cannot be routed safely."""


@dataclass(frozen=True)
class DepartmentOutputRule:
    """One resolved delivery rule from the department configuration."""

    name: str
    department: str
    manufacturer: str
    output_format: str
    layout: Mapping[str, Any]
    per_order: bool = False
    omit_order_label: bool = False
    apply_color_to_artwork: bool = False

    @property
    def extension(self) -> str:
        return ".png" if self.output_format in {"png_master", "png_per_item"} else ".ai"

    @property
    def is_png(self) -> bool:
        return self.extension == ".png"

    @property
    def ai_compatibility(self) -> str:
        return "CS5" if self.output_format == "cs5_ai" else "Illustrator 8"


@dataclass(frozen=True)
class DepartmentDelivery:
    """A single customer-downloadable production file and its source rows."""

    rule: DepartmentOutputRule
    output_name: str
    rows: tuple[Mapping[str, Any], ...]


def normalize_identifier(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def read_department_rules(path: Path | None = None) -> Mapping[str, Any]:
    source = path or CONFIG_PATH
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DepartmentOutputError(f"部门成品规则文件不存在：{source}") from exc
    if not isinstance(data, Mapping):
        raise DepartmentOutputError("部门成品规则不是有效的 JSON 对象")
    return data


def resolve_department_output(
    department: object,
    manufacturer: object = "",
    *,
    rules: Mapping[str, Any] | None = None,
) -> DepartmentOutputRule:
    """Map one order row to its final file type.

    The W rule has precedence over the generic department label rules because
    W's delivery format is selected by manufacturer.  An unmatched department
    remains a whole AI8 delivery, which preserves the legacy safe default.
    """

    config = rules or read_department_rules()
    shop_rules = _mapping(config.get("shop_rules"))
    requirements = shop_rules.get("department_output_requirements")
    if not isinstance(requirements, list):
        raise DepartmentOutputError("部门成品规则缺少 department_output_requirements")

    department_text = str(department or "").strip()
    manufacturer_text = str(manufacturer or "").strip()
    normalized_department = normalize_identifier(department_text)
    matched = _find_requirement(requirements, normalized_department)
    if matched is None:
        return DepartmentOutputRule(
            name="DEFAULT",
            department=department_text,
            manufacturer=manufacturer_text,
            output_format="ai8",
            layout={},
        )

    name = str(matched.get("name") or "DEFAULT")
    output_format = str(matched.get("output_format") or "ai8")
    layout = _mapping(matched.get("layout"))
    if output_format == "manufacturer_specific":
        manufacturer_rule = _find_manufacturer_rule(matched, manufacturer_text)
        output_format = str(manufacturer_rule.get("output_format") or "ai8")
        return DepartmentOutputRule(
            name=name,
            department=department_text,
            manufacturer=manufacturer_text,
            output_format=output_format,
            layout=layout,
            per_order=output_format == "png_per_item",
            omit_order_label=output_format == "png_per_item",
            apply_color_to_artwork=output_format == "cs5_ai",
        )

    return DepartmentOutputRule(
        name=name,
        department=department_text,
        manufacturer=manufacturer_text,
        output_format=output_format,
        layout=layout,
        per_order=name == "D_CONTAINS",
        apply_color_to_artwork=name == "H",
    )


def build_department_deliveries(
    rows: Iterable[Mapping[str, Any]],
    *,
    base_name: str,
    rules: Mapping[str, Any] | None = None,
) -> list[DepartmentDelivery]:
    """Split an input table into download-ready deliveries.

    A delivery never mixes incompatible departments.  D and MY-W120 are
    further split by order, so their mandated one-order/one-graphic output
    cannot accidentally be combined into a whole AI file.
    """

    buckets: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    plans: dict[tuple[str, str, str, str], DepartmentOutputRule] = {}
    for index, row in enumerate(rows, start=1):
        department = _row_value(row, _DEPARTMENT_KEYS)
        manufacturer = _row_value(row, _MANUFACTURER_KEYS)
        order_no = _row_value(row, _ORDER_KEYS) or f"ROW-{index}"
        rule = resolve_department_output(department, manufacturer, rules=rules)
        identity = _delivery_identity(rule, order_no)
        buckets.setdefault(identity, []).append(row)
        plans[identity] = rule

    sequence_by_name: dict[str, int] = {}
    result: list[DepartmentDelivery] = []
    for identity, grouped_rows in buckets.items():
        rule = plans[identity]
        raw_name = _delivery_base_name(base_name, rule, identity[3])
        count = sequence_by_name.get(raw_name, 0) + 1
        sequence_by_name[raw_name] = count
        suffix = "" if count == 1 else f"-{count}"
        result.append(
            DepartmentDelivery(
                rule=rule,
                output_name=f"{raw_name}{suffix}{rule.extension}",
                rows=tuple(grouped_rows),
            )
        )
    return result


def set_png_resolution(path: Path, dpi: int = 300) -> None:
    """Write standard PNG physical-resolution metadata without re-encoding pixels."""

    if int(dpi) <= 0:
        raise DepartmentOutputError("PNG 分辨率必须为正数")
    data = path.read_bytes()
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise DepartmentOutputError(f"不是 PNG 文件，无法写入分辨率：{path.name}")

    pixels_per_meter = int(round(int(dpi) / 0.0254))
    replacement = _png_chunk(b"pHYs", struct.pack(">IIB", pixels_per_meter, pixels_per_meter, 1))
    offset = len(signature)
    chunks: list[bytes] = []
    wrote_phys = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise DepartmentOutputError(f"PNG 数据损坏，无法写入分辨率：{path.name}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise DepartmentOutputError(f"PNG 数据损坏，无法写入分辨率：{path.name}")
        kind = data[offset + 4 : offset + 8]
        chunk = data[offset:end]
        if kind == b"pHYs":
            offset = end
            continue
        chunks.append(chunk)
        if kind == b"IHDR":
            chunks.append(replacement)
            wrote_phys = True
        offset = end
    if not wrote_phys:
        raise DepartmentOutputError(f"PNG 缺少 IHDR，无法写入分辨率：{path.name}")
    path.write_bytes(signature + b"".join(chunks))


def _find_requirement(requirements: list[Any], department: str) -> Mapping[str, Any] | None:
    # Manufacturer-dependent W must win even if configurations are reordered.
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            continue
        if str(requirement.get("name") or "") == "W_CONTAINS" and _matches(requirement, department):
            return requirement
    for requirement in requirements:
        if isinstance(requirement, Mapping) and _matches(requirement, department):
            return requirement
    return None


def _matches(requirement: Mapping[str, Any], department: str) -> bool:
    match = str(requirement.get("match") or "exact").lower()
    candidates = [normalize_identifier(value) for value in requirement.get("departments", [])]
    if match == "contains":
        return any(candidate and candidate in department for candidate in candidates)
    return department in candidates


def _find_manufacturer_rule(requirement: Mapping[str, Any], manufacturer: str) -> Mapping[str, Any]:
    normalized_manufacturer = normalize_identifier(manufacturer)
    fallback: Mapping[str, Any] | None = None
    for item in requirement.get("manufacturer_rules", []):
        if not isinstance(item, Mapping):
            continue
        candidate = str(item.get("manufacturer") or "")
        if candidate.lower() == "other":
            fallback = item
        elif normalize_identifier(candidate) == normalized_manufacturer:
            return item
    if fallback is None:
        raise DepartmentOutputError("W 部门规则缺少 other 厂家兜底输出")
    return fallback


def _delivery_identity(rule: DepartmentOutputRule, order_no: str) -> tuple[str, str, str, str]:
    department = normalize_identifier(rule.department) or "DEFAULT"
    manufacturer = normalize_identifier(rule.manufacturer)
    if rule.name == "W_CONTAINS" and rule.output_format not in {"cs5_ai", "png_per_item"}:
        manufacturer = "OTHER"
    scope = _safe_component(order_no) if rule.per_order else ""
    return rule.name, department, manufacturer, scope


def _delivery_base_name(base_name: str, rule: DepartmentOutputRule, scope: str) -> str:
    pieces = [_safe_component(base_name) or "output", _safe_component(rule.department) or rule.name]
    if rule.output_format == "cs5_ai":
        pieces.append("MY-W196")
    elif rule.output_format == "png_per_item":
        pieces.append(scope or "item")
    elif rule.output_format == "png_master":
        pieces.append("580x2000mm")
    elif rule.per_order:
        pieces.append(scope or "order")
    return "-".join(pieces)


def _row_value(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.casefold())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _safe_component(value: object) -> str:
    text = str(value or "").strip()
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", text).strip("._-")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
