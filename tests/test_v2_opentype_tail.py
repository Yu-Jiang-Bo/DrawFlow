from types import SimpleNamespace

from src.renderer import v2_opentype_tail as opentype_tail


def test_resolves_template_selected_alternate_ordinal_from_feature_lookup():
    lookup = SimpleNamespace(
        LookupType=3,
        SubTable=[SimpleNamespace(alternates={"c": ["c.1", "c.2", "c.3"]})],
    )
    font = {
        "GSUB": SimpleNamespace(
            table=SimpleNamespace(
                FeatureList=SimpleNamespace(
                    FeatureRecord=[SimpleNamespace(FeatureTag="aalt", Feature=SimpleNamespace(LookupListIndex=[0]))]
                ),
                LookupList=SimpleNamespace(Lookup=[lookup]),
            )
        )
    }

    assert opentype_tail._alternate_glyph_name(font, "aalt", 2, "c") == "c.2"


def test_resolves_single_substitution_feature_for_template_tail_profile():
    lookup = SimpleNamespace(
        LookupType=1,
        SubTable=[SimpleNamespace(mapping={"c": "c.swash"})],
    )
    font = {
        "GSUB": SimpleNamespace(
            table=SimpleNamespace(
                FeatureList=SimpleNamespace(
                    FeatureRecord=[SimpleNamespace(FeatureTag="swsh", Feature=SimpleNamespace(LookupListIndex=[0]))]
                ),
                LookupList=SimpleNamespace(Lookup=[lookup]),
            )
        )
    }

    assert opentype_tail._alternate_glyph_name(font, "swsh", 1, "c") == "c.swash"


def test_reads_pairpos_kerning_x_advance_for_complete_word_layout():
    pair_record = SimpleNamespace(SecondGlyph="r", Value1=SimpleNamespace(XAdvance=-42))
    pair_set = SimpleNamespace(PairValueRecord=[pair_record])
    lookup = SimpleNamespace(
        LookupType=2,
        SubTable=[
            SimpleNamespace(
                Format=1,
                Coverage=SimpleNamespace(glyphs=["c.2"]),
                PairSet=[pair_set],
            )
        ],
    )
    font = {
        "GPOS": SimpleNamespace(
            table=SimpleNamespace(
                FeatureList=SimpleNamespace(
                    FeatureRecord=[SimpleNamespace(FeatureTag="kern", Feature=SimpleNamespace(LookupListIndex=[0]))]
                ),
                LookupList=SimpleNamespace(Lookup=[lookup]),
            )
        )
    }

    assert opentype_tail._gpos_pair_x_advance(font, "c.2", "r") == -42


def test_materializes_svg_with_template_profile_and_normalized_endpoint(tmp_path, monkeypatch):
    font_file = tmp_path / "demo.ttf"
    font_file.write_bytes(b"demo-font")

    class FakeFont:
        def close(self):
            return None

    monkeypatch.setattr(opentype_tail, "TTFont", lambda _path, lazy=False: FakeFont())
    monkeypatch.setattr(opentype_tail, "_alternate_glyph_name", lambda *_args: "c.2")
    monkeypatch.setattr(
        opentype_tail,
        "_glyph_svg",
        lambda *_args: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>\n',
    )
    resolver = opentype_tail.OpenTypeTailResolver(font_dirs=[])
    monkeypatch.setattr(resolver, "find_font_file", lambda _name: font_file)

    glyph = resolver.materialize(
        font_postscript_name="DemoPS",
        feature="aalt",
        alternate_index=2,
        letter="C",
        output_dir=tmp_path / "assets",
    )

    assert glyph.glyph_name == "c.2"
    assert glyph.letter == "c"
    assert glyph.path.is_absolute()
    assert glyph.path.exists()
    assert glyph.task_payload()["opentype_alternate_index"] == 2


def test_materializes_one_complete_word_for_mixed_pua_and_opentype_tails(tmp_path):
    calls = []

    class Resolver:
        def resolve_alternate_glyph_name(self, **kwargs):
            calls.append(("opentype", kwargs))
            return "c.2"

        def resolve_codepoint_glyph_name(self, **kwargs):
            calls.append(("pua", kwargs))
            return "m.pua"

        def materialize_word(self, **kwargs):
            calls.append(("word", kwargs))
            return SimpleNamespace(task_payload=lambda: {"path": "cream.svg", "glyph_names": ["c.2", "r", "e", "a", "m.pua"]})

    specs = [
        {
            "key": "tail_name_first_c",
            "position": "first",
            "glyph_mode": "opentype_alternate",
            "font_postscript_name": "DemoPS",
            "opentype_feature": "aalt",
            "opentype_alternate_index": 2,
        },
        {
            "key": "tail_name_last_m",
            "position": "last",
            "glyph_mode": "pua_contiguous",
            "font_postscript_name": "DemoPS",
            "pua_base": 0xE000,
        },
    ]

    opentype_tail._materialize_action_tails(
        specs,
        action={"source_field": "name", "preset": "direct_text"},
        values={"name": "Cream"},
        resolver=Resolver(),
        asset_dir=tmp_path,
    )

    assert calls == [
        ("opentype", {
            "font_postscript_name": "DemoPS", "feature": "aalt", "alternate_index": 2, "letter": "C",
        }),
        ("pua", {
            "font_postscript_name": "DemoPS", "codepoint": 0xE00C,
        }),
        ("word", {
            "font_postscript_name": "DemoPS", "text": "Cream", "endpoint_glyphs": {0: "c.2", 4: "m.pua"},
            "output_dir": tmp_path,
        }),
    ]
    assert specs[0]["opentype_word_asset"]["path"] == "cream.svg"
    assert specs[1]["opentype_word_asset"]["glyph_names"][-1] == "m.pua"


def test_selected_opentype_tail_materialization_creates_the_component_asset_directory(tmp_path, monkeypatch):
    captured_dirs = []

    class Resolver:
        def __init__(self, **_kwargs):
            return None

        def resolve_alternate_glyph_name(self, **_kwargs):
            return "c.2"

        def materialize_word(self, *, output_dir, **_kwargs):
            captured_dirs.append(output_dir)
            return SimpleNamespace(task_payload=lambda: {"path": str(output_dir / "cream.svg")})

    monkeypatch.setattr(opentype_tail, "OpenTypeTailResolver", Resolver)
    output_ai = tmp_path / "missing" / "artwork" / "component.ai"
    render_task = {
        "outputs": [{
            "key": "Output_main",
            "actions": [{
                "type": "replace_slot_text",
                "group": "font",
                "option_key": "F3",
                "source_field": "name",
                "preset": "direct_text",
                "tails": [{
                    "key": "tail_name_first_c",
                    "position": "first",
                    "glyph_mode": "opentype_alternate",
                    "font_postscript_name": "DemoPS",
                    "opentype_feature": "aalt",
                    "opentype_alternate_index": 2,
                }],
            }],
        }],
    }

    opentype_tail.materialize_selected_opentype_tail_assets(
        render_task,
        values={"name": "Cream"},
        selections={"Output_main": {"font": "F3"}},
        output_ai=output_ai,
    )

    assert captured_dirs == [output_ai.parent / ".component.opentype-tail-glyphs"]
    assert captured_dirs[0].is_dir()


def test_skips_optional_blank_opentype_tail_slot_without_resolving_endpoints(tmp_path):
    class Resolver:
        def materialize(self, **_kwargs):
            raise AssertionError("optional blank should not resolve an OpenType endpoint")

    specs = [
        {
            "key": "tail_name_first_a",
            "position": "first",
            "glyph_mode": "opentype_alternate",
            "font_postscript_name": "DemoPS",
            "opentype_feature": "aalt",
            "opentype_alternate_index": 1,
        }
    ]

    opentype_tail._materialize_action_tails(
        specs,
        action={"source_field": "nickname", "preset": "direct_text", "required": False},
        values={"nickname": "   "},
        resolver=Resolver(),
        asset_dir=tmp_path,
    )

    assert "tail_vector_asset" not in specs[0]
