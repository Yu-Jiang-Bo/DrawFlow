"""CSV parser for the pure text MVP."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List


FIELD_ALIASES = {
    "order_no": ["订单号", "订单编号", "内部订单号", "order_no", "Order No"],
    "custom_text": ["定制信息", "客户留言", "custom_text", "文字", "名字"],
    "size": ["作图尺寸", "作图大小", "图尺寸", "成品作图尺寸", "尺寸", "Size"],
    "font": ["字体", "字体名称", "Font", "font"],
    "color": ["字体颜色", "字体色", "颜色", "文字颜色", "color"],
}


def read_csv_rows(path: Path | str) -> List[Dict[str, str]]:
    csv_path = Path(path)
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312", "cp936"):
        try:
            with csv_path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(2048)
                handle.seek(0)
                if sample.startswith("sep="):
                    handle.readline()
                reader = csv.DictReader(handle)
                return [
                    {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
                    for row in reader
                    if any(str(v or "").strip() for v in row.values())
                ]
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    lower_map = {key.strip().lower(): value for key, value in row.items()}
    for target, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            value = lower_map.get(alias.strip().lower())
            if value:
                normalized[target] = value
                break
        else:
            normalized[target] = ""
    return normalized


def normalize_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    return [normalize_row(row) for row in rows]
