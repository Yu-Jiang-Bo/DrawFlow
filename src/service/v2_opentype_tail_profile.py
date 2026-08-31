"""Infer a template tail's OpenType profile from its Illustrator outline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.renderer.v2_opentype_tail import OpenTypeTailError, OpenTypeTailGlyph, OpenTypeTailResolver


_TAIL_RE = re.compile(r"^tail_(?P<field>[A-Za-z0-9_]+)_(?P<position>first|last)_(?P<sample>[A-Za-z])$", re.I)
# The source and candidate are the same Illustrator curve outline expressed
# with integer coordinates in a 0..1000 box.  A real match only differs by
# rounding noise; accepting a visibly different alternate is never safe.
_MAX_OUTLINE_MEAN_DELTA = 0.5
OutlinePoint = tuple[int, int]
OutlineTriple = tuple[OutlinePoint, OutlinePoint, OutlinePoint]
OutlinePath = tuple[str, list[OutlineTriple]]


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
        candidate_ids: dict[str, OpenTypeTailGlyph] = {}
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
            for candidate in candidates:
                candidate_ids[_candidate_id(candidate)] = candidate

        if not candidate_ids:
            return raw
        candidate_signatures = self._probe(candidate_ids, work_dir=Path(work_dir))
        for tail in proven:
            candidates = candidates_by_font_letter.get((tail["font"], tail["letter"]), [])
            matches = [
                (score, candidate)
                for candidate in candidates
                for score in [_outline_match_score(tail["signature"], candidate_signatures.get(_candidate_id(candidate), ""))]
                if score is not None and score <= _MAX_OUTLINE_MEAN_DELTA
            ]
            if not matches:
                _mark_tail_status(
                    raw,
                    tail["path"],
                    "unresolved",
                    "没有匹配到该模板样本的 OpenType 候选字形，未写入尾巴配置。",
                )
                continue
            glyph_names = {candidate.glyph_name for _, candidate in matches}
            if len(glyph_names) != 1:
                _mark_tail_status(
                    raw,
                    tail["path"],
                    "unresolved",
                    "模板样本匹配到多个不同 OpenType 字形，未写入尾巴配置。",
                )
                continue
            # A font can expose one glyph through both aalt and salt. Those
            # are equivalent outlines, so select a canonical *profile* after
            # proving glyph identity. Do not let minute outline-rounding
            # differences choose a different feature on another machine.
            selected = min(
                (candidate for _, candidate in matches),
                key=_canonical_profile_sort_key,
            )
            _mark_tail_profile(raw, tail["path"], selected)
        return raw

    def _probe(self, candidates: Mapping[str, OpenTypeTailGlyph], *, work_dir: Path) -> dict[str, str]:
        task_path = work_dir / f"probe-opentype-tail-{uuid4().hex}.json"
        output_path = task_path.with_name(task_path.stem + "-result.json")
        task = {
            "output_json": str(output_path),
            "candidates": [
                {"id": identifier, "svg_path": str(candidate.path)}
                for identifier, candidate in sorted(candidates.items())
            ],
        }
        task_path.write_text(json.dumps(task, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        try:
            self.bridge.render(self.script_path, task_path)
        except (IllustratorBridgeError, OSError, RuntimeError):
            return {}
        try:
            result = json.loads(output_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = result.get("candidates") if isinstance(result, Mapping) else []
        if not isinstance(entries, list):
            return {}
        return {
            str(entry.get("id") or ""): str(entry.get("outline_signature") or "")
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("id") and entry.get("outline_signature")
        }


def _tail_evidence(raw_scan: Mapping[str, Any]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for item in _walk_mappings(raw_scan):
        key = str(item.get("key") or item.get("name") or "").strip()
        match = _TAIL_RE.match(key)
        if not match:
            continue
        path = str(item.get("path") or item.get("layer_path") or "").strip()
        if not path:
            continue
        record = merged.setdefault(path, {"path": path, "letter": match.group("sample").casefold(), "font": "", "signature": ""})
        record["letter"] = str(item.get("sample") or match.group("sample")).casefold()
        record["font"] = _first_text(record["font"], _font_name(item))
        record["signature"] = _first_text(record["signature"], item.get("outline_signature"))
    return [merged[key] for key in sorted(merged, key=str.casefold)]


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


def _mark_tail_profile(raw_scan: Mapping[str, Any], path: str, candidate: OpenTypeTailGlyph) -> None:
    for item in _walk_mappings(raw_scan):
        if str(item.get("path") or item.get("layer_path") or "").strip() != path:
            continue
        key = str(item.get("key") or item.get("name") or "").strip()
        if not _TAIL_RE.match(key):
            continue
        item["opentype_feature"] = candidate.feature
        item["opentype_alternate_index"] = candidate.alternate_index
        item["tail_profile_status"] = "auto"
        item["tail_profile_message"] = "已按模板样本轮廓自动匹配 OpenType 字形。"


def _mark_tail_status(raw_scan: Mapping[str, Any], path: str, status: str, message: str) -> None:
    for item in _walk_mappings(raw_scan):
        if str(item.get("path") or item.get("layer_path") or "").strip() != path:
            continue
        key = str(item.get("key") or item.get("name") or "").strip()
        if _TAIL_RE.match(key):
            item["tail_profile_status"] = status
            item["tail_profile_message"] = message


def _candidate_id(candidate: OpenTypeTailGlyph) -> str:
    payload = "\0".join((candidate.font_sha256, candidate.feature, str(candidate.alternate_index), candidate.letter, candidate.glyph_name))
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


def _outline_match_score(source: str, candidate: str) -> float | None:
    """Return normalized Illustrator-outline distance, independent of path start.

    Importing the same glyph from SVG can reverse a contour or choose another
    first point.  The full contour still has the same point count and handles;
    compare all cyclic/reversed forms rather than treating serialization order
    as a semantic difference.
    """

    if source and source == candidate:
        return 0.0
    source_paths = _parse_outline_signature(source)
    candidate_paths = _parse_outline_signature(candidate)
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
