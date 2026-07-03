import json
from pathlib import Path

from openpyxl import Workbook

from src.service.job_store import JobStore
from src.service.render_service import RenderService
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
                        "template_ai": "fake-template.ai",
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
    assert task["groups"][0]["items"][0]["production_label_lines"] == ["ORDER1", "Gold  Meg"]


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
    assert Path(template.assets[0]["stored_path"]).name == "design-a.ai"
    assert (storage_dir / "JJMB202607030002" / "assets" / "design-a.ai").exists()


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
