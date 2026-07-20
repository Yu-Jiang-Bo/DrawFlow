import io
import json
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.service.local_client import LocalClientError, LocalDrawFlowClient, LocalTemplateCache
from src.service.runtime_templates import sha256_file


class FakeCentral:
    def __init__(self, manifest, bundle):
        self.manifest = manifest
        self.bundle = bundle
        self.imported = None
        self.downloads = 0
        self.base_url = "fake://central"

    def get_manifest(self, template_id):
        assert template_id == self.manifest["template_id"]
        return self.manifest

    def download_bundle(self, template_id, version):
        self.downloads += 1
        return self.bundle

    def import_scan(self, payload):
        self.imported = payload
        return {"template_id": payload["template_id"], "onboarding": {"draft": {"structure": payload["scan"]}}}


def make_bundle(
    tmp_path,
    *,
    version="v0001",
    bad_hash=False,
    required_fonts=None,
    include_template_config=False,
):
    source = tmp_path / version
    source.mkdir()
    (source / "template.ai").write_bytes(b"ai")
    (source / "rules.json").write_text(json.dumps({"required_fonts": required_fonts or []}), encoding="utf-8")
    if include_template_config:
        (source / "template.config.json").write_text(
            json.dumps({"style_options": {"Style5": {"width_pt": 10}}}),
            encoding="utf-8",
        )
    assets_dir = source / "assets"
    assets_dir.mkdir()
    (assets_dir / "asset.ai").write_bytes(b"asset")
    files = []
    names = ["template.ai", "rules.json", "assets/asset.ai"]
    if include_template_config:
        names.insert(1, "template.config.json")
    for name in names:
        path = source / name
        files.append({"path": name, "sha256": "bad" if bad_hash and name == "template.ai" else sha256_file(path)})
    manifest = {
        "template_id": "DEMO001",
        "version": version,
        "template": {
            "template_id": "DEMO001",
            "name": "Demo",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "default_columns": 3,
            "default_hide_boxes": True,
        },
        "required_fonts": required_fonts or [],
        "assets": [{"file_name": "asset.ai", "role": "独立设计资源", "path": "assets/asset.ai"}],
        "files": files,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(source / "template.ai", "template.ai")
        archive.write(source / "rules.json", "rules.json")
        if include_template_config:
            archive.write(source / "template.config.json", "template.config.json")
        archive.write(source / "assets/asset.ai", "assets/asset.ai")
    return manifest, buffer.getvalue()


def write_order(path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["内部订单号", "生产部门", "模板", "字体", "定制信息", "字体颜色", "设计"])
    sheet.append(["ORDER1", "K", "DEMO001", "F1", "Alice", "Gold", "Design1"])
    workbook.save(path)


def test_local_cache_downloads_hits_cache_and_updates_versions(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    central = FakeCentral(manifest, bundle)
    cache = LocalTemplateCache(central, tmp_path / "local")

    first = cache.ensure_template("DEMO001")
    second = cache.ensure_template("DEMO001")
    central.manifest, central.bundle = make_bundle(tmp_path, version="v0002")
    third = cache.ensure_template("DEMO001")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert third.version == "v0002"
    assert third.cache_hit is False
    assert central.downloads == 2
    template = cache.registry().get_template("DEMO001")
    assert template.assets[0]["file_name"] == "asset.ai"
    assert Path(template.assets[0]["stored_path"]).exists()


def test_local_cache_registers_template_config_for_structured_renderers(tmp_path):
    manifest, bundle = make_bundle(tmp_path, include_template_config=True)
    cache = LocalTemplateCache(FakeCentral(manifest, bundle), tmp_path / "local")

    cache.ensure_template("DEMO001")

    template = cache.registry().get_template("DEMO001")
    assert template.template_config is not None
    assert Path(template.template_config).name == "template.config.json"
    assert Path(template.template_config).exists()


def test_local_cache_rejects_hash_mismatch(tmp_path):
    manifest, bundle = make_bundle(tmp_path, bad_hash=True)

    with pytest.raises(LocalClientError, match="SHA256"):
        LocalTemplateCache(FakeCentral(manifest, bundle), tmp_path / "local").ensure_template("DEMO001")


def test_local_cache_rejects_unsafe_zip_member(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("../escape.txt", "bad")

    with pytest.raises(LocalClientError, match="不安全路径"):
        LocalTemplateCache(FakeCentral(manifest, buffer.getvalue()), tmp_path / "local").ensure_template("DEMO001")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("file_path", "../outside.ai", "不安全路径"),
        ("asset_path", "C:/outside.ai", "不安全路径"),
        ("file_hash", "", "SHA256 无效"),
    ],
)
def test_local_cache_rejects_unsafe_manifest_paths_and_hashes(tmp_path, field, value, message):
    manifest, bundle = make_bundle(tmp_path)
    if field == "file_path":
        manifest["files"][0]["path"] = value
    elif field == "asset_path":
        manifest["assets"][0]["path"] = value
    else:
        manifest["files"][0]["sha256"] = value
    central = FakeCentral(manifest, bundle)

    with pytest.raises(LocalClientError, match=message):
        LocalTemplateCache(central, tmp_path / "local").ensure_template("DEMO001")

    assert central.downloads == 0


def test_local_render_downloads_template_and_runs_dry_run(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    order = tmp_path / "orders.xlsx"
    write_order(order)
    client = LocalDrawFlowClient(FakeCentral(manifest, bundle), tmp_path / "local", font_dirs=[])

    record = client.render({"template_id": "DEMO001", "order_file": str(order), "dry_run": True})

    assert record["status"] == "completed", record
    assert record["template_cache"]["version"] == "v0001"
    assert Path(record["outputs"]["render_task"]).exists()


def test_local_render_reports_missing_fonts_before_illustrator(tmp_path):
    manifest, bundle = make_bundle(tmp_path, required_fonts=["MissingFont"])
    order = tmp_path / "orders.xlsx"
    write_order(order)
    client = LocalDrawFlowClient(FakeCentral(manifest, bundle), tmp_path / "local", font_dirs=[])

    with pytest.raises(LocalClientError, match="本机缺少模板字体"):
        client.render({"template_id": "DEMO001", "order_file": str(order), "dry_run": True})


def test_local_scan_uploads_scan_json_and_files_to_central(tmp_path):
    class FakeInspector:
        def scan(self, template, store, visible=False):
            return {"scan_evidence": {"scan_version": "scan-1", "items": [{"name": "Name"}]}}

    manifest, bundle = make_bundle(tmp_path)
    central = FakeCentral(manifest, bundle)
    client = LocalDrawFlowClient(central, tmp_path / "local", inspector=FakeInspector())

    result = client.scan_and_import(
        {"template_id": "DEMO001", "name": "Demo", "template_type": "pure_text"},
        [{"filename": "template.ai", "content": b"ai"}],
    )

    assert result["template_id"] == "DEMO001"
    assert central.imported["scan"]["scan_version"] == "scan-1"
    assert central.imported["files"][0]["filename"] == "template.ai"
