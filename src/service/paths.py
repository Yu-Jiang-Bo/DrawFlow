"""Shared filesystem paths for DrawFlow services."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"
SERVICE_JOBS_DIR = OUTPUT_DIR / "service-jobs"
SERVICE_UPLOADS_DIR = OUTPUT_DIR / "service-uploads"
TEMPLATE_STORAGE_DIR = PROJECT_ROOT / "templates"
DRAWFLOW_DATA_DIR = Path(os.environ.get("DRAWFLOW_DATA_DIR", PROJECT_ROOT / "drawflow-data"))
V2_TEMPLATE_DATA_DIR = DRAWFLOW_DATA_DIR / "v2-templates"
LOCAL_DRAWFLOW_DIR = Path(
    os.environ.get(
        "DRAWFLOW_LOCAL_DATA_DIR",
        Path(os.environ.get("LOCALAPPDATA", PROJECT_ROOT / ".localappdata")) / "DrawFlow",
    )
)
