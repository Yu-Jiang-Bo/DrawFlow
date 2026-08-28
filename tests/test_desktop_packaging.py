from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_packaging_builds_a_manual_windows_installer_with_only_needed_client_resources():
    script = (ROOT / "deploy" / "package-desktop.ps1").read_text(encoding="utf-8")
    package = (ROOT / "desktop" / "package.json").read_text(encoding="utf-8")

    assert "package-client.ps1" in script
    assert "DrawFlow-Setup-$ClientVersion.exe" in script
    assert "drawflow-client.json" in script
    assert "_internal" in script
    assert "npm.cmd run build:win" in script
    assert '"nsis"' in package
    assert '"perMachine": false' in package
    assert '"DrawFlowClient.exe"' in package


def test_electron_shell_does_not_enable_node_for_the_proxied_web_page():
    security = (ROOT / "desktop" / "desktop-security.cjs").read_text(encoding="utf-8")
    main = (ROOT / "desktop" / "main.cjs").read_text(encoding="utf-8")

    assert "nodeIntegration: false" in security
    assert "contextIsolation: true" in security
    assert "sandbox: true" in security
    assert "setWindowOpenHandler" in main
    assert "isAllowedGatewayNavigation" in main
    assert 'webContents.on("will-redirect"' in main


def test_deployment_docs_direct_colleagues_to_the_desktop_setup_not_a_raw_gateway_zip():
    deployment = (ROOT / "deploy" / "DEPLOY-DESKTOP-AGENT.md").read_text(encoding="utf-8")
    operations = (ROOT / "deploy" / "DEPLOY-SCHEME2-OPERATIONS.md").read_text(encoding="utf-8")

    assert "DrawFlow-Setup-<version>.exe" in deployment
    assert "不自动打开系统浏览器" in deployment
    assert "把 `drawflow-client-20260720-scheme2-r8.zip` 发送到出图电脑" not in operations
    assert "DrawFlow-Setup-<version>.exe" in operations
