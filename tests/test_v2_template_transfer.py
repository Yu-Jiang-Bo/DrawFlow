import hashlib
import io
from pathlib import Path

import pytest

from src.service.v2_template_transfer import (
    TransferError,
    atomic_switch_verified_file,
    download_stream_to_file,
    file_sha256,
    iter_file_chunks,
    receive_ai_stream,
)


class TrackingStream(io.BytesIO):
    def __init__(self, payload: bytes, *, fail_on_read: int | None = None):
        super().__init__(payload)
        self.fail_on_read = fail_on_read
        self.read_sizes: list[int] = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("stream transfer must not call unbounded read()")
        if self.fail_on_read is not None and len(self.read_sizes) >= self.fail_on_read:
            raise OSError("connection dropped")
        return super().read(size)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_receive_ai_stream_rejects_non_ai_without_reading_or_writing(tmp_path):
    stream = TrackingStream(b"not-ai")

    with pytest.raises(TransferError, match=".ai") as exc:
        receive_ai_stream(stream, tmp_path / "assets", "template.png", chunk_size=2)

    assert exc.value.code == "unsupported_ai_extension"
    assert stream.read_sizes == []
    assert not (tmp_path / "assets").exists()


def test_receive_ai_stream_reads_multiple_chunks_and_returns_asset_manifest(tmp_path):
    payload = b"0123456789abcdef"
    stream = TrackingStream(payload)
    observed_chunks = []

    record = receive_ai_stream(
        stream,
        tmp_path / "draft" / "assets",
        "template.ai",
        role="template",
        scan_version="scan-1",
        draft_version="d0002",
        mime_type="application/illustrator",
        relative_to=tmp_path / "draft",
        chunk_size=5,
        on_chunk=observed_chunks.append,
    )

    assert (tmp_path / "draft" / "assets" / "template.ai").read_bytes() == payload
    assert stream.read_sizes == [5, 5, 5, 5, 5]
    assert observed_chunks == [5, 5, 5, 1]
    assert record == {
        "file_name": "template.ai",
        "role": "template",
        "path": "assets/template.ai",
        "size_bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "mime_type": "application/illustrator",
        "extension": ".ai",
        "scan_version": "scan-1",
        "draft_version": "d0002",
        "draft_revision": "d0002",
    }


def test_interrupted_upload_keeps_existing_asset_and_cleans_temp_file(tmp_path):
    destination = tmp_path / "draft" / "assets"
    destination.mkdir(parents=True)
    existing = destination / "template.ai"
    existing.write_bytes(b"old-ai")
    stream = TrackingStream(b"new-ai-content", fail_on_read=2)

    with pytest.raises(TransferError) as exc:
        receive_ai_stream(stream, destination, "template.ai", chunk_size=4)

    assert exc.value.code == "stream_interrupted"
    assert existing.read_bytes() == b"old-ai"
    assert not [item for item in destination.iterdir() if item.name.startswith(".template.ai.") and item.suffix == ".tmp"]


def test_download_sha256_mismatch_does_not_switch_existing_file_and_cleans_temp(tmp_path):
    final = tmp_path / "cache" / "template-bundle.zip"
    final.parent.mkdir()
    final.write_bytes(b"old-bundle")
    stream = TrackingStream(b"new-bundle")

    with pytest.raises(TransferError) as exc:
        download_stream_to_file(stream, final, expected_sha256="0" * 64, chunk_size=3)

    assert exc.value.code == "sha256_mismatch"
    assert final.read_bytes() == b"old-bundle"
    assert not [item for item in final.parent.iterdir() if item.name.startswith(".template-bundle.zip.")]
    assert stream.read_sizes == [3, 3, 3, 3, 3]


def test_download_stream_verifies_sha256_and_atomically_switches(tmp_path):
    final = tmp_path / "cache" / "template-bundle.zip"
    final.parent.mkdir()
    final.write_bytes(b"old-bundle")
    payload = b"new-bundle-bytes"
    stream = TrackingStream(payload)

    record = download_stream_to_file(stream, final, expected_sha256=sha256_bytes(payload), chunk_size=4)

    assert final.read_bytes() == payload
    assert stream.read_sizes == [4, 4, 4, 4, 4]
    assert record == {"path": str(final), "size_bytes": len(payload), "sha256": sha256_bytes(payload)}


def test_download_uses_a_short_staging_name_for_deep_destinations(tmp_path, monkeypatch):
    destination = tmp_path
    # A 225-character final path is valid on legacy Windows, while the former
    # staging convention pushed it beyond the 260-character path limit.
    while len(str(destination / "template-bundle.zip")) < 225:
        destination /= "deep-cache-segment"
    final = destination / "template-bundle.zip"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"old-bundle")
    payload = b"new-bundle-bytes"
    opened = []
    original_open = Path.open

    def record_staging_open(path, mode="r", *args, **kwargs):
        if mode == "xb":
            opened.append(path)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_staging_open)

    download_stream_to_file(
        TrackingStream(payload),
        final,
        expected_sha256=sha256_bytes(payload),
    )

    legacy_staging = final.with_name(f".{final.name}.{'f' * 32}.tmp")
    assert len(str(legacy_staging)) > 260
    assert opened and opened[0].name.startswith(".df-")
    assert len(opened[0].name) == len(".df-") + 16
    assert len(str(opened[0])) < 260
    assert final.read_bytes() == payload


def test_file_chunk_iterator_and_atomic_switch_helper_are_bounded(tmp_path):
    staging = tmp_path / "template.ai.download"
    final = tmp_path / "template.ai"
    payload = b"abcdefghij"
    staging.write_bytes(payload)
    final.write_bytes(b"old-ai")

    chunks = list(iter_file_chunks(staging, chunk_size=3))
    record = atomic_switch_verified_file(staging, final, expected_sha256=file_sha256(staging, chunk_size=2), chunk_size=3)

    assert chunks == [b"abc", b"def", b"ghi", b"j"]
    assert final.read_bytes() == payload
    assert not staging.exists()
    assert record["sha256"] == sha256_bytes(payload)
