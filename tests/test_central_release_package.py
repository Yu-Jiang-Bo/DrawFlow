from __future__ import annotations

import shutil
import subprocess
import zipfile
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required for release-package verification")
def test_linux_central_package_excludes_windows_scan_client(tmp_path: Path) -> None:
    """The central package must retain server validation but omit Windows scan code."""

    project = tmp_path / "central-package-project"
    (project / "deploy" / "linux").mkdir(parents=True)
    (project / "src" / "service").mkdir(parents=True)
    (project / "config").mkdir()
    (project / "templates").mkdir()
    (project / "output" / "template-configs" / "JJMB202603281027102517").mkdir(parents=True)
    (project / "output" / "template-named" / "JJMB202509231236046265").mkdir(parents=True)

    shutil.copy2(
        PROJECT_ROOT / "deploy" / "package-linux-central.ps1",
        project / "deploy" / "package-linux-central.ps1",
    )
    shutil.copy2(
        PROJECT_ROOT / "deploy" / "assert-master-release.ps1",
        project / "deploy" / "assert-master-release.ps1",
    )
    shutil.copy2(
        PROJECT_ROOT / "deploy" / "release-path-guards.ps1",
        project / "deploy" / "release-path-guards.ps1",
    )
    shutil.copy2(
        PROJECT_ROOT / "deploy" / "master-release-snapshot.ps1",
        project / "deploy" / "master-release-snapshot.ps1",
    )
    shutil.copy2(PROJECT_ROOT / "deploy" / "README-LINUX.md", project / "deploy" / "README-LINUX.md")
    for script in (PROJECT_ROOT / "deploy" / "linux").glob("*.sh"):
        shutil.copy2(script, project / "deploy" / "linux" / script.name)

    (project / "config" / "templates.json").write_text('{"templates": []}', encoding="utf-8")
    (project / "templates" / ".keep").write_text("", encoding="utf-8")
    (project / "requirements.txt").write_text("", encoding="utf-8")
    config_output = project / "output" / "template-configs" / "JJMB202603281027102517" / "template.config.json"
    named_output = project / "output" / "template-named" / "JJMB202509231236046265" / "curved-title-mark-report.json"
    config_output.parent.mkdir(parents=True, exist_ok=True)
    named_output.parent.mkdir(parents=True, exist_ok=True)
    config_output.write_text("{}", encoding="utf-8")
    named_output.write_text("{}", encoding="utf-8")
    (project / "src" / "service" / "__init__.py").write_text("", encoding="utf-8")
    (project / "src" / "service" / "local_client.py").write_text("client_only = True\n", encoding="utf-8")
    (project / "src" / "service" / "local_gateway.py").write_text("gateway_only = True\n", encoding="utf-8")
    (project / "src" / "service" / "local_scan_client.py").write_text(
        'secret = getattr(client, "scan_worker_secret", "")\n', encoding="utf-8"
    )
    (project / "src" / "service" / "v2_scan_worker_auth.py").write_text(
        "SERVER_VALIDATION = True\n", encoding="utf-8"
    )
    (project / "src" / "service" / "v2_template_validation.py").write_text(
        "TEMPLATE_VALIDATION = True\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(project), "symbolic-ref", "HEAD", "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "user.name=DrawFlow Tests",
            "-c",
            "user.email=drawflow-tests@example.invalid",
            "commit",
            "-m",
            "test baseline",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    environment = os.environ.copy()
    environment["DRAWFLOW_RELEASE_SNAPSHOT_BASE"] = str(
        PROJECT_ROOT / "output" / "central-release-test-snapshots"
    )
    completed = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project / "deploy" / "package-linux-central.ps1"),
            "-ReleaseName",
            "test-central-package",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    release_root = project / "release" / "test-central-package"
    assert (release_root / "src" / "service" / "v2_scan_worker_auth.py").is_file()
    assert (release_root / "src" / "service" / "v2_template_validation.py").is_file()
    assert not (release_root / "src" / "service" / "local_client.py").exists()
    assert not (release_root / "src" / "service" / "local_gateway.py").exists()
    assert not (release_root / "src" / "service" / "local_scan_client.py").exists()
    assert all(b"\r\n" not in script.read_bytes() for script in (release_root / "deploy" / "linux").glob("*.sh"))
    with zipfile.ZipFile(project / "release" / "test-central-package.zip") as archive:
        entry_names = set(archive.namelist())
    assert all("\\" not in entry_name for entry_name in entry_names)
    assert "deploy/linux/install.sh" in entry_names
    assert "src/service/v2_scan_worker_auth.py" in entry_names
    assert "src/service/local_scan_client.py" not in entry_names
