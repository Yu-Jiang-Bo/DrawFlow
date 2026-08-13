from __future__ import annotations

from pathlib import Path
import struct

from src.service.v2_font_inventory import (
    font_names_from_file,
    missing_required_fonts,
    normalize_font_name,
)


def _minimal_font(*names: tuple[int, str], base_offset: int = 0) -> bytes:
    encoded = []
    strings = bytearray()
    for name_id, value in names:
        raw = value.encode("utf-16-be")
        encoded.append(struct.pack(">HHHHHH", 3, 1, 0x0409, name_id, len(raw), len(strings)))
        strings.extend(raw)
    name_table = struct.pack(">HHH", 0, len(encoded), 6 + 12 * len(encoded)) + b"".join(encoded) + strings
    header = struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0)
    directory = b"name" + struct.pack(">III", 0, base_offset + len(header) + 16, len(name_table))
    return header + directory + name_table


def _minimal_collection(*faces: tuple[tuple[int, str], ...]) -> bytes:
    header_size = 12 + 4 * len(faces)
    offsets = []
    payloads = []
    offset = header_size
    for names in faces:
        payload = _minimal_font(*names, base_offset=offset)
        offsets.append(offset)
        payloads.append(payload)
        offset += len(payload)
    return b"ttcf" + struct.pack(">II", 0x00010000, len(faces)) + b"".join(
        struct.pack(">I", value) for value in offsets
    ) + b"".join(payloads)


def test_reads_embedded_family_full_postscript_and_typographic_names(tmp_path: Path):
    font = tmp_path / "opaque.ttf"
    font.write_bytes(
        _minimal_font(
            (1, "Austin Pen"),
            (4, "Austin Pen Regular"),
            (6, "AustinPen"),
            (16, "Austin Pen Family"),
            (17, "Regular Display"),
        )
    )

    assert font_names_from_file(font) == {
        "Austin Pen",
        "Austin Pen Regular",
        "AustinPen",
        "Austin Pen Family",
        "Regular Display",
    }


def test_matches_required_font_by_embedded_name_instead_of_filename(tmp_path: Path):
    (tmp_path / "unrelated-file.ttf").write_bytes(_minimal_font((6, "TimesNewRomanPSMT")))

    assert missing_required_fonts(["Times New Roman PS MT"], [tmp_path]) == []


def test_broken_font_uses_filename_stem_as_safe_fallback(tmp_path: Path):
    (tmp_path / "Fallback Font.ttf").write_bytes(b"not-a-font")

    assert missing_required_fonts(["Fallback-Font"], [tmp_path]) == []


def test_reads_every_face_from_true_type_and_open_type_collections(tmp_path: Path):
    font = tmp_path / "families.otc"
    font.write_bytes(
        _minimal_collection(
            ((6, "FirstPostScript"),),
            ((16, "Second Family"), (17, "Bold")),
        )
    )

    assert font_names_from_file(font) == {"FirstPostScript", "Second Family", "Bold"}
    assert missing_required_fonts(["First Post Script", "second-family"], [tmp_path]) == []


def test_inventory_cache_refreshes_when_font_file_changes(tmp_path: Path):
    font = tmp_path / "mutable.ttf"
    font.write_bytes(_minimal_font((6, "BeforeName")))
    assert missing_required_fonts(["Before Name"], [tmp_path]) == []

    font.write_bytes(_minimal_font((6, "AfterName"), (4, "After Name Regular")))

    assert missing_required_fonts(["After Name"], [tmp_path]) == []
    assert missing_required_fonts(["Before Name"], [tmp_path]) == ["Before Name"]


def test_normalization_ignores_case_spaces_and_punctuation():
    assert normalize_font_name("MTD-AlFresco") == normalize_font_name("mtd al fresco")
