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


def test_atomic_replace_retries_one_transient_permission_error(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    record = store.create({"template_id": "A"})
    real_replace = job_store_module.os.replace
    calls = []
    delays = []

    def replace_after_transient_failure(source, destination):
        calls.append((source, destination))
        if len(calls) == 1:
            raise PermissionError("simulated Windows sharing violation")
        return real_replace(source, destination)

    monkeypatch.setattr(job_store_module.os, "replace", replace_after_transient_failure)
    monkeypatch.setattr(job_store_module.time, "sleep", delays.append)

    store.update(record, status="running")

    assert store.load(record["job_id"])["status"] == "running"
    assert len(calls) == 2
    assert delays == [job_store_module.JOB_SAVE_REPLACE_RETRY_DELAY_SECONDS]


def test_persistent_permission_error_stops_after_bounded_retries_and_keeps_previous_record(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    record = store.create({"template_id": "A"})
    calls = []

    def reject_locked_replace(source, destination):
        calls.append((source, destination))
        raise PermissionError("locked")

    monkeypatch.setattr(job_store_module.os, "replace", reject_locked_replace)
    monkeypatch.setattr(job_store_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="locked"):
        store.update(record, status="running")

    assert len(calls) == job_store_module.JOB_SAVE_REPLACE_ATTEMPTS
    assert store.load(record["job_id"])["status"] == "queued"
