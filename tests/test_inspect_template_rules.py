import json
from pathlib import Path

from src.inspect_template_rules import build_comparison_report, discover_ai_templates, inspect_template, run_batch


class FakeBridge:
    def __init__(self, *, fail_names=()):
        self.fail_names = set(fail_names)
        self.calls = []

    def render(self, script, task_file):
        task = json.loads(Path(task_file).read_text(encoding="utf-8"))
        source = Path(task["input_ai"])
        self.calls.append((Path(script), Path(task_file)))
        if source.name in self.fail_names:
            raise RuntimeError("scan failed")
        Path(task["output_json"]).write_text(
            json.dumps(
                {
                    "document": {"source_ai": str(source)},
                    "layers": [{"name": "Template"}],
                    "items": [
                        {"type": "GroupItem", "name": "F1", "text": "", "path": "Template/F1"},
                        {
                            "type": "TextFrame",
                            "name": "Name1",
                            "text": "Sample",
                            "text_kind": "TextType.AREATEXT",
                            "path": "Template/Name1",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return "ok"


def make_ai(root, relative):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake ai", encoding="utf-8")
    return path


def test_discovers_only_ai_files_recursively(tmp_path):
    root = tmp_path / "samples"
    first = make_ai(root, "纯文本/a.ai")
    second = make_ai(root, "设计/b.AI")
    make_ai(root, "设计/not-ai.txt")

    expected = sorted([first, second], key=lambda path: path.as_posix().lower())
    assert discover_ai_templates(root) == expected


def test_inspection_writes_scan_and_editable_draft(tmp_path):
    root = tmp_path / "samples"
    source = make_ai(root, "纯文本/DEMO001.ai")
    output = tmp_path / "output"
    bridge = FakeBridge()

    result = inspect_template(
        source,
        input_root=root,
        output_root=output,
        script=tmp_path / "inspect.jsx",
        bridge=bridge,
    )

    scan = json.loads(Path(result["scan"]).read_text(encoding="utf-8"))
    draft = json.loads(Path(result["draft"]).read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert result["category"] == "纯文本"
    assert scan["document"]["relative_path"] == "纯文本/DEMO001.ai"
    assert scan["scan_version"]
    assert draft["template"]["template_id"] == "DEMO001"
    assert draft["validation"]["status"] == "draft"
    assert draft["audit"]["confirmed_at"] == ""


def test_resume_reuses_scan_without_calling_illustrator(tmp_path):
    root = tmp_path / "samples"
    source = make_ai(root, "纯文本/DEMO002.ai")
    output = tmp_path / "output"
    first_bridge = FakeBridge()
    inspect_template(
        source,
        input_root=root,
        output_root=output,
        script=tmp_path / "inspect.jsx",
        bridge=first_bridge,
    )
    resume_bridge = FakeBridge(fail_names={source.name})

    result = inspect_template(
        source,
        input_root=root,
        output_root=output,
        script=tmp_path / "inspect.jsx",
        bridge=resume_bridge,
        resume=True,
    )

    assert result["status"] == "ok"
    assert resume_bridge.calls == []


def test_batch_keeps_processing_after_one_scan_failure(tmp_path):
    root = tmp_path / "samples"
    good = make_ai(root, "good.ai")
    bad = make_ai(root, "bad.ai")

    index = run_batch(
        [bad, good],
        input_root=root,
        output_root=tmp_path / "output",
        script=tmp_path / "inspect.jsx",
        bridge=FakeBridge(fail_names={bad.name}),
    )

    assert index["total"] == 2
    assert index["succeeded"] == 1
    assert index["failed"] == 1
    assert index["items"][0]["error"] == "scan failed"
    failed_scan = json.loads(Path(index["items"][0]["scan"]).read_text(encoding="utf-8"))
    failed_draft = json.loads(Path(index["items"][0]["draft"]).read_text(encoding="utf-8"))
    assert failed_scan["fatal_error"] == "scan failed"
    assert {item["code"] for item in failed_draft["validation"]["unresolved_items"]} >= {
        "confirmation_required",
        "profile",
        "text_targets",
        "scan_failed",
    }


def test_resume_does_not_promote_cached_failure_to_success(tmp_path):
    root = tmp_path / "samples"
    bad = make_ai(root, "bad.ai")
    output = tmp_path / "output"
    first = run_batch(
        [bad],
        input_root=root,
        output_root=output,
        script=tmp_path / "inspect.jsx",
        bridge=FakeBridge(fail_names={bad.name}),
    )
    resume_bridge = FakeBridge()

    resumed = run_batch(
        [bad],
        input_root=root,
        output_root=output,
        script=tmp_path / "inspect.jsx",
        bridge=resume_bridge,
        resume=True,
    )

    assert first["failed"] == 1
    assert resumed["failed"] == 1
    assert resumed["succeeded"] == 0
    assert resume_bridge.calls == []


def test_comparison_report_groups_profiles_and_manual_review():
    report = build_comparison_report(
        {
            "total": 3,
            "succeeded": 2,
            "failed": 1,
            "items": [
                {
                    "template_id": "A",
                    "relative_path": "纯文本/A.ai",
                    "category": "纯文本",
                    "profile": "pure_text",
                    "unresolved_count": 1,
                    "status": "ok",
                },
                {
                    "template_id": "B",
                    "relative_path": "复合/B.ai",
                    "category": "复合",
                    "profile": "unclassified",
                    "unresolved_count": 3,
                    "status": "ok",
                },
                {
                    "template_id": "C",
                    "relative_path": "复合/C.ai",
                    "category": "复合",
                    "profile": "unclassified",
                    "unresolved_count": 4,
                    "status": "failed",
                    "error": "scan failed",
                },
            ],
        }
    )

    assert report["categories"]["纯文本"]["profiles"] == {"pure_text": 1}
    assert report["categories"]["复合"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "profiles": {"unclassified": 2},
    }
    assert report["profiles"] == {"pure_text": 1, "unclassified": 2}
    assert [item["template_id"] for item in report["manual_review"]] == ["B", "C"]
