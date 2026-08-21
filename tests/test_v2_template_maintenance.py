import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.service.v2_template_limits import (
    StreamingWriteGuard,
    V2TemplateLimitConfig,
    V2TemplateLimitError,
    V2UploadConcurrencyGate,
    require_disk_space_before_write,
    require_disk_space_during_write,
    require_single_file_size,
)
from src.service.v2_template_maintenance import (
    build_maintenance_snapshot,
    central_upload_decision,
    drawing_group_safe_view,
    list_template_metadata,
)


def test_single_file_limit_returns_natural_chinese_reason(tmp_path):
    limits = V2TemplateLimitConfig(max_file_size_bytes=8, temp_dir=tmp_path, min_free_space_bytes=0)

    with pytest.raises(V2TemplateLimitError) as exc:
        require_single_file_size(9, limits)

    assert exc.value.code == "v2_file_too_large"
    assert "单文件超过上限" in exc.value.reason


def test_concurrency_gate_rejects_extra_upload_with_chinese_reason(tmp_path):
    gate = V2UploadConcurrencyGate(
        V2TemplateLimitConfig(max_file_size_bytes=10, max_concurrent_uploads=1, temp_dir=tmp_path)
    )

    with gate.acquire():
        with pytest.raises(V2TemplateLimitError) as exc:
            with gate.acquire():
                pass

    assert exc.value.code == "v2_upload_concurrency_exceeded"
    assert "并发上传数已达到上限" in exc.value.reason
    with gate.acquire():
        assert gate.active_uploads == 1
    assert gate.active_uploads == 0


def test_disk_preflight_and_during_write_stop_safely_with_chinese_reasons(tmp_path):
    limits = V2TemplateLimitConfig(max_file_size_bytes=100, temp_dir=tmp_path, min_free_space_bytes=50)
    target = tmp_path / "incoming.ai"

    with pytest.raises(V2TemplateLimitError) as preflight:
        require_disk_space_before_write(target, 20, limits, free_space_getter=lambda _path: 60)

    with pytest.raises(V2TemplateLimitError) as during:
        require_disk_space_during_write(target, limits, free_space_getter=lambda _path: 49)

    guard = StreamingWriteGuard(target, config=limits, expected_size_bytes=10, free_space_getter=lambda _path: 49)
    with pytest.raises(V2TemplateLimitError) as streaming:
        guard.record_chunk(4)

    assert "写入前已停止" in preflight.value.reason
    assert "写入过程中磁盘剩余空间低于安全余量" in during.value.reason
    assert streaming.value.code == "v2_disk_space_during_write_failed"


def test_metadata_listing_handles_hundreds_without_reading_ai_file_content(tmp_path, monkeypatch):
    root = tmp_path / "v2"
    for index in range(125):
        template_dir = root / f"V2META{index:03d}"
        asset_dir = template_dir / "versions" / "v0001" / "assets"
        asset_dir.mkdir(parents=True)
        (asset_dir / "template.ai").write_bytes(b"ai-bytes")
        _write_json(
            template_dir / "state.json",
            {
                "template_id": f"V2META{index:03d}",
                "template": {"template_id": f"V2META{index:03d}", "name": f"模板 {index}", "shop_name": ""},
                "draft": None,
                "publication": {"status": "active", "current_version": "v0001", "rollback_version": ""},
                "versions": [{"version": "v0001", "created_at": "now", "manifest_sha256": "abc"}],
            },
        )

    original_open = Path.open
    original_read_bytes = Path.read_bytes

    def fail_ai_open(self, *args, **kwargs):
        if self.suffix == ".ai":
            raise AssertionError("metadata listing must not open AI files")
        return original_open(self, *args, **kwargs)

    def fail_ai_read_bytes(self):
        if self.suffix == ".ai":
            raise AssertionError("metadata listing must not read AI bytes")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "open", fail_ai_open)
    monkeypatch.setattr(Path, "read_bytes", fail_ai_read_bytes)

    metadata = list_template_metadata(root)
    snapshot = build_maintenance_snapshot(
        root,
        limits=V2TemplateLimitConfig(temp_dir=tmp_path, min_free_space_bytes=100),
        disk_usage_getter=lambda _path: SimpleNamespace(total=1000, used=250, free=750),
    )

    assert len(metadata) == 125
    assert snapshot["templates"]["total"] == 125
    assert snapshot["disk"]["free_bytes"] == 750


def test_drawing_group_safe_view_hides_capacity_and_disk_fields(tmp_path):
    snapshot = {
        "disk": {"free_bytes": 200, "used_bytes": 800, "capacity": "hidden"},
        "limits": {"min_free_space_bytes": 100, "max_file_size_bytes": 10},
        "templates": {"total": 1, "active": 1, "with_draft": 0, "version_count": 1},
        "template_metadata": [
            {
                "template_id": "V2SAFE001",
                "template": {"template_id": "V2SAFE001", "name": "Safe"},
                "draft": None,
                "publication": {"status": "active"},
                "versions": [{"version": "v0001"}],
            }
        ],
    }

    safe = drawing_group_safe_view(snapshot)
    keys = _all_keys(safe)

    assert safe["summary"] == {"total": 1, "active": 1, "with_draft": 0, "version_count": 1}
    assert not any(any(marker in key.lower() for marker in ("disk", "free", "usage", "capacity")) for key in keys)


def test_official_order_output_upload_guard_rejects_with_chinese_reason():
    decision = central_upload_decision("official_order_output")

    assert decision.allowed is False
    assert decision.code == "v2_official_order_output_upload_forbidden"
    assert "正式订单成品不得上传中央服务" in decision.reason


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _all_keys(value):
    if isinstance(value, dict):
        keys = list(value.keys())
        for item in value.values():
            keys.extend(_all_keys(item))
        return keys
    if isinstance(value, list):
        keys = []
        for item in value:
            keys.extend(_all_keys(item))
        return keys
    return []
