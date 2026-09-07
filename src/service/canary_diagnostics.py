"""Keep canary renderer artifacts diagnostic-only before a job is persisted."""

from __future__ import annotations

from typing import Any, MutableMapping


def suppress_delivery_outputs(record: MutableMapping[str, Any]) -> None:
    outputs = dict(record.get("outputs") or {})
    record["canary"] = True
    record["canary_outputs"] = outputs
    record["outputs"] = {
        key: value
        for key, value in outputs.items()
        if key not in {"primary_output", "output_bundle"}
    }


__all__ = ["suppress_delivery_outputs"]
