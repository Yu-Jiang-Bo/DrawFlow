import json
from pathlib import Path

from src.service.rule_store import DepartmentRuleStore, infer_department_rule_from_text


def write_rules(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "default": {"show_frame": False},
                "shop_rules": {"global_requirements": {"must_outline_text": True}},
                "rules": [
                    {
                        "name": "H",
                        "display_name": "H 部门",
                        "departments": ["H"],
                        "match": "exact",
                        "label_fields": ["order_no", "text"],
                        "label_lines": [["order_no"], ["text"]],
                        "apply_color_to_artwork": True,
                        "show_frame": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_publish_department_rule_preserves_global_sections(tmp_path):
    rules_path = tmp_path / "department_rules.json"
    drafts_path = tmp_path / "drafts.json"
    write_rules(rules_path)
    store = DepartmentRuleStore(rules_path, drafts_path)

    result = store.publish(
        {
            "rule_name": "K_T",
            "display_name": "K/T 部门",
            "departments": ["K", "T"],
            "label_fields": ["订单号", "字体颜色"],
            "show_frame": False,
            "apply_color_to_artwork": False,
        }
    )

    raw = json.loads(rules_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert raw["default"]["show_frame"] is False
    assert raw["shop_rules"]["global_requirements"]["must_outline_text"] is True
    assert any(rule["name"] == "K_T" for rule in raw["rules"])
    saved = next(rule for rule in raw["rules"] if rule["name"] == "K_T")
    assert saved["label_fields"] == ["order_no", "color_option"]
    assert saved["label_lines"] == [["order_no"], ["color_option"]]


def test_save_department_draft_and_read_back(tmp_path):
    rules_path = tmp_path / "department_rules.json"
    drafts_path = tmp_path / "drafts.json"
    write_rules(rules_path)
    store = DepartmentRuleStore(rules_path, drafts_path)

    store.save_draft(
        {
            "rule_name": "D_CONTAINS",
            "display_name": "含 D 部门",
            "departments": "D",
            "match": "contains",
            "label_fields": "订单号、产品名称",
            "show_frame": True,
        }
    )

    payload = store.read()
    assert payload["rules"][0]["name"] == "H"
    assert payload["drafts"][0]["rule_name"] == "D_CONTAINS"
    assert payload["drafts"][0]["label_fields"] == ["order_no", "product_name"]


def test_infer_department_rule_from_natural_text():
    draft = infer_department_rule_from_text("K/T 部门输出订单号和字体颜色，不带框，颜色只作为标注")

    assert draft["departments"] == ["K", "T"]
    assert draft["label_fields"] == ["order_no", "color_option"]
    assert draft["show_frame"] is False
    assert draft["apply_color_to_artwork"] is False
