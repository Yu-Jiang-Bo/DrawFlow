"""Small filesystem helpers for V2 template storage."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_segment(value: str) -> str:
    return "".join(
        char
        for char in str(value).strip()
        if char.isascii() and (char.isalnum() or char in {"-", "_"})
    )


def safe_name(value: str, fallback: str) -> str:
    name = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in Path(value).name).strip("._")
    return name or fallback


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    for index in range(2, 10000):
        next_candidate = directory / f"{candidate.stem}-{index}{candidate.suffix}"
        if not next_candidate.exists():
            return next_candidate
    raise RuntimeError(f"Cannot allocate unique path: {filename}")


def optional_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, payload)
    temporary.replace(path)


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
