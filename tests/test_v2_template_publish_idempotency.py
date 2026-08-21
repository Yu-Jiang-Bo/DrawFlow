import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from src.service.v2_template_store import (
    V2TemplatePublishConflict,
    V2TemplateStore,
)


def draft_store(tmp_path):
    store = V2TemplateStore(tmp_path / "v2")
    store.save_draft(
        "V2DEMO001",
        metadata={"name": "Demo"},
        config={"version": 1},
        assets=[{"filename": "template.ai", "content": b"source-ai"}],
    )
    return store


def test_same_draft_revision_publish_retry_returns_original_version(tmp_path):
    store = draft_store(tmp_path)
    revision = store.get_state("V2DEMO001")["draft"]["revision"]
    first = store.publish_draft("V2DEMO001", expected_revision=revision)
    second = store.publish_draft("V2DEMO001", expected_revision=revision)
    assert first["publication"]["current_version"] == second["publication"]["current_version"] == "v0001"
    assert [item["version"] for item in second["versions"]] == ["v0001"]
    assert second["versions"][0]["source_draft_revision"] == revision
    manifest = json.loads(
        (tmp_path / "v2/V2DEMO001/versions/v0001/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_draft_revision"] == revision


def test_concurrent_same_revision_publish_creates_only_one_version(tmp_path):
    store = draft_store(tmp_path)
    revision = store.get_state("V2DEMO001")["draft"]["revision"]
    ready = Barrier(2)

    def publish():
        ready.wait()
        return store.publish_draft("V2DEMO001", expected_revision=revision)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: publish(), range(2)))
    assert [item["publication"]["current_version"] for item in results] == ["v0001", "v0001"]
    assert [path.name for path in (tmp_path / "v2/V2DEMO001/versions").iterdir()] == ["v0001"]
    assert len(store.get_state("V2DEMO001")["versions"]) == 1


def test_published_revision_is_not_reused_after_current_version_is_inactive(tmp_path):
    store = draft_store(tmp_path)
    revision = store.get_state("V2DEMO001")["draft"]["revision"]
    store.publish_draft("V2DEMO001", expected_revision=revision)
    store.deactivate_current("V2DEMO001")
    with pytest.raises(V2TemplatePublishConflict, match="不能重复发布"):
        store.publish_draft("V2DEMO001", expected_revision=revision)
    assert [item["version"] for item in store.get_state("V2DEMO001")["versions"]] == ["v0001"]
