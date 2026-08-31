from src.service.v2_scan_worker_auth import scan_evidence_sha256
from src.service.v2_tail_profile_proof import pua_tail_profile_issues


def _config(pua_base=0xE040, font="TailFont"):
    return {
        "outputs": [{
            "design": {"options": [{"font_dependencies": [font], "slots": [{"tails": [{
                "key": "tail_name_last_m", "position": "last", "sample": "m", "pua_base": pua_base,
            }]}]}]},
            "font": {"options": []},
        }],
    }


def _trusted(scan):
    scan["tail_profile_proof"] = {
        "version": 1,
        "worker_id": "test-worker",
        "evidence_sha256": scan_evidence_sha256(scan),
    }
    return scan


def test_pua_profile_requires_exact_auto_scanner_profile():
    config = _config()
    scan = _config()
    tail = scan["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    tail["font_dependencies"] = ["TailFont"]
    tail["tail_profile_status"] = "auto"
    tail["tail_profile_coverage"] = {"version": 1, "alphabet": "abcdefghijklmnopqrstuvwxyz", "verified": True}
    _trusted(scan)

    assert pua_tail_profile_issues(config, scan) == []


def test_tail_profile_rejects_a_different_configured_font_dependency():
    config = _config(font="UnrelatedFont")
    scan = _config(font="TailFont")
    tail = scan["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    tail.update({
        "font_dependencies": ["TailFont"],
        "tail_profile_status": "auto",
        "tail_profile_coverage": {"version": 1, "alphabet": "abcdefghijklmnopqrstuvwxyz", "verified": True},
    })
    _trusted(scan)

    issues = pua_tail_profile_issues(config, scan)
    assert issues[0]["code"] == "tail_font_dependency_unverified"


def test_pua_profile_rejects_missing_auto_scan_proof_or_changed_codepoint():
    config = _config()
    scan = _config()
    assert pua_tail_profile_issues(config, scan)[0]["code"] == "tail_pua_profile_unverified"

    scan["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0].update({
        "tail_profile_status": "auto", "pua_base": 0xE041,
    })
    assert pua_tail_profile_issues(config, scan)[0]["path"].endswith("tails[0]")


def test_opentype_profile_also_requires_signed_full_alphabet_scan():
    config = _config()
    tail = config["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    tail.pop("pua_base")
    tail.update({"opentype_feature": "aalt", "opentype_alternate_index": 2})
    scan = _config()
    scanned = scan["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0]
    scanned.pop("pua_base")
    scanned.update({
        "font_dependencies": ["TailFont"],
        "opentype_feature": "aalt",
        "opentype_alternate_index": 2,
        "tail_profile_status": "auto",
        "tail_profile_coverage": {"version": 1, "alphabet": "abcdefghijklmnopqrstuvwxyz", "verified": True},
    })
    assert pua_tail_profile_issues(config, scan)[0]["code"] == "tail_opentype_profile_unverified"

    _trusted(scan)
    assert pua_tail_profile_issues(config, scan) == []

    config["outputs"][0]["design"]["options"][0]["font_dependencies"] = ["DifferentTailFont"]
    assert pua_tail_profile_issues(config, scan)[0]["code"] == "tail_font_dependency_unverified"
