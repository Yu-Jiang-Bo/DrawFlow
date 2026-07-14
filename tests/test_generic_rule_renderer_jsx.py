from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path("scripts/illustrator/render_generic_rule_pack.jsx")


def test_generic_renderer_hardcodes_name_alternating_colors_only():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "task.orders.length" in source
    assert "applyOptionGroups" in source
    assert "applyVariables" in source
    assert "applyAssets" in source
    assert "task.dimensions" in source
    assert "task.text_policies" in source
    assert "findPageItemsByName" in source
    assert 'String(variable.target || "") + "_ANCHOR"' in source
    assert "copyTextStyle(fontSource, frame)" in source
    assert 'applyNameAlternatingColors(frame, String(variable.target || ""), String(variable.name_delimiter || "|"))' in source
    assert 'if (target !== "Name" || !delimiter) return;' in source
    assert "[215, 25, 32]" in source
    assert "[0, 0, 0]" in source
    assert "applyTextEffects" not in source
    assert "TEXT_EFFECT_HANDLERS" not in source
    assert "applyTextEffectRange" not in source
    assert "applyCharacterStyles" not in source
    assert "doc-color-cmyk" in source
    assert "doc-color-rgb" in source
    assert "output.outline_text" in source
    assert "settings.rotation_deg" in source
    assert "settings.scale_percent" in source
    assert "settings.offset_x_mm" in source
    outline_body = source[source.index("if (transforms.outline_text)"):source.index("function applyOutputSettings")]
    assert "findPageItemsByName" in outline_body
    assert "outlineItems.length" in outline_body
    assert "JJMB" not in source


def test_generic_renderer_javascript_parses_in_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source = SCRIPT.read_text(encoding="utf-8").replace("#target illustrator", "", 1)

    result = subprocess.run(
        [node, "-e", "new Function(process.argv[1]);", source],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
