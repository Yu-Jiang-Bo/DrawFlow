"""Materialize template-scoped OpenType tail text as complete SVG outlines.

Illustrator's ``TextFrame.contents`` assignment replaces the local alternate
glyph selection that a template artist chose in the Glyphs panel.  A V2 tail
profile therefore records the OpenType feature and alternate ordinal selected
for *that template sample*.  At render time this module resolves the requested
endpoint from the installed font and emits a complete outlined text run that
Illustrator can embed without relying on a global ``aalt`` convention. Keeping
the middle glyphs and the alternate endpoints in one outline prevents a long
swash from being independently distorted to a normal letter box.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from html import escape
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from src.service.v2_font_inventory import FONT_EXTENSIONS, default_font_dirs, font_names_from_file, normalize_font_name
from .v2_template_execution_contract import split_pipe_part


_FEATURE_TAG_RE = re.compile(r"^[A-Za-z0-9]{4}$")
_LETTER_RE = re.compile(r"^[A-Za-z]$")


class OpenTypeTailError(ValueError):
    """A deterministic preflight failure for an OpenType tail profile."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class OpenTypeTailGlyph:
    path: Path
    glyph_name: str
    font_postscript_name: str
    font_sha256: str
    feature: str
    alternate_index: int
    letter: str
    unicode_codepoint: int | None = None

    def task_payload(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "glyph_name": self.glyph_name,
            "font_postscript_name": self.font_postscript_name,
            "font_sha256": self.font_sha256,
            "opentype_feature": self.feature,
            "opentype_alternate_index": self.alternate_index,
            "letter": self.letter,
            **({"unicode_codepoint": self.unicode_codepoint} if self.unicode_codepoint is not None else {}),
        }


@dataclass(frozen=True)
class OpenTypeTailWord:
    """A complete text run with template-selected endpoint glyphs."""

    path: Path
    glyph_names: tuple[str, ...]
    font_postscript_name: str
    font_sha256: str
    text: str

    def task_payload(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "glyph_names": list(self.glyph_names),
            "font_postscript_name": self.font_postscript_name,
            "font_sha256": self.font_sha256,
            "text": self.text,
        }


def materialize_selected_opentype_tail_assets(
    render_task: Mapping[str, Any],
    *,
    values: Mapping[str, str],
    selections: Mapping[str, Mapping[str, str]],
    output_ai: Path | str,
    output_key: str = "",
    font_dirs: Iterable[Path | str] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``render_task`` with selected OpenType tails resolved.

    Only selected actions are materialized.  This keeps unrelated template
    profiles from blocking an order whose chosen font never uses them.
    """

    task = deepcopy(dict(render_task))
    output_path = Path(output_ai).resolve()
    asset_dir = output_path.parent / f".{output_path.stem}.opentype-tail-glyphs"
    resolver = OpenTypeTailResolver(font_dirs=font_dirs)
    for output in task.get("outputs", []):
        if not isinstance(output, Mapping):
            continue
        current_output_key = str(output.get("key") or "")
        if output_key and current_output_key != output_key:
            continue
        selected = selections.get(current_output_key, {})
        if not isinstance(selected, Mapping):
            continue
        for action in output.get("actions", []):
            if not _is_selected_replace_action(action, selected):
                continue
            for specs in _selected_tail_specs(action, selected):
                _materialize_action_tails(
                    specs,
                    action=action,
                    values=values,
                    resolver=resolver,
                    asset_dir=asset_dir,
                )
    return task


def _is_selected_replace_action(action: Any, selected: Mapping[str, str]) -> bool:
    if not isinstance(action, Mapping) or str(action.get("type") or "") != "replace_slot_text":
        return False
    group = str(action.get("group") or "")
    option = str(action.get("option_key") or "")
    return bool(group and option and str(selected.get(group) or "") == option)


def _selected_tail_specs(action: Mapping[str, Any], selected: Mapping[str, str]) -> list[list[dict[str, Any]]]:
    direct = action.get("tails")
    if isinstance(direct, list) and direct:
        return [direct]
    style_source = action.get("style_source")
    if not isinstance(style_source, Mapping):
        return []
    source_group = str(style_source.get("group") or "")
    source_option = str(selected.get(source_group) or "")
    tails_by_option = style_source.get("tails_by_option")
    if not isinstance(tails_by_option, Mapping):
        return []
    selected_specs = tails_by_option.get(source_option)
    return [selected_specs] if isinstance(selected_specs, list) and selected_specs else []


def _materialize_action_tails(
    specs: list[dict[str, Any]],
    *,
    action: Mapping[str, Any],
    values: Mapping[str, str],
    resolver: "OpenTypeTailResolver",
    asset_dir: Path,
) -> None:
    endpoint_value = _action_text_value(action, values)
    # Optional blanks are removed by the Illustrator renderer.  They have no
    # endpoint to materialize and must not turn an otherwise valid order into
    # an OpenType preflight failure.
    if not str(endpoint_value).strip() and not bool(action.get("required")):
        return
    # Pure PUA tasks still use Illustrator's existing text substitution path.
    # Once one endpoint needs a GSUB alternate, the complete word is outlined
    # from one font, including any adjacent PUA endpoint.  Rendering endpoint
    # vectors independently changes their stroke weight relative to the body.
    if not any(
        isinstance(spec, Mapping) and str(spec.get("glyph_mode") or "") == "opentype_alternate"
        for spec in specs
    ):
        return
    asset_dir.mkdir(parents=True, exist_ok=True)
    endpoint_indexes = _latin_endpoint_indexes(endpoint_value)
    endpoint_glyphs: dict[int, str] = {}
    font_postscript_name = ""
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        position = str(spec.get("position") or "")
        endpoint = endpoint_indexes.get(position)
        if endpoint is None:
            raise OpenTypeTailError(
                "opentype_tail_endpoint_missing",
                f"OpenType 尾巴字形需要拉丁首字或尾字：{endpoint_value}",
            )
        endpoint_index, letter = endpoint
        spec_font = str(spec.get("font_postscript_name") or "").strip()
        if not font_postscript_name:
            font_postscript_name = spec_font
        elif spec_font != font_postscript_name:
            raise OpenTypeTailError("opentype_tail_font_mismatch", "同一尾巴文字槽位必须使用同一份字体轮廓。")
        glyph_mode = str(spec.get("glyph_mode") or "")
        if glyph_mode == "opentype_alternate":
            glyph_name = resolver.resolve_alternate_glyph_name(
                font_postscript_name=spec_font,
                feature=str(spec.get("opentype_feature") or ""),
                alternate_index=spec.get("opentype_alternate_index"),
                letter=letter,
            )
        elif glyph_mode in {"pua_contiguous", "glyph_map"}:
            glyph_name = resolver.resolve_codepoint_glyph_name(
                font_postscript_name=spec_font,
                codepoint=_pua_codepoint_for_tail(spec, letter),
            )
        else:
            raise OpenTypeTailError(
                "tail_glyph_coverage_missing",
                f"尾巴字形缺少可验证映射：{spec.get('key') or ''}",
            )
        existing = endpoint_glyphs.get(endpoint_index)
        if existing and existing != glyph_name:
            raise OpenTypeTailError("opentype_tail_endpoint_conflict", "单字符文字不能同时使用不同的首尾尾巴字形。")
        endpoint_glyphs[endpoint_index] = glyph_name

    word = resolver.materialize_word(
        font_postscript_name=font_postscript_name,
        text=endpoint_value,
        endpoint_glyphs=endpoint_glyphs,
        output_dir=asset_dir,
    )
    for spec in specs:
        if isinstance(spec, dict):
            spec["opentype_word_asset"] = word.task_payload()


def _action_text_value(action: Mapping[str, Any], values: Mapping[str, str]) -> str:
    value = str(values.get(str(action.get("source_field") or ""), ""))
    if str(action.get("preset") or "") == "split_by_pipe":
        return split_pipe_part(value, action.get("source_part_index"))
    return value


def _pua_codepoint_for_tail(spec: Mapping[str, Any], letter: str) -> int:
    normalized_letter = str(letter or "").casefold()
    if not _LETTER_RE.match(normalized_letter):
        raise OpenTypeTailError("opentype_tail_endpoint_missing", "尾巴字形需要单个拉丁字母。")
    glyph_map = spec.get("glyph_map")
    if isinstance(glyph_map, Mapping):
        codepoint = glyph_map.get(normalized_letter)
        if isinstance(codepoint, bool) or not isinstance(codepoint, int):
            raise OpenTypeTailError("tail_glyph_coverage_missing", f"尾巴字形缺少字母映射：{normalized_letter}")
        return codepoint
    base = spec.get("pua_base")
    if isinstance(base, bool) or not isinstance(base, int):
        raise OpenTypeTailError("tail_glyph_coverage_missing", "尾巴字形缺少 PUA 编码。")
    return base + (ord(normalized_letter) - ord("a"))


def _latin_endpoints(value: str) -> tuple[str, str]:
    indexes = _latin_endpoint_indexes(value)
    if not indexes:
        return "", ""
    return indexes["first"][1], indexes["last"][1]


def _latin_endpoint_indexes(value: str) -> dict[str, tuple[int, str]]:
    letters = [(index, character) for index, character in enumerate(str(value or "")) if _LETTER_RE.match(character)]
    if not letters:
        return {}
    return {"first": letters[0], "last": letters[-1]}


class OpenTypeTailResolver:
    """Resolve one installed font's feature alternates and write SVG outlines."""

    def __init__(self, *, font_dirs: Iterable[Path | str] | None = None) -> None:
        self.font_dirs = [Path(path) for path in (font_dirs if font_dirs is not None else default_font_dirs())]

    def materialize(
        self,
        *,
        font_postscript_name: str,
        feature: str,
        alternate_index: Any,
        letter: str,
        output_dir: Path | str,
    ) -> OpenTypeTailGlyph:
        postscript_name = str(font_postscript_name or "").strip()
        tag = str(feature or "").strip().casefold()
        if not postscript_name:
            raise OpenTypeTailError("opentype_tail_font_missing", "OpenType 尾巴字形缺少字体 PostScript 名称。")
        if not _FEATURE_TAG_RE.match(tag):
            raise OpenTypeTailError("opentype_tail_profile_invalid", "OpenType 尾巴字形特性必须是四位标签。")
        if isinstance(alternate_index, bool) or not isinstance(alternate_index, int) or alternate_index < 1:
            raise OpenTypeTailError("opentype_tail_profile_invalid", "OpenType 尾巴字形替代序号必须是正整数。")
        if not _LETTER_RE.match(str(letter or "")):
            raise OpenTypeTailError("opentype_tail_endpoint_missing", "OpenType 尾巴字形需要单个拉丁字母。")

        font_path = self.find_font_file(postscript_name)
        try:
            font = TTFont(str(font_path), lazy=False)
        except Exception as exc:  # FontTools surfaces many format-specific exceptions.
            raise OpenTypeTailError("opentype_tail_font_invalid", f"无法读取 OpenType 字体：{postscript_name}") from exc
        try:
            glyph_name = _alternate_glyph_name(font, tag, alternate_index, str(letter).casefold())
            svg = _glyph_svg(font, glyph_name)
        finally:
            font.close()
        return self._write_glyph_asset(
            font_path=font_path,
            glyph_name=glyph_name,
            svg=svg,
            output_dir=output_dir,
            filename_prefix=f"{tag}-{alternate_index}-{str(letter).casefold()}",
            font_postscript_name=postscript_name,
            feature=tag,
            alternate_index=alternate_index,
            letter=str(letter).casefold(),
        )

    def resolve_alternate_glyph_name(
        self,
        *,
        font_postscript_name: str,
        feature: str,
        alternate_index: Any,
        letter: str,
    ) -> str:
        postscript_name = str(font_postscript_name or "").strip()
        tag = str(feature or "").strip().casefold()
        if not postscript_name:
            raise OpenTypeTailError("opentype_tail_font_missing", "OpenType 尾巴字形缺少字体 PostScript 名称。")
        if not _FEATURE_TAG_RE.match(tag):
            raise OpenTypeTailError("opentype_tail_profile_invalid", "OpenType 尾巴字形特性必须是四位标签。")
        if isinstance(alternate_index, bool) or not isinstance(alternate_index, int) or alternate_index < 1:
            raise OpenTypeTailError("opentype_tail_profile_invalid", "OpenType 尾巴字形替代序号必须是正整数。")
        if not _LETTER_RE.match(str(letter or "")):
            raise OpenTypeTailError("opentype_tail_endpoint_missing", "OpenType 尾巴字形需要单个拉丁字母。")
        font_path = self.find_font_file(postscript_name)
        try:
            font = TTFont(str(font_path), lazy=False)
        except Exception as exc:
            raise OpenTypeTailError("opentype_tail_font_invalid", f"无法读取 OpenType 字体：{postscript_name}") from exc
        try:
            return _alternate_glyph_name(font, tag, alternate_index, str(letter).casefold())
        finally:
            font.close()

    def resolve_codepoint_glyph_name(self, *, font_postscript_name: str, codepoint: int) -> str:
        postscript_name = str(font_postscript_name or "").strip()
        if not postscript_name:
            raise OpenTypeTailError("opentype_tail_font_missing", "尾巴字形缺少字体 PostScript 名称。")
        if not isinstance(codepoint, int) or not 0xE000 <= codepoint <= 0xF8FF:
            raise OpenTypeTailError("tail_glyph_coverage_invalid", "尾巴字形 PUA 编码不合法。")
        font_path = self.find_font_file(postscript_name)
        try:
            font = TTFont(str(font_path), lazy=False)
        except Exception as exc:
            raise OpenTypeTailError("opentype_tail_font_invalid", f"无法读取尾巴字体：{postscript_name}") from exc
        try:
            glyph_name = (font.getBestCmap() or {}).get(codepoint)
            if not glyph_name:
                raise OpenTypeTailError("tail_glyph_coverage_missing", f"字体没有 PUA 尾巴字形：U+{codepoint:04X}")
            return glyph_name
        finally:
            font.close()

    def materialize_word(
        self,
        *,
        font_postscript_name: str,
        text: str,
        endpoint_glyphs: Mapping[int, str],
        output_dir: Path | str,
    ) -> OpenTypeTailWord:
        postscript_name = str(font_postscript_name or "").strip()
        if not postscript_name:
            raise OpenTypeTailError("opentype_tail_font_missing", "OpenType 尾巴字形缺少字体 PostScript 名称。")
        if not str(text or ""):
            raise OpenTypeTailError("opentype_tail_endpoint_missing", "OpenType 尾巴字形缺少文字内容。")
        font_path = self.find_font_file(postscript_name)
        try:
            font = TTFont(str(font_path), lazy=False)
        except Exception as exc:
            raise OpenTypeTailError("opentype_tail_font_invalid", f"无法读取 OpenType 字体：{postscript_name}") from exc
        try:
            glyph_names = _text_glyph_names(font, str(text), endpoint_glyphs)
            svg = _text_svg(font, glyph_names)
        finally:
            font.close()
        digest = _sha256_file(font_path)
        signature = hashlib.sha256((str(text) + "\0" + "\0".join(glyph_names)).encode("utf-8")).hexdigest()[:16]
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{digest[:16]}-word-{signature}.svg"
        if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != svg:
            path.write_text(svg, encoding="utf-8")
        return OpenTypeTailWord(
            path=path,
            glyph_names=tuple(glyph_names),
            font_postscript_name=postscript_name,
            font_sha256=digest,
            text=str(text),
        )

    def materialize_codepoint(
        self,
        *,
        font_postscript_name: str,
        codepoint: int,
        letter: str,
        output_dir: Path | str,
    ) -> OpenTypeTailGlyph:
        postscript_name = str(font_postscript_name or "").strip()
        if not postscript_name:
            raise OpenTypeTailError("opentype_tail_font_missing", "尾巴字形缺少字体 PostScript 名称。")
        if not isinstance(codepoint, int) or not 0xE000 <= codepoint <= 0xF8FF:
            raise OpenTypeTailError("tail_glyph_coverage_invalid", "尾巴字形 PUA 编码不合法。")
        if not _LETTER_RE.match(str(letter or "")):
            raise OpenTypeTailError("opentype_tail_endpoint_missing", "尾巴字形需要单个拉丁字母。")
        font_path = self.find_font_file(postscript_name)
        try:
            font = TTFont(str(font_path), lazy=False)
        except Exception as exc:
            raise OpenTypeTailError("opentype_tail_font_invalid", f"无法读取尾巴字体：{postscript_name}") from exc
        try:
            glyph_name = (font.getBestCmap() or {}).get(codepoint)
            if not glyph_name:
                raise OpenTypeTailError("tail_glyph_coverage_missing", f"字体没有 PUA 尾巴字形：U+{codepoint:04X}")
            svg = _glyph_svg(font, glyph_name)
        finally:
            font.close()
        return self._write_glyph_asset(
            font_path=font_path,
            glyph_name=glyph_name,
            svg=svg,
            output_dir=output_dir,
            filename_prefix=f"pua-{codepoint:04X}-{str(letter).casefold()}",
            font_postscript_name=postscript_name,
            feature="pua",
            alternate_index=0,
            letter=str(letter).casefold(),
            unicode_codepoint=codepoint,
        )

    def _write_glyph_asset(
        self,
        *,
        font_path: Path,
        glyph_name: str,
        svg: str,
        output_dir: Path | str,
        filename_prefix: str,
        font_postscript_name: str,
        feature: str,
        alternate_index: int,
        letter: str,
        unicode_codepoint: int | None = None,
    ) -> OpenTypeTailGlyph:
        digest = _sha256_file(font_path)
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_glyph = re.sub(r"[^A-Za-z0-9_-]+", "_", glyph_name).strip("_") or "glyph"
        filename = f"{digest[:16]}-{filename_prefix}-{safe_glyph}.svg"
        path = target_dir / filename
        if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != svg:
            path.write_text(svg, encoding="utf-8")
        return OpenTypeTailGlyph(
            path=path,
            glyph_name=glyph_name,
            font_postscript_name=font_postscript_name,
            font_sha256=digest,
            feature=feature,
            alternate_index=alternate_index,
            letter=letter,
            unicode_codepoint=unicode_codepoint,
        )

    def find_font_file(self, postscript_name: str) -> Path:
        wanted = normalize_font_name(postscript_name)
        matches: list[Path] = []
        for directory in self.font_dirs:
            try:
                candidates = directory.iterdir()
            except OSError:
                continue
            for path in candidates:
                try:
                    if not path.is_file() or path.suffix.casefold() not in FONT_EXTENSIONS:
                        continue
                    names = {normalize_font_name(name) for name in font_names_from_file(path)}
                except (OSError, ValueError):
                    continue
                if wanted in names:
                    matches.append(path)
        if not matches:
            raise OpenTypeTailError("opentype_tail_font_missing", f"未找到 OpenType 尾巴字体：{postscript_name}")
        return sorted(matches, key=lambda path: str(path).casefold())[0]


def _alternate_glyph_name(font: TTFont, feature: str, alternate_index: int, letter: str) -> str:
    if "GSUB" not in font:
        raise OpenTypeTailError("opentype_tail_feature_missing", f"字体没有 GSUB 特性：{feature}")
    feature_list = font["GSUB"].table.FeatureList
    lookup_list = font["GSUB"].table.LookupList
    if feature_list is None or lookup_list is None:
        raise OpenTypeTailError("opentype_tail_feature_missing", f"字体没有 GSUB 特性：{feature}")
    lookup_indexes: list[int] = []
    for record in feature_list.FeatureRecord or []:
        if str(record.FeatureTag or "").casefold() == feature:
            lookup_indexes.extend(record.Feature.LookupListIndex or [])
    if not lookup_indexes:
        raise OpenTypeTailError("opentype_tail_feature_missing", f"字体没有 OpenType 特性：{feature}")
    alternates: list[str] = []
    for lookup_index in lookup_indexes:
        try:
            lookup = lookup_list.Lookup[lookup_index]
        except (IndexError, TypeError):
            continue
        lookup_type = int(getattr(lookup, "LookupType", 0) or 0)
        if lookup_type not in {1, 3}:
            continue
        for subtable in getattr(lookup, "SubTable", []) or []:
            if lookup_type == 1:
                replacement = getattr(subtable, "mapping", {}).get(letter)
                candidates = [replacement] if replacement else []
            else:
                candidates = getattr(subtable, "alternates", {}).get(letter, [])
            for candidate in candidates:
                if candidate not in alternates:
                    alternates.append(candidate)
    if len(alternates) < alternate_index:
        raise OpenTypeTailError(
            "opentype_tail_glyph_missing",
            f"字体 {feature} 没有字母 {letter} 的第 {alternate_index} 个替代字形。",
        )
    return alternates[alternate_index - 1]


def _glyph_svg(font: TTFont, glyph_name: str) -> str:
    glyph_set = font.getGlyphSet()
    if glyph_name not in glyph_set:
        raise OpenTypeTailError("opentype_tail_glyph_missing", f"OpenType 替代字形不存在：{glyph_name}")
    glyph = glyph_set[glyph_name]
    bounds_pen = BoundsPen(glyph_set)
    glyph.draw(bounds_pen)
    if not bounds_pen.bounds:
        raise OpenTypeTailError("opentype_tail_glyph_missing", f"OpenType 替代字形没有可见轮廓：{glyph_name}")
    x_min, y_min, x_max, y_max = bounds_pen.bounds
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0:
        raise OpenTypeTailError("opentype_tail_glyph_missing", f"OpenType 替代字形没有有效尺寸：{glyph_name}")
    path_pen = SVGPathPen(glyph_set)
    glyph.draw(path_pen)
    commands = path_pen.getCommands()
    if not commands:
        raise OpenTypeTailError("opentype_tail_glyph_missing", f"OpenType 替代字形没有 SVG 路径：{glyph_name}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x_min:g} {-y_max:g} {width:g} {height:g}">\n'
        f'  <path d="{escape(commands, quote=True)}" transform="scale(1,-1)"/>\n'
        "</svg>\n"
    )


def _text_glyph_names(font: TTFont, text: str, endpoint_glyphs: Mapping[int, str]) -> list[str]:
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()
    glyph_names: list[str] = []
    for index, character in enumerate(text):
        glyph_name = str(endpoint_glyphs.get(index) or cmap.get(ord(character)) or "")
        if not glyph_name or glyph_name not in glyph_set:
            raise OpenTypeTailError("opentype_tail_glyph_missing", f"字体缺少文字字形：{character}")
        glyph_names.append(glyph_name)
    return glyph_names


def _text_svg(font: TTFont, glyph_names: list[str]) -> str:
    glyph_set = font.getGlyphSet()
    x_cursor = 0.0
    path_entries: list[tuple[float, str]] = []
    bounds: tuple[float, float, float, float] | None = None
    for index, glyph_name in enumerate(glyph_names):
        glyph = glyph_set[glyph_name]
        bounds_pen = BoundsPen(glyph_set)
        glyph.draw(bounds_pen)
        if bounds_pen.bounds:
            x_min, y_min, x_max, y_max = bounds_pen.bounds
            bounds = _merge_text_bounds(bounds, (x_min + x_cursor, y_min, x_max + x_cursor, y_max))
            path_pen = SVGPathPen(glyph_set)
            glyph.draw(path_pen)
            commands = path_pen.getCommands()
            if commands:
                path_entries.append((x_cursor, commands))
        advance = float(font["hmtx"].metrics.get(glyph_name, (0, 0))[0])
        if index + 1 < len(glyph_names):
            advance += _gpos_pair_x_advance(font, glyph_name, glyph_names[index + 1])
        x_cursor += advance
    if not bounds:
        raise OpenTypeTailError("opentype_tail_glyph_missing", "OpenType 文字没有可见轮廓。")
    x_min, y_min, x_max, y_max = bounds
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0:
        raise OpenTypeTailError("opentype_tail_glyph_missing", "OpenType 文字没有有效尺寸。")
    paths = "\n".join(
        f'  <path d="{escape(commands, quote=True)}" transform="translate({x:g},0) scale(1,-1)"/>'
        for x, commands in path_entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x_min:g} {-y_max:g} {width:g} {height:g}">\n'
        "  <g>\n"
        f"{paths}\n"
        "  </g>\n"
        "</svg>\n"
    )


def _merge_text_bounds(
    current: tuple[float, float, float, float] | None,
    next_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if current is None:
        return next_bounds
    return (
        min(current[0], next_bounds[0]),
        min(current[1], next_bounds[1]),
        max(current[2], next_bounds[2]),
        max(current[3], next_bounds[3]),
    )


def _gpos_pair_x_advance(font: TTFont, left_glyph: str, right_glyph: str) -> float:
    """Return `kern` PairPos XAdvance without pretending to be a full shaper."""

    if "GPOS" not in font:
        return 0.0
    try:
        table = font["GPOS"].table
        feature_list = table.FeatureList
        lookup_list = table.LookupList
        if feature_list is None or lookup_list is None:
            return 0.0
        lookup_indexes: list[int] = []
        for record in feature_list.FeatureRecord or []:
            if str(record.FeatureTag or "").casefold() == "kern":
                lookup_indexes.extend(record.Feature.LookupListIndex or [])
        adjustment = 0.0
        for lookup_index in lookup_indexes:
            lookup = lookup_list.Lookup[lookup_index]
            if int(getattr(lookup, "LookupType", 0) or 0) != 2:
                continue
            for subtable in getattr(lookup, "SubTable", []) or []:
                value = _pair_pos_x_advance(subtable, left_glyph, right_glyph)
                if value is not None:
                    adjustment += value
        return adjustment
    except (AttributeError, IndexError, KeyError, TypeError):
        return 0.0


def _pair_pos_x_advance(subtable: Any, left_glyph: str, right_glyph: str) -> float | None:
    coverage = list(getattr(getattr(subtable, "Coverage", None), "glyphs", []) or [])
    if left_glyph not in coverage:
        return None
    value_record = None
    if int(getattr(subtable, "Format", 0) or 0) == 1:
        pair_sets = getattr(subtable, "PairSet", None) or []
        pair_set = pair_sets[coverage.index(left_glyph)] if coverage.index(left_glyph) < len(pair_sets) else None
        for pair in getattr(pair_set, "PairValueRecord", []) or []:
            if str(getattr(pair, "SecondGlyph", "")) == right_glyph:
                value_record = getattr(pair, "Value1", None)
                break
    elif int(getattr(subtable, "Format", 0) or 0) == 2:
        class1 = int(getattr(getattr(subtable, "ClassDef1", None), "classDefs", {}).get(left_glyph, 0))
        class2 = int(getattr(getattr(subtable, "ClassDef2", None), "classDefs", {}).get(right_glyph, 0))
        class1_records = getattr(subtable, "Class1Record", []) or []
        if class1 < len(class1_records):
            class2_records = getattr(class1_records[class1], "Class2Record", []) or []
            if class2 < len(class2_records):
                value_record = getattr(class2_records[class2], "Value1", None)
    if value_record is None:
        return None
    return float(getattr(value_record, "XAdvance", 0) or 0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "OpenTypeTailError",
    "OpenTypeTailGlyph",
    "OpenTypeTailWord",
    "OpenTypeTailResolver",
    "materialize_selected_opentype_tail_assets",
]
