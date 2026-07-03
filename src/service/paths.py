"""Shared filesystem paths for the local service."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"
SERVICE_JOBS_DIR = OUTPUT_DIR / "service-jobs"
TEMPLATE_STORAGE_DIR = PROJECT_ROOT / "templates"
