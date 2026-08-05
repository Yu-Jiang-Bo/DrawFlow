import json
from pathlib import Path

from openpyxl import Workbook

from src.service.http_server import RenderRequestHandler
from src.service.job_store import JobStore
from src.service.paths import DRAWFLOW_DATA_DIR, TEMPLATE_STORAGE_DIR
from src.service.render_service import RenderService, SUPPORTED_RENDER_PIPELINES, _effective_pipeline
from src.service.template_registry import DEFAULT_PIPELINES, TemplateRegistry
from src.service.v2_template_boundary import (
    V2_API_PREFIX,
    V2_DATA_DIR,
    V2_LOCAL_GATEWAY_PREFIX,
    V2_RENDER_PIPELINE,
    V2_TEMPLATE_TYPE,
    first_release_policy,
    is_v2_pipeline,
    is_v2_template_type,
)


LEGACY_TEMPLATE_BASELINES = {
    "JJMB202509231236046265": ("curved_title_text", "jjmb_202509_curved"),
    "JJMB202508261001394920": ("pure_text_color_design", "jjmb_202508"),
    "JJMB202510241154389614": ("pure_text_color_design", "generic_rules_only"),
    "JJMB202603281027102517": ("pure_text_style", "jjmb_202603_grouped"),
}


def _write_legacy_baseline_templates_config(path: Path) -> None:
    fake_ai = path.parent / "fake-template.ai"
    curved_font_report = path.parent / "curved-font-report.json"
    curved_rules_path = path.parent / "curved.rules.json"
    grouped_config_path = path.parent / "template-202603.config.json"
    grouped_rules_path = path.parent / "template-202603.rules.json"
    generic_rules_path = path.parent / "template-202510.rules.json"

    fake_ai.write_text("fake ai", encoding="utf-8")
    curved_font_report.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "status": "ok",
                        "font_option": "F1",
                        "font_name": "Test Font",
                        "baseline_ratio": {},
                        "bounds_shape_ratio": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    curved_rules_path.write_text(
        json.dumps(
            {
                "mode": "annotated_ai",
                "capabilities": ["text_on_curve"],
                "slots": [{"name": "Title", "type": "text_on_curve"}],
            }
        ),
        encoding="utf-8",
    )
    grouped_config_path.write_text(
        json.dumps(
            {
                "font_options": {"F7": {"type": "text", "font_name": "TestFont", "font_size_pt": 48}},
                "style_options": {
                    "Style1": {
                        "width_pt": 226.7716535433,
                        "height_pt": 141.7322834646,
                        "width_mm": 80,
                        "height_mm": 50,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    grouped_rules_path.write_text(
        json.dumps({"font_options": ["F7"], "style_options": ["Style1"]}),
        encoding="utf-8",
    )
    generic_rules_path.write_text(
        Path("templates/JJMB202510241154389614/template.rules.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "templates": [
                    {
                        "template_id": "JJMB202508261001394920",
                        "name": "Legacy 202508",
                        "template_type": "pure_text_color_design",
                        "pipeline": "jjmb_202508",
                        "status": "active",
                        "template_ai": str(fake_ai),
                        "default_columns": 3,
                        "default_hide_boxes": True,
                    },
                    {
                        "template_id": "JJMB202509231236046265",
                        "name": "Legacy 202509",
                        "template_type": "curved_title_text",
                        "pipeline": "jjmb_202509_curved",
                        "status": "active",
                        "template_ai": str(fake_ai),
                        "template_config": str(curved_font_report),
                        "template_rules_config": str(curved_rules_path),
                        "default_columns": 3,
                        "default_hide_boxes": True,
                    },
                    {
                        "template_id": "JJMB202510241154389614",
                        "name": "Legacy 202510",
                        "template_type": "pure_text_color_design",
                        "pipeline": "generic_rules_only",
                        "status": "active",
                        "template_ai": str(fake_ai),
                        "template_rules_config": str(generic_rules_path),
                        "default_columns": 4,
                        "default_hide_boxes": True,
                    },
                    {
                        "template_id": "JJMB202603281027102517",
                        "name": "Legacy 202603",
                        "template_type": "pure_text_style",
                        "pipeline": "jjmb_202603_grouped",
                        "status": "active",
                        "template_ai": str(fake_ai),
                        "template_config": str(grouped_config_path),
                        "template_rules_config": str(grouped_rules_path),
                        "default_columns": 4,
                        "default_hide_boxes": True,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_legacy_order(
    path: Path,
    *,
    template_id: str,
    order_no: str,
    department: str = "",
    manufacturer: str = "",
    custom_text: str = "Meg",
    quantity: int = 1,
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "订单备注",
            "店名",
            "内部订单号",
            "Order",
            "SKU",
            "产品中文名称",
            "购买数量",
            "生产部门",
            "Department",
            "模板",
            "template",
            "订单明细id",
            "SPU",
            "字体",
            "Font",
            "定制信息",
            "name",
            "字体颜色",
            "Color",
            "设计",
            "Design",
            "厂家",
            "Manufacturer",
            "Style Option",
            "Style",
            "Year",
        ]
    )
    sheet.append(
        [
            "",
            "Q-206",
            order_no,
            order_no,
            "SKU1",
            "皮质钥匙扣",
            quantity,
            department,
            department,
            template_id,
            template_id,
            f"{order_no}-DETAIL",
            "SPU1",
            "F7",
            "F7",
            custom_text,
            custom_text,
            "Gold",
            "Gold",
            "Design 3",
            "Design1",
            manufacturer,
            manufacturer,
            "Style 1",
            "Style1",
            2026,
        ]
    )
    workbook.save(path)


def _write_curved_order(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["内部订单号", "订单明细id", "生产部门", "产品中文名称", "字体颜色", "模板", "定制信息"])
    sheet.append(
        [
            "ORDER-202509",
            "ORDER-202509-DETAIL",
            "T",
            "圣诞曲线标题挂件",
            "Red",
            "JJMB202509231236046265",
            "Font Options:F1\nTitle:Family\nName:1. Kai",
        ]
    )
    workbook.save(path)


def test_v2_namespace_is_separate_from_legacy_template_storage():
    assert V2_API_PREFIX == "/api/v2/templates"
    assert V2_LOCAL_GATEWAY_PREFIX == "/local/v2/templates"
    assert V2_DATA_DIR == DRAWFLOW_DATA_DIR / "v2-templates"
    assert V2_DATA_DIR != TEMPLATE_STORAGE_DIR
    assert TEMPLATE_STORAGE_DIR.name == "templates"


def test_v2_first_release_policy_keeps_non_migration_boundaries():
    policy = first_release_policy()

    assert policy["migrates_legacy_templates"] is False
    assert policy["executes_local_shared_scope"] is False
    assert policy["allows_natural_language_rules"] is False
    assert policy["allows_arbitrary_jsx"] is False


def test_v2_identifiers_do_not_enter_legacy_registry_or_render_pipelines():
    assert is_v2_template_type(V2_TEMPLATE_TYPE)
    assert is_v2_pipeline(V2_RENDER_PIPELINE)
    assert V2_TEMPLATE_TYPE not in DEFAULT_PIPELINES
    assert V2_RENDER_PIPELINE not in SUPPORTED_RENDER_PIPELINES
    assert not is_v2_template_type("pure_text_color_design")
    assert not is_v2_pipeline("generic_rules_only")


def test_existing_four_templates_keep_their_legacy_route_baseline():
    registry = TemplateRegistry()

    for template_id, (template_type, pipeline) in LEGACY_TEMPLATE_BASELINES.items():
        template = registry.get_template(template_id)
        assert template.status == "active"
        assert template.template_type == template_type
        assert template.pipeline == pipeline
        assert _effective_pipeline(template) == pipeline


def test_existing_legacy_templates_keep_dry_run_public_output_baseline(tmp_path):
    config_path = tmp_path / "templates.json"
    _write_legacy_baseline_templates_config(config_path)
    registry = TemplateRegistry(config_path)
    cases = [
        {
            "template_id": "JJMB202508261001394920",
            "order_path": tmp_path / "orders-202508.xlsx",
            "write_order": lambda path: _write_legacy_order(
                path,
                template_id="JJMB202508261001394920",
                order_no="ORDER-202508",
                department="H",
            ),
            "output_keys": {"graphic_files", "summary_files", "bundle_plan", "delivery_plan", "output_manifest"},
            "task_type": "render_batch",
            "graphic_names": ["ORDER-202508.png"],
        },
        {
            "template_id": "JJMB202509231236046265",
            "order_path": tmp_path / "orders-202509.xlsx",
            "write_order": _write_curved_order,
            "output_keys": {"single_order_files", "bundle_plan", "delivery_plan", "output_manifest"},
            "task_type": "render_batch",
        },
        {
            "template_id": "JJMB202510241154389614",
            "order_path": tmp_path / "orders-202510.xlsx",
            "write_order": lambda path: _write_legacy_order(
                path,
                template_id="JJMB202510241154389614",
                order_no="ORDER-202510",
                department="ZW",
                manufacturer="MY-W120",
                custom_text="Alice|Bob",
                quantity=2,
            ),
            "output_keys": {"graphic_files", "bundle_plan", "delivery_plan", "output_manifest"},
            "task_type": "generic_template_rules",
            "graphic_names": ["ORDER-202510-1.png", "ORDER-202510-2.png"],
            "output_format": "png",
        },
        {
            "template_id": "JJMB202603281027102517",
            "order_path": tmp_path / "orders-202603.xlsx",
            "write_order": lambda path: _write_legacy_order(
                path,
                template_id="JJMB202603281027102517",
                order_no="ORDER-202603",
                department="H",
                custom_text="Alice",
            ),
            "output_keys": {"graphic_files", "summary_files", "bundle_plan", "delivery_plan", "output_manifest"},
            "task_type": "render_batch",
            "graphic_names": ["ORDER-202603.png"],
        },
    ]

    for case in cases:
        case["write_order"](case["order_path"])
        record = RenderService(
            registry=registry,
            jobs=JobStore(tmp_path / f"jobs-{case['template_id']}"),
        ).submit({"template_id": case["template_id"], "order_file": str(case["order_path"]), "dry_run": True})

        assert record["status"] == "completed", record.get("error")
        assert record["stats"]["dry_run"] is True
        assert case["output_keys"] <= set(record["outputs"])
        assert "primary_output" not in record["outputs"]
        assert V2_TEMPLATE_TYPE not in json.dumps(record["outputs"], ensure_ascii=False)
        task = json.loads(Path(record["outputs"]["render_task"]).read_text(encoding="utf-8"))
        assert task["type"] == case["task_type"]
        if "output_format" in case:
            assert task["output"]["format"] == case["output_format"]
        if "graphic_names" in case:
            assert [item["name"] for item in record["outputs"]["graphic_files"]] == case["graphic_names"]


def test_legacy_api_template_payload_does_not_expose_v2_namespace(tmp_path):
    config_path = tmp_path / "templates.json"
    _write_legacy_baseline_templates_config(config_path)
    registry = TemplateRegistry(config_path)
    handler = object.__new__(RenderRequestHandler)

    payloads = [handler._template_payload(template) for template in registry.list_templates()]

    assert {payload["template_id"] for payload in payloads} == set(LEGACY_TEMPLATE_BASELINES)
    payload_blob = json.dumps(payloads, ensure_ascii=False)
    assert V2_API_PREFIX not in payload_blob
    assert V2_LOCAL_GATEWAY_PREFIX not in payload_blob
    assert V2_TEMPLATE_TYPE not in payload_blob
    assert V2_RENDER_PIPELINE not in payload_blob


def test_v2_fixture_readme_records_first_release_scope():
    text = Path("tests/fixtures/v2_templates/README.md").read_text(encoding="utf-8")

    assert "不迁移现有四个生产模板" in text
    assert "不执行 `component_key` / `scope=local/shared` 传播" in text
    assert "真实 `.ai`" in text
