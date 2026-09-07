import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_client_payload_build_requires_semver_and_emits_release_metadata():
    script = (ROOT / "deploy" / "package-client.ps1").read_text(encoding="utf-8")
    assert "$ClientVersion" in script
    assert "drawflow-client-$ClientVersion.payload.zip" in script
    assert "drawflow/client-release/v1" in script
    assert "drawflow/client-build-source/v1" in script
    assert "drawflow-release-source.json" in script
    assert "HEAD^{tree}" in script
    assert "Get-FileHash" in script
    assert '.client-payload-$ClientVersion' in script
    assert "drawflow-client.example.json" not in script
    assert "start-client.bat" not in script
    assert "drawflow-client.json" not in script
    assert "$ArchivePath" not in script


def test_initial_installer_is_per_user_and_keeps_drawflow_business_data_outside_app_dir():
    installer = (ROOT / "deploy" / "installer" / "DrawFlow.iss").read_text(encoding="utf-8")
    script = (ROOT / "deploy" / "package-setup.ps1").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in installer
    assert "{localappdata}\\Programs\\DrawFlow" in installer
    assert "DrawFlowClient.exe" in script
    assert "UpdateBaseUrl must be absolute HTTPS" in script
    assert "drawflow-launcher.json" in script
    assert "$updateUri.UserInfo" in script
    assert "$centralUri.UserInfo" in script


def test_user_facing_docs_only_direct_colleagues_to_the_one_time_setup_package():
    client_readme = (ROOT / "deploy" / "client" / "README-CLIENT.md").read_text(encoding="utf-8")
    deployment = (ROOT / "deploy" / "DEPLOY-DESKTOP-AGENT.md").read_text(encoding="utf-8")
    assert "不得直接发给同事" in client_readme
    assert "DrawFlow-Setup-<version>.exe" in client_readme
    assert "同事只接收一次 `DrawFlow-Setup-<version>.exe`" in deployment
    assert "用户不得手工替换或直接运行 `DrawFlowClient.exe`" in deployment


def test_scheme_two_operations_do_not_offer_a_direct_client_zip_install_path():
    operations = (ROOT / "deploy" / "DEPLOY-SCHEME2-OPERATIONS.md").read_text(encoding="utf-8")
    assert "把 `drawflow-client-20260720-scheme2-r8.zip` 发送到出图电脑" not in operations
    assert "生产同事只接收 `DrawFlow-Setup-<version>.exe`" in operations


def test_all_client_and_central_release_entrypoints_require_clean_master():
    entrypoints = (
        "package-client.ps1",
        "package-launcher.ps1",
        "package-setup.ps1",
        "package-release.ps1",
        "package-linux-central.ps1",
        "publish-client-release.ps1",
    )
    for name in entrypoints:
        script = (ROOT / "deploy" / name).read_text(encoding="utf-8")
        if name == "publish-client-release.ps1":
            assert "assert-master-release.ps1" in script, name
        else:
            assert "master-release-snapshot.ps1" in script, name

    snapshot = (ROOT / "deploy" / "master-release-snapshot.ps1").read_text(encoding="utf-8")
    assert "assert-master-release.ps1" in snapshot
    assert "worktree add --detach" in snapshot
    assert "worktree remove --force" in snapshot


def test_master_release_guard_rejects_other_branches_and_uncommitted_files(tmp_path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required to exercise the release guard.")

    repository = tmp_path / "repository"
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repository), "symbolic-ref", "HEAD", "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )
    (repository / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
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

    guard = ROOT / "deploy" / "assert-master-release.ps1"

    def run_guard():
        return subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(guard),
                "-ProjectRoot",
                str(repository),
            ],
            capture_output=True,
            text=True,
        )

    assert run_guard().returncode == 0
    subprocess.run(
        ["git", "-C", str(repository), "checkout", "-b", "codex/not-master"],
        check=True,
        capture_output=True,
        text=True,
    )
    wrong_branch = run_guard()
    assert wrong_branch.returncode != 0
    assert "only from master" in (wrong_branch.stdout + wrong_branch.stderr)

    subprocess.run(
        ["git", "-C", str(repository), "checkout", "master"],
        check=True,
        capture_output=True,
        text=True,
    )
    (repository / "tracked.txt").write_text("not committed\n", encoding="utf-8")
    dirty_master = run_guard()
    assert dirty_master.returncode != 0
    assert "no uncommitted files" in (dirty_master.stdout + dirty_master.stderr)

    (repository / "tracked.txt").write_text("committed\n", encoding="utf-8")
    (repository / "src").mkdir()
    (repository / "src" / "uncommitted_feature.py").write_text("UNCOMMITTED = True\n", encoding="utf-8")
    untracked_source = run_guard()
    assert untracked_source.returncode != 0
    assert "no uncommitted files" in (untracked_source.stdout + untracked_source.stderr)


def test_release_name_cannot_escape_release_directory(tmp_path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required to exercise the release path guard.")

    runner = tmp_path / "check-release-path.ps1"
    runner.write_text(
        "param([string]$Guard, [string]$Base, [string]$Name)\n"
        ". $Guard\n"
        "Resolve-SafeReleaseChildPath -BaseDirectory $Base -Name $Name -Label 'ReleaseName'\n",
        encoding="utf-8",
    )
    release_base = tmp_path / "release"
    release_base.mkdir()
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner),
            "-Guard",
            str(ROOT / "deploy" / "release-path-guards.ps1"),
            "-Base",
            str(release_base),
            "-Name",
            "..\\src",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "only letters" in (result.stdout + result.stderr)


def test_master_snapshot_restores_location_and_rejects_dirty_inherited_worktree(tmp_path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required to exercise the master snapshot.")

    repository = tmp_path / "snapshot-repository"
    (repository / "deploy").mkdir(parents=True)
    shutil.copy2(ROOT / "deploy" / "assert-master-release.ps1", repository / "deploy")
    shutil.copy2(ROOT / "deploy" / "master-release-snapshot.ps1", repository / "deploy")
    (repository / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repository), "symbolic-ref", "HEAD", "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=DrawFlow Tests",
            "-c",
            "user.email=drawflow-tests@example.invalid",
            "commit",
            "-m",
            "snapshot baseline",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lifecycle_runner = tmp_path / "snapshot-lifecycle.ps1"
    lifecycle_runner.write_text(
        "param([string]$Repo)\n"
        ". (Join-Path $Repo 'deploy\\master-release-snapshot.ps1')\n"
        "$context = $null\n"
        "try {\n"
        "  $context = Enter-MasterReleaseSnapshot -InvocationRoot $Repo\n"
        "  $snapshot = $context.SourceRoot\n"
        "  Set-Location -LiteralPath $snapshot\n"
        "} finally {\n"
        "  if ($context) { Exit-MasterReleaseSnapshot -Context $context }\n"
        "}\n"
        "if (Test-Path -LiteralPath $snapshot) { throw 'snapshot directory still exists' }\n"
        "$registered = @(& git -C $Repo worktree list --porcelain)\n"
        "if ($registered -contains ('worktree ' + $snapshot)) { throw 'snapshot is still registered' }\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("DRAWFLOW_MASTER_REPOSITORY_ROOT", None)
    environment.pop("DRAWFLOW_MASTER_SNAPSHOT_ROOT", None)
    environment["DRAWFLOW_RELEASE_SNAPSHOT_BASE"] = str(
        ROOT / "output" / f"snapshot-lifecycle-{os.getpid()}"
    )
    lifecycle = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(lifecycle_runner),
            "-Repo",
            str(repository),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert lifecycle.returncode == 0, lifecycle.stdout + lifecycle.stderr

    injected = tmp_path / "dirty-inherited-snapshot"
    subprocess.run(
        ["git", "-C", str(repository), "worktree", "add", "--detach", str(injected), "master"],
        check=True,
        capture_output=True,
        text=True,
    )
    (injected / "tracked.txt").write_text("tampered\n", encoding="utf-8")
    inherited_runner = tmp_path / "snapshot-inherited.ps1"
    inherited_runner.write_text(
        "param([string]$Repo, [string]$Snapshot)\n"
        ". (Join-Path $Repo 'deploy\\master-release-snapshot.ps1')\n"
        "Enter-MasterReleaseSnapshot -InvocationRoot $Snapshot\n",
        encoding="utf-8",
    )
    inherited_environment = environment.copy()
    inherited_environment["DRAWFLOW_MASTER_REPOSITORY_ROOT"] = str(repository)
    inherited_environment["DRAWFLOW_MASTER_SNAPSHOT_ROOT"] = str(injected)
    inherited = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(inherited_runner),
            "-Repo",
            str(repository),
            "-Snapshot",
            str(injected),
        ],
        capture_output=True,
        text=True,
        env=inherited_environment,
    )
    assert inherited.returncode != 0
    assert "contains uncommitted files" in (inherited.stdout + inherited.stderr)
    subprocess.run(
        ["git", "-C", str(repository), "worktree", "remove", "--force", str(injected)],
        check=True,
        capture_output=True,
        text=True,
    )
