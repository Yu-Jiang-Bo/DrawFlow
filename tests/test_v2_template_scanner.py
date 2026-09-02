import json
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from src.service import v2_template_scanner as scanner_module
from src.renderer.v2_opentype_tail import OpenTypeTailGlyph
from src.service.v2_opentype_tail_profile import (
    OpenTypeTailProfileInferer,
    _illustrator_outline_shape,
    _outline_match_score,
)
from src.service.v2_template_scanner import (
    V2_SCAN_PROTOCOL_VERSION,
    V2TemplateScanner,
    V2TemplateScannerError,
    evidence_is_current,
    normalize_v2_template_scan,
)


def group(path, name=None, **extra):
    return {"type": "GroupItem", "name": name or Path(path).name, "path": path, **extra}


def layer(path, name=None, **extra):
    return {"type": "Layer", "name": name or Path(path).name, "path": path, **extra}


def text(path, name=None, **extra):
    return {
        "type": "TextFrame",
        "name": name or Path(path).name,
        "path": path,
        "font_name": "Milkshake",
        **extra,
    }


def path_item(path, name=None, **extra):
    return {"type": "PathItem", "name": name or Path(path).name, "path": path, **extra}


def base_raw_scan(*items):
    return {
        "document": {"illustrator_version": "28.7.1", "template_sha256": "template-hash"},
        "scanned_at": "2026-08-07T00:00:00Z",
        "items": list(items),
    }


def valid_scan_items():
    return [
        group("Template", "Template"),
        group("Template/Output_main", "Output_main"),
        group("Template/Output_main/Style", "Style"),
        path_item("Template/Output_main/Style/style1", "style1", bounds=[0, 72, 144, 0], closed_dimension_box=True),
        group("Template/Output_main/Design", "Design"),
        group("Template/Output_main/Design/Design03", "Design03"),
        text("Template/Output_main/Design/Design03/slot_name", "slot_name"),
        path_item("Template/Output_main/Design/Design03/anchor_name", "anchor_name"),
        group("Template/Output_main/Font", "Font"),
        group("Template/Output_main/Font/F1", "F1"),
        text("Template/Output_main/Font/F1/slot_name", "slot_name", font_name="ArialMT"),
        group("Template/Colors", "Colors"),
        path_item(
            "Template/Colors/Pink",
            "Pink",
            fill_color={"typename": "RGBColor", "red": 255, "green": 192, "blue": 203},
        ),
    ]


def issue_codes(result):
    return {issue["code"] for issue in result["issues"]}


def complete_alternate_coverage(**_kwargs):
    return {letter: f"{letter}.tail" for letter in "abcdefghijklmnopqrstuvwxyz"}


class WritingBridge:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def render(self, script_path, task_path):
        task = json.loads(Path(task_path).read_text(encoding="utf-8"))
        self.calls.append({"script_path": Path(script_path), "task_path": Path(task_path), "task": task})
        Path(task["output_json"]).write_text(
            json.dumps(
                {
                    "document": {
                        "source_ai": task["input_ai"],
                        "illustrator_version": "29.0",
                    },
                    "scanned_at": "2026-08-07T00:00:00Z",
                    "items": self.items,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


class SilentBridge:
    def render(self, script_path, task_path):
        return ""


def test_normalizes_scan_with_stable_sorting_and_digest():
    first = base_raw_scan(*reversed(valid_scan_items()), group("Outside/Junk", "Junk"))
    second = base_raw_scan(*valid_scan_items())

    a = normalize_v2_template_scan(first)
    b = normalize_v2_template_scan(second)

    assert a["blocked"] is False
    assert b["blocked"] is False
    assert [output["key"] for output in a["outputs"]] == ["Output_main"]
    assert a["outputs"][0]["style"]["options"][0]["key"] == "style1"
    assert a["outputs"][0]["style"]["options"][0]["closed_dimension_box"] is True
    assert a["outputs"][0]["design"]["options"][0]["slots"][0]["key"] == "slot_name"
    assert a["evidence"]["object_path_digest"] == b["evidence"]["object_path_digest"]
    assert a["evidence"]["scan_protocol_version"] == V2_SCAN_PROTOCOL_VERSION


def test_accepts_single_output_alias_and_spaced_design_font_names():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output", "Output"),
            group("Template/Output/Design", "Design"),
            group("Template/Output/Design/Design 1", "Design 1"),
            text("Template/Output/Design/Design 1/slot_name", "slot_name"),
            path_item("Template/Output/Design/Design 1/anchor_name", "anchor_name"),
            text("Template/Output/Design/Design 1/slot_logo", "slot_logo"),
            text("Template/Output/Design/Design 1/tail_name_last_m", "tail_name_last_m"),
            group("Template/Output/Design/Design 1/Assets", "Assets"),
            group("Template/Output/Design/Design 1/Assets/logo", "logo"),
            group("Template/Output/Design/Design 1/Assets/logo/A", "A"),
            group("Template/Output/Design/design19", "design19"),
            text("Template/Output/Design/design19/slot_title", "slot_title"),
            group("Template/Output/Font", "Font"),
            group("Template/Output/Font/F 1", "F 1"),
            text("Template/Output/Font/F 1/slot_name", "slot_name"),
            group("Template/Output/Font/f2", "f2"),
            text("Template/Output/Font/f2/slot_title", "slot_title"),
        )
    )

    output = result["outputs"][0]
    assert result["blocked"] is False
    assert output["key"] == "Output_main"
    assert [option["key"] for option in output["design"]["options"]] == ["Design1", "design19"]
    assert [option["key"] for option in output["font"]["options"]] == ["F1", "f2"]


def test_blocks_equivalent_output_and_option_names_after_normalization():
    duplicate_output = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output", "Output"),
            group("Template/Output_main", "Output_main"),
        )
    )
    duplicate_design = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output", "Output"),
            group("Template/Output/Design", "Design"),
            group("Template/Output/Design/Design1", "Design1"),
            text("Template/Output/Design/Design1/slot_name", "slot_name"),
            group("Template/Output/Design/Design01", "Design01"),
            text("Template/Output/Design/Design01/slot_title", "slot_title"),
        )
    )

    assert duplicate_output["blocked"] is True
    assert "duplicate_output" in issue_codes(duplicate_output)
    assert duplicate_design["blocked"] is True
    assert "duplicate_design_option" in issue_codes(duplicate_design)


def test_single_text_font_without_slot_becomes_default_font_reference():
    items = valid_scan_items()
    for item in items:
        if item["path"] == "Template/Output_main/Font/F1/slot_name":
            item["name"] = "font_sample"
            item["path"] = "Template/Output_main/Font/F1/font_sample"
            break

    result = normalize_v2_template_scan(base_raw_scan(*items))

    font = result["outputs"][0]["fonts"][0]
    assert result["blocked"] is False
    assert font["slots"] == []
    assert font["font_reference"]["path"] == "Template/Output_main/Font/F1/font_sample"
    assert font["font_reference"]["font_dependencies"] == ["ArialMT"]


def test_multi_text_font_without_slots_is_not_guessed_as_font_reference():
    items = valid_scan_items()
    for item in items:
        if item["path"] == "Template/Output_main/Font/F1/slot_name":
            item["name"] = "font_sample_a"
            item["path"] = "Template/Output_main/Font/F1/font_sample_a"
            break
    items.append(text("Template/Output_main/Font/F1/font_sample_b", "font_sample_b", font_name="ArialMT"))

    result = normalize_v2_template_scan(base_raw_scan(*items))

    font = result["outputs"][0]["fonts"][0]
    assert result["blocked"] is False
    assert font["slots"] == []
    assert "font_reference" not in font
    pending = next(issue for issue in result["issues"] if issue["code"] == "font_reference_confirmation_required")
    assert pending["status"] == "pending"
    assert pending["path"] == "Template/Output_main/Font/F1"


def test_template_named_layer_does_not_count_as_duplicate_root():
    items = [
        layer("Template", "Template"),
        group("Template/Template", "Template"),
        group("Template/Template/Output_main", "Output_main"),
        group("Template/Template/Output_main/Font", "Font"),
        group("Template/Template/Output_main/Font/F1", "F1"),
        text("Template/Template/Output_main/Font/F1/slot_name", "slot_name"),
    ]

    result = normalize_v2_template_scan(base_raw_scan(*items))

    assert "template_root_multiple" not in issue_codes(result)
    assert result["blocked"] is False
    assert result["outputs"][0]["key"] == "Output_main"
    assert result["outputs"][0]["fonts"][0]["key"] == "F1"
    assert result["outputs"][0]["fonts"][0]["slots"][0]["key"] == "slot_name"


def test_normalizes_slot_keep_ratio_marker_for_composition_preservation():
    items = valid_scan_items()
    for item in items:
        if item["path"] == "Template/Output_main/Design/Design03/slot_name":
            item["preserve_composition"] = True
            break

    result = normalize_v2_template_scan(base_raw_scan(*items))

    slot = result["outputs"][0]["design"]["options"][0]["slots"][0]
    assert slot["preserve_composition"] is True


def test_reports_missing_and_multiple_template_roots():
    missing = normalize_v2_template_scan(base_raw_scan(group("Template Copy", "Template Copy")))
    multiple = normalize_v2_template_scan(
        base_raw_scan(group("Template", "Template"), group("Other/Template", "Template"))
    )

    assert missing["blocked"] is True
    assert "template_root_missing" in issue_codes(missing)
    assert multiple["blocked"] is True
    assert "template_root_multiple" in issue_codes(multiple)
    paths = next(issue["layer_paths"] for issue in multiple["issues"] if issue["code"] == "template_root_multiple")
    assert paths == ["Other/Template", "Template"]


def test_reports_duplicate_names_with_all_layer_paths():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Font", "Font"),
            group("Template/Output_main/Font/F1", "F1"),
            text("Template/Output_main/Font/F1/slot_name", "slot_name"),
            text("Template/Output_main/Font/F1/slot_NAME_copy", " slot_NAME "),
        )
    )

    duplicate = next(issue for issue in result["issues"] if issue["code"] == "duplicate_name")
    assert result["blocked"] is True
    assert duplicate["layer_paths"] == [
        "Template/Output_main/Font/F1/slot_name",
        "Template/Output_main/Font/F1/slot_NAME_copy",
    ]


def test_reports_wrong_hierarchy_and_bad_output_sequence():
    wrong_hierarchy = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            text("Template/Output_main/slot_name", "slot_name"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design-3", "Design-3"),
        )
    )
    bad_sides = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_SideA", "Output_SideA"),
            group("Template/Output_SideC", "Output_SideC"),
        )
    )

    assert {"marker_wrong_hierarchy", "design_option_name_invalid"} <= issue_codes(wrong_hierarchy)
    assert "output_sequence_invalid" in issue_codes(bad_sides)


def test_reports_wrong_hierarchy_from_jsx_raw_items():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Style", "Style"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/slot_name", "slot_name"),
            group("Template/Output_main/Assets", "Assets"),
        )
    )

    assert {"container_wrong_hierarchy", "marker_wrong_hierarchy", "assets_wrong_hierarchy"} <= issue_codes(result)


def test_marker_visible_bounds_are_preserved():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name", visible_bounds=[0, 72, 144, 0]),
            path_item("Template/Output_main/Design/Design03/anchor_name", "anchor_name", visible_bounds=[1, 71, 143, 1]),
            text(
                "Template/Output_main/Design/Design03/tail_name_first_a",
                "tail_name_first_a",
                visible_bounds=[2, 70, 20, 2],
                position="first",
                sample="a",
                related_slot="slot_name",
                text="a",
                font_name="TailFont",
            ),
        )
    )

    option = result["outputs"][0]["design"]["options"][0]
    assert option["slots"][0]["visible_bounds"] == [0, 72, 144, 0]
    assert option["slots"][0]["dimensions"] == {"width_mm": 50.8, "height_mm": 25.4}
    assert option["anchors"][0]["visible_bounds"] == [1, 71, 143, 1]
    assert option["tails"][0]["visible_bounds"] == [2, 70, 20, 2]
    assert option["tails"][0]["position"] == "first"
    assert option["tails"][0]["sample"] == "a"
    assert option["tails"][0]["related_slot"] == "slot_name"
    assert option["tails"][0]["text"] == "a"
    assert option["tails"][0]["font_dependencies"] == ["TailFont"]


def test_preserves_auto_matched_opentype_tail_profile_from_scanned_evidence():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name"),
            text(
                "Template/Output_main/Design/Design03/tail_name_first_c",
                "tail_name_first_c",
                position="first",
                sample="c",
                font_name="TailFont",
                opentype_feature="aalt",
                opentype_alternate_index=2,
                tail_profile_status="auto",
                tail_profile_message="matched",
            ),
        )
    )

    tail = result["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    assert tail["opentype_feature"] == "aalt"
    assert tail["opentype_alternate_index"] == 2
    assert tail["tail_profile_status"] == "auto"


def test_preserves_auto_matched_pua_tail_profile_from_scanned_evidence():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name"),
            text(
                "Template/Output_main/Design/Design03/tail_name_last_m",
                "tail_name_last_m",
                position="last",
                sample="m",
                font_name="TailFont",
                pua_base=0xE040,
                tail_profile_status="auto",
            ),
        )
    )

    tail = result["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    assert tail["pua_base"] == 0xE040
    assert tail["tail_profile_status"] == "auto"


def test_outline_profile_inference_sets_only_the_matching_template_profile(tmp_path):
    class Resolver:
        verify_alternate_coverage = staticmethod(complete_alternate_coverage)

        def materialize_alternate_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(
                    path=tmp_path / "aalt-1.svg",
                    glyph_name="c.1",
                    font_postscript_name="TailFont",
                    font_sha256="font-hash",
                    feature="aalt",
                    alternate_index=1,
                    letter="c",
                ),
                OpenTypeTailGlyph(
                    path=tmp_path / "aalt-2.svg",
                    glyph_name="c.2",
                    font_postscript_name="TailFont",
                    font_sha256="font-hash",
                    feature="aalt",
                    alternate_index=2,
                    letter="c",
                ),
            ]

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "id": item["id"],
                                "outline_signature": "sample-signature" if item["svg_path"].endswith("aalt-2.svg") else "other",
                            }
                            for item in task["candidates"]
                        ]
                    }
                ),
                encoding="utf-8",
            )

    raw = {
        "items": [
            {
                "name": "tail_name_first_c",
                "path": "Template/Output_main/Design/Design03/tail_name_first_c",
                "font": {"name": "TailFont"},
                "outline_signature": "sample-signature",
            }
        ]
    }

    result = OpenTypeTailProfileInferer(bridge=ProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)

    tail = result["items"][0]
    assert tail["opentype_feature"] == "aalt"
    assert tail["opentype_alternate_index"] == 2
    assert tail["tail_profile_status"] == "auto"
    assert "opentype_feature" not in raw["items"][0]


def test_outline_profile_inference_uses_font_outline_before_svg_probe(tmp_path):
    source_signature = "C:2:0,0:0,0:0,0:1000,0:1000,0:1000,0"

    class Resolver:
        verify_alternate_coverage = staticmethod(complete_alternate_coverage)

        def materialize_alternate_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(tmp_path / "aalt-1.svg", "c.1", "TailFont", "font-hash", "aalt", 1, "c"),
                OpenTypeTailGlyph(tmp_path / "aalt-2.svg", "c.2", "TailFont", "font-hash", "aalt", 2, "c"),
            ]

    class NeverProbeBridge:
        def render(self, *_args):
            raise AssertionError("a proven font outline must not import SVG through Illustrator")

    class VectorInferer(OpenTypeTailProfileInferer):
        def _fonttools_shapes(self, candidates):
            return {
                identifier: _illustrator_outline_shape(source_signature)
                for identifier, candidate in candidates.items()
                if candidate.glyph_name == "c.2"
            }

    raw = {"items": [{
        "name": "tail_name_first_c",
        "path": "Template/Output_main/Design/Design03/tail_name_first_c",
        "font": {"name": "TailFont"},
        "outline_signature": source_signature,
    }]}

    result = VectorInferer(bridge=NeverProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)

    assert result["items"][0]["opentype_feature"] == "aalt"
    assert result["items"][0]["opentype_alternate_index"] == 2


def test_outline_profile_match_ignores_contour_direction_and_start_point():
    source = "C:2:0,0:0,1:1,0:10,0:10,1:11,0"
    imported_svg = "C:2:10,0:11,0:10,1:0,0:1,0:0,1"

    assert _outline_match_score(source, imported_svg) == 0.0


def test_outline_profile_match_ignores_exact_duplicate_paths_from_svg_opening():
    source = "C:2:0,0:0,1:1,0:10,0:10,1:11,0"
    duplicated_import = source + "|C:2:10,0:11,0:10,1:0,0:1,0:0,1"

    assert _outline_match_score(source, duplicated_import) == 0.0


def test_outline_profile_match_uses_a_half_point_rounding_boundary():
    source = "C:1:0,0:0,0:0,0"
    within_rounding_noise = "C:1:3,0:0,0:0,0"
    outside_rounding_noise = "C:1:4,0:0,0:0,0"

    assert _outline_match_score(source, within_rounding_noise) == 0.5
    assert _outline_match_score(source, outside_rounding_noise) > 0.5


def test_outline_profile_inference_uses_canonical_profile_for_same_glyph_aliases(tmp_path):
    class Resolver:
        verify_alternate_coverage = staticmethod(complete_alternate_coverage)

        def materialize_alternate_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(tmp_path / "swsh-1.svg", "c.tail", "TailFont", "font-hash", "swsh", 1, "c"),
                OpenTypeTailGlyph(tmp_path / "aalt-2.svg", "c.tail", "TailFont", "font-hash", "aalt", 2, "c"),
            ]

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps({"candidates": [{"id": item["id"], "outline_signature": "sample-signature"} for item in task["candidates"]]}),
                encoding="utf-8",
            )

    raw = {
        "items": [{
            "name": "tail_name_first_c",
            "path": "Template/Output_main/Design/Design03/tail_name_first_c",
            "font": {"name": "TailFont"},
            "outline_signature": "sample-signature",
        }]
    }

    tail = OpenTypeTailProfileInferer(bridge=ProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)["items"][0]

    assert tail["tail_profile_status"] == "auto"
    assert tail["opentype_feature"] == "aalt"
    assert tail["opentype_alternate_index"] == 2


def test_outline_profile_inference_falls_back_to_proven_contiguous_pua_profile(tmp_path):
    class Resolver:
        def materialize_alternate_candidates(self, **_kwargs):
            return []

        def materialize_contiguous_pua_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(
                    path=tmp_path / "pua-e04c.svg",
                    glyph_name="m.tail",
                    font_postscript_name="TailFont",
                    font_sha256="font-hash",
                    feature="pua",
                    alternate_index=0,
                    letter="m",
                    unicode_codepoint=0xE04C,
                )
            ]

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps({"candidates": [{"id": item["id"], "outline_signature": "sample-signature"} for item in task["candidates"]]}),
                encoding="utf-8",
            )

    raw = {
        "items": [{
            "name": "tail_name_last_m",
            "path": "Template/Output_main/Font/F2/tail_name_last_m",
            "font": {"name": "TailFont"},
            "outline_signature": "sample-signature",
        }]
    }

    tail = OpenTypeTailProfileInferer(bridge=ProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)["items"][0]

    assert tail["tail_profile_status"] == "auto"
    assert tail["pua_base"] == 0xE040
    assert "opentype_feature" not in tail


def test_outline_profile_probe_splits_large_candidate_sets_into_isolated_batches(tmp_path):
    calls = []

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            calls.append(task["candidates"])
            Path(task["output_json"]).write_text(
                json.dumps({"candidates": [
                    {"id": item["id"], "outline_signature": item["id"]}
                    for item in task["candidates"]
                ]}),
                encoding="utf-8",
            )

    candidates = {
        f"candidate-{index}": OpenTypeTailGlyph(
            path=tmp_path / f"candidate-{index}.svg",
            glyph_name=f"m.{index}",
            font_postscript_name="TailFont",
            font_sha256="font-hash",
            feature="aalt",
            alternate_index=index + 1,
            letter="m",
        )
        for index in range(13)
    }

    result = OpenTypeTailProfileInferer(bridge=ProbeBridge())._probe(candidates, work_dir=tmp_path)

    assert [len(call) for call in calls] == [12, 1]
    assert result == {identifier: identifier for identifier in candidates}


def test_outline_profile_inference_does_not_choose_between_distinct_matched_glyphs(tmp_path):
    class Resolver:
        verify_alternate_coverage = staticmethod(complete_alternate_coverage)

        def materialize_alternate_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(tmp_path / "one.svg", "c.1", "TailFont", "font-hash", "aalt", 1, "c"),
                OpenTypeTailGlyph(tmp_path / "two.svg", "c.2", "TailFont", "font-hash", "aalt", 2, "c"),
            ]

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps({"candidates": [{"id": item["id"], "outline_signature": "sample-signature"} for item in task["candidates"]]}),
                encoding="utf-8",
            )

    raw = {
        "items": [{
            "name": "tail_name_first_c",
            "path": "Template/Output_main/Design/Design03/tail_name_first_c",
            "font": {"name": "TailFont"},
            "outline_signature": "sample-signature",
        }]
    }

    tail = OpenTypeTailProfileInferer(bridge=ProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)["items"][0]

    assert "opentype_feature" not in tail
    assert tail["tail_profile_status"] == "unresolved"
    assert "多个不同" in tail["tail_profile_message"]


def test_outline_profile_inference_does_not_persist_an_incomplete_opentype_coverage(tmp_path):
    class Resolver:
        @staticmethod
        def verify_alternate_coverage(**_kwargs):
            return {"c": "c.tail"}

        def materialize_alternate_candidates(self, **_kwargs):
            return [
                OpenTypeTailGlyph(tmp_path / "aalt-2.svg", "c.tail", "TailFont", "font-hash", "aalt", 2, "c"),
            ]

        def materialize_contiguous_pua_candidates(self, **_kwargs):
            return []

    class ProbeBridge:
        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps({"candidates": [{"id": item["id"], "outline_signature": "sample-signature"} for item in task["candidates"]]}),
                encoding="utf-8",
            )

    raw = {"items": [{
        "name": "tail_name_first_c",
        "path": "Template/Output_main/Design/Design03/tail_name_first_c",
        "font": {"name": "TailFont"},
        "outline_signature": "sample-signature",
    }]}

    tail = OpenTypeTailProfileInferer(bridge=ProbeBridge(), resolver=Resolver()).apply(raw, work_dir=tmp_path)["items"][0]

    assert "opentype_feature" not in tail
    assert tail["tail_profile_status"] == "unresolved"
    assert "完整覆盖" in tail["tail_profile_message"]


def test_scanner_marks_tail_unresolved_when_the_auto_probe_raises(tmp_path):
    class RaisingInferer:
        def apply(self, *_args, **_kwargs):
            raise RuntimeError("probe failed")

    raw = {
        "items": [{
            "name": "tail_name_first_c",
            "path": "Template/Output_main/Design/Design03/tail_name_first_c",
            "outline_signature": "sample-signature",
        }]
    }

    result = V2TemplateScanner(tail_profile_inferer=RaisingInferer())._infer_opentype_tail_profiles(raw, tmp_path)

    assert result["items"][0]["tail_profile_status"] == "unresolved"


def test_opentype_tail_probe_opens_each_svg_without_creating_a_blank_document():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "illustrator"
        / "probe_v2_opentype_tail_candidates.jsx"
    ).read_text(encoding="utf-8")

    assert "document = app.open(source);" in source
    assert "function documentBounds(document)" in source
    assert "function topLevelDocumentItems(document)" in source
    assert "function uniquePathSignatures(paths)" in source
    assert "app.documents.add(" not in source


def test_design_option_visible_bounds_are_preserved_as_output_dimensions():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group(
                "Template/Output_main/Design/Design14",
                "Design14",
                visible_bounds=[0, 160, 440, 0],
            ),
            text("Template/Output_main/Design/Design14/slot_name1", "slot_name1"),
        )
    )

    option = result["outputs"][0]["design"]["options"][0]
    assert option["visible_bounds"] == [0, 160, 440, 0]
    assert option["dimensions"] == {"width_mm": 155.222, "height_mm": 56.444}


def test_tail_samples_match_slot_field_exactly_not_by_prefix():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name"),
            text("Template/Output_main/Design/Design03/tail_name_first_a", "tail_name_first_a"),
            text("Template/Output_main/Design/Design03/tail_name_extra_first_a", "tail_name_extra_first_a"),
        )
    )

    slot = result["outputs"][0]["design"]["options"][0]["slots"][0]
    assert [tail["key"] for tail in slot["tails"]] == ["tail_name_first_a"]


def test_same_slot_name_under_different_designs_does_not_conflict():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name"),
            group("Template/Output_main/Design/Design05", "Design05"),
            text("Template/Output_main/Design/Design05/slot_name", "slot_name"),
        )
    )

    assert "duplicate_name" not in issue_codes(result)
    assert [option["key"] for option in result["outputs"][0]["design"]["options"]] == ["Design03", "Design05"]


def test_design_assets_must_match_local_slot_key():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template", source_ai="C:/main.ai"),
            group("Template/Output_main", "Output_main", source_ai="C:/main.ai"),
            group("Template/Output_main/Design", "Design", source_ai="C:/main.ai"),
            group("Template/Output_main/Design/Design03", "Design03", source_ai="C:/main.ai"),
            text("Template/Output_main/Design/Design03/slot_name", "slot_name", source_ai="C:/main.ai"),
            group("Template/Output_main/Design/Design03/Assets", "Assets", source_ai="C:/main.ai"),
            group("Template/Output_main/Design/Design03/Assets/initial", "initial", source_ai="C:/other.ai"),
            group("Template/Output_main/Design/Design03/Assets/initial/A", "A", source_ai="C:/other.ai"),
        )
    )

    assert {"asset_slot_missing", "asset_not_local"} <= issue_codes(result)
    asset = result["outputs"][0]["design"]["options"][0]["assets"][0]
    assert asset["asset_key"] == "initial"
    assert asset["slot"] == "slot_initial"


def test_design_assets_with_matching_slot_are_scanned_per_design_scope():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_initial", "slot_initial"),
            group("Template/Output_main/Design/Design03/Assets", "Assets"),
            group("Template/Output_main/Design/Design03/Assets/initial", "initial"),
            group("Template/Output_main/Design/Design03/Assets/initial/A", "A"),
            group("Template/Output_main/Design/Design05", "Design05"),
            text("Template/Output_main/Design/Design05/slot_initial", "slot_initial"),
        )
    )

    assert "asset_slot_missing" not in issue_codes(result)
    design03, design05 = result["outputs"][0]["design"]["options"]
    assert design03["slots"][0]["asset_key"] == "initial"
    assert design05["slots"][0].get("asset_key") is None


def test_evidence_hash_invalidates_when_ai_file_changes():
    ai = Path("output") / ".pytest-v2-template-scanner-template.ai"
    ai.parent.mkdir(parents=True, exist_ok=True)
    try:
        ai.write_bytes(b"first")
        result = normalize_v2_template_scan(base_raw_scan(*valid_scan_items()), ai_path=ai)

        assert evidence_is_current(result["evidence"], ai) is True

        ai.write_bytes(b"second")

        assert evidence_is_current(result["evidence"], ai) is False
    finally:
        if ai.exists():
            ai.unlink()


def test_v2_template_scanner_runs_bridge_and_normalizes_output(tmp_path):
    ai = tmp_path / "template.ai"
    ai.write_bytes(b"ai-bytes")
    bridge = WritingBridge(valid_scan_items())
    scanner = V2TemplateScanner(bridge=bridge, work_dir=tmp_path / "tasks")

    result = scanner.scan(ai, template_id="V2SCAN001", fields={"name": "Demo"})

    assert result["blocked"] is False
    assert result["outputs"][0]["key"] == "Output_main"
    assert result["evidence"]["template_sha256"] == hashlib.sha256(b"ai-bytes").hexdigest()
    assert result["document"]["source_ai"] == "template.ai"
    assert bridge.calls[0]["script_path"].name == "scan_v2_template.jsx"
    assert bridge.calls[0]["task"]["input_ai"] == str(ai)
    assert Path(bridge.calls[0]["task"]["output_json"]).is_file()


def test_v2_template_scanner_uses_isolated_illustrator_session_by_default(tmp_path, monkeypatch):
    ai = tmp_path / "template.ai"
    ai.write_bytes(b"ai-bytes")
    bridge_kwargs = []

    class RecordingBridge:
        def __init__(self, **kwargs):
            bridge_kwargs.append(kwargs)

        def render(self, _script_path, task_path):
            task = json.loads(Path(task_path).read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps(base_raw_scan(*valid_scan_items()), ensure_ascii=False),
                encoding="utf-8",
            )

    monkeypatch.setattr(scanner_module, "IllustratorBridge", RecordingBridge)
    scanner = V2TemplateScanner(work_dir=tmp_path / "tasks")

    result = scanner.scan(ai)

    assert result["blocked"] is False
    assert bridge_kwargs == [{"visible": False, "fresh_instance": True, "quit_after": True}]


def test_v2_template_scanner_reports_missing_json_without_fake_success(tmp_path):
    ai = tmp_path / "template.ai"
    ai.write_bytes(b"ai-bytes")
    scanner = V2TemplateScanner(bridge=SilentBridge(), work_dir=tmp_path / "tasks")

    with pytest.raises(V2TemplateScannerError) as exc_info:
        scanner.scan(ai)

    assert exc_info.value.code == "v2_scan_output_missing"
    assert "没有生成扫描结果" in str(exc_info.value)


def test_missing_template_sha256_blocks_scan_evidence():
    raw = base_raw_scan(*valid_scan_items())
    raw["document"].pop("template_sha256")

    result = normalize_v2_template_scan(raw)

    assert result["blocked"] is True
    assert "template_sha256_missing" in issue_codes(result)


def test_recommendations_are_pending_and_based_on_scan_facts():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design03", "Design03"),
            text("Template/Output_main/Design/Design03/slot_initial", "slot_initial"),
            group("Template/Output_main/Design/Design03/Assets", "Assets"),
            group("Template/Output_main/Design/Design03/Assets/initial", "initial"),
            group("Template/Output_main/Design/Design03/Assets/initial/A", "A"),
            group("Template/Output_main/Design/Design05", "Design05"),
            text("Template/Output_main/Design/Design05/slot_name", "slot_name"),
            path_item("Template/Output_main/Design/Design05/tail_name_first_a", "tail_name_first_a"),
            group("Template/Output_main/Font", "Font"),
            group("Template/Output_main/Font/F10", "F10"),
            text("Template/Output_main/Font/F10/slot_title", "slot_title", text_kind="TextType.PATHTEXT"),
        )
    )

    presets = {item["preset"] for item in result["recommendations"]}
    assert {"initial_with_text", "direct_text", "path_text", "design_font_combo"} <= presets
    assert "tail_text" not in presets
    assert {item["status"] for item in result["recommendations"]} == {"pending"}


def test_recommends_slotwise_handling_for_multiple_slots_with_tail_sample():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Design", "Design"),
            group("Template/Output_main/Design/Design02", "Design02"),
            text("Template/Output_main/Design/Design02/slot_name1", "slot_name1"),
            text("Template/Output_main/Design/Design02/slot_title", "slot_title"),
            text("Template/Output_main/Design/Design02/tail_name1_last_m", "tail_name1_last_m"),
        )
    )

    recommendation = next(item for item in result["recommendations"] if item["path"].endswith("/Design02"))

    assert recommendation["preset"] == "mixed_slots"
    assert "分别确认" in recommendation["reason"]


def test_font_and_color_dependencies_are_recorded_and_invalid_fills_block():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Output_main/Font", "Font"),
            group("Template/Output_main/Font/F1", "F1", font_name="Milkshake"),
            text("Template/Output_main/Font/F1/slot_name", "slot_name", font_name="ArialMT"),
            group("Template/Colors", "Colors"),
            path_item("Template/Colors/Black", "Black", fill_color={"cmyk": [0, 0, 0, 100]}),
            group("Template/Colors/Mixed", "Mixed"),
            path_item("Template/Colors/Mixed/a", "a", fill_color={"rgb": [1, 2, 3]}),
            path_item("Template/Colors/Mixed/b", "b", fill_color={"rgb": [3, 2, 1]}),
            path_item("Template/Colors/Gradient", "Gradient", fill_color={"typename": "GradientColor"}),
            path_item("Template/Colors/Pattern", "Pattern", fill_type="pattern"),
        )
    )

    assert {"color_fill_inconsistent", "gradient_fill", "pattern_fill"} <= issue_codes(result)
    assert result["dependencies"]["fonts"] == [
        {"scope": "option", "path": "Template/Output_main/Font/F1", "font_name": "ArialMT"},
        {"scope": "option", "path": "Template/Output_main/Font/F1", "font_name": "Milkshake"},
        {"scope": "slot", "path": "Template/Output_main/Font/F1/slot_name", "font_name": "ArialMT"},
    ]
    assert result["colors"][0]["key"] == "Black"
    assert result["colors"][0]["space"] == "CMYK"


def test_spot_tint_is_recorded_and_inconsistent_tints_block():
    result = normalize_v2_template_scan(
        base_raw_scan(
            group("Template", "Template"),
            group("Template/Output_main", "Output_main"),
            group("Template/Colors", "Colors"),
            path_item("Template/Colors/Gold", "Gold", fill_color={"space": "SPOT", "spot": "Gold Ink", "tint": 50}),
            group("Template/Colors/MixedGold", "MixedGold"),
            path_item("Template/Colors/MixedGold/a", "a", fill_color={"space": "SPOT", "spot": "Gold Ink", "tint": 50}),
            path_item("Template/Colors/MixedGold/b", "b", fill_color={"space": "SPOT", "spot": "Gold Ink", "tint": 80}),
        )
    )

    assert "color_fill_inconsistent" in issue_codes(result)
    assert result["colors"] == [
        {
            "key": "Gold",
            "path": "Template/Colors/Gold",
            "space": "SPOT",
            "value": "Gold Ink",
            "tint": 50.0,
            "source_paths": ["Template/Colors/Gold"],
        }
    ]


def test_normalizes_nested_jsx_scan_contract():
    raw = {
        "scan_protocol_version": "v2-template-scan/1.0",
        "illustrator_version": "29.0",
        "scanned_at": "2026-08-07T00:00:00Z",
        "document": {"source_ai": "C:/template.ai", "template_sha256": "abc123"},
        "template": {"name": "Template", "object_type": "GroupItem", "layer_path": "Template"},
        "items": [
            {"name": "Template", "object_type": "GroupItem", "layer_path": "Template"},
            {"name": "Style", "object_type": "GroupItem", "layer_path": "Template/Output_main/Style"},
            {"name": "Design", "object_type": "GroupItem", "layer_path": "Template/Output_main/Design"},
            {"name": "Font", "object_type": "GroupItem", "layer_path": "Template/Output_main/Font"},
        ],
        "outputs": [
            {
                "key": "Output_main",
                "name": "Output_main",
                "object_type": "GroupItem",
                "layer_path": "Template/Output_main",
                "style": {"name": "Style", "object_type": "GroupItem", "layer_path": "Template/Output_main/Style"},
                "styles": [
                    {
                        "key": "style1",
                        "name": "style1",
                        "object_type": "PathItem",
                        "layer_path": "Template/Output_main/Style/style1",
                        "visible_bounds": [0, 72, 144, 0],
                    }
                ],
                "design": {"name": "Design", "object_type": "GroupItem", "layer_path": "Template/Output_main/Design"},
                "designs": [
                    {
                        "key": "Design03",
                        "name": "Design03",
                        "object_type": "GroupItem",
                        "layer_path": "Template/Output_main/Design/Design03",
                        "slots": [
                            {
                                "key": "slot_logo",
                                "name": "slot_logo",
                                "object_type": "TextFrame",
                                "layer_path": "Template/Output_main/Design/Design03/slot_logo",
                                "text_kind": "point_text",
                                "visible_bounds": [0, 72, 72, 0],
                                "font": {"name": "ArialMT"},
                            }
                        ],
                        "assets": [
                            {
                                "key": "logo",
                                "asset_key": "logo",
                                "object_type": "GroupItem",
                                "layer_path": "Template/Output_main/Design/Design03/Assets/logo",
                                "values": [
                                    {
                                        "key": "A",
                                        "name": "A",
                                        "object_type": "GroupItem",
                                        "layer_path": "Template/Output_main/Design/Design03/Assets/logo/A",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "font": {"name": "Font", "object_type": "GroupItem", "layer_path": "Template/Output_main/Font"},
                "fonts": [
                    {
                        "key": "F10",
                        "name": "F10",
                        "object_type": "GroupItem",
                        "layer_path": "Template/Output_main/Font/F10",
                        "slots": [
                            {
                                "key": "slot_title",
                                "name": "slot_title",
                                "object_type": "TextFrame",
                                "layer_path": "Template/Output_main/Font/F10/slot_title",
                                "text_kind": "path_text",
                                "text": {"font": {"name": "Milkshake"}},
                            }
                        ],
                    }
                ],
            }
        ],
        "colors": [
            {
                "key": "Gold",
                "name": "Gold",
                "object_type": "PathItem",
                "layer_path": "Template/Colors/Gold",
                "fill_color": {"type": "SpotColor", "space": "Spot", "spot": "Gold Ink", "tint": 100},
            }
        ],
    }

    result = normalize_v2_template_scan(raw)

    assert result["blocked"] is False
    output = result["outputs"][0]
    assert output["summary"] == {
        "styles": 1,
        "designs": 1,
        "fonts": 1,
        "slots": 2,
        "anchors": 0,
        "tails": 0,
        "assets": 1,
        "fixed_objects": 0,
        "fixed_annotations": 0,
    }
    assert output["designs"][0]["assets"][0]["slot"] == "slot_logo"
    assert output["designs"][0]["slots"][0]["asset_key"] == "logo"
    assert output["designs"][0]["slots"][0]["visible_bounds"] == [0, 72, 72, 0]
    assert result["colors"] == [
        {
            "key": "Gold",
            "path": "Template/Colors/Gold",
            "space": "SPOT",
            "value": "Gold Ink",
            "tint": 100.0,
            "source_paths": ["Template/Colors/Gold"],
        }
    ]
    assert {"font_name": "ArialMT", "path": "Template/Output_main/Design/Design03/slot_logo", "scope": "slot"} in result["dependencies"]["fonts"]
    assert {"font_name": "Milkshake", "path": "Template/Output_main/Font/F10/slot_title", "scope": "slot"} in result["dependencies"]["fonts"]


def test_preserves_jsx_fixed_object_summary_without_detail_items():
    raw = {
        "document": {"template_sha256": "template-hash"},
        "template": {"name": "Template", "object_type": "GroupItem", "layer_path": "Template"},
        "items": [
            {"name": "Template", "object_type": "GroupItem", "layer_path": "Template"},
            {"name": "Output_main", "object_type": "GroupItem", "layer_path": "Template/Output_main"},
            {"name": "Font", "object_type": "GroupItem", "layer_path": "Template/Output_main/Font"},
            {"name": "F1", "object_type": "GroupItem", "layer_path": "Template/Output_main/Font/F1"},
        ],
        "outputs": [
            {
                "key": "Output_main",
                "name": "Output_main",
                "object_type": "GroupItem",
                "layer_path": "Template/Output_main",
                "font": {"name": "Font", "object_type": "GroupItem", "layer_path": "Template/Output_main/Font"},
                "fonts": [
                    {
                        "key": "F1",
                        "name": "F1",
                        "object_type": "GroupItem",
                        "layer_path": "Template/Output_main/Font/F1",
                        "fixed_object_count": 2,
                        "fixed_object_type_counts": {"PathItem": 1, "GroupItem": 1},
                    }
                ],
            }
        ],
    }

    result = normalize_v2_template_scan(raw)

    font = result["outputs"][0]["fonts"][0]
    assert result["blocked"] is False
    assert font["fixed_object_count"] == 2
    assert font["fixed_object_type_counts"] == {"GroupItem": 1, "PathItem": 1}
    assert font["fixed_objects"] == [{"key": "unnamed_fixed_objects", "count": 2, "path": "Template/Output_main/Font/F1"}]
    assert result["outputs"][0]["summary"]["fixed_objects"] == 2


def test_collects_explicit_fixed_annotations_without_guessing_the_artwork_type():
    items = valid_scan_items()
    items.extend(
        [
            path_item(
                "Template/Output_main/Design/Design03/fixed",
                "fixed",
                bounds=[120, 48, 140, 28],
            ),
            group(
                "Template/Output_main/Design/Design03/fixed_legacy",
                "fixed_legacy",
                bounds=[150, 52, 180, 22],
            ),
            group(
                "Template/Output_main/Design/Design03/fixd_legacy",
                "fixd_legacy",
                bounds=[220, 50, 250, 20],
            ),
            path_item(
                "Template/Output_main/Design/Design03/ordinary_star",
                "ordinary_star",
                bounds=[190, 48, 210, 28],
            ),
        ]
    )

    result = normalize_v2_template_scan(base_raw_scan(*items))

    design = result["outputs"][0]["designs"][0]
    assert result["blocked"] is False
    assert design["fixed_annotations"] == [
        {
            "key": "fixd_legacy",
            "path": "Template/Output_main/Design/Design03/fixd_legacy",
            "type": "GroupItem",
            "visible_bounds": [220, 50, 250, 20],
            "dimensions": {"width_mm": 10.583, "height_mm": 10.583},
        },
        {
            "key": "fixed",
            "path": "Template/Output_main/Design/Design03/fixed",
            "type": "PathItem",
            "visible_bounds": [120, 48, 140, 28],
            "dimensions": {"width_mm": 7.056, "height_mm": 7.056},
        },
        {
            "key": "fixed_legacy",
            "path": "Template/Output_main/Design/Design03/fixed_legacy",
            "type": "GroupItem",
            "visible_bounds": [150, 52, 180, 22],
            "dimensions": {"width_mm": 10.583, "height_mm": 10.583},
        },
    ]
    assert all(item["key"] != "ordinary_star" for item in design["fixed_annotations"])
    assert result["outputs"][0]["summary"]["fixed_annotations"] == 3


def test_blocks_fixed_annotation_nested_in_a_replaceable_slot_or_assets():
    items = valid_scan_items()
    items.extend(
        [
            path_item(
                "Template/Output_main/Design/Design03/slot_name/fixed",
                "fixed",
            ),
            group("Template/Output_main/Design/Design03/Assets", "Assets"),
            group(
                "Template/Output_main/Design/Design03/Assets/logo",
                "logo",
            ),
            path_item(
                "Template/Output_main/Design/Design03/Assets/logo/fixed",
                "fixed",
            ),
        ]
    )

    result = normalize_v2_template_scan(base_raw_scan(*items))

    assert result["blocked"] is True
    assert "fixed_marker_forbidden_scope" in issue_codes(result)


def test_scan_errors_are_sanitized_for_web_consumption():
    result = normalize_v2_template_scan(
        {
            "document": {"template_sha256": "template-hash"},
            "scan_errors": [
                {
                    "path": "$",
                    "code": "scan_failed",
                    "message": "COM failed at C:/Users/Administrator/secret/template.ai Traceback token=abc123",
                }
            ],
        }
    )

    reason = next(issue["reason"] for issue in result["issues"] if issue["code"] == "scan_failed")
    assert result["blocked"] is True
    assert "COM" not in reason
    assert "C:/Users" not in reason
    assert "Traceback" not in reason
    assert "token" not in reason
    assert "本地 Illustrator 扫描失败" in reason


def test_scan_v2_template_jsx_executes_against_mock_illustrator_document():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the JSX scan harness")
    script_path = Path("scripts/illustrator/scan_v2_template.jsx").resolve()
    harness = f"""
const fs = require('fs');
const NativeJSON = JSON;
const source = fs.readFileSync({json.dumps(str(script_path))}, 'utf8').replace(/^#target.*\\r?\\n/, '');
const writes = {{}};
global.JSON = undefined;
global.$ = {{ getenv: () => 'task.json' }};
global.UserInteractionLevel = {{ DONTDISPLAYALERTS: 0 }};
global.SaveOptions = {{ DONOTSAVECHANGES: 0 }};
global.TextType = {{ POINTTEXT: 'POINTTEXT', AREATEXT: 'AREATEXT', PATHTEXT: 'PATHTEXT' }};
function folder() {{ return {{ exists: true, parent: null, create: () => true }}; }}
global.File = function(path) {{
  const f = {{
    fsName: String(path),
    exists: true,
    parent: folder(),
    encoding: 'UTF-8',
    open: () => true,
    read: () => NativeJSON.stringify({{ input_ai: 'template.ai', output_json: 'scan.json', input_sha256: 'abc123' }}),
    write: text => {{ writes[String(path)] = text; }},
    close: () => undefined
  }};
  f.parent.parent = f.parent;
  return f;
}};
function group(name, children) {{
  return {{ typename: 'GroupItem', name, pageItems: children || [], visibleBounds: [0, 100, 100, 0], opacity: 100 }};
}}
function pathItem(name, fillColor) {{
  return {{ typename: 'PathItem', name, filled: true, closed: true, pathPoints: [1, 2, 3, 4], fillColor, visibleBounds: [0, 20, 20, 0], opacity: 100 }};
}}
function text(name, kind) {{
  return {{
    typename: 'TextFrame',
    name,
    contents: 'Logo',
    kind,
    visibleBounds: [0, 40, 80, 0],
    opacity: 100,
    textRange: {{ characterAttributes: {{
      textFont: {{ name: 'Milkshake-Regular', family: 'Milkshake', style: 'Regular' }},
      size: 24,
      tracking: 0,
      horizontalScale: 100,
      verticalScale: 100,
      fillColor: {{ typename: 'RGBColor', red: 1, green: 2, blue: 3 }}
    }} }}
  }};
}}
function link(parent) {{
  (parent.pageItems || []).forEach(child => {{
    child.parent = parent;
    if (child.pageItems) link(child);
  }});
  return parent;
}}
const fixed = {{ typename: 'PathItem', name: '', filled: true, closed: true, pathPoints: [1], visibleBounds: [0, 10, 10, 0], opacity: 100 }};
const design = group('Design 1', [
  group('slot_logo', [text('slot_logo_text', TextType.PATHTEXT), pathItem('keep_ratio_heart', {{ typename: 'RGBColor', red: 0, green: 0, blue: 0 }}), pathItem('fixed', {{ typename: 'RGBColor', red: 0, green: 0, blue: 0 }})]),
  text(' slot_LOGO ', TextType.POINTTEXT),
  group('Assets', [group('logo', [group('A', [])])]),
  fixed
]);
const font = group('F 1', [text('slot_title', TextType.POINTTEXT)]);
const template = link(group('Template', [
  group('Output', [group('Design', [design]), group('Font', [font])]),
  group('Colors', [pathItem('Black', {{ typename: 'RGBColor', red: 0, green: 0, blue: 0 }})])
]));
const doc = {{
  typename: 'Document',
  name: 'template.ai',
  documentColorSpace: 'RGB',
  width: 100,
  height: 100,
  artboards: [1],
  pageItems: [template],
  groupItems: [],
  close: () => undefined
}};
function collectGroups(item) {{
  if (item.typename === 'GroupItem') doc.groupItems.push(item);
  (item.pageItems || []).forEach(collectGroups);
}}
collectGroups(template);
template.parent = doc;
global.app = {{
  version: '29.0',
  open: () => doc,
  userInteractionLevel: 0
}};
new Function(source)();
const scan = NativeJSON.parse(writes['scan.json']);
const option = scan.outputs[0].designs[0];
if (scan.status !== 'blocked') throw new Error('duplicate slot should block');
if (scan.outputs[0].key !== 'Output_main') throw new Error('single Output alias was not normalized');
if (option.key !== 'Design 1') throw new Error('spaced Design name was not scanned');
if (scan.outputs[0].fonts[0].key !== 'F 1') throw new Error('spaced Font name was not scanned');
if (option.fixed_object_count !== 1) throw new Error('fixed object count lost');
if (scan.items.some(item => item.name === '' || item.layer_path.indexOf('/PathItem') >= 0)) throw new Error('fixed object leaked into items');
if (!option.slots.some(slot => slot.text && slot.text.text_kind === 'path_text')) throw new Error('path text not detected');
if (!option.slots.some(slot => slot.preserve_composition === true)) throw new Error('keep ratio marker not detected');
if (!scan.items.some(item => item.name === 'fixed')) throw new Error('nested fixed marker was omitted from evidence');
if (scan.colors[0].fill_color.space !== 'RGB') throw new Error('RGB color not scanned');
if (!scan.issues.some(issue => issue.code === 'slot_duplicate')) throw new Error('duplicate slot issue missing');
console.log(NativeJSON.stringify({{ status: scan.status, fixed: option.fixed_object_count, colors: scan.colors.length, fixed_emitted: scan.items.some(item => item.name === 'fixed') }}));
"""

    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "blocked", "fixed": 1, "colors": 1, "fixed_emitted": True}
