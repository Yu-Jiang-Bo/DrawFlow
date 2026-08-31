"""Safe, repeatable migration helpers for existing V2 tail profiles.

New uploads receive profiles during scanning.  This module is intentionally
separate because an existing published template must never be silently
rewritten: a caller has to provide fresh scan evidence for the exact AI asset,
then create a new draft, real-preview it, and publish it through the normal
versioned workflow.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterator, Mapping


PROFILE_KEYS = (
    "opentype_feature",
    "opentype_alternate_index",
    "pua_base",
    "glyph_map",
)

TailLocator = tuple[int, str, int, int, int]


class OpenTypeTailMigrationError(ValueError):
    """The supplied evidence cannot safely update the selected draft."""


def iter_slot_tails(config: Mapping[str, Any]) -> Iterator[tuple[TailLocator, dict[str, Any]]]:
    """Yield every V2 tail with a stable structural locator."""

    for output_index, output in enumerate(config.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        for branch in ("design", "font"):
            section = output.get(branch)
            if not isinstance(section, Mapping):
                continue
            for option_index, option in enumerate(section.get("options", [])):
                if not isinstance(option, Mapping):
                    continue
                for slot_index, slot in enumerate(option.get("slots", [])):
                    if not isinstance(slot, Mapping):
                        continue
                    for tail_index, tail in enumerate(slot.get("tails", [])):
                        if isinstance(tail, Mapping):
                            yield (output_index, branch, option_index, slot_index, tail_index), dict(tail)


def proven_tail_profiles(evidence: Mapping[str, Any]) -> dict[TailLocator, dict[str, Any]]:
    """Extract only scan-proven OpenType/PUA profiles from normalized evidence."""

    profiles: dict[TailLocator, dict[str, Any]] = {}
    for locator, tail in iter_slot_tails(evidence):
        if tail.get("tail_profile_status") != "auto":
            continue
        if not any(key in tail for key in ("opentype_feature", "pua_base", "glyph_map")):
            continue
        profiles[locator] = {key: deepcopy(tail[key]) for key in PROFILE_KEYS if key in tail}
    return profiles


def merge_proven_tail_profiles(
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Merge only proven profiles when the draft has identical tail identities.

    The caller must separately verify that ``evidence`` was produced from the
    current draft AI before invoking this function.  Locators alone are never
    sufficient proof—each target tail's key, endpoint direction and sample
    letter must agree exactly.
    """

    merged = deepcopy(dict(config))
    profiles = proven_tail_profiles(evidence)
    if not profiles:
        raise OpenTypeTailMigrationError("扫描证据中没有可迁移的已验证尾巴字形。")
    targets = dict(iter_slot_tails(merged))
    missing = sorted(set(profiles).difference(targets))
    if missing:
        raise OpenTypeTailMigrationError(f"当前草稿缺少扫描证据中的尾巴位置：{missing}")
    sources = dict(iter_slot_tails(evidence))
    changes: list[dict[str, Any]] = []
    for locator, profile in sorted(profiles.items()):
        target = targets[locator]
        source = sources[locator]
        for key in ("key", "position", "sample"):
            if str(target.get(key) or "") != str(source.get(key) or ""):
                raise OpenTypeTailMigrationError(f"尾巴身份不一致，拒绝迁移：{locator} 的 {key}")
        for key in PROFILE_KEYS:
            target.pop(key, None)
        target.update(profile)
        _replace_tail(merged, locator, target)
        changes.append({
            "locator": list(locator),
            "key": target.get("key"),
            "position": target.get("position"),
            "sample": target.get("sample"),
            **{key: deepcopy(target[key]) for key in PROFILE_KEYS if key in target},
        })
    return merged, changes


def _replace_tail(config: dict[str, Any], locator: TailLocator, replacement: Mapping[str, Any]) -> None:
    output_index, branch, option_index, slot_index, tail_index = locator
    config["outputs"][output_index][branch]["options"][option_index]["slots"][slot_index]["tails"][tail_index] = dict(replacement)


__all__ = [
    "OpenTypeTailMigrationError",
    "PROFILE_KEYS",
    "TailLocator",
    "iter_slot_tails",
    "merge_proven_tail_profiles",
    "proven_tail_profiles",
]
