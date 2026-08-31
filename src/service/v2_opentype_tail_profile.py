"""Infer a template tail's OpenType profile from its Illustrator outline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.renderer.v2_opentype_tail import OpenTypeTailError, OpenTypeTailGlyph, OpenTypeTailResolver


_TAIL_RE = re.compile(r"^tail_(?P<field>[A-Za-z0-9_]+)_(?P<position>first|last)_(?P<sample>[A-Za-z])$", re.I)
# The source and candidate are the same Illustrator curve outline expressed
# with integer coordinates in a 0..1000 box.  A real match only differs by
# rounding noise; accepting a visibly different alternate is never safe.
_MAX_OUTLINE_MEAN_DELTA = 0.5
_PROBE_BATCH_SIZE = 12
# The template signature is integer-rounded and Illustrator may decompose a
# TrueType quadratic spline into a different number of cubic spans.  Correct
# glyphs stay below 17 in the normalized 0..1000 coordinate space across the
# supported TTF/CFF fixtures; wrong alternates are materially farther away.
_MAX_VECTOR_OUTLINE_MEAN_DELTA = 20.0
_VECTOR_OUTLINE_SAMPLE_COUNT = 96
OutlinePoint = tuple[int, int]
OutlineTriple = tuple[OutlinePoint, OutlinePoint, OutlinePoint]
OutlinePath = tuple[str, list[OutlineTriple]]
VectorPoint = tuple[float, float]
VectorPath = tuple[str, list[VectorPoint]]


class OpenTypeTailProfileInferer:
    """Match a scanned Illustrator tail sample to its font's GSUB candidates.

    The source and candidates are both passed through Illustrator to produce
    normalized path signatures.  This is intentional: a font table tells us
    what is available, but not which Glyphs-panel alternate an artist chose.
    """

    def __init__(
        self,
        *,
        bridge: Any,
        resolver: OpenTypeTailResolver | None = None,
        script_path: str | Path | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.bridge = bridge
        self.resolver = resolver or OpenTypeTailResolver()
        self.script_path = Path(script_path or repo_root / "scripts" / "illustrator" / "probe_v2_opentype_tail_candidates.jsx")

    def apply(self, raw_scan: Mapping[str, Any], *, work_dir: str | Path) -> dict[str, Any]:
        """Return a copy of ``raw_scan`` augmented only by proven profiles."""

        raw = _copy_scan(raw_scan)
        tails = _tail_evidence(raw)
        proven = [tail for tail in tails if tail["signature"] and tail["font"] and tail["letter"]]
        if not proven:
            return raw

        candidates_by_font_letter: dict[tuple[str, str], list[OpenTypeTailGlyph]] = {}
        for tail in proven:
            key = (tail["font"], tail["letter"])
            if key in candidates_by_font_letter:
                continue
            try:
                candidates = self.resolver.materialize_alternate_candidates(
                    font_postscript_name=key[0],
                    letter=key[1],
                    output_dir=Path(work_dir) / "opentype-tail-candidates",
                )
            except OpenTypeTailError as exc:
                candidates = []
                _mark_tail_status(raw, tail["path"], "unresolved", str(exc))
            candidates_by_font_letter[key] = candidates
        candidate_ids: dict[str, OpenTypeTailGlyph] = {}
        for key, candidates in candidates_by_font_letter.items():
            # A one-letter tail from the template already contains an exact
            # outline box.  Filter impossible candidates before asking
            # Illustrator to open their SVGs: some display fonts expose
            # hundreds of ornate alternates, and an unrelated malformed SVG
            # must not prevent every other template from being scanned.
            candidates = _shape_compatible_candidates(
                [tail for tail in proven if (tail["font"], tail["letter"]) == key],
                candidates,
            )
            candidates_by_font_letter[key] = candidates
            for candidate in candidates:
                candidate_ids[_candidate_id(candidate)] = candidate

        unmatched: list[dict[str, Any]] = []
        coverage_cache: dict[tuple[str, str, int], str] = {}
        vector_shapes = self._fonttools_shapes(candidate_ids)
        for tail in proven:
            candidates = candidates_by_font_letter.get((tail["font"], tail["letter"]), [])
            selected, message = _unique_vector_matched_candidate(
                tail,
                candidates,
                vector_shapes,
            )
            if selected is None:
                unmatched.append({**tail, "gsub_message": message})
                continue
            coverage_message = self._alternate_coverage_message(selected, coverage_cache)
            if coverage_message:
                unmatched.append({**tail, "gsub_message": coverage_message})
                continue
            _mark_tail_profile(raw, tail["path"], selected)

        # FontTools is the primary proof path: it compares the template's
        # already-scanned Illustrator outline to the same glyph table without
        # opening arbitrary SVG files in Illustrator.  Keep the Illustrator
        # SVG probe as a strict fallback for format edge cases only.
        if unmatched:
            fallback_ids = {
                _candidate_id(candidate): candidate
                for tail in unmatched
                for candidate in candidates_by_font_letter.get((tail["font"], tail["letter"]), [])
            }
            candidate_signatures = self._probe(fallback_ids, work_dir=Path(work_dir)) if fallback_ids else {}
            remaining_unmatched: list[dict[str, str]] = []
            for tail in unmatched:
                selected, message = _unique_matched_candidate(
                    tail,
                    candidates_by_font_letter.get((tail["font"], tail["letter"]), []),
                    candidate_signatures,
                )
                if selected is None:
                    remaining_unmatched.append({**tail, "gsub_message": message or tail["gsub_message"]})
                    continue
                coverage_message = self._alternate_coverage_message(selected, coverage_cache)
                if coverage_message:
                    remaining_unmatched.append({**tail, "gsub_message": coverage_message})
                    continue
                _mark_tail_profile(raw, tail["path"], selected)
            unmatched = remaining_unmatched

        if not unmatched:
            return raw

        # Legacy fonts often expose their endpoint alternates as PUA glyphs
        # instead of GSUB features. Try this only after direct OpenType lookup
        # has no proven answer, and only accept a full contiguous a-z run.
        pua_by_font_letter: dict[tuple[str, str], list[OpenTypeTailGlyph]] = {}
        for tail in unmatched:
            key = (tail["font"], tail["letter"])
            if key in pua_by_font_letter:
                continue
            materialize_pua = getattr(self.resolver, "materialize_contiguous_pua_candidates", None)
            if not callable(materialize_pua):
                pua_by_font_letter[key] = []
                continue
            try:
                candidates = materialize_pua(
                    font_postscript_name=key[0],
                    letter=key[1],
                    output_dir=Path(work_dir) / "pua-tail-candidates",
                )
            except OpenTypeTailError:
                candidates = []
            pua_by_font_letter[key] = candidates
        pua_ids: dict[str, OpenTypeTailGlyph] = {}
        for key, candidates in pua_by_font_letter.items():
            candidates = _shape_compatible_candidates(
                [tail for tail in unmatched if (tail["font"], tail["letter"]) == key],
                candidates,
            )
            pua_by_font_letter[key] = candidates
            for candidate in candidates:
                pua_ids[_candidate_id(candidate)] = candidate

        pua_vector_shapes = self._fonttools_shapes(pua_ids)
        remaining_pua: list[dict[str, str]] = []
        for tail in unmatched:
            selected, message = _unique_vector_matched_candidate(
                tail,
                pua_by_font_letter.get((tail["font"], tail["letter"]), []),
                pua_vector_shapes,
            )
            if selected is None:
                remaining_pua.append({**tail, "pua_message": message})
                continue
            _mark_tail_profile(raw, tail["path"], selected)
        if not remaining_pua:
            return raw

        fallback_pua_ids = {
            _candidate_id(candidate): candidate
            for tail in remaining_pua
            for candidate in pua_by_font_letter.get((tail["font"], tail["letter"]), [])
        }
        pua_signatures = self._probe(fallback_pua_ids, work_dir=Path(work_dir)) if fallback_pua_ids else {}
        for tail in remaining_pua:
            selected, message = _unique_matched_candidate(
                tail,
                pua_by_font_letter.get((tail["font"], tail["letter"]), []),
                pua_signatures,
            )
            if selected is None:
                _mark_tail_status(
                    raw,
                    tail["path"],
                    "unresolved",
                    message or tail["pua_message"] or tail["gsub_message"] or "没有匹配到该模板样本的尾巴字形，未写入尾巴配置。",
                )
                continue
            _mark_tail_profile(raw, tail["path"], selected)
        return raw

    def _alternate_coverage_message(
        self,
        candidate: OpenTypeTailGlyph,
        cache: dict[tuple[str, str, int], str],
    ) -> str:
        """Return a publication-safe coverage failure for a GSUB profile.

        PUA candidates are constructed only after their complete a-z mapping
        has already been proven.  GSUB profiles need an equivalent check here:
        one template sample cannot authorize the same ordinal for all future
        first/last letters.
        """

        if candidate.feature == "pua":
            return ""
        key = (candidate.font_sha256, candidate.feature, candidate.alternate_index)
        if key in cache:
            return cache[key]
        verify = getattr(self.resolver, "verify_alternate_coverage", None)
        if not callable(verify):
            message = "无法验证该 OpenType 尾巴规则是否完整覆盖 a-z，未写入尾巴配置。"
            cache[key] = message
            return message
        try:
            mapped = verify(
                font_postscript_name=candidate.font_postscript_name,
                feature=candidate.feature,
                alternate_index=candidate.alternate_index,
                coverage="abcdefghijklmnopqrstuvwxyz",
            )
        except OpenTypeTailError as exc:
            message = f"OpenType 尾巴规则无法完整覆盖 a-z：{exc}"
            cache[key] = message
            return message
        if not isinstance(mapped, Mapping) or any(str(letter) not in mapped for letter in "abcdefghijklmnopqrstuvwxyz"):
            message = "OpenType 尾巴规则未证明完整覆盖 a-z，未写入尾巴配置。"
            cache[key] = message
            return message
        cache[key] = ""
        return ""

    def _fonttools_shapes(self, candidates: Mapping[str, OpenTypeTailGlyph]) -> dict[str, list[VectorPath]]:
        """Load candidate outlines directly from font data, without SVG import."""

        result: dict[str, list[VectorPath]] = {}
        find_font_file = getattr(self.resolver, "find_font_file", None)
        if not callable(find_font_file):
            # Lightweight test/dry-run resolvers can still use the strict
            # Illustrator-probe fallback without implementing font inventory.
            return result
        fonts: dict[str, TTFont] = {}
        try:
            for identifier, candidate in candidates.items():
                try:
                    font = fonts.get(candidate.font_sha256)
                    if font is None:
                        font_path = find_font_file(candidate.font_postscript_name)
                        font = TTFont(str(font_path), lazy=False)
                        fonts[candidate.font_sha256] = font
                    shape = _fonttools_glyph_shape(font, candidate.glyph_name)
                    if shape:
                        result[identifier] = shape
                except (OpenTypeTailError, OSError, ValueError, KeyError):
                    continue
        finally:
            for font in fonts.values():
                try:
                    font.close()
                except Exception:
                    pass
        return result

    def _probe(self, candidates: Mapping[str, OpenTypeTailGlyph], *, work_dir: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        pairs = sorted(candidates.items())
        for offset in range(0, len(pairs), _PROBE_BATCH_SIZE):
            task_path = work_dir / f"probe-opentype-tail-{uuid4().hex}.json"
            output_path = task_path.with_name(task_path.stem + "-result.json")
            task = {
                "output_json": str(output_path),
                "candidates": [
                    {"id": identifier, "svg_path": str(candidate.path)}
                    for identifier, candidate in pairs[offset:offset + _PROBE_BATCH_SIZE]
                ],
            }
            task_path.write_text(json.dumps(task, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            try:
                self.bridge.render(self.script_path, task_path)
            except (IllustratorBridgeError, OSError, RuntimeError):
                continue
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            entries = payload.get("candidates") if isinstance(payload, Mapping) else []
            if not isinstance(entries, list):
                continue
            result.update(
                {
                    str(entry.get("id") or ""): str(entry.get("outline_signature") or "")
                    for entry in entries
                    if isinstance(entry, Mapping) and entry.get("id") and entry.get("outline_signature")
                }
            )
        return result


def _tail_evidence(raw_scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in _walk_mappings(raw_scan):
        key = str(item.get("key") or item.get("name") or "").strip()
        match = _TAIL_RE.match(key)
        if not match:
            continue
        path = str(item.get("path") or item.get("layer_path") or "").strip()
        if not path:
            continue
        record = merged.setdefault(
            path,
            {"path": path, "letter": match.group("sample").casefold(), "font": "", "signature": "", "outline_aspect_ratio": None},
        )
        record["letter"] = str(item.get("sample") or match.group("sample")).casefold()
        record["font"] = _first_text(record["font"], _font_name(item))
        record["signature"] = _first_text(record["signature"], item.get("outline_signature"))
        record["outline_aspect_ratio"] = record["outline_aspect_ratio"] or _tail_outline_aspect_ratio(item)
    return [merged[key] for key in sorted(merged, key=str.casefold)]


def _tail_outline_aspect_ratio(item: Mapping[str, Any]) -> float | None:
    """Return a sample ratio with Illustrator's local text scaling removed."""

    bounds = item.get("outline_bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        return None
    try:
        width = abs(float(bounds[2]) - float(bounds[0]))
        height = abs(float(bounds[1]) - float(bounds[3]))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    font = item.get("font")
    if not isinstance(font, Mapping) and isinstance(item.get("text"), Mapping):
        font = item["text"].get("font")
    horizontal = 100.0
    vertical = 100.0
    if isinstance(font, Mapping):
        try:
            horizontal = float(font.get("horizontal_scale") or 100.0)
            vertical = float(font.get("vertical_scale") or 100.0)
        except (TypeError, ValueError):
            return None
    if horizontal <= 0 or vertical <= 0:
        return None
    return (width / height) * (vertical / horizontal)


def _shape_compatible_candidates(
    tails: Iterable[Mapping[str, Any]],
    candidates: Iterable[OpenTypeTailGlyph],
) -> list[OpenTypeTailGlyph]:
    """Keep candidates matching at least one sample's unscaled outline box.

    A ratio is a cheap exclusion test only.  The Illustrator-normalized path
    signature remains the sole proof used to write a profile.  If an older
    scanner lacks bounds, retain every candidate to preserve compatibility.
    """

    ratios = [
        float(tail["outline_aspect_ratio"])
        for tail in tails
        if isinstance(tail.get("outline_aspect_ratio"), (int, float)) and float(tail["outline_aspect_ratio"]) > 0
    ]
    materialized = list(candidates)
    if not ratios:
        return materialized
    compatible = [
        candidate
        for candidate in materialized
        if candidate.outline_aspect_ratio is not None
        and any(_outline_ratio_matches(float(candidate.outline_aspect_ratio), source_ratio) for source_ratio in ratios)
    ]
    return compatible or materialized


def _outline_ratio_matches(candidate_ratio: float, source_ratio: float) -> bool:
    return abs(candidate_ratio - source_ratio) <= max(0.005, max(candidate_ratio, source_ratio) * 0.002)


def _walk_mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _copy_scan(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _font_name(item: Mapping[str, Any]) -> str:
    for key in ("font_name", "fontName", "font_family", "fontFamily", "text_font", "textFont", "font"):
        value = item.get(key)
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("family")
        if str(value or "").strip():
            return str(value).strip()
    text = item.get("text")
    return _font_name(text) if isinstance(text, Mapping) else ""


def _unique_matched_candidate(
    tail: Mapping[str, str],
    candidates: Iterable[OpenTypeTailGlyph],
    signatures: Mapping[str, str],
) -> tuple[OpenTypeTailGlyph | None, str]:
    matches = [
        (score, candidate)
        for candidate in candidates
        for score in [_outline_match_score(str(tail.get("signature") or ""), signatures.get(_candidate_id(candidate), ""))]
        if score is not None and score <= _MAX_OUTLINE_MEAN_DELTA
    ]
    return _select_unique_candidate_match(matches)


def _unique_vector_matched_candidate(
    tail: Mapping[str, Any],
    candidates: Iterable[OpenTypeTailGlyph],
    shapes: Mapping[str, list[VectorPath]],
) -> tuple[OpenTypeTailGlyph | None, str]:
    source_shape = _illustrator_outline_shape(str(tail.get("signature") or ""))
    if not source_shape:
        return None, ""
    matches = [
        (score, candidate)
        for candidate in candidates
        for score in [_best_vector_outline_match_score(source_shape, shapes.get(_candidate_id(candidate), []))]
        if score is not None and score <= _MAX_VECTOR_OUTLINE_MEAN_DELTA
    ]
    return _select_unique_candidate_match(matches)


def _select_unique_candidate_match(
    matches: Iterable[tuple[float, OpenTypeTailGlyph]],
) -> tuple[OpenTypeTailGlyph | None, str]:
    matches = list(matches)
    if not matches:
        return None, ""
    glyph_names = {candidate.glyph_name for _, candidate in matches}
    if len(glyph_names) != 1:
        return None, "模板样本匹配到多个不同尾巴字形，未写入尾巴配置。"
    pua_profiles = {_pua_profile_key(candidate) for _, candidate in matches if candidate.unicode_codepoint is not None}
    if len(pua_profiles) > 1:
        return None, "模板样本匹配到多个不同 PUA 字形组，未写入尾巴配置。"
    # A font can expose one glyph through both aalt and salt. Those are
    # equivalent outlines, so select one stable profile only after proving
    # glyph identity.
    return min((candidate for _, candidate in matches), key=_canonical_profile_sort_key), ""


def _mark_tail_profile(raw_scan: Mapping[str, Any], path: str, candidate: OpenTypeTailGlyph) -> None:
    for item in _walk_mappings(raw_scan):
        if str(item.get("path") or item.get("layer_path") or "").strip() != path:
            continue
        key = str(item.get("key") or item.get("name") or "").strip()
        if not _TAIL_RE.match(key):
            continue
        if candidate.unicode_codepoint is not None:
            item.pop("opentype_feature", None)
            item.pop("opentype_alternate_index", None)
            if candidate.glyph_map is not None:
                item.pop("pua_base", None)
                item["glyph_map"] = dict(candidate.glyph_map)
            else:
                item.pop("glyph_map", None)
                item["pua_base"] = _pua_base(candidate)
            item["tail_profile_message"] = "已按模板样本轮廓自动匹配 PUA 连续字形。"
        else:
            item["opentype_feature"] = candidate.feature
            item["opentype_alternate_index"] = candidate.alternate_index
            item["tail_profile_message"] = "已按模板样本轮廓自动匹配 OpenType 字形。"
        item["tail_profile_status"] = "auto"
        # The inferer only reaches this point after resolver-level a-z
        # coverage verification.  Preserve that fact for the central service
        # to bind into its signed scanner receipt.
        item["tail_profile_coverage"] = {
            "version": 1,
            "alphabet": "abcdefghijklmnopqrstuvwxyz",
            "verified": True,
        }


def _pua_base(candidate: OpenTypeTailGlyph) -> int:
    if candidate.unicode_codepoint is None:
        raise ValueError("PUA candidate missing codepoint")
    if candidate.pua_base is not None:
        return candidate.pua_base
    return candidate.unicode_codepoint - (ord(candidate.letter) - ord("a"))


def _pua_profile_key(candidate: OpenTypeTailGlyph) -> tuple[str, tuple[tuple[str, int], ...] | int]:
    if candidate.glyph_map is not None:
        return "glyph_map", tuple(sorted((str(letter), int(codepoint)) for letter, codepoint in candidate.glyph_map.items()))
    return "pua_base", _pua_base(candidate)


def _mark_tail_status(raw_scan: Mapping[str, Any], path: str, status: str, message: str) -> None:
    for item in _walk_mappings(raw_scan):
        if str(item.get("path") or item.get("layer_path") or "").strip() != path:
            continue
        key = str(item.get("key") or item.get("name") or "").strip()
        if _TAIL_RE.match(key):
            item["tail_profile_status"] = status
            item["tail_profile_message"] = message


def _candidate_id(candidate: OpenTypeTailGlyph) -> str:
    payload = "\0".join((candidate.font_sha256, candidate.feature, str(candidate.alternate_index), candidate.letter, candidate.glyph_name, str(candidate.unicode_codepoint or "")))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_profile_sort_key(candidate: OpenTypeTailGlyph) -> tuple[int, str, int]:
    """Return the stable preference used when aliases expose one glyph."""

    feature = candidate.feature.casefold()
    preferred = {"aalt": 0, "salt": 1, "swsh": 2}
    if feature in preferred:
        feature_rank = preferred[feature]
    elif re.fullmatch(r"ss\d\d", feature):
        feature_rank = 3
    else:
        feature_rank = 4
    return feature_rank, feature, candidate.alternate_index


def _first_text(current: Any, next_value: Any) -> str:
    return str(current or "").strip() or str(next_value or "").strip()


def _fonttools_glyph_shape(font: TTFont, glyph_name: str) -> list[VectorPath]:
    """Return a scale-free boundary sample for one glyph-table outline."""

    glyph_set = font.getGlyphSet()
    if glyph_name not in glyph_set:
        return []
    glyph = glyph_set[glyph_name]
    bounds_pen = BoundsPen(glyph_set)
    glyph.draw(bounds_pen)
    if not bounds_pen.bounds:
        return []
    x_min, y_min, x_max, y_max = bounds_pen.bounds
    width = float(x_max - x_min)
    height = float(y_max - y_min)
    if width <= 0 or height <= 0:
        return []

    recording = RecordingPen()
    # TrueType quadratic contours are exactly convertible to cubics. A tiny
    # approximation tolerance prevents FontTools from coalescing a long run
    # of off-curve points; the final comparison resamples the visible curve,
    # so it remains independent of the segment count Illustrator chose.
    glyph.draw(Qu2CuPen(recording, 0.01, all_cubic=True))
    paths: list[tuple[str, list[tuple[VectorPoint, VectorPoint, VectorPoint, VectorPoint]]]] = []
    segments: list[tuple[VectorPoint, VectorPoint, VectorPoint, VectorPoint]] = []
    start: VectorPoint | None = None
    current: VectorPoint | None = None

    def finish(closed: bool) -> None:
        nonlocal segments, start, current
        if closed and current is not None and start is not None and current != start:
            segments.append((current, current, start, start))
        if segments:
            paths.append(("C" if closed else "O", segments))
        segments = []
        start = None
        current = None

    for operation, values in recording.value:
        if operation == "moveTo":
            finish(False)
            start = (float(values[0][0]), float(values[0][1]))
            current = start
        elif operation == "lineTo" and current is not None:
            end = (float(values[0][0]), float(values[0][1]))
            segments.append((current, current, end, end))
            current = end
        elif operation == "curveTo" and current is not None:
            controls = [(float(point[0]), float(point[1])) for point in values]
            for index in range(0, len(controls), 3):
                if index + 2 >= len(controls):
                    break
                first, second, end = controls[index:index + 3]
                segments.append((current, first, second, end))
                current = end
        elif operation == "closePath":
            finish(True)
        elif operation == "endPath":
            finish(False)
    finish(False)

    def normalize(point: VectorPoint) -> VectorPoint:
        x = (point[0] - float(x_min)) * 1000.0 / width
        y = (point[1] - float(y_min)) * 1000.0 / height
        return x, y

    # Illustrator and FontTools use opposite document Y directions in some
    # font formats. Store both orientations as separate paths only at compare
    # time, rather than guessing from the font container.
    return [(kind, _resample_cubic_segments(segments, normalize)) for kind, segments in paths]


def _illustrator_outline_shape(value: str) -> list[VectorPath]:
    paths = _deduplicate_outline_paths(_parse_outline_signature(value))
    result: list[VectorPath] = []
    for kind, points in paths:
        if not points:
            continue
        segments: list[tuple[VectorPoint, VectorPoint, VectorPoint, VectorPoint]] = []
        limit = len(points) if kind == "C" else len(points) - 1
        for index in range(max(0, limit)):
            anchor, _left, right = points[index]
            next_anchor, next_left, _next_right = points[(index + 1) % len(points)]
            segments.append((
                (float(anchor[0]), float(anchor[1])),
                (float(right[0]), float(right[1])),
                (float(next_left[0]), float(next_left[1])),
                (float(next_anchor[0]), float(next_anchor[1])),
            ))
        samples = _resample_cubic_segments(segments, lambda point: point)
        if samples:
            result.append((kind, samples))
    return result


def _resample_cubic_segments(
    segments: Iterable[tuple[VectorPoint, VectorPoint, VectorPoint, VectorPoint]],
    normalize: Any,
) -> list[VectorPoint]:
    """Sample a contour by arc length, decoupling matching from node count."""

    polyline: list[VectorPoint] = []
    for first, control_one, control_two, last in segments:
        for step in range(13):
            if polyline and step == 0:
                continue
            t = step / 12.0
            inverse = 1.0 - t
            point = (
                inverse**3 * first[0] + 3.0 * inverse**2 * t * control_one[0] + 3.0 * inverse * t**2 * control_two[0] + t**3 * last[0],
                inverse**3 * first[1] + 3.0 * inverse**2 * t * control_one[1] + 3.0 * inverse * t**2 * control_two[1] + t**3 * last[1],
            )
            polyline.append(normalize(point))
    if len(polyline) < 2:
        return []
    lengths = [0.0]
    for previous, current in zip(polyline, polyline[1:]):
        dx = current[0] - previous[0]
        dy = current[1] - previous[1]
        lengths.append(lengths[-1] + (dx * dx + dy * dy) ** 0.5)
    total = lengths[-1]
    if total <= 0:
        return []
    sampled: list[VectorPoint] = []
    segment_index = 1
    for index in range(_VECTOR_OUTLINE_SAMPLE_COUNT):
        target = total * index / _VECTOR_OUTLINE_SAMPLE_COUNT
        while segment_index < len(lengths) - 1 and lengths[segment_index] < target:
            segment_index += 1
        before = lengths[segment_index - 1]
        after = lengths[segment_index]
        fraction = 0.0 if after <= before else (target - before) / (after - before)
        start = polyline[segment_index - 1]
        end = polyline[segment_index]
        sampled.append((start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction))
    return sampled


def _vector_outline_match_score(source: list[VectorPath], candidate: list[VectorPath]) -> float | None:
    if not source or len(source) != len(candidate):
        return None
    remaining = list(candidate)
    total = 0.0
    coordinate_count = 0
    for source_path in source:
        choices = [
            (index, _vector_path_match_score(source_path, candidate_path))
            for index, candidate_path in enumerate(remaining)
            if candidate_path[0] == source_path[0]
        ]
        choices = [(index, score) for index, score in choices if score is not None]
        if not choices:
            return None
        index, score = min(choices, key=lambda item: item[1])
        total += score
        coordinate_count += len(source_path[1]) * 2
        remaining.pop(index)
    return total / coordinate_count if coordinate_count else None


def _best_vector_outline_match_score(source: list[VectorPath], candidate: list[VectorPath]) -> float | None:
    scores = [
        _vector_outline_match_score(source, candidate),
        _vector_outline_match_score(source, [(kind, [(x, 1000.0 - y) for x, y in points]) for kind, points in candidate]),
    ]
    values = [score for score in scores if score is not None]
    return min(values) if values else None


def _vector_path_match_score(source: VectorPath, candidate: VectorPath) -> float | None:
    if source[0] != candidate[0] or len(source[1]) != len(candidate[1]) or not source[1]:
        return None
    source_points = source[1]
    candidate_points = candidate[1]
    best: float | None = None
    for reverse in (False, True):
        points = list(reversed(candidate_points)) if reverse else candidate_points
        for shift in range(len(points)):
            shifted = points[shift:] + points[:shift]
            score = sum(
                abs(first[0] - second[0]) + abs(first[1] - second[1])
                for first, second in zip(source_points, shifted)
            )
            if best is None or score < best:
                best = score
    return best


def _outline_match_score(source: str, candidate: str) -> float | None:
    """Return normalized Illustrator-outline distance, independent of path start.

    Importing the same glyph from SVG can reverse a contour or choose another
    first point.  The full contour still has the same point count and handles;
    compare all cyclic/reversed forms rather than treating serialization order
    as a semantic difference.
    """

    if source and source == candidate:
        return 0.0
    source_paths = _deduplicate_outline_paths(_parse_outline_signature(source))
    candidate_paths = _deduplicate_outline_paths(_parse_outline_signature(candidate))
    if not source_paths or len(source_paths) != len(candidate_paths):
        return None
    remaining = list(candidate_paths)
    total = 0.0
    coordinate_count = 0
    for source_path in source_paths:
        candidates = [
            (index, _path_match_score(source_path, candidate_path))
            for index, candidate_path in enumerate(remaining)
            if candidate_path[0] == source_path[0] and len(candidate_path[1]) == len(source_path[1])
        ]
        candidates = [(index, score) for index, score in candidates if score is not None]
        if not candidates:
            return None
        index, score = min(candidates, key=lambda item: item[1])
        total += score
        coordinate_count += len(source_path[1]) * 6
        remaining.pop(index)
    return total / coordinate_count if coordinate_count else None


def _deduplicate_outline_paths(paths: list[OutlinePath]) -> list[OutlinePath]:
    """Drop exact geometric duplicates emitted by Illustrator while opening SVG.

    Illustrator may expose a compound path and its component path twice in a
    document-level page-item collection.  An exact duplicate has no additional
    visible geometry, so removing only zero-distance copies keeps comparison
    deterministic without broadening the matching tolerance.
    """

    result: list[OutlinePath] = []
    for path in paths:
        if any(_path_match_score(path, existing) == 0.0 for existing in result):
            continue
        result.append(path)
    return result


def _parse_outline_signature(value: str) -> list[OutlinePath]:
    result: list[OutlinePath] = []
    for raw_path in str(value or "").split("|"):
        parts = raw_path.split(":")
        if len(parts) < 5 or parts[0] not in {"C", "O"}:
            return []
        try:
            point_count = int(parts[1])
        except ValueError:
            return []
        if point_count <= 0 or len(parts[2:]) != point_count * 3:
            return []
        points = [_parse_outline_point(token) for token in parts[2:]]
        if any(point is None for point in points):
            return []
        triples = [tuple(points[index:index + 3]) for index in range(0, len(points), 3)]
        result.append((parts[0], triples))
    return result


def _parse_outline_point(value: str) -> tuple[int, int] | None:
    pair = str(value).split(",")
    if len(pair) != 2:
        return None
    try:
        return int(pair[0]), int(pair[1])
    except ValueError:
        return None


def _path_match_score(
    source: OutlinePath,
    candidate: OutlinePath,
) -> float | None:
    if source[0] != candidate[0] or len(source[1]) != len(candidate[1]):
        return None
    source_points = source[1]
    candidate_points = candidate[1]
    best: float | None = None
    for reversed_path in (False, True):
        points = _reversed_outline_path(candidate_points) if reversed_path else candidate_points
        for shift in range(len(points)):
            shifted = points[shift:] + points[:shift]
            score = _outline_point_distance(source_points, shifted)
            if best is None or score < best:
                best = score
    return best


def _reversed_outline_path(
    points: list[OutlineTriple],
) -> list[OutlineTriple]:
    return [(anchor, right, left) for anchor, left, right in reversed(points)]


def _outline_point_distance(
    first: list[OutlineTriple],
    second: list[OutlineTriple],
) -> float:
    return float(
        sum(
            abs(first_value - second_value)
            for first_point, second_point in zip(first, second)
            for first_handle, second_handle in zip(first_point, second_point)
            for first_value, second_value in zip(first_handle, second_handle)
        )
    )
