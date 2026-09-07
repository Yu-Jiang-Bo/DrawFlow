from __future__ import annotations

import hashlib
import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from src.service.multi_template_output import MultiTemplateOutputError, MultiTemplateResultCollector
from src.service import multi_template_output as output_module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint(template_id: str, output: Path, *, status: str = "succeeded") -> dict[str, object]:
    return {
        "template_id": template_id,
        "status": status,
        "attempt": 1,
        "primary_output": str(output),
        "primary_output_sha256": _sha256(output),
    }


def _parent(tmp_path: Path, checkpoints: list[dict[str, object]]) -> dict[str, object]:
    job_dir = tmp_path / "parent-job"
    job_dir.mkdir(exist_ok=True)
    return {
        "job_id": "parent-001",
        "job_dir": str(job_dir),
        "multi_template": {"template_checkpoints": checkpoints},
    }


def _child_zip(tmp_path: Path, template_id: str, members: list[tuple[str, bytes]]) -> Path:
    digest = hashlib.sha256(template_id.encode("utf-8")).hexdigest()[:12]
    output = tmp_path / "parent-job" / "children" / digest / "attempt-1" / "output.zip"
    output.parent.mkdir(parents=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name:.*", category=UserWarning)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members:
                archive.writestr(name, content)
    return output


def test_collector_builds_complete_zip_with_template_isolation_and_internal_structure(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"A"), ("summary/master.ai", b"summary")])
    template_b = _child_zip(tmp_path, "B", [("department/W/ORDER1.ai", b"B")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a), _checkpoint("B", template_b)])

    result = MultiTemplateResultCollector().collect(parent, status="completed")

    assert result.kind == "primary_output"
    with zipfile.ZipFile(result.path) as archive:
        assert archive.read("templates/A/department/W/ORDER1.ai") == b"A"
        assert archive.read("templates/A/summary/master.ai") == b"summary"
        assert archive.read("templates/B/department/W/ORDER1.ai") == b"B"
        assert not any(name.startswith("children/") or "batch-manifest" in name for name in archive.namelist())


def test_collector_rejects_partial_batch_without_publishing_output(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/K/ORDER1.ai", b"A")])
    template_b = _child_zip(tmp_path, "B", [("department/K/ORDER2.ai", b"B")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a), _checkpoint("B", template_b, status="failed")])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed_with_errors")

    assert caught.value.code == "multi_template_output_status_invalid"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_refuses_primary_output_until_every_checkpoint_has_succeeded(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/K/ORDER1.ai", b"A")])
    template_b = _child_zip(tmp_path, "B", [("department/K/ORDER2.ai", b"B")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a), _checkpoint("B", template_b, status="failed")])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_status_invalid"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_renames_same_template_member_collisions_without_flattening(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"first"), ("department/W/ORDER1.ai", b"second")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    result = MultiTemplateResultCollector().collect(parent, status="completed")

    with zipfile.ZipFile(result.path) as archive:
        assert archive.read("templates/A/department/W/ORDER1.ai") == b"first"
        assert archive.read("templates/A/department/W/ORDER1-2.ai") == b"second"


@pytest.mark.parametrize("member", ["../outside.ai", "..\\outside.ai", "/absolute.ai", "C:/absolute.ai"])
def test_collector_rejects_unsafe_child_zip_members_without_publishing_output(tmp_path, member):
    template_a = _child_zip(tmp_path, "A", [(member, b"unsafe")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_zip_unsafe"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_mutated_child_output_before_publishing(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"original")])
    checkpoint = _checkpoint("A", template_a)
    template_a.write_bytes(b"changed")
    parent = _parent(tmp_path, [checkpoint])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_hash_invalid"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_output_claimed_by_a_different_template_child_directory(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/K/A.ai", b"A")])
    template_b = _child_zip(tmp_path, "B", [("department/K/B.ai", b"B")])
    checkpoint_a = _checkpoint("A", template_a)
    checkpoint_a.update({"primary_output": str(template_b), "primary_output_sha256": _sha256(template_b)})
    parent = _parent(tmp_path, [checkpoint_a, _checkpoint("B", template_b)])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_missing"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_output_from_a_different_attempt(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/K/A.ai", b"A")])
    checkpoint = _checkpoint("A", template_a)
    checkpoint["attempt"] = 2
    parent = _parent(tmp_path, [checkpoint])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_missing"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_symbolic_link_members_without_publishing_output(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"safe")])
    link = zipfile.ZipInfo("department/W/current")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(template_a, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(link, b"ORDER1.ai")
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_zip_unsafe"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_directory_shaped_symbolic_link_members(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"safe")])
    link = zipfile.ZipInfo("department/W/current/")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(template_a, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(link, b"ORDER1.ai")
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_zip_unsafe"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_converts_temporary_file_creation_failure_without_publishing_output(tmp_path, monkeypatch):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"safe")])
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    def fail_mkstemp(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(output_module.tempfile, "mkstemp", fail_mkstemp)
    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_package_failed"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))


def test_collector_rejects_encrypted_zip_member_without_publishing_output(tmp_path):
    template_a = _child_zip(tmp_path, "A", [("department/W/ORDER1.ai", b"safe")])
    payload = bytearray(template_a.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = 0
        while (index := payload.find(signature, start)) >= 0:
            payload[index + offset] |= 0x01
            start = index + len(signature)
    template_a.write_bytes(payload)
    parent = _parent(tmp_path, [_checkpoint("A", template_a)])

    with pytest.raises(MultiTemplateOutputError) as caught:
        MultiTemplateResultCollector().collect(parent, status="completed")

    assert caught.value.code == "multi_template_output_zip_unsafe"
    assert not list((Path(str(parent["job_dir"])) / "output").glob("*.zip"))
