"""Persistent job records for render requests."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .paths import SERVICE_JOBS_DIR


JOB_SAVE_REPLACE_ATTEMPTS = 4
JOB_SAVE_REPLACE_RETRY_DELAY_SECONDS = 0.05


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root: Path | str = SERVICE_JOBS_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, request: Dict[str, Any], *, record_fields: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        record = {
            "job_id": job_id,
            "status": "queued",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "request": request,
            "job_dir": str(job_dir),
            "outputs": {},
            "stats": {},
            "progress": {"current": 0, "total": 0, "stage": "queued"},
            "error": "",
            "error_code": "",
            "technical_error": "",
        }
        record.update(dict(record_fields or {}))
        self.save(record)
        return record

    def load(self, job_id: str) -> Dict[str, Any]:
        path = self.root / job_id / "job.json"
        if not path.exists():
            raise KeyError(f"任务不存在: {job_id}")
        return self._with_live_progress(json.loads(path.read_text(encoding="utf-8")))

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0 or not self.root.exists():
            return []
        records: List[Dict[str, Any]] = []
        for path in self.root.glob("*/job.json"):
            try:
                records.append(self._with_live_progress(json.loads(path.read_text(encoding="utf-8"))))
            except json.JSONDecodeError:
                continue
        records.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        return records[:limit]

    def save(self, record: Dict[str, Any]) -> None:
        record["updated_at"] = utc_now()
        path = Path(record["job_dir"]) / "job.json"
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as target:
                target.write(json.dumps(record, ensure_ascii=False, indent=2))
                target.flush()
                os.fsync(target.fileno())
            _replace_with_permission_retry(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def update(self, record: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
        record.update(changes)
        self.save(record)
        return record

    def _with_live_progress(self, record: Dict[str, Any]) -> Dict[str, Any]:
        job_dir = str(record.get("job_dir") or "")
        if not job_dir:
            return record
        progress_path = Path(job_dir) / "progress.json"
        if not progress_path.exists():
            return record
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return record
        if isinstance(progress, dict):
            merged = dict(record.get("progress") or {})
            merged.update(progress)
            merged["current"] = max(_safe_int(record.get("progress", {}).get("current")), _safe_int(progress.get("current")))
            merged["total"] = max(_safe_int(record.get("progress", {}).get("total")), _safe_int(progress.get("total")))
            record["progress"] = merged
        return record


def _safe_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _replace_with_permission_retry(source: Path, destination: Path) -> None:
    for attempt in range(JOB_SAVE_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt + 1 >= JOB_SAVE_REPLACE_ATTEMPTS:
                raise
            time.sleep(JOB_SAVE_REPLACE_RETRY_DELAY_SECONDS)
