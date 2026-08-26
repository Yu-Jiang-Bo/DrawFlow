from __future__ import annotations

import pytest

from src.service import job_store as job_store_module
from src.service.job_store import JobStore


def test_failed_atomic_replace_keeps_the_previous_complete_job_record(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    record = store.create({"template_id": "A"})
    job_file = tmp_path / "jobs" / record["job_id"] / "job.json"

    def reject_replace(source, destination):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(job_store_module.os, "replace", reject_replace)
    with pytest.raises(OSError, match="simulated"):
        store.update(record, status="running")

    assert store.load(record["job_id"])["status"] == "queued"
    assert job_file.is_file()
    assert not list(job_file.parent.glob(".job.json.*.tmp"))
