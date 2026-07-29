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

ANNOTATION_COLOR = "COLOR"
ANNOTATION_PRODUCT_NAME = "PRODUCT_NAME"

EXPORT_UNIT_PER_ORDER = "PER_ORDER"
EXPORT_UNIT_PER_GRAPHIC = "PER_GRAPHIC"

FILE_FORMAT_AI8 = "AI8"
FILE_FORMAT_AI_CS5 = "AI_CS5"
FILE_FORMAT_AI_STANDARD = "AI_STANDARD"
FILE_FORMAT_PNG_CMYK = "PNG_CMYK"

DEPARTMENT_SPECS: Mapping[str, Mapping[str, Any]] = {
    "T": {
        "departments": ("T",),
        "exportUnit": EXPORT_UNIT_PER_ORDER,
        "fileFormat": FILE_FORMAT_AI8,
        "fillActualColor": False,
        "annotation_type": ANNOTATION_COLOR,
        "single_order_ai": True,
        "hasMaster": True,
        "cropMasterHeight": True,
        "master_group_by_color": True,
        "master_frame_width_mm": 580.0,
        "master_frame_height_mm": 2000.0,
    },
    "K": {
        "departments": ("K",),
        "exportUnit": EXPORT_UNIT_PER_ORDER,
        "fileFormat": FILE_FORMAT_AI8,
        "fillActualColor": False,
        "annotation_type": ANNOTATION_COLOR,
        "single_order_ai": True,
        "hasMaster": True,
        "cropMasterHeight": True,
        "master_group_by_color": True,
        "master_frame_width_mm": 480.0,
        "master_frame_height_mm": 2000.0,
    },
    "ZK_FK": {
        "departments": ("ZK", "FK"),
        "exportUnit": EXPORT_UNIT_PER_ORDER,
        "fileFormat": FILE_FORMAT_AI8,
        "fillActualColor": False,
        "annotation_type": ANNOTATION_COLOR,
        "single_order_ai": True,
        "hasMaster": True,
        "cropMasterHeight": True,
        "master_group_by_color": True,
        "master_frame_width_mm": 450.0,
        "master_frame_height_mm": 2000.0,
    },
    "PW_EW": {
        "departments": ("PW", "EW"),
        "exportUnit": EXPORT_UNIT_PER_ORDER,
        "fileFormat": FILE_FORMAT_AI8,
        "fillActualColor": False,
        "annotation_type": ANNOTATION_PRODUCT_NAME,
        "single_order_ai": True,
        "hasMaster": True,
        "cropMasterHeight": False,
        "master_group_by_color": False,
        "master_frame_width_mm": None,
        "master_frame_height_mm": None,
    },
    "D_CONTAINS": {
        "match": "contains",
        "departments": ("D",),
        "exportUnit": EXPORT_UNIT_PER_ORDER,
        "fileFormat": FILE_FORMAT_AI8,
        "fillActualColor": False,
        "annotation_type": ANNOTATION_PRODUCT_NAME,
        "single_order_ai": True,
        "hasMaster": False,
        "cropMasterHeight": False,
        "master_group_by_color": False,
        "master_frame_width_mm": None,
        "master_frame_height_mm": None,
    },
}
DEPARTMENT_CONFIG = DEPARTMENT_SPECS

_COLOR_TRANSLATIONS = {
    "RED": "红色",
    "BLACK": "黑色",
    "WHITE": "白色",
    "GOLD": "金色",
    "SILVER": "银色",
    "ROSEGOLD": "玫瑰金",
    "BLUE": "蓝色",
    "NAVY": "藏蓝色",
    "PINK": "粉色",
    "DARKGREEN": "深绿色",
    "GREEN": "绿色",
    "PURPLE": "紫色",
    "YELLOW": "黄色",
    "ORANGE": "橙色",
    "GRAY": "灰色",
    "GREY": "灰色",
}

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
    export_unit: str = EXPORT_UNIT_PER_ORDER
    file_format: str = FILE_FORMAT_AI8
    per_order: bool = False
    omit_order_label: bool = False
    apply_color_to_artwork: bool = False
    fill_actual_color: bool = False
    annotation_type: str = ANNOTATION_COLOR
    single_order_ai: bool = False
    has_master: bool = True
    crop_master_height: bool = False
    master_group_by_color: bool = False
    master_frame_width_mm: float | None = None
    master_frame_height_mm: float | None = None

    @property
    def extension(self) -> str:
        return ".png" if self.is_png else ".ai"

    @property
    def is_png(self) -> bool:
        return self.file_format == FILE_FORMAT_PNG_CMYK or self.output_format in {"png_master", "png_per_item", "png_cmyk"}

    @property
    def ai_compatibility(self) -> str:
        if self.file_format == FILE_FORMAT_AI_CS5 or self.output_format == "cs5_ai":
            return "CS5"
        if self.file_format == FILE_FORMAT_AI_STANDARD or self.output_format == "ai_standard":
            return FILE_FORMAT_AI_STANDARD
        return "Illustrator 8"


@dataclass(frozen=True)
class DepartmentDelivery:
    """A single customer-downloadable production file and its source rows."""

    rule: DepartmentOutputRule
    output_name: str
    rows: tuple[Mapping[str, Any], ...]


def normalize_identifier(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def is_department_d(dept_name: object) -> bool:
    return "D" in normalize_identifier(dept_name)


def translate_color_to_chinese(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return text
    return _COLOR_TRANSLATIONS.get(normalize_identifier(text), text)


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
    output_format = _normalized_output_format(matched)
    layout = _mapping(matched.get("layout"))
    config_defaults = _mapping(DEPARTMENT_SPECS.get(name))
    if output_format == "manufacturer_specific":
        manufacturer_rule = _find_manufacturer_rule(matched, manufacturer_text)
        output_format = _normalized_output_format(manufacturer_rule)
        file_format = _resolved_file_format(manufacturer_rule, output_format)
        export_unit = _resolved_export_unit(manufacturer_rule, matched)
        layout = {**layout, **_mapping(manufacturer_rule.get("layout"))}
        fill_actual_color = _resolved_bool(
            manufacturer_rule,
            matched,
            primary_keys=("fillActualColor", "fill_actual_color", "apply_color_to_artwork"),
            fallback=output_format == "cs5_ai",
        )
        has_master = _resolved_bool(
            manufacturer_rule,
            matched,
            primary_keys=("hasMaster", "has_master"),
            fallback=False,
        )
        return DepartmentOutputRule(
            name=name,
            department=department_text,
            manufacturer=manufacturer_text,
            output_format=output_format,
            export_unit=export_unit,
            file_format=file_format,
            layout=layout,
            omit_order_label=_resolved_bool(
                manufacturer_rule,
                matched,
                primary_keys=("omitOrderLabel", "omit_order_label"),
                fallback=False,
            ),
            per_order=_resolved_bool(
                manufacturer_rule,
                matched,
                primary_keys=("perOrder", "per_order", "single_order_ai"),
                fallback=export_unit == EXPORT_UNIT_PER_ORDER
                and output_format not in {"png_cmyk", "png_per_item"}
                and not has_master,
            ),
            apply_color_to_artwork=fill_actual_color,
            fill_actual_color=fill_actual_color,
            has_master=has_master,
            crop_master_height=_resolved_bool(
                manufacturer_rule,
                matched,
                primary_keys=("cropMasterHeight", "crop_master_height"),
                fallback=False,
            ),
            master_frame_width_mm=_resolved_float(
                manufacturer_rule,
                matched,
                primary_keys=("master_frame_width_mm", "masterFrameWidthMm"),
                fallback=_positive_float(layout.get("frame_width_mm"), layout.get("target_width_mm")),
            ),
            master_frame_height_mm=_resolved_float(
                manufacturer_rule,
                matched,
                primary_keys=("master_frame_height_mm", "masterFrameHeightMm"),
                fallback=_positive_float(layout.get("frame_height_mm"), layout.get("target_height_mm")),
            ),
        )

    file_format = _resolved_file_format(matched, output_format)
    export_unit = _resolved_export_unit(matched, config_defaults)
    fill_actual_color = _resolved_bool(
        matched,
        config_defaults,
        primary_keys=("fillActualColor", "fill_actual_color", "apply_color_to_artwork"),
        fallback=name == "H",
    )
    return DepartmentOutputRule(
        name=name,
        department=department_text,
        manufacturer=manufacturer_text,
        output_format=output_format,
        export_unit=export_unit,
        file_format=file_format,
        layout=layout,
        apply_color_to_artwork=fill_actual_color,
        fill_actual_color=fill_actual_color,
        annotation_type=str(_setting(matched, config_defaults, "annotation_type", ANNOTATION_COLOR)),
        single_order_ai=_bool_setting(matched, config_defaults, "single_order_ai", False),
        has_master=_resolved_bool(
            matched,
            config_defaults,
            primary_keys=("hasMaster", "has_master"),
            fallback=True,
        ),
        crop_master_height=_resolved_bool(
            matched,
            config_defaults,
            primary_keys=("cropMasterHeight", "crop_master_height"),
            fallback=bool(layout.get("crop_master_height")),
        ),
        master_group_by_color=_bool_setting(
            matched,
            config_defaults,
            "master_group_by_color",
            bool(layout.get("group_by_color")),
        ),
        master_frame_width_mm=_float_setting(
            matched.get("master_frame_width_mm"),
            layout.get("frame_width_mm"),
            config_defaults.get("master_frame_width_mm"),
        ),
        master_frame_height_mm=_float_setting(
            matched.get("master_frame_height_mm"),
            layout.get("frame_height_mm"),
            config_defaults.get("master_frame_height_mm"),
        ),
    )


def build_department_deliveries(
    rows: Iterable[Mapping[str, Any]],
    *,
    base_name: str,
    rules: Mapping[str, Any] | None = None,
) -> list[DepartmentDelivery]:
    """Split an input table into download-ready deliveries.

    A delivery never mixes incompatible departments.  MY-W120 is further split
    by order item, while reusable single-order AI output is handled by the
    202508 renderer before any optional master delivery is created.
    """

    buckets: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    plans: dict[tuple[str, str, str, str], DepartmentOutputRule] = {}
    for index, row in enumerate(rows, start=1):
        department = _row_value(row, _DEPARTMENT_KEYS)
        manufacturer = _row_value(row, _MANUFACTURER_KEYS)
        order_no = _row_value(row, _ORDER_KEYS) or f"ROW-{index}"
        rule = resolve_department_output(department, manufacturer, rules=rules)
        identity = (
            rule.name,
            normalize_identifier(rule.department) or "DEFAULT",
            normalize_identifier(rule.manufacturer),
            f"{order_no}|{index}",
        ) if rule.export_unit == EXPORT_UNIT_PER_GRAPHIC else _delivery_identity(rule, order_no)
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


def finalize_cmyk_png(path: Path, *, dpi: int = 300, color_mode: str = "CMYK") -> None:
    """Finalize a production PNG that was rendered from a CMYK Illustrator document."""

    if str(color_mode or "").strip().upper() != "CMYK":
        raise DepartmentOutputError(f"PNG 成品必须使用 CMYK 色彩模式配置：{path.name}")
    set_png_resolution(path, dpi)


def _find_requirement(requirements: list[Any], department: str) -> Mapping[str, Any] | None:
    # Exact department families such as PW/EW must win before broad contains
    # rules; then manufacturer-dependent W wins over other contains rules.
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            continue
        if str(requirement.get("match") or "exact").lower() == "exact" and _matches(requirement, department):
            return requirement
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
    if str(requirement.get("name") or "") == "D_CONTAINS":
        return is_department_d(department)
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
    if rule.name == "W_CONTAINS" and rule.file_format not in {FILE_FORMAT_AI_CS5, FILE_FORMAT_PNG_CMYK}:
        manufacturer = "OTHER"
    scope = _safe_component(order_no) if rule.per_order else ""
    return rule.name, department, manufacturer, scope


def _delivery_base_name(base_name: str, rule: DepartmentOutputRule, scope: str) -> str:
    pieces = [_safe_component(base_name) or "output", _safe_component(rule.department) or rule.name]
    if rule.export_unit == EXPORT_UNIT_PER_GRAPHIC:
        return _safe_component(scope.split("|", 1)[0]) or "ORDER"
    if rule.file_format == FILE_FORMAT_AI_CS5:
        pieces.append("MY-W196")
    elif rule.is_png:
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


def _normalized_output_format(source: Mapping[str, Any]) -> str:
    raw = str(source.get("output_format") or "").strip().lower()
    if raw:
        return raw
    return _output_format_from_file_format(str(source.get("fileFormat") or source.get("file_format") or "AI8"))


def _resolved_file_format(source: Mapping[str, Any], output_format: str) -> str:
    value = str(source.get("fileFormat") or source.get("file_format") or "").strip().upper()
    if value:
        return value
    if output_format == "cs5_ai":
        return FILE_FORMAT_AI_CS5
    if output_format == "ai_standard":
        return FILE_FORMAT_AI_STANDARD
    if output_format in {"png_master", "png_per_item", "png_cmyk"}:
        return FILE_FORMAT_PNG_CMYK
    return FILE_FORMAT_AI8


def _output_format_from_file_format(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == FILE_FORMAT_AI_CS5:
        return "cs5_ai"
    if normalized == FILE_FORMAT_AI_STANDARD:
        return "ai_standard"
    if normalized == FILE_FORMAT_PNG_CMYK:
        return "png_cmyk"
    return "ai8"


def _resolved_export_unit(source: Mapping[str, Any], defaults: Mapping[str, Any]) -> str:
    value = str(
        source.get("exportUnit")
        or source.get("export_unit")
        or defaults.get("exportUnit")
        or defaults.get("export_unit")
        or EXPORT_UNIT_PER_ORDER
    ).strip().upper()
    return EXPORT_UNIT_PER_GRAPHIC if value == EXPORT_UNIT_PER_GRAPHIC else EXPORT_UNIT_PER_ORDER


def _resolved_bool(
    source: Mapping[str, Any],
    defaults: Mapping[str, Any],
    *,
    primary_keys: tuple[str, ...],
    fallback: bool,
) -> bool:
    for key in primary_keys:
        if key in source:
            return bool(source[key])
    for key in primary_keys:
        if key in defaults:
            return bool(defaults[key])
    return bool(fallback)


def _resolved_float(
    source: Mapping[str, Any],
    defaults: Mapping[str, Any],
    *,
    primary_keys: tuple[str, ...],
    fallback: float | None,
) -> float | None:
    for key in primary_keys:
        value = _positive_float(source.get(key))
        if value is not None:
            return value
    for key in primary_keys:
        value = _positive_float(defaults.get(key))
        if value is not None:
            return value
    return fallback


def _positive_float(*values: object) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _setting(
    source: Mapping[str, Any],
    defaults: Mapping[str, Any],
    key: str,
    fallback: Any,
) -> Any:
    if key in source:
        return source[key]
    if key in defaults:
        return defaults[key]
    return fallback


def _bool_setting(
    source: Mapping[str, Any],
    defaults: Mapping[str, Any],
    key: str,
    fallback: bool,
) -> bool:
    return bool(_setting(source, defaults, key, fallback))


def _float_setting(*values: Any) -> float | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if result > 0:
            return result
    return None
