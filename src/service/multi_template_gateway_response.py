"""Safe public representations of durable multi-template parent jobs."""

from __future__ import annotations

from typing import Any, Mapping


def public_multi_template_job(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return parent task detail without local paths or mutable snapshots."""
    metadata = _mapping(record.get("multi_template"))
    preflight = _mapping(metadata.get("preflight"))
    checkpoints = {
        str(item.get("template_id") or ""): _mapping(item)
        for item in _list_of_mappings(metadata.get("template_checkpoints"))
        if str(item.get("template_id") or "")
    }
    canary_groups = {
        str(item.get("template_id") or ""): _mapping(item)
        for item in _list_of_mappings(_mapping(metadata.get("canary")).get("groups"))
        if str(item.get("template_id") or "")
    }
    groups = _list_of_mappings(preflight.get("groups"))
    issues = _deduplicated_issues(
        _list_of_mappings(preflight.get("issues"))
        + _list_of_mappings(metadata.get("issues"))
    )
    summaries = [
        _template_summary(group, checkpoints.get(str(group.get("template_id") or ""), {}), canary_groups)
        for group in groups
        if str(group.get("template_id") or "")
    ]
    outputs = _public_outputs(_mapping(record.get("outputs")))
    status = str(record.get("status") or "")
    parent_error_code = _public_code(record.get("error_code"))
    return {
        "job_id": str(record.get("job_id") or ""),
        "job_type": "multi_template_parent",
        "status": status,
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "progress": _public_progress(record.get("progress")),
        "error": _public_error(parent_error_code, kind="parent"),
        "error_code": parent_error_code,
        "request": {
            "mode": "multi_template",
            "sheet_name": str(metadata.get("sheet_name") or ""),
            "order_filename": str(_mapping(record.get("request")).get("order_filename") or ""),
        },
        "template_count": len(summaries),
        "group_count": len(summaries),
        "order_count": sum(_non_negative_int(item.get("order_count")) for item in summaries),
        "template_summaries": summaries,
        "issues": [_issue(item) for item in issues],
        "child_jobs": [_child_job(summary) for summary in summaries if summary["child_job_id"]],
        "actions": _actions(status, summaries, outputs),
        "outputs": outputs,
    }


def _template_summary(
    group: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    canary_groups: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    template_id = str(group.get("template_id") or "")
    canary = _mapping(canary_groups.get(template_id))
    preflight_error_code = _public_code(group.get("error_code"))
    error_code = _public_code(checkpoint.get("error_code"))
    return {
        "template_id": template_id,
        "order_count": _non_negative_int(group.get("order_count")),
        "excel_rows": [_non_negative_int(value) for value in _list(group.get("excel_rows"))],
        "order_nos": [str(value) for value in _list(group.get("order_nos"))],
        "preflight_status": "ready" if bool(group.get("can_render")) else "failed",
        "preflight_error_code": preflight_error_code,
        "preflight_error": _public_error(preflight_error_code, kind="preflight"),
        "canary_status": str(canary.get("status") or "pending"),
        "status": str(checkpoint.get("status") or "pending"),
        "attempt": _non_negative_int(checkpoint.get("attempt")),
        "template_version": str(checkpoint.get("template_version") or ""),
        "child_job_id": _public_child_job_id(checkpoint.get("child_job_id")),
        "error_code": error_code,
        "error": _public_error(error_code, kind="checkpoint"),
        "failure_scope": str(checkpoint.get("failure_scope") or ""),
    }


def _child_job(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_id": str(summary.get("template_id") or ""),
        "job_id": str(summary.get("child_job_id") or ""),
        "status": str(summary.get("status") or ""),
        "attempt": _non_negative_int(summary.get("attempt")),
    }


def _public_outputs(outputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "primary_output_available": bool(str(outputs.get("primary_output") or "")),
        "partial_output_available": bool(str(outputs.get("partial_output") or "")),
        "file_count": _non_negative_int(outputs.get("output_file_count")),
    }


def _actions(
    status: str,
    summaries: list[Mapping[str, Any]],
    outputs: Mapping[str, Any],
) -> dict[str, bool]:
    has_failed = any(str(item.get("status") or "") in {"failed", "canary_failed"} for item in summaries)
    return {
        "execute": status == "ready" and bool(summaries),
        "retry_failed": status in {"ready", "completed_with_errors", "failed"} and has_failed,
        "resume": status == "interrupted",
        "download_primary_output": bool(outputs.get("primary_output_available")),
        "download_partial_output": bool(outputs.get("partial_output_available")),
    }


def _issue(value: Mapping[str, Any]) -> dict[str, Any]:
    code = _public_code(value.get("code"))
    return {
        "code": code,
        "message": _public_error(code, kind="issue"),
        "suggestion": _public_suggestion(code),
        "template_id": str(value.get("template_id") or ""),
        "excel_row": _non_negative_int(value.get("excel_row")),
        "order_no": str(value.get("order_no") or ""),
    }


def _public_progress(value: Any) -> dict[str, Any]:
    progress = _mapping(value)
    return {
        "current": _non_negative_int(progress.get("current")),
        "total": _non_negative_int(progress.get("total")),
        "stage": str(progress.get("stage") or ""),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_negative_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _public_code(value: Any) -> str:
    text = str(value or "").strip()
    if text and len(text) <= 96 and all(character.isascii() and (character.islower() or character.isdigit() or character == "_") for character in text):
        return text
    return "multi_template_error" if text else ""


def _public_child_job_id(value: Any) -> str:
    text = str(value or "").strip()
    if text and len(text) <= 128 and all(character.isascii() and (character.isalnum() or character in "_-") for character in text):
        return text
    return ""


def _public_error(code: str, *, kind: str) -> str:
    if not code:
        return ""
    messages = {
        "template_id_missing": "模板 ID 不能为空。",
        "template_id_invalid": "模板 ID 格式不合法。",
        "template_not_found": "模板不存在或尚未发布。",
        "template_not_published": "模板尚未发布可用版本。",
        "template_not_active": "模板已停用，不能参与本次渲染。",
        "template_config_unavailable": "模板运行配置不完整。",
        "template_config_missing": "模板配置不完整。",
        "template_pipeline_invalid": "模板渲染流程不可执行。",
        "template_asset_unavailable": "模板文件不可用。",
        "missing_required_fonts": "本机缺少模板所需字体。",
        "orders_empty": "订单表没有可预检的订单行。",
        "source_hash_unavailable": "订单文件无法校验。",
        "multi_template_preflight_failed": "订单或模板预检未通过，请修正后重新提交。",
        "multi_template_order_file_missing": "订单文件不存在，请重新上传后预检。",
        "multi_template_preflight_storage_failed": "订单文件无法保存或读取，请检查本机存储后重试。",
        "multi_template_preflight_unavailable": "多模板订单预检暂时不可用，请稍后重新提交。",
        "multi_template_preflight_invalid": "多模板订单预检结果无效，请重新提交。",
        "multi_template_snapshot_invalid": "模板预检快照不完整，请重新预检后再渲染。",
        "multi_template_repreflight_required": "预检快照已变化，请重新预检后再渲染。",
        "multi_template_checkpoint_persist_failed": "父任务状态保存失败，后续模板已停止。",
        "multi_template_output_package_failed": "多模板成品打包失败，未生成可下载文件。",
    }
    if code in messages:
        return messages[code]
    if kind == "parent":
        return "多模板任务未完成，请检查任务状态后重试。"
    if kind == "preflight":
        return "模板预检未通过，请检查模板配置和订单字段。"
    return "模板组渲染未完成，请检查模板配置和订单数据后重试。"


def _public_suggestion(code: str) -> str:
    if code in {"template_id_missing", "template_id_invalid"}:
        return "请在“模板”列填写已启用模板的完整 ID。"
    if code in {"template_not_found", "template_not_published", "template_not_active"}:
        return "请确认模板已发布且处于启用状态。"
    return "请修正订单或模板配置后重新预检。"


def _deduplicated_issues(items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for item in items:
        key = (
            _public_code(item.get("code")),
            str(item.get("template_id") or ""),
            _non_negative_int(item.get("excel_row")),
            str(item.get("order_no") or ""),
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


__all__ = ["public_multi_template_job"]
