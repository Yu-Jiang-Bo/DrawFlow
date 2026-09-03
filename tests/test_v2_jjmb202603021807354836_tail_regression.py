"""Regression coverage for JJMB202603021807354836 F2/F3 tail rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.renderer import v2_template_renderer
from src.service.v2_opentype_tail_migration import merge_proven_tail_profiles
from src.service.v2_render_task import compile_v2_render_task


_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "jjmb202603021807354836_tail_regression.json"


def _fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("font", "name"),
    [("F2", "Hanh"), ("F2", "Mew"), ("F3", "Chanida"), ("F3", "Juliet")],
)
def test_real_values_compile_the_expected_f2_and_f3_render_paths(tmp_path, monkeypatch, font, name):
    fixture = _fixture()
    merged, changes = merge_proven_tail_profiles(
        fixture["config"],
        fixture["migration_evidence"],
        tail_keys=["tail_name_first_a", "tail_name_last_n"],
    )
    assert [change["key"] for change in changes] == ["tail_name_first_a", "tail_name_last_n"]
    f2_tails = merged["outputs"][0]["font"]["options"][1]["slots"][0]["tails"]
    f11_tail = merged["outputs"][0]["font"]["options"][3]["slots"][0]["tails"][0]
    assert [(tail["opentype_feature"], tail["opentype_alternate_index"]) for tail in f2_tails] == [("aalt", 2), ("aalt", 3)]
    assert "opentype_feature" not in f11_tail

    task = compile_v2_render_task(
        merged,
        fixture["render_scan"],
        template_id=fixture["template_id"],
        template_version="v0001",
        template_sha256=fixture["template_sha256"],
        config_version="d0013-tail-fix",
        font_check={"ok": True, "missing": []},
    )
    action = next(
        item for item in task["outputs"][0]["actions"]
        if item.get("type") == "replace_slot_text" and item.get("group") == "font" and item.get("option_key") == font
    )
    if font == "F2":
        assert [
            (tail["glyph_mode"], tail["opentype_feature"], tail["opentype_alternate_index"])
            for tail in action["tails"]
        ] == [("opentype_alternate", "aalt", 2), ("opentype_alternate", "aalt", 3)]
    else:
        assert action["tails"] == []

    captured = {}
    monkeypatch.setattr(
        v2_template_renderer,
        "materialize_selected_opentype_tail_assets",
        lambda render_task, **kwargs: captured.update(kwargs) or render_task,
    )
    template_ai = tmp_path / "JJMB202603021807354836.ai"
    template_ai.write_bytes(b"fixture")
    execution = v2_template_renderer.build_v2_execution_task(
        task,
        template_ai=template_ai,
        output_ai=tmp_path / "rendered.ai",
        values={"style": "style1", "font": font, "name": name},
    )
    assert execution["selections"] == {"Output_main": {"style": "style1", "font": font}}
    assert captured["values"]["name"] == name
    assert captured["selections"]["Output_main"]["font"] == font
