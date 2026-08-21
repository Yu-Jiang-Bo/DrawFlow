"""V2 template namespace and first-release isolation rules."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from .paths import V2_TEMPLATE_DATA_DIR


V2_API_PREFIX = "/api/v2/templates"
V2_LOCAL_GATEWAY_PREFIX = "/local/v2/templates"
V2_TEMPLATE_TYPE = "v2_illustrator_template"
V2_RENDER_PIPELINE = "v2_illustrator_template"
V2_DATA_DIR: Path = V2_TEMPLATE_DATA_DIR

_FIRST_RELEASE_POLICY: Dict[str, bool] = {
    "migrates_legacy_templates": False,
    "executes_local_shared_scope": False,
    "allows_natural_language_rules": False,
    "allows_arbitrary_jsx": False,
}


def is_v2_template_type(value: object) -> bool:
    return str(value or "").strip() == V2_TEMPLATE_TYPE


def is_v2_pipeline(value: object) -> bool:
    return str(value or "").strip() == V2_RENDER_PIPELINE


def first_release_policy() -> Dict[str, bool]:
    return dict(_FIRST_RELEASE_POLICY)
