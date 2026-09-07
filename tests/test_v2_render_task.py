import hashlib
import json
from pathlib import Path
import subprocess
import textwrap

import pytest

from src.service.v2_render_task import (
    ALLOWED_V2_ACTIONS,
    V2_RENDER_TASK_SCHEMA,
    V2RenderTaskError,
    compile_v2_render_task,
    stable_v2_render_task_json,
)
from src.renderer.v2_template_renderer import (
    V2TemplateRenderer,
    V2TemplateRendererError,
    build_v2_execution_task,
)
from src.service.v2_order_plan import build_v2_order_units
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_template_store import V2TemplateStore
from src.service.v2_template_validation import validate_v2_template_configuration
from tests.test_v2_workbench_js_behavior import HARNESS


TEMPLATE_SHA = "a" * 64
TAIL_PUA_BASE = 0xF000
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def render_config():
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": "V2RENDER001", "name": "Render demo", "shop_name": ""},
        "outputs": [
            {
                "key": "Output_main",
                "style": {
                    "field": "size",
                    "options": [
                        {"key": "style1", "dimensions": {"mode": "style", "width_mm": 80, "height_mm": 50}}
                    ],
                },
                "design": {
                    "field": "design",
                    "options": [
                        {
                            "key": "Design03",
                            "content_preset": "initial_with_text",
                            "slots": [
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "preset": "direct_text",
                                    "anchor": "anchor_name",
                                },
                                {
                                    "key": "slot_initial",
                                    "source_field": "initial",
                                    "preset": "asset_replace",
                                    "asset_key": "initial_top",
                                },
                            ],
                            "assets": [
                                {
                                    "asset_key": "initial_top",
                                    "slot": "slot_initial",
                                    "supported_values": ["A", "B"],
                                }
                            ],
                        }
                    ],
                },
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F10",
                            "content_preset": "design_font_combo",
                            "slots": [
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "preset": "direct_text",
                                    "font_dependencies": ["Milkshake"],
                                }
                            ],
                        }
                    ],
                },
            }
        ],
        "field_bindings": {"size": "Size", "design": "Design", "font": "Font", "name": "Name", "initial": "Initial"},
        "option_mappings": [
            {"field": "font", "source_value": "F10", "target": "F10", "output": "Output_main", "group": "font"},
            {"field": "design", "source_value": "03", "target": "Design03", "output": "Output_main", "group": "design"},
            {"field": "size", "source_value": "small", "target": "style1", "output": "Output_main", "group": "style"},
        ],
        "checks": {key: "confirmed" for key in ("output", "fields", "options", "slots", "content", "dimensions", "colors", "preview")},
        "audit": {"scan_version": "scan-1", "template_sha256": TEMPLATE_SHA, "config_version": 3},
    }


def multi_output_config():
    config = render_config()
    config["outputs"] = [
        {
            "key": "Output_SideA",
            "design": {
                "field": "front_design",
                "options": [{"key": "Design03", "slots": [{"key": "slot_name", "source_field": "front_name"}]}],
            },
        },
        {
            "key": "Output_SideB",
            "font": {
                "field": "inside_font",
                "options": [{"key": "F10", "slots": [{"key": "slot_name", "source_field": "inside_name"}]}],
            },
        },
    ]
    config["field_bindings"] = {"front_design": "FrontDesign", "inside_font": "InsideFont", "front_name": "FrontName", "inside_name": "InsideName"}
    config["option_mappings"] = [
        {"field": "inside_font", "source_value": "F10", "target": "F10", "output": "Output_SideB", "group": "font"},
        {"field": "front_design", "source_value": "03", "target": "Design03", "output": "Output_SideA", "group": "design"},
    ]
    return config


def scan_evidence():
    return {
        "$schema": "custom-renderer/v2-template-scan",
        "scan_protocol_version": 1,
        "evidence": {
            "template_sha256": TEMPLATE_SHA,
            "scan_protocol_version": 1,
            "illustrator_version": "29.0",
            "scanned_at": "2026-08-07T00:00:00Z",
            "object_path_digest": "b" * 64,
        },
        "template": {"path": "Template"},
        "outputs": [
            {
                "key": "Output_main",
                "path": "Template/Output_main",
                "styles": [{"key": "style1", "path": "Template/Output_main/Style/style1"}],
                "designs": [
                    {
                        "key": "Design03",
                        "path": "Template/Output_main/Design/Design03",
                        "dimensions": {"width_mm": 80, "height_mm": 50},
                        "slots": [
                            {"key": "slot_name", "path": "Template/Output_main/Design/Design03/slot_name"},
                            {"key": "slot_initial", "path": "Template/Output_main/Design/Design03/slot_initial"},
                        ],
                        "anchors": [{"key": "anchor_name", "path": "Template/Output_main/Design/Design03/anchor_name"}],
                        "tails": [],
                        "assets": [{"asset_key": "initial_top", "path": "Template/Output_main/Design/Design03/Assets/initial_top"}],
                    }
                ],
                "fonts": [
                    {
                        "key": "F10",
                        "path": "Template/Output_main/Font/F10",
                        "slots": [{"key": "slot_name", "path": "Template/Output_main/Font/F10/slot_name"}],
                        "anchors": [],
                        "tails": [],
                    }
                ],
            }
        ],
        "dependencies": {"fonts": [{"scope": "slot", "path": "Template/Output_main/Font/F10/slot_name", "font_name": "Milkshake"}]},
        "issues": [],
        "blocked": False,
    }


def multi_output_scan():
    scan = scan_evidence()
    scan["outputs"] = [
        {
            "key": "Output_SideA",
            "path": "Template/Output_SideA",
            "designs": [
                {
                    "key": "Design03",
                    "path": "Template/Output_SideA/Design/Design03",
                    "dimensions": {"width_mm": 80, "height_mm": 50},
                    "slots": [{"key": "slot_name", "path": "Template/Output_SideA/Design/Design03/slot_name"}],
                    "anchors": [],
                    "tails": [],
                    "assets": [],
                }
            ],
            "styles": [],
            "fonts": [],
        },
        {
            "key": "Output_SideB",
            "path": "Template/Output_SideB",
            "fonts": [
                {
                    "key": "F10",
                    "path": "Template/Output_SideB/Font/F10",
                    "slots": [{"key": "slot_name", "path": "Template/Output_SideB/Font/F10/slot_name"}],
                    "anchors": [],
                    "tails": [],
                }
            ],
            "styles": [],
            "designs": [],
        },
    ]
    return scan


def compile_task(config=None, scan=None, **overrides):
    kwargs = {
        "template_id": "V2RENDER001",
        "template_version": "v0007",
        "template_sha256": TEMPLATE_SHA,
        "config_version": "d0012",
        "font_check": {"ok": True, "missing": []},
    }
    kwargs.update(overrides)
    return compile_v2_render_task(config or render_config(), scan or scan_evidence(), **kwargs)


def _configure_plain_font_reference(config, scan):
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "direct_text"
    design["assets"] = []
    design["slots"] = [
        {"key": "slot_name", "source_field": "name", "preset": "direct_text", "anchor": "anchor_name"},
        {"key": "slot_title", "source_field": "title", "preset": "direct_text"},
    ]
    config["field_bindings"]["title"] = "Title"
    scanned_design = scan["outputs"][0]["designs"][0]
    scanned_design["slots"] = [
        {"key": "slot_name", "path": "Template/Output_main/Design/Design03/slot_name"},
        {"key": "slot_title", "path": "Template/Output_main/Design/Design03/slot_title"},
    ]
    scanned_design["assets"] = []
    config["outputs"][0]["font"]["options"][0]["slots"] = []
    scanned_font = scan["outputs"][0]["fonts"][0]
    scanned_font["slots"] = []
    scanned_font["font_reference"] = {
        "path": "Template/Output_main/Font/F10/font_sample",
        "type": "TextFrame",
        "font_dependencies": ["Milkshake"],
    }


def test_uses_single_unmarked_font_reference_for_all_design_text_slots():
    config = render_config()
    scan = scan_evidence()
    _configure_plain_font_reference(config, scan)

    task = compile_task(config, scan)

    design_actions = [
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design"
    ]
    assert {action["slot_key"] for action in design_actions} == {"slot_name", "slot_title"}
    assert all(
        action["style_source"]["paths_by_option"] == {"F10": "Template/Output_main/Font/F10/font_sample"}
        for action in design_actions
    )
    font_actions = [action for action in task["outputs"][0]["actions"] if action.get("group") == "font"]
    assert [action["type"] for action in font_actions] == ["copy_option_group"]
    assert font_actions[0]["source_only"] is True


def test_rejects_unmarked_font_without_a_single_text_reference():
    config = render_config()
    scan = scan_evidence()
    _configure_plain_font_reference(config, scan)
    del scan["outputs"][0]["fonts"][0]["font_reference"]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config, scan)

    assert exc_info.value.code == "font_reference_missing"


def _workbench_split_config() -> dict:
    script = r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2RENDER001", name: "Workbench Split" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2RENDER001", name: "Workbench Split", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design02",
                      recommended_preset: "split_by_pipe",
                      slots: [
                        { key: "slot_name1", source_field: "name" },
                        { key: "slot_name2", source_field: "name" }
                      ],
                      anchors: [],
                      tails: [],
                      assets: []
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  field_bindings: { name: "Name", design: "Design" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();
          console.log("WORKBENCH_CONFIG:" + JSON.stringify(buildControlledConfig()));
        })().catch((error) => { console.error(error); process.exit(1); });
    """
    try:
        completed = subprocess.run(
            ["node", "-e", HARNESS + "\n" + textwrap.dedent(script)],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("Node.js is unavailable")
    assert completed.returncode == 0, completed.stderr + completed.stdout
    marker = "WORKBENCH_CONFIG:"
    line = next((item for item in completed.stdout.splitlines() if item.startswith(marker)), "")
    assert line, completed.stdout
    return json.loads(line[len(marker):])


def test_compiles_v2_render_task_with_stable_json_and_whitelisted_actions():
    first = compile_task()
    second = compile_task()

    assert first == second
    assert stable_v2_render_task_json(first) == stable_v2_render_task_json(second)
    assert first["$schema"] == V2_RENDER_TASK_SCHEMA
    assert first["template"] == {"template_id": "V2RENDER001", "version": "v0007", "sha256": TEMPLATE_SHA}
    assert first["scan"]["object_path_digest"] == "b" * 64
    assert first["font_check"] == {"ok": True, "missing": []}
    assert len(first["task_sha256"]) == 64
    task_hash_payload = dict(first)
    task_hash_payload.pop("task_sha256")
    assert first["task_sha256"] == hashlib.sha256(stable_v2_render_task_json(task_hash_payload).encode("utf-8")).hexdigest()
    actions = first["outputs"][0]["actions"]
    assert {action["type"] for action in actions} <= ALLOWED_V2_ACTIONS
    assert all("jsx" not in str(action).lower() and "script" not in str(action).lower() for action in actions)
    assert [item["group"] for item in first["option_mappings"]] == ["design", "font", "style"]
    fit_action = next(action for action in actions if action["type"] == "fit_output_bounds")
    assert fit_action["group"] == "style"
    assert fit_action["style_key"] == "style1"
    assert fit_action["dimensions"] == {"mode": "style", "width_mm": 80, "height_mm": 50}
    assert not any(action["type"] == "replace_slot_text" and action.get("slot_key") == "slot_initial" for action in actions)
    asset_action = next(action for action in actions if action["type"] == "bind_asset_library")
    assert asset_action["slot_key"] == "slot_initial"
    assert asset_action["slot_path"] == "Template/Output_main/Design/Design03/slot_initial"
    assert asset_action["source_field"] == "initial"
    assert asset_action["supported_values"] == ["A", "B"]
    assert asset_action["value_key"] == "Output_main|design|Design03|asset|initial_top"
    name_action = next(
        action
        for action in actions
        if action["type"] == "replace_slot_text"
        and action["group"] == "design"
        and action["slot_key"] == "slot_name"
    )
    assert name_action["value_key"] == "Output_main|design|Design03|slot|slot_name"


def test_compiles_and_resolves_combined_initial_content(tmp_path):
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["slots"][1]["source_field"] = "name"
    design["assets"][0]["supported_values"].append("K")
    config["field_bindings"].pop("initial")

    task = compile_task(config=config)
    execution = build_v2_execution_task(
        task,
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "output.ai",
        values={"size": "small", "design": "03", "font": "F10", "name": "Back|K"},
    )

    assert execution["resolved_values"] == {
        "Output_main|design|Design03|asset|initial_top": "K",
        "Output_main|design|Design03|slot|slot_name": "Back",
    }


@pytest.mark.parametrize(
    ("personalization", "error_code"),
    [("A|B", "initial_content_ambiguous"), ("Zelda", "asset_value_missing")],
)
def test_invalid_initial_content_never_enters_illustrator(tmp_path, personalization, error_code):
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["slots"][1]["source_field"] = "name"
    config["field_bindings"].pop("initial")
    task = compile_task(config=config)

    class RecordingBridge:
        def __init__(self):
            self.calls = []

        def render(self, script_path, task_path):
            self.calls.append((script_path, task_path))

    bridge = RecordingBridge()
    renderer = V2TemplateRenderer(bridge=bridge, script_path=tmp_path / "render_v2_template.jsx")
    task_file = tmp_path / "execution.json"

    with pytest.raises(V2TemplateRendererError) as exc_info:
        renderer.render(
            task,
            template_ai=tmp_path / "template.ai",
            output_ai=tmp_path / "output.ai",
            values={"size": "small", "design": "03", "font": "F10", "name": personalization},
            task_file=task_file,
        )

    assert exc_info.value.code == error_code
    assert bridge.calls == []
    assert not task_file.exists()


def test_compiles_multi_initial_assets_in_slot_order_and_resolves_values(tmp_path):
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "multi_initials"
    design["slots"] = [
        {"key": "slot_initial_top", "source_field": "names", "preset": "asset_replace", "asset_key": "initial_top"},
        {"key": "slot_initial_bottom", "source_field": "names", "preset": "asset_replace", "asset_key": "initial_bottom"},
    ]
    design["assets"] = [
        {"asset_key": "initial_bottom", "slot": "slot_initial_bottom", "supported_values": ["B"]},
        {"asset_key": "initial_top", "slot": "slot_initial_top", "supported_values": ["A"]},
    ]
    config["field_bindings"]["names"] = "Names"
    scan = scan_evidence()
    scan_design = scan["outputs"][0]["designs"][0]
    scan_design["slots"] = [
        {"key": "slot_initial_top", "path": "Template/Output_main/Design/Design03/slot_initial_top"},
        {"key": "slot_initial_bottom", "path": "Template/Output_main/Design/Design03/slot_initial_bottom"},
    ]
    scan_design["anchors"] = []
    scan_design["assets"] = [
        {"asset_key": "initial_bottom", "path": "Template/Output_main/Design/Design03/Assets/initial_bottom"},
        {"asset_key": "initial_top", "path": "Template/Output_main/Design/Design03/Assets/initial_top"},
    ]

    task = compile_task(config=config, scan=scan)
    asset_actions = [
        action for action in task["outputs"][0]["actions"] if action["type"] == "bind_asset_library"
    ]
    execution = build_v2_execution_task(
        task,
        template_ai=tmp_path / "template.ai",
        output_ai=tmp_path / "output.ai",
        values={"size": "small", "design": "03", "font": "F10", "name": "Label", "names": "Amy|Bob"},
    )

    assert [(action["asset_key"], action["slot_key"]) for action in asset_actions] == [
        ("initial_top", "slot_initial_top"),
        ("initial_bottom", "slot_initial_bottom"),
    ]
    assert execution["resolved_values"] == {
        "Output_main|design|Design03|asset|initial_top": "A",
        "Output_main|design|Design03|asset|initial_bottom": "B",
    }


def test_compiled_preview_warnings_flow_into_v2_production_units():
    config = render_config()
    config["preview"] = {"evidence": {"warnings": ["请核对细长文字", "请核对细长文字"]}}
    task = compile_task(config=config)
    units = build_v2_order_units(
        config,
        task,
        [
            {
                "Order No": "ORDER-1",
                "Detail ID": "LINE-1",
                "Dept": "K",
                "Product": "Bracelet",
                "Font Color": "Gold",
                "Size": "small",
                "Design": "03",
                "Font": "F10",
                "Name": "Alice",
                "Initial": "A",
            }
        ],
        {
            "preflight_rows": [
                {
                    "row": 1,
                    "order_id": "ORDER-1",
                    "outputs": [{"output": "Output_main", "style": "style1", "design": "Design03", "font": "F10"}],
                }
            ]
        },
    )

    assert task["render_warnings"] == ["请核对细长文字"]
    assert units[0].template_version == "v0007"
    assert units[0].render_warnings == ("请核对细长文字",)


@pytest.mark.parametrize(
    ("source_width", "source_height", "expected_width", "expected_height"),
    [
        (50.139, 30.139, 50, 30),
        (200.197, 50.197, 200, 50),
        (260.537, 70.577, 260, 70),
        (300.2873, 70.2873, 300, 70),
    ],
)
def test_compiles_style_scan_dimensions_as_production_upper_bounds(source_width, source_height, expected_width, expected_height):
    config = render_config()
    config["outputs"][0]["style"]["options"][0]["dimensions"] = {
        "mode": "style",
        "width_mm": source_width,
        "height_mm": source_height,
        "tolerance_mm": 0.007,
    }

    task = compile_task(config=config)

    actions = task["outputs"][0]["actions"]
    select_action = next(action for action in actions if action["type"] == "select_style")
    fit_action = next(action for action in actions if action["type"] == "fit_output_bounds")
    assert select_action["dimensions"]["width_mm"] == expected_width
    assert select_action["dimensions"]["height_mm"] == expected_height
    assert select_action["source_only"] is True
    assert fit_action["dimensions"]["width_mm"] == expected_width
    assert fit_action["dimensions"]["height_mm"] == expected_height


def test_compiles_scanned_design_dimensions_when_output_has_no_style_dimension():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    scan["outputs"][0]["styles"] = []
    scan["outputs"][0]["designs"][0]["dimensions"] = {"width_mm": 155.035, "height_mm": 56.652}

    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert fit_actions == [
        {
            "type": "fit_output_bounds",
            "group": "design",
            "option_key": "Design03",
            "dimensions": {"width_mm": 155.035, "height_mm": 56.652, "tolerance_mm": 0.007},
        }
    ]


def test_compiles_single_design_anchor_dimensions_as_final_output_frame():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 165.15, "height_mm": 131.018}
    design["slots"][0]["dimensions"] = {"width_mm": 163.657, "height_mm": 85.03}
    design["anchors"][0]["dimensions"] = {"width_mm": 150.231, "height_mm": 47.231}

    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert fit_actions == [
        {
            "type": "fit_output_bounds",
            "group": "design",
            "option_key": "Design03",
            "dimensions": {"width_mm": 150.231, "height_mm": 47.231, "tolerance_mm": 0.007},
        }
    ]


def test_falls_back_to_design_group_when_single_design_anchor_has_no_dimensions():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 165.15, "height_mm": 131.018}
    design["slots"][0]["dimensions"] = {"width_mm": 163.657, "height_mm": 85.03}

    task = compile_task(config=config, scan=scan)

    fit_action = next(action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds")
    assert fit_action["dimensions"] == {"width_mm": 165.15, "height_mm": 131.018, "tolerance_mm": 0.007}


@pytest.mark.parametrize(
    "invalid_anchor_dimensions",
    [
        {"width_mm": 0, "height_mm": 47.231},
        {"width_mm": -150.231, "height_mm": 47.231},
        {"width_mm": "invalid", "height_mm": 47.231},
        {"width_mm": True, "height_mm": 47.231},
        {"width_mm": 150.231, "height_mm": True},
    ],
)
def test_falls_back_to_design_group_when_single_design_anchor_dimensions_are_invalid(invalid_anchor_dimensions):
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 165.15, "height_mm": 131.018}
    design["slots"][0]["dimensions"] = {"width_mm": 163.657, "height_mm": 85.03}
    design["anchors"][0]["dimensions"] = invalid_anchor_dimensions

    task = compile_task(config=config, scan=scan)

    fit_action = next(action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds")
    assert fit_action["dimensions"] == {"width_mm": 165.15, "height_mm": 131.018, "tolerance_mm": 0.007}


def test_compiles_single_design_slot_dimensions_when_slot_has_no_anchor():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    config["outputs"][0]["design"]["options"][0]["slots"][0].pop("anchor")
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 165.15, "height_mm": 131.018}
    design["slots"][0]["dimensions"] = {"width_mm": 163.657, "height_mm": 85.03}

    task = compile_task(config=config, scan=scan)

    fit_action = next(action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds")
    assert fit_action["dimensions"] == {"width_mm": 163.657, "height_mm": 85.03, "tolerance_mm": 0.007}


def test_compiles_multiple_design_slots_with_design_group_dimensions():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    design_config = config["outputs"][0]["design"]["options"][0]
    design_config["content_preset"] = "mixed_slots"
    design_config["slots"] = [
        {"key": "slot_name", "source_field": "name", "preset": "direct_text", "anchor": "anchor_name"},
        {"key": "slot_initial", "source_field": "initial", "preset": "direct_text"},
    ]
    design_config["assets"] = []
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 165.15, "height_mm": 131.018}
    design["slots"][0]["dimensions"] = {"width_mm": 150.0, "height_mm": 47.0}
    design["slots"][1]["dimensions"] = {"width_mm": 60.0, "height_mm": 20.0}

    validation = validate_v2_template_configuration(config)
    assert validation["can_save"] is True
    assert all(issue["status"] != "blocked" for issue in validation["issues"])
    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert fit_actions == [
        {
            "type": "fit_output_bounds",
            "group": "design",
            "option_key": "Design03",
            "dimensions": {"width_mm": 165.15, "height_mm": 131.018, "tolerance_mm": 0.007},
        }
    ]


def test_compiles_primary_anchor_dimensions_when_design_has_optional_subtitle_slot_and_fixed_style():
    config = render_config()
    config["field_bindings"]["subtitle"] = "Subtitle"
    design_config = config["outputs"][0]["design"]["options"][0]
    design_config["content_preset"] = "mixed_slots"
    design_config["slots"] = [
        {"key": "slot_name", "source_field": "name", "preset": "direct_text", "anchor": "anchor_name"},
        {
            "key": "slot_subtitle",
            "source_field": "subtitle",
            "required": False,
            "preset": "direct_text",
            "anchor": "anchor_subtitle",
        },
    ]
    design_config["assets"] = []
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["dimensions"] = {"width_mm": 167.973, "height_mm": 131.393}
    design["slots"] = [
        {"key": "slot_name", "path": "Template/Output_main/Design/Design03/slot_name"},
        {"key": "slot_subtitle", "path": "Template/Output_main/Design/Design03/slot_subtitle"},
    ]
    design["anchors"] = [
        {
            "key": "anchor_name",
            "path": "Template/Output_main/Design/Design03/anchor_name",
            "dimensions": {"width_mm": 150.231, "height_mm": 47.231},
        },
        {
            "key": "anchor_subtitle",
            "path": "Template/Output_main/Design/Design03/anchor_subtitle",
            "dimensions": {"width_mm": 70.056, "height_mm": 6.056},
        },
    ]

    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert any(action["group"] == "style" for action in fit_actions)
    fit_action = next(action for action in fit_actions if action["group"] == "design")
    assert fit_action["dimensions"] == {"width_mm": 150.231, "height_mm": 47.231, "tolerance_mm": 0.007}
    assert fit_action["layout_mode"] == "preserve_slot_anchors"


def test_compiles_scanned_design_dimensions_when_style_metadata_has_no_fixed_size():
    config = render_config()
    config["outputs"][0]["style"]["options"][0]["dimensions"] = {"mode": "style"}
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["dimensions"] = {"width_mm": 155.035, "height_mm": 56.652}

    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert fit_actions == [
        {
            "type": "fit_output_bounds",
            "group": "design",
            "option_key": "Design03",
            "dimensions": {"width_mm": 155.035, "height_mm": 56.652, "tolerance_mm": 0.007},
        }
    ]


def test_compiles_design_dimensions_when_any_style_option_lacks_a_fixed_size():
    config = render_config()
    config["outputs"][0]["style"]["options"].append({"key": "style2", "dimensions": {"mode": "style"}})
    config["option_mappings"].append(
        {"field": "size", "source_value": "large", "target": "style2", "output": "Output_main", "group": "style"}
    )
    scan = scan_evidence()
    scan["outputs"][0]["styles"].append({"key": "style2", "path": "Template/Output_main/Style/style2"})

    task = compile_task(config=config, scan=scan)

    fit_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "fit_output_bounds"]
    assert any(action["group"] == "style" and action["style_key"] == "style1" for action in fit_actions)
    assert any(action["group"] == "design" and action["option_key"] == "Design03" for action in fit_actions)
    assert not any(action["group"] == "style" and action.get("style_key") == "style2" for action in fit_actions)


def test_rejects_no_style_template_when_any_design_lacks_scanned_dimensions():
    config = render_config()
    config["outputs"][0].pop("style")
    config["field_bindings"].pop("size")
    config["option_mappings"] = [item for item in config["option_mappings"] if item["group"] != "style"]
    scan = scan_evidence()
    scan["outputs"][0]["styles"] = []
    scan["outputs"][0]["designs"][0].pop("dimensions")

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "design_dimensions_missing"
    assert "重新扫描并发布模板" in str(exc_info.value)


def test_compiles_path_text_preset_with_scanned_path_text_kind():
    config = render_config()
    config["field_bindings"]["title"] = "Title"
    config["outputs"][0]["font"]["options"][0]["slots"].append(
        {"key": "slot_title", "source_field": "title", "preset": "path_text"}
    )
    scan = scan_evidence()
    scan["outputs"][0]["fonts"][0]["slots"].append(
        {
            "key": "slot_title",
            "path": "Template/Output_main/Font/F10/slot_title",
            "text_kind": "path_text",
            "preset": "path_text",
        }
    )

    task = compile_task(config=config, scan=scan)

    path_action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_title")
    assert path_action["preset"] == "path_text"
    assert path_action["text_kind"] == "path_text"
    assert path_action["object_path"] == "Template/Output_main/Font/F10/slot_title"


def test_compiles_split_by_pipe_slots_with_ordered_source_part_indices():
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "split_by_pipe"
    design["assets"] = []
    design["slots"] = [
        {"key": "slot_name", "source_field": "name", "preset": "split_by_pipe"},
        {"key": "slot_year", "source_field": "name", "preset": "split_by_pipe"},
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["slots"] = [
        {"key": "slot_name", "path": "Template/Output_main/Design/Design03/slot_name"},
        {"key": "slot_year", "path": "Template/Output_main/Design/Design03/slot_year"},
    ]

    task = compile_task(config=config, scan=scan)

    actions = [
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design"
    ]
    assert [(action["slot_key"], action["source_field"], action["source_part_index"]) for action in actions] == [
        ("slot_name", "name", 0),
        ("slot_year", "name", 1),
    ]


def test_compiles_split_by_pipe_alias_slots_by_bound_order_header():
    config = render_config()
    config["field_bindings"].update({"name1": "Name", "name2": "Name"})
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "mixed_slots"
    design["assets"] = []
    design["slots"] = [
        {"key": "slot_name1", "source_field": "name1", "preset": "split_by_pipe"},
        {"key": "slot_name2", "source_field": "name2", "preset": "split_by_pipe"},
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["slots"] = [
        {"key": "slot_name1", "path": "Template/Output_main/Design/Design03/slot_name1"},
        {"key": "slot_name2", "path": "Template/Output_main/Design/Design03/slot_name2"},
    ]

    task = compile_task(config=config, scan=scan)

    actions = [
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design"
    ]
    assert [(action["slot_key"], action["source_field"], action["source_part_index"]) for action in actions] == [
        ("slot_name1", "name1", 0),
        ("slot_name2", "name2", 1),
    ]


def test_compiles_split_by_pipe_task_from_workbench_controlled_config():
    config = _workbench_split_config()
    config["audit"]["template_sha256"] = TEMPLATE_SHA
    scan = scan_evidence()
    scan["outputs"][0]["designs"] = [
        {
            "key": "Design02",
            "path": "Template/Output_main/Design/Design02",
            "dimensions": {"width_mm": 80, "height_mm": 50},
            "slots": [
                {"key": "slot_name1", "path": "Template/Output_main/Design/Design02/slot_name1"},
                {"key": "slot_name2", "path": "Template/Output_main/Design/Design02/slot_name2"},
            ],
            "anchors": [],
            "tails": [],
            "assets": [],
        }
    ]

    task = compile_task(config=config, scan=scan)

    actions = [
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design"
    ]
    assert [(action["slot_key"], action["preset"], action["source_part_index"]) for action in actions] == [
        ("slot_name1", "split_by_pipe", 0),
        ("slot_name2", "split_by_pipe", 1),
    ]


def test_rejects_path_text_preset_for_non_path_text_scan_slot():
    config = render_config()
    config["outputs"][0]["font"]["options"][0]["slots"][0]["preset"] = "path_text"

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config)

    assert exc_info.value.code == "path_text_slot_invalid"
    assert exc_info.value.path == "$.Output_main.font.F10.slot_name.preset"


def test_compiles_tail_text_metadata_from_current_option_scope():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [
        {"key": "tail_name_first_a", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE},
        {"key": "tail_name_last_a", "position": "last", "sample": "a", "pua_base": TAIL_PUA_BASE},
    ]
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"},
        {"key": "tail_name_last_a", "path": "Template/Output_main/Design/Design03/tail_name_last_a"},
    ]

    task = compile_task(config=config, scan=scan)

    action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_name")
    assert action["preset"] == "tail_text"
    assert action["tail_paths"] == [
        "Template/Output_main/Design/Design03/tail_name_first_a",
        "Template/Output_main/Design/Design03/tail_name_last_a",
    ]
    assert action["tails"] == [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "path": "Template/Output_main/Design/Design03/tail_name_first_a",
            "glyph_mode": "pua_contiguous",
            "pua_base": TAIL_PUA_BASE,
            "coverage": "a-z",
        },
        {
            "key": "tail_name_last_a",
            "position": "last",
            "sample": "a",
            "path": "Template/Output_main/Design/Design03/tail_name_last_a",
            "glyph_mode": "pua_contiguous",
            "pua_base": TAIL_PUA_BASE,
            "coverage": "a-z",
        },
    ]


def test_compiles_legacy_direct_text_tail_sample_for_runtime_glyph_verification():
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "direct_text"
    design["assets"] = []
    design["slots"] = [
        {
            "key": "slot_name",
            "source_field": "name",
            "preset": "direct_text",
            "anchor": "anchor_name",
            "tails": [{"key": "tail_name_last_m", "position": "last", "sample": "m"}],
        }
    ]
    scan = scan_evidence()
    scan_design = scan["outputs"][0]["designs"][0]
    scan_design["slots"][0]["tails"] = [{"key": "tail_name_last_m", "path": "Template/Output_main/Design/Design03/tail_name_last_m"}]
    scan_design["tails"] = [{"key": "tail_name_last_m", "path": "Template/Output_main/Design/Design03/tail_name_last_m"}]

    task = compile_task(config=config, scan=scan)
    action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_name")

    assert action["tails"] == [
        {
            "key": "tail_name_last_m",
            "position": "last",
            "sample": "m",
            "path": "Template/Output_main/Design/Design03/tail_name_last_m",
            "glyph_mode": "plain_text",
        }
    ]


def test_rejects_unconfirmed_direct_text_tail_sample():
    config = render_config()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "direct_text"
    design["assets"] = []
    design["slots"] = [
        {
            "key": "slot_name",
            "source_field": "name",
            "preset": "direct_text",
            "anchor": "anchor_name",
            "tails": [{"key": "tail_name_last_m", "position": "last", "sample": "m"}],
        }
    ]
    scan = scan_evidence()
    scan_design = scan["outputs"][0]["designs"][0]
    scanned_tails = [
        {"key": "tail_name_last_m", "path": "Template/Output_main/Design/Design03/tail_name_last_m"},
        {"key": "tail_name_last_n", "path": "Template/Output_main/Design/Design03/tail_name_last_n"},
    ]
    scan_design["slots"][0]["tails"] = scanned_tails
    scan_design["tails"] = scanned_tails

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "tail_sample_unconfirmed"
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails"


def test_rejects_unconfirmed_direct_text_font_style_tail_sample():
    config = render_config()
    font_slot = config["outputs"][0]["font"]["options"][0]["slots"][0]
    font_slot["tails"] = [{"key": "tail_name_last_m", "position": "last", "sample": "m"}]
    scan = scan_evidence()
    scan_font = scan["outputs"][0]["fonts"][0]
    scanned_tails = [
        {"key": "tail_name_last_m", "path": "Template/Output_main/Font/F10/tail_name_last_m"},
        {"key": "tail_name_last_n", "path": "Template/Output_main/Font/F10/tail_name_last_n"},
    ]
    scan_font["slots"][0]["tails"] = scanned_tails
    scan_font["tails"] = scanned_tails

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "tail_sample_unconfirmed"
    assert exc_info.value.path == "$.Output_main.font.F10.slot_name.tails"


def test_compiles_mixed_slots_without_overwriting_independent_sources_or_tails():
    config = render_config()
    config["field_bindings"]["title"] = "Title"
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "mixed_slots"
    design["assets"] = []
    design["slots"] = [
        {
            "key": "slot_name1",
            "source_field": "name",
            "preset": "direct_text",
            "tails": [{"key": "tail_name1_last_m", "position": "last", "sample": "m", "pua_base": TAIL_PUA_BASE}],
        },
        {
            "key": "slot_title",
            "source_field": "title",
            "preset": "direct_text",
        },
    ]
    scan = scan_evidence()
    scan_design = scan["outputs"][0]["designs"][0]
    scan_design["slots"] = [
        {"key": "slot_name1", "path": "Template/Output_main/Design/Design03/slot_name1"},
        {"key": "slot_title", "path": "Template/Output_main/Design/Design03/slot_title"},
    ]
    scan_design["tails"] = [{"key": "tail_name1_last_m", "path": "Template/Output_main/Design/Design03/tail_name1_last_m"}]

    task = compile_task(config=config, scan=scan)

    copy = next(action for action in task["outputs"][0]["actions"] if action["type"] == "copy_option_group" and action["group"] == "design")
    actions = [
        action for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design"
    ]
    assert copy["content_preset"] == "mixed_slots"
    assert [(action["slot_key"], action["source_field"], action["source_part_index"], action["preset"]) for action in actions] == [
        ("slot_name1", "name", 0, "direct_text"),
        ("slot_title", "title", 0, "direct_text"),
    ]
    assert actions[0]["tail_paths"] == ["Template/Output_main/Design/Design03/tail_name1_last_m"]
    assert actions[1]["tail_paths"] == []


def test_rejects_tail_text_without_confirmed_tail_sample():
    config = render_config()
    config["outputs"][0]["design"]["options"][0]["slots"][0]["preset"] = "tail_text"

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config)

    assert exc_info.value.code == "tail_text_sample_missing"
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails"


def test_rejects_tail_text_without_verified_glyph_coverage():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [{"key": "tail_name_first_a", "position": "first", "sample": "a"}]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"}
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "tail_glyph_coverage_missing"
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails[0]"


def test_rejects_tail_text_when_scanned_slot_tail_sample_is_not_confirmed():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [{"key": "tail_name_first_a", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE}]
    scan = scan_evidence()
    design = scan["outputs"][0]["designs"][0]
    design["slots"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"},
        {"key": "tail_name_last_a", "path": "Template/Output_main/Design/Design03/tail_name_last_a"},
    ]
    design["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"},
        {"key": "tail_name_last_a", "path": "Template/Output_main/Design/Design03/tail_name_last_a"},
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "tail_sample_unconfirmed"
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails"


def test_compiles_tail_text_glyph_map_coverage():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "glyph_map": {chr(ord("a") + index): 0xE200 + index for index in range(26)},
        }
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"}
    ]

    task = compile_task(config=config, scan=scan)

    action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_name")
    assert action["tails"][0]["glyph_mode"] == "glyph_map"
    assert action["tails"][0]["glyph_map"]["a"] == 0xE200
    assert action["tails"][0]["glyph_map"]["z"] == 0xE219


def test_compiles_template_scoped_opentype_tail_profile_with_its_font_dependency():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["font_dependencies"] = ["helloHoneyPS"]
    design_slot["tails"] = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "sample": "a",
            "opentype_feature": "aalt",
            "opentype_alternate_index": 2,
        }
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"}
    ]

    task = compile_task(config=config, scan=scan)

    action = next(action for action in task["outputs"][0]["actions"] if action.get("slot_key") == "slot_name")
    assert action["tails"][0] == {
        "key": "tail_name_first_a",
        "position": "first",
        "sample": "a",
        "path": "Template/Output_main/Design/Design03/tail_name_first_a",
        "glyph_mode": "opentype_alternate",
        "opentype_feature": "aalt",
        "opentype_alternate_index": 2,
        "font_postscript_name": "helloHoneyPS",
        "coverage": "runtime-verified",
    }


def test_rejects_tail_text_invalid_sample_letter():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [{"key": "tail_name_first_a", "position": "first", "sample": "aa", "pua_base": TAIL_PUA_BASE}]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"}
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "config_contract_invalid"
    assert "$.outputs[0].design.options[0].slots[0].tails[0].sample" in str(exc_info.value)


def test_rejects_tail_text_duplicate_position_samples():
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [
        {"key": "tail_name_first_a", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE},
        {"key": "tail_name_first_b", "position": "first", "sample": "b", "pua_base": TAIL_PUA_BASE},
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_first_a", "path": "Template/Output_main/Design/Design03/tail_name_first_a"},
        {"key": "tail_name_first_b", "path": "Template/Output_main/Design/Design03/tail_name_first_b"},
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "tail_position_duplicate"
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails[1].position"


@pytest.mark.parametrize(
    ("tail", "code", "path_suffix"),
    [
        ({"key": "tail_title_first_a", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE}, "tail_slot_mismatch", ".key"),
        ({"key": "tail_name_last_a", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE}, "tail_position_mismatch", ".position"),
        ({"key": "tail_name_first_b", "position": "first", "sample": "a", "pua_base": TAIL_PUA_BASE}, "tail_sample_mismatch", ".sample"),
    ],
)
def test_rejects_tail_text_name_that_does_not_match_structured_fields(tail, code, path_suffix):
    config = render_config()
    design_slot = config["outputs"][0]["design"]["options"][0]["slots"][0]
    design_slot["preset"] = "tail_text"
    design_slot["tails"] = [tail]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": tail["key"], "path": f"Template/Output_main/Design/Design03/{tail['key']}"}
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == code
    assert exc_info.value.path == "$.Output_main.design.Design03.slot_name.tails[0]" + path_suffix


def test_rejects_template_sha_mismatch_before_illustrator_task_creation():
    config = render_config()
    config["audit"]["template_sha256"] = "c" * 64

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_v2_render_task(
            config,
            scan_evidence(),
            template_id="V2RENDER001",
            template_version="v0007",
            template_sha256=TEMPLATE_SHA,
            config_version="d0012",
        )

    assert exc_info.value.code == "template_sha256_mismatch"
    assert exc_info.value.path == "$.evidence.template_sha256"


def test_rejects_missing_config_audit_template_sha_before_illustrator_task_creation():
    config = render_config()
    config["audit"].pop("template_sha256")

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config)

    assert exc_info.value.code == "template_sha256_mismatch"


def test_rejects_scan_sha_mismatch_before_illustrator_task_creation():
    scan = scan_evidence()
    scan["evidence"]["template_sha256"] = "d" * 64

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "template_sha256_mismatch"


def test_rejects_scan_with_blocking_issue_status_even_if_flag_is_false():
    scan = scan_evidence()
    scan["blocked"] = False
    scan["issues"] = [{"status": "blocked", "code": "duplicate_name"}]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "scan_blocked"


@pytest.mark.parametrize(
    ("font_check", "code"),
    [
        (None, "font_check_missing"),
        ({}, "font_check_invalid"),
        ({"ok": True, "missing": ["Milkshake"]}, "font_check_failed"),
        ({"ok": False, "missing": []}, "font_check_failed"),
        ({"ok": True, "missing": [123]}, "font_check_invalid"),
    ],
)
def test_rejects_missing_invalid_or_failed_font_check(font_check, code):
    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(font_check=font_check)

    assert exc_info.value.code == code


def test_rejects_config_references_missing_scan_object_path():
    scan = scan_evidence()
    scan["outputs"][0]["fonts"][0]["slots"] = []

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "scan_object_missing"
    assert "F10/slot_name" in str(exc_info.value)


def test_rejects_config_anchor_without_scan_path():
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["anchors"] = []

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "scan_object_missing"
    assert exc_info.value.path.endswith(".anchor")


def test_keeps_design_and_font_same_slot_keys_on_distinct_paths():
    task = compile_task()

    slot_actions = [action for action in task["outputs"][0]["actions"] if action["type"] == "replace_slot_text"]
    design_slot = next(action for action in slot_actions if action["group"] == "design" and action["slot_key"] == "slot_name")
    font_slot = next(action for action in slot_actions if action["group"] == "font" and action["slot_key"] == "slot_name")

    assert design_slot["object_path"] == "Template/Output_main/Design/Design03/slot_name"
    assert design_slot["anchor_path"] == "Template/Output_main/Design/Design03/anchor_name"
    assert design_slot["style_source"] == {
        "group": "font",
        "slot_key": "slot_name",
        "paths_by_option": {"F10": "Template/Output_main/Font/F10/slot_name"},
    }
    assert font_slot["object_path"] == "Template/Output_main/Font/F10/slot_name"
    assert font_slot["font_dependencies"] == ["Milkshake"]
    font_copy = next(action for action in task["outputs"][0]["actions"] if action["type"] == "copy_option_group" and action["group"] == "font")
    assert font_copy["source_only"] is True


def test_passes_tail_font_samples_to_the_design_style_source():
    config = render_config()
    scan = scan_evidence()
    font_option = config["outputs"][0]["font"]["options"][0]
    font_option["key"] = "F3"
    font_option["content_preset"] = "tail_text"
    font_option["slots"][0].update(
        {
            "preset": "tail_text",
            "tails": [
                {"key": "tail_name_last_m", "position": "last", "sample": "m", "pua_base": TAIL_PUA_BASE}
            ],
        }
    )
    config["option_mappings"][0].update({"source_value": "F3", "target": "F3"})
    scan_font = scan["outputs"][0]["fonts"][0]
    scan_font["key"] = "F3"
    scan_font["path"] = "Template/Output_main/Font/F3"
    scan_font["slots"][0]["path"] = "Template/Output_main/Font/F3/slot_name"
    scan_font["slots"][0]["tails"] = [
        {"key": "tail_name_last_m", "path": "Template/Output_main/Font/F3/tail_name_last_m"}
    ]
    scan_font["tails"] = [
        {"key": "tail_name_last_m", "path": "Template/Output_main/Font/F3/tail_name_last_m"}
    ]

    task = compile_task(config, scan)

    design_action = next(
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design" and action["slot_key"] == "slot_name"
    )
    assert design_action["style_source"]["paths_by_option"] == {"F3": "Template/Output_main/Font/F3/slot_name"}
    assert design_action["style_source"]["tails_by_option"] == {
        "F3": [
            {
                "key": "tail_name_last_m",
                "position": "last",
                "sample": "m",
                "path": "Template/Output_main/Font/F3/tail_name_last_m",
                "glyph_mode": "pua_contiguous",
                "pua_base": TAIL_PUA_BASE,
                "font_postscript_name": "Milkshake",
                "coverage": "a-z",
            }
        ]
    }


def test_carries_preserve_composition_from_scanned_keep_ratio_slot():
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["slots"][0]["preserve_composition"] = True

    task = compile_task(scan=scan)

    design_slot = next(
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design" and action["slot_key"] == "slot_name"
    )

    assert design_slot["preserve_composition"] is True


def test_carries_slot_fit_mode_to_illustrator_action():
    config = render_config()
    config["outputs"][0]["design"]["options"][0]["slots"][0]["fit_mode"] = "fill_width"

    task = compile_task(config=config)

    design_slot = next(
        action
        for action in task["outputs"][0]["actions"]
        if action["type"] == "replace_slot_text" and action["group"] == "design" and action["slot_key"] == "slot_name"
    )
    assert design_slot["fit_mode"] == "fill_width"


def test_rejects_duplicate_scan_object_keys_in_same_scope():
    scan = scan_evidence()
    scan["outputs"][0]["fonts"][0]["slots"].append({"key": "slot_name", "path": "Template/other"})

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "scan_object_duplicate"
    assert "Font/F10/slot_name" in str(exc_info.value)


def test_rejects_duplicate_scan_anchor_keys_in_same_option_scope():
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["anchors"].append(
        {"key": "anchor_name", "path": "Template/Output_main/Design/Design03/other_anchor"}
    )

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(scan=scan)

    assert exc_info.value.code == "scan_object_duplicate"
    assert "anchor_name" in str(exc_info.value)


def test_rejects_duplicate_scan_tail_keys_in_same_option_scope():
    config = render_config()
    config["outputs"][0]["design"]["options"][0]["slots"][0]["preset"] = "tail_text"
    config["outputs"][0]["design"]["options"][0]["slots"][0]["tails"] = [
        {"key": "tail_name_last_a", "position": "last", "sample": "a", "pua_base": TAIL_PUA_BASE}
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"][0]["tails"] = [
        {"key": "tail_name_last_a", "path": "Template/Output_main/Design/Design03/tail_name_last_a"},
        {"key": "tail_name_last_a", "path": "Template/Output_main/Design/Design03/tail_name_last_a_copy"},
    ]

    with pytest.raises(V2RenderTaskError) as exc_info:
        compile_task(config=config, scan=scan)

    assert exc_info.value.code == "scan_object_duplicate"
    assert "tail_name_last_a" in str(exc_info.value)


def test_records_multi_output_order_from_contract_order():
    task = compile_task(config=multi_output_config(), scan=multi_output_scan())

    assert [(output["key"], output["order"]) for output in task["outputs"]] == [
        ("Output_SideA", 1),
        ("Output_SideB", 2),
    ]
    assert task["outputs"][0]["actions"][0]["object_path"] == "Template/Output_SideA/Design/Design03"
    assert task["outputs"][1]["actions"][0]["object_path"] == "Template/Output_SideB/Font/F10"
    assert all("style_source" not in action for output in task["outputs"] for action in output["actions"])


def test_pure_font_output_does_not_mark_font_copy_as_source_only():
    config = render_config()
    config["outputs"][0]["design"] = {"field": "", "options": []}
    config["field_bindings"] = {"font": "Font", "name": "Name"}
    config["option_mappings"] = [
        {"field": "font", "source_value": "F10", "target": "F10", "output": "Output_main", "group": "font"}
    ]
    scan = scan_evidence()
    scan["outputs"][0]["designs"] = []

    task = compile_task(config=config, scan=scan)

    font_copy = next(action for action in task["outputs"][0]["actions"] if action["type"] == "copy_option_group" and action["group"] == "font")
    assert "source_only" not in font_copy
    assert all("style_source" not in action for action in task["outputs"][0]["actions"])


def test_compiles_from_store_draft_revision_and_source_version(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2RENDER001",
        metadata={"template_id": "V2RENDER001", "name": "Render demo"},
        config=render_config(),
        scan=scan_evidence(),
        source_version="v0007",
    )
    draft = store.read_draft("V2RENDER001")

    task = compile_task(
        config=draft["config"],
        scan=draft["scan"],
        template_id=draft["metadata"]["template_id"],
        template_version=draft["manifest"]["source_version"],
        config_version=draft["manifest"]["draft_revision"],
        config_sha256=draft["manifest"]["config_sha256"],
        scan_sha256=draft["manifest"]["scan_sha256"],
    )

    assert task["template"]["version"] == "v0007"
    assert task["config"]["version"] == "d0001"
    assert task["config"]["sha256"] == draft["manifest"]["config_sha256"]
    assert task["scan"]["sha256"] == draft["manifest"]["scan_sha256"]
