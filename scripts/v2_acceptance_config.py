"""Pure scan-to-config helpers for the isolated V2 acceptance runner."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from src.service.v2_order_preflight import preflight_v2_order_rows
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_VERIFICATION_KEYS


def _by_key(items: Any, key: str) -> dict[str, Any]:
    matches = [
        dict(item) for item in items
        if isinstance(item, Mapping) and str(item.get("key") or "") == key
    ]
    if len(matches) != 1:
        raise ValueError(f"扫描与源配置无法唯一对应：{key}")
    return matches[0]


def _slot(scan_slot: Mapping[str, Any], scan_option: Mapping[str, Any], old: Mapping[str, Any]) -> dict[str, Any]:
    old_tails = {
        str(item.get("key") or ""): dict(item)
        for item in old.get("tails", []) if isinstance(item, Mapping)
    }
    tails = []
    for item in scan_slot.get("tails", []):
        key = str(item.get("key") or "")
        tail = {name: item.get(name) for name in ("key", "position", "sample")}
        for proof in ("pua_base", "glyph_map"):
            if old_tails.get(key, {}).get(proof) not in (None, "", {}):
                tail[proof] = deepcopy(old_tails[key][proof])
        tails.append(tail)
    anchor = str(scan_slot.get("anchor") or "")
    anchor_item = next(
        (item for item in scan_option.get("anchors", []) if item.get("key") == anchor),
        {},
    )
    dimensions = dict(anchor_item.get("dimensions") or scan_slot.get("dimensions") or {})
    preset = str(old.get("preset") or scan_slot.get("preset") or "direct_text")
    if preset == "tail_text" and any(not (tail.get("pua_base") or tail.get("glyph_map")) for tail in tails):
        preset = "direct_text"
    if "path" in str(scan_slot.get("text_kind") or "").casefold():
        preset = "path_text"
    return {
        "key": str(scan_slot["key"]),
        "source_field": str(old.get("source_field") or "name"),
        "required": bool(old.get("required", True)),
        "preset": preset,
        "anchor": anchor,
        "tails": tails,
        "asset_key": str(scan_slot.get("asset_key") or ""),
        "dimension_rule": {
            "mode": "anchor" if anchor else "slot",
            "tolerance_mm": 0.007,
            **dimensions,
        },
        "font_dependencies": list(scan_slot.get("font_dependencies") or []),
        "color_binding": str(old.get("color_binding") or ""),
    }


def _option(group: str, scanned: Mapping[str, Any], old: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(old))
    result.update({"key": str(scanned["key"]), "label": str(old.get("label") or scanned["key"])})
    if group == "style":
        old_dimensions = dict(old.get("dimensions") or {})
        dimensions = dict(scanned.get("dimensions") or old_dimensions)
        result["dimensions"] = {
            "mode": str(old_dimensions.get("mode") or "fixed"),
            "tolerance_mm": 0.007,
            **dimensions,
        }
        return result
    old_slots = [dict(item) for item in old.get("slots", []) if isinstance(item, Mapping)]
    slots = [
        _slot(item, scanned, _by_key(old_slots, str(item["key"])))
        for item in scanned.get("slots", [])
    ]
    if len(slots) == 2 and {item["key"] for item in slots} == {"slot_name1", "slot_name2"}:
        for item in slots:
            item["source_field"] = "name1" if item["key"] == "slot_name1" else "name2"
        content_preset = "mixed_slots"
    else:
        content_preset = str(old.get("content_preset") or (slots[0]["preset"] if len(slots) == 1 else ""))
    old_assets = {
        str(item.get("asset_key") or ""): dict(item)
        for item in old.get("assets", []) if isinstance(item, Mapping)
    }
    assets = []
    for item in scanned.get("assets", []):
        key = str(item.get("asset_key") or "")
        scanned_fields = {
            name: deepcopy(item.get(name)) for name in ("asset_key", "slot", "supported_values")
        }
        assets.append({**old_assets.get(key, {}), **scanned_fields})
    result.update({
        "content_preset": content_preset,
        "font_dependencies": list(scanned.get("font_dependencies") or []),
        "slots": slots,
        "assets": assets,
    })
    return result


def _rebuild_outputs(config: Mapping[str, Any], scan: Mapping[str, Any]) -> list[dict[str, Any]]:
    old_outputs = [
        dict(item) for item in config.get("outputs", []) if isinstance(item, Mapping)
    ]
    outputs = []
    for scanned in scan.get("outputs", []):
        output = deepcopy(_by_key(old_outputs, str(scanned["key"])))
        output["key"] = str(scanned["key"])
        output["display_name"] = (
            "主效果图" if output["key"] == "Output_main"
            else str(output.get("display_name") or output["key"])
        )
        for group, scan_name in (("style", "styles"), ("design", "designs"), ("font", "fonts")):
            old_group = dict(output.get(group) or {})
            old_options = old_group.get("options", [])
            old_group["options"] = [
                _option(group, item, _by_key(old_options, str(item["key"])))
                for item in scanned.get(scan_name, [])
            ]
            output[group] = old_group
        outputs.append(output)
    return outputs


def _set_bindings_and_mappings(config: dict[str, Any], outputs: list[dict[str, Any]]) -> None:
    used_fields = {
        str(dict(output.get(group) or {}).get("field") or "")
        for output in outputs for group in ("style", "design", "font")
    }
    used_fields |= {
        str(slot.get("source_field") or "")
        for output in outputs
        for group in ("design", "font")
        for option in dict(output.get(group) or {}).get("options", [])
        for slot in option.get("slots", [])
    }
    if "name1" in used_fields or "name2" in used_fields:
        used_fields.add("name")
    bindings = {
        str(key): str(value)
        for key, value in dict(config.get("field_bindings") or {}).items()
        if str(key) in used_fields and str(key) != "title"
    }
    if "name" in used_fields:
        bindings["name"] = str(bindings.get("name") or "Name")
    if "name1" in used_fields or "name2" in used_fields:
        bindings.update({"name1": "Name", "name2": "Title"})
    config["field_bindings"] = bindings
    valid_targets = {
        (output["key"], group, option["key"])
        for output in outputs
        for group in ("style", "design", "font")
        for option in output[group]["options"]
    }
    config["option_mappings"] = [
        dict(item) for item in config.get("option_mappings", [])
        if (item.get("output"), item.get("group"), item.get("target")) in valid_targets
    ]


def build_acceptance_config(
    source: Mapping[str, Any], scan: Mapping[str, Any], template_id: str
) -> dict[str, Any]:
    if scan.get("blocked") or scan.get("issues"):
        raise ValueError("本次真实扫描含阻断问题，不能构造验收配置。")
    config = deepcopy(dict(source))
    template = dict(config.get("template") or {})
    template.update({"template_id": template_id, "name": str(template.get("name") or "V2 真实验收")})
    config["template"] = template
    outputs = _rebuild_outputs(config, scan)
    config["outputs"] = outputs
    scan_colors = {str(item.get("key") or "") for item in scan.get("colors", [])}
    config["colors"] = [
        item for item in config.get("colors", []) if str(item.get("key") or "") in scan_colors
    ]
    _set_bindings_and_mappings(config, outputs)
    config["checks"] = {
        key: {
            "status": "pending" if key == "preview" else "confirmed",
            "reason": "隔离验收已核对本次真实扫描与配置。",
        }
        for key in V2_VERIFICATION_KEYS
    }
    config["preview"] = {"sample_rows": [], "evidence": {}}
    audit = dict(config.get("audit") or {})
    evidence = dict(scan.get("evidence") or {})
    audit.update({
        "scan_version": str(evidence.get("object_path_digest") or ""),
        "template_sha256": str(evidence.get("template_sha256") or ""),
        "config_version": int(audit.get("config_version") or 0) + 1,
    })
    config.update({"$schema": V2_CONTRACT_SCHEMA, "schema_version": 1, "audit": audit})
    return config


def _mapping_value(
    config: Mapping[str, Any], output: str, group: str, field: str, target: str
) -> str:
    return next((
        str(item.get("source_value") or "")
        for item in config.get("option_mappings", [])
        if item.get("output") == output
        and item.get("group") == group
        and item.get("field") == field
        and item.get("target") == target
    ), target)


def sample_for_design02(config: Mapping[str, Any]) -> dict[str, str]:
    bindings = dict(config.get("field_bindings") or {})
    sample: dict[str, str] = {}
    for output in config.get("outputs", []):
        for group in ("style", "design", "font"):
            data = dict(output.get(group) or {})
            options = list(data.get("options", []))
            if not options:
                continue
            has_design02 = group == "design" and any(item.get("key") == "Design02" for item in options)
            target = "Design02" if has_design02 else str(options[0]["key"])
            field = str(data.get("field") or "")
            header = str(bindings.get(field) or "")
            if not field or not header:
                raise ValueError(f"{output.get('key')}/{group} 缺少真实订单字段绑定。")
            sample[header] = _mapping_value(config, str(output["key"]), group, field, target)
    sample.update({str(bindings["name1"]): "Alice", str(bindings["name2"]): "Manager"})
    return sample


def split_probe(config: Mapping[str, Any], sample: Mapping[str, Any]) -> dict[str, Any]:
    clone, selected = deepcopy(dict(config)), None
    for output in clone["outputs"]:
        for option in output["design"]["options"]:
            keys = {slot["key"] for slot in option["slots"]}
            if option["key"] == "Design10" and keys == {"slot_name1", "slot_name2"}:
                selected = (output, option)
    if selected is None:
        raise ValueError("未找到可用于共享字段拆分验证的双槽设计。")
    output, option = selected
    option["content_preset"] = "split_by_pipe"
    for slot in option["slots"]:
        slot.update({"source_field": "name", "preset": "split_by_pipe"})
    field = str(output["design"]["field"])
    header = str(clone["field_bindings"]["name"])
    base = dict(sample)
    design_header = str(clone["field_bindings"][field])
    base[design_header] = _mapping_value(clone, output["key"], "design", field, option["key"])
    good, bad = dict(base), dict(base)
    good[header], bad[header] = "Alice | Manager", "Alice"
    accepted = preflight_v2_order_rows(clone, [good])
    rejected = preflight_v2_order_rows(clone, [bad])
    if not accepted.get("can_render") or rejected.get("can_render"):
        raise RuntimeError("共享字段拆分合同未产生预期的通过/阻断结果。")
    return {
        "option": option["key"],
        "with_pipe": {"can_render": True},
        "without_pipe": {
            "can_render": False,
            "issues": [
                {"code": item["code"], "reason": item["reason"]} for item in rejected["issues"]
            ],
        },
    }


__all__ = ["build_acceptance_config", "sample_for_design02", "split_probe"]
