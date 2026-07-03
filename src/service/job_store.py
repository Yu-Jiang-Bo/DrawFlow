"""Persistent job records for render requests."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .paths import SERVICE_JOBS_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root: Path | str = SERVICE_JOBS_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, request: Dict[str, Any]) -> Dict[str, Any]:
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
            "error": "",
        }
        self.save(record)
        return record

    def load(self, job_id: str) -> Dict[str, Any]:
        path = self.root / job_id / "job.json"
        if not path.exists():
            raise KeyError(f"任务不存在: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0 or not self.root.exists():
            return []
        records: List[Dict[str, Any]] = []
        for path in self.root.glob("*/job.json"):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        records.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        return records[:limit]

    def save(self, record: Dict[str, Any]) -> None:
        record["updated_at"] = utc_now()
        path = Path(record["job_dir"]) / "job.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, record: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
        record.update(changes)
        self.save(record)
        return record
