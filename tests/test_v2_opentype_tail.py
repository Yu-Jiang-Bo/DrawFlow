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


def test_materializes_pua_and_opentype_tail_vectors_together(tmp_path):
    calls = []

    class Resolver:
        def materialize(self, **kwargs):
            calls.append(("opentype", kwargs))
            return SimpleNamespace(task_payload=lambda: {"path": "first-c.svg"})

        def materialize_codepoint(self, **kwargs):
            calls.append(("pua", kwargs))
            return SimpleNamespace(task_payload=lambda: {"path": "last-m.svg"})

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
            "font_postscript_name": "DemoPS", "feature": "aalt", "alternate_index": 2,
            "letter": "C", "output_dir": tmp_path,
        }),
        ("pua", {
            "font_postscript_name": "DemoPS", "codepoint": 0xE00C,
            "letter": "m", "output_dir": tmp_path,
        }),
    ]
    assert specs[0]["opentype_glyph_asset"] == {"path": "first-c.svg"}
    assert specs[0]["tail_vector_asset"] == {"path": "first-c.svg"}
    assert specs[1]["tail_vector_asset"] == {"path": "last-m.svg"}


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
