import json
from pathlib import Path

from openpyxl import Workbook

from src.jjmb_config_grouped_main import build_grouped_task
from src.render_task import RenderTaskError
from src.service.job_store import JobStore
from src.service.http_server import RenderRequestHandler
from src.service.render_service import (
    RenderService,
    _configured_font_options,
    _design_font_options,
    _merge_202508_template_config,
    _missing_202508_font_configs,
)
from src.service.template_registry import TemplateRegistry


def write_order_xlsx(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "订单备注",
            "店名",
            "内部订单号",
            "SKU",
            "产品中文名称",
            "购买数量",
            "生产部门",
            "模板",
            "订单明细id",
            "SPU",
            "字体",
            "定制信息",
            "字体颜色",
            "设计",
        ]
    )
    sheet.append(
        [
            "",
            "Q-206",
            "ORDER1",
            "SKU1",
            "平纹方形皮质首饰盒",
            "1",
            "K",
            "JJMB202508261001394920",
            "DETAIL1",
            "SPU1",
            "F7",
            "Meg",
            "Gold",
            "Design 3",
        ]
    )
    workbook.save(path)


def write_templates_config(path: Path) -> None:
    fake_ai = path.parent / "fake-template.ai"
    fake_ai.write_text("fake ai", encoding="utf-8")
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "templates": [
                    {
                        "template_id": "JJMB202508261001394920",
                        "name": "测试模板",
                        "template_type": "pure_text_color_design",
                        "pipeline": "jjmb_202508",
                        "status": "active",
                        "template_ai": str(fake_ai),
                        "default_columns": 3,
                        "default_hide_boxes": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_service_dry_run_creates_job_and_render_task(tmp_path):
    config_path = tmp_path / "templates.json"
    order_path = tmp_path / "orders.xlsx"
    write_templates_config(config_path)
    write_order_xlsx(order_path)

    service = RenderService(
        registry=TemplateRegistry(config_path),
        jobs=JobStore(tmp_path / "jobs"),
    )

    record = service.submit(
        {
            "template_id": "JJMB202508261001394920",
            "order_file": str(order_path),
            "dry_run": True,
            "output_name": "result.ai",
        }
    )

    assert record["status"] == "completed"
    assert record["stats"]["groups"] == 1
    assert record["stats"]["items"] == 1
    assert record["stats"]["dry_run"] is True
    task_path = Path(record["outputs"]["render_task"])
    assert task_path.exists()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["groups"][0]["items"][0]["production_label_lines"] == ["ORDER1", "Gold"]
    assert task["output"]["color_mode"] == "CMYK"
    assert task["output"]["outline_text"] is True
    assert task["output"]["pathfinder_merge"] is True


def test_template_registry_resolves_defaults(tmp_path):
    config_path = tmp_path / "templates.json"
    write_templates_config(config_path)

    template = TemplateRegistry(config_path).get_template("JJMB202508261001394920")

    assert template.default_columns == 3
    assert template.default_hide_boxes is True
    assert template.pipeline == "jjmb_202508"


def test_template_registry_upserts_uploaded_template_and_rules(tmp_path):
    config_path = tmp_path / "templates.json"
    storage_dir = tmp_path / "templates"
    registry = TemplateRegistry(config_path, storage_dir)

    ai_path = registry.save_uploaded_ai("JJMB202607030001", "source.ai", b"fake ai")
    rule_path = registry.save_template_config(
        "JJMB202607030001",
        '{"template_id":"JJMB202607030001","defaults":{"color":"Gold"}}',
    )
    template = registry.upsert_template(
        {
            "template_id": "JJMB202607030001",
            "name": "新增模板",
            "template_type": "pure_text_color_design",
            "status": "active",
            "template_ai": registry.to_config_path(ai_path),
            "template_config": registry.to_config_path(rule_path),
            "default_columns": "6",
            "default_hide_boxes": "false",
        }
    )

    assert template.template_id == "JJMB202607030001"
    assert template.template_ai.exists()
    assert template.template_config and template.template_config.exists()
    assert template.default_columns == 6
    assert template.default_hide_boxes is False
    assert template.pipeline == "jjmb_202508"


def test_register_template_uses_reference_ai_when_size_template_is_empty(tmp_path):
    handler = object.__new__(RenderRequestHandler)
    handler.registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")

    template = handler._register_template(
        {
            "template_id": "JJMB202607030005",
            "name": "只传原始参考模板",
            "template_type": "pure_text_color_design",
            "status": "active",
        },
        {"reference_ai": [{"filename": "source.ai", "content": b"source ai"}]},
    )

    assert template.template_ai and template.template_ai.exists()
    assert template.template_ai_role == "原始参考模板"
    assert template.assets == []


def test_register_template_keeps_existing_reference_when_size_template_is_added(tmp_path):
    handler = object.__new__(RenderRequestHandler)
    handler.registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")

    first = handler._register_template(
        {
            "template_id": "JJMB202607030015",
            "name": "先传原始参考模板",
            "template_type": "pure_text_color_design",
            "status": "active",
        },
        {"reference_ai": [{"filename": "source.ai", "content": b"source ai"}]},
    )

    updated = handler._register_template(
        {
            "template_id": first.template_id,
            "name": first.name,
            "template_type": first.template_type,
            "status": "active",
        },
        {"template_ai": [{"filename": "layout.ai", "content": b"layout ai"}]},
    )

    assert updated.template_ai and updated.template_ai.read_bytes() == b"layout ai"
    assert updated.template_ai_role == "尺寸/作图区模板"
    assert len(updated.assets) == 1
    assert updated.assets[0]["role"] == "原始参考模板"
    reference_copy = Path(updated.assets[0]["stored_path"])
    assert reference_copy.read_bytes() == b"source ai"


def test_register_template_keeps_reference_ai_as_asset_when_size_template_exists(tmp_path):
    handler = object.__new__(RenderRequestHandler)
    handler.registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")

    template = handler._register_template(
        {
            "template_id": "JJMB202607030006",
            "name": "参考和尺寸模板",
            "template_type": "pure_text_color_design",
            "status": "active",
        },
        {
            "template_ai": [{"filename": "layout.ai", "content": b"layout ai"}],
            "reference_ai": [{"filename": "source.ai", "content": b"source ai"}],
        },
    )

    assert template.template_ai and template.template_ai.exists()
    assert template.template_ai_role == "尺寸/作图区模板"
    assert len(template.assets) == 1
    assert template.assets[0]["role"] == "原始参考模板"


def test_register_template_saves_rules_without_overwriting_structure_config(tmp_path):
    handler = object.__new__(RenderRequestHandler)
    handler.registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    structure_config = tmp_path / "curved-title-mark-report.json"
    structure_config.write_text('{"entries":[{"font_option":"F14","status":"ok"}]}', encoding="utf-8")
    ai_path = handler.registry.save_uploaded_ai("JJMB202607030007", "template.ai", b"ai")
    handler.registry.upsert_template(
        {
            "template_id": "JJMB202607030007",
            "name": "曲线标题模板",
            "template_type": "curved_title_text",
            "pipeline": "jjmb_202509_curved",
            "status": "active",
            "template_ai": handler.registry.to_config_path(ai_path),
            "template_config": str(structure_config),
        }
    )

    template = handler._register_template(
        {
            "template_id": "JJMB202607030007",
            "name": "曲线标题模板",
            "template_type": "curved_title_text",
            "status": "active",
            "template_rules_json": '{"raw_text":"业务规则","font_options":["F14"],"parser":{"source":"llm"}}',
            "template_rules_text": "业务规则",
        },
        {},
    )

    assert template.template_config == structure_config
    assert template.template_rules_config and template.template_rules_config.name == "template.rules.json"
    assert "font_options" in template.template_rules_config.read_text(encoding="utf-8")


def test_template_registry_saves_multiple_ai_assets(tmp_path):
    config_path = tmp_path / "templates.json"
    storage_dir = tmp_path / "templates"
    registry = TemplateRegistry(config_path, storage_dir)

    ai_path = registry.save_uploaded_ai("JJMB202607030002", "main.ai", b"main ai")
    assets = registry.save_uploaded_assets(
        "JJMB202607030002",
        [
            {"filename": "design-a.ai", "content": b"asset a"},
            {"filename": "design-b.ai", "content": b"asset b"},
        ],
        role="独立设计模板",
    )
    template = registry.upsert_template(
        {
            "template_id": "JJMB202607030002",
            "name": "多资产模板",
            "template_type": "pure_text_color_design",
            "status": "active",
            "template_ai": registry.to_config_path(ai_path),
            "assets": assets,
        }
    )

    assert len(template.assets) == 2
    assert template.assets[0]["file_name"] == "design-a.ai"
    assert template.assets[0]["role"] == "独立设计模板"
    assert Path(template.assets[0]["stored_path"]).name == "design-a.ai"
    assert (storage_dir / "JJMB202607030002" / "assets" / "design-a.ai").exists()


def test_render_service_reads_design_font_options_from_llm_rule_shape():
    assert _design_font_options(
        {
            "design_options": {
                "design_font_options": ["F10", "F11", "F12"],
            }
        }
    ) == ["F10", "F11", "F12"]


def test_render_service_normalizes_object_option_rules():
    config = {
        "font_options": [{"id": "F1"}, {"name": "F2"}],
        "design_font_options": [{"font_option": "F10"}],
        "design_options": {
            "design_font_options": [{"id": "F11"}],
        },
    }

    assert _configured_font_options(config) == ["F1", "F2"]
    assert _design_font_options(config) == ["F10", "F11"]


def test_202508_template_config_merge_fills_missing_font_options():
    base = {
        "font_options": {
            "F1": {"font_name": "Base Font"},
        },
        "design_options": {"Design1": {"box": "base"}},
    }
    reference = {
        "font_options": {
            "F1": {"font_name": "Reference Font"},
            "F7": {"font_name": "Reference F7"},
        }
    }

    merged = _merge_202508_template_config(base, reference)

    assert merged["font_options"]["F1"]["font_name"] == "Base Font"
    assert merged["font_options"]["F7"]["font_name"] == "Reference F7"
    assert merged["design_options"] == {"Design1": {"box": "base"}}


def test_202508_missing_font_configs_reports_used_options_only_once():
    config = {"font_options": {"F1": {"font_name": "A"}}}

    assert _missing_202508_font_configs(config, ["F1", "F7", "F7", ""]) == ["F7"]


def test_template_registry_deletes_asset_registration_without_removing_files(tmp_path):
    config_path = tmp_path / "templates.json"
    storage_dir = tmp_path / "templates"
    registry = TemplateRegistry(config_path, storage_dir)

    ai_path = registry.save_uploaded_ai("JJMB202607030003", "main.ai", b"main ai")
    assets = registry.save_uploaded_assets(
        "JJMB202607030003",
        [{"filename": "design-a.ai", "content": b"asset a"}],
        role="独立设计模板",
    )
    asset_path = storage_dir / "JJMB202607030003" / "assets" / "design-a.ai"
    registry.upsert_template(
        {
            "template_id": "JJMB202607030003",
            "name": "待删除模板",
            "template_type": "pure_text_color_design",
            "status": "active",
            "template_ai": registry.to_config_path(ai_path),
            "assets": assets,
        }
    )

    removed = registry.delete_template_asset("JJMB202607030003", 0)

    assert removed["file_name"] == "design-a.ai"
    assert ai_path.exists()
    assert asset_path.exists()
    assert registry.get_template("JJMB202607030003").assets == []


def test_template_registry_deletes_primary_ai_registration_without_removing_file(tmp_path):
    config_path = tmp_path / "templates.json"
    storage_dir = tmp_path / "templates"
    registry = TemplateRegistry(config_path, storage_dir)

    ai_path = registry.save_uploaded_ai("JJMB202607030004", "main.ai", b"main ai")
    registry.upsert_template(
        {
            "template_id": "JJMB202607030004",
            "name": "待删除主模板",
            "template_type": "pure_text_color_design",
            "status": "active",
            "template_ai": registry.to_config_path(ai_path),
        }
    )

    removed = registry.delete_template_ai("JJMB202607030004")
    template = registry.get_template("JJMB202607030004")

    assert removed["role"] == "尺寸/作图区模板"
    assert ai_path.exists()
    assert template.template_ai is None


def test_service_accepts_string_boolean_flags(tmp_path):
    config_path = tmp_path / "templates.json"
    order_path = tmp_path / "orders.xlsx"
    write_templates_config(config_path)
    write_order_xlsx(order_path)

    service = RenderService(
        registry=TemplateRegistry(config_path),
        jobs=JobStore(tmp_path / "jobs"),
    )

    record = service.submit(
        {
            "template_id": "JJMB202508261001394920",
            "order_file": str(order_path),
            "dry_run": "true",
            "hide_boxes": "false",
        }
    )

    assert record["status"] == "completed"
    task_path = Path(record["outputs"]["render_task"])
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["layout"]["show_style_boxes"] is True


def test_grouped_pipeline_reports_template_mismatch_when_no_groups(tmp_path):
    order_path = tmp_path / "orders.xlsx"
    write_order_xlsx(order_path)

    try:
        build_grouped_task(
            xlsx_path=order_path,
            template_config=tmp_path / "template.config.json",
            output_ai=tmp_path / "out.ai",
            columns=4,
        )
    except RenderTaskError as exc:
        message = str(exc)
        assert "订单表没有解析到可渲染内容" in message
        assert "JJMB202508261001394920" in message
        assert "JJMB202603281027102517" in message
    else:
        raise AssertionError("template mismatch should fail with a readable error")


def test_service_rejects_missing_order_file(tmp_path):
    config_path = tmp_path / "templates.json"
    write_templates_config(config_path)
    service = RenderService(
        registry=TemplateRegistry(config_path),
        jobs=JobStore(tmp_path / "jobs"),
    )

    try:
        service.submit({"template_id": "JJMB202508261001394920", "order_file": ""})
    except Exception as exc:
        assert "缺少 order_file" in str(exc)
    else:
        raise AssertionError("missing order_file should fail")


def test_job_store_lists_recent_jobs(tmp_path):
    jobs = JobStore(tmp_path / "jobs")
    first = jobs.create({"template_id": "A"})
    second = jobs.create({"template_id": "B"})

    recent = jobs.list_recent(2)

    assert [item["job_id"] for item in recent] == [second["job_id"], first["job_id"]]
