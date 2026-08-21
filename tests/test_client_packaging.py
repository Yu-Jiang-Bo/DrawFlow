from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_client_payload_build_requires_semver_and_emits_release_metadata():
    script = (ROOT / "deploy" / "package-client.ps1").read_text(encoding="utf-8")
    assert "$ClientVersion" in script
    assert "drawflow-client-$ClientVersion.payload.zip" in script
    assert "drawflow/client-release/v1" in script
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
