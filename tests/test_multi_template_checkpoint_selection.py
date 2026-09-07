from __future__ import annotations

import pytest

from src.service.multi_template_checkpoint_selection import (
    CheckpointSelectionError,
    mark_orphaned_running,
    normal_execute_template_ids,
    resume_template_ids,
    retry_failed_template_ids,
)


def test_checkpoint_selection_keeps_first_template_order_and_excludes_successes():
    checkpoints = [
        {"template_id": "A", "status": "succeeded"},
        {"template_id": "B", "status": "failed", "failure_scope": "template"},
        {"template_id": "C", "status": "canary_failed"},
        {"template_id": "D", "status": "pending"},
        {"template_id": "E", "status": "interrupted"},
        {"template_id": "F", "status": "failed", "failure_scope": "system"},
        {"template_id": "G", "status": "ready"},
    ]

    assert normal_execute_template_ids(checkpoints) == ("D",)
    assert retry_failed_template_ids(checkpoints) == ("B", "C", "F")
    assert resume_template_ids(checkpoints) == ("D", "E", "F")


def test_selector_rejects_active_checkpoints_but_resume_marks_them_interrupted():
    checkpoints = [
        {"template_id": "A", "status": "running"},
        {"template_id": "B", "status": "canary_running"},
    ]

    with pytest.raises(CheckpointSelectionError):
        normal_execute_template_ids(checkpoints)
    with pytest.raises(CheckpointSelectionError):
        retry_failed_template_ids(checkpoints)

    recovered, template_ids = mark_orphaned_running(checkpoints)

    assert template_ids == ("A", "B")
    assert [item["status"] for item in recovered] == ["interrupted", "interrupted"]
    assert all(item["error_code"] == "multi_template_process_interrupted" for item in recovered)
    assert resume_template_ids(recovered) == ("A", "B")
