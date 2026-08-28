"use strict";

const path = require("node:path");
const { app, BrowserWindow } = require("electron");
const { DesktopRuntimeError, createDesktopRuntime } = require("./desktop-runtime.cjs");
const { readCentralUrl } = require("./desktop-config.cjs");
const {
  DESKTOP_WEB_PREFERENCES,
  GATEWAY_ORIGIN,
  isAllowedGatewayNavigation,
} = require("./desktop-security.cjs");

const GATEWAY_URL = `${GATEWAY_ORIGIN}/`;
let mainWindow = null;
let runtime = null;
let isQuitting = false;

function resolveClientRoot() {
  if (process.env.DRAWFLOW_DESKTOP_CLIENT_ROOT) {
    return path.resolve(process.env.DRAWFLOW_DESKTOP_CLIENT_ROOT);
  }
  return app.isPackaged
    ? path.join(process.resourcesPath, "client")
    : path.join(__dirname, "build", "client");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function showStartupError(error) {
  const message = error instanceof Error ? error.message : "桌面客户端启动失败。";
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <main style="font-family:system-ui;padding:36px;max-width:620px">
      <h1>DrawFlow 无法启动</h1>
      <p>${escapeHtml(message)}</p>
      <p>请确认已安装最新版 DrawFlow；若仍失败，请联系管理员并提供本机日志。</p>
    </main>`)}
  )}`);
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    show: false,
    title: "DrawFlow",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      ...DESKTOP_WEB_PREFERENCES,
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  const blockExternalNavigation = (event, url) => {
    if (!isAllowedGatewayNavigation(url)) {
      event.preventDefault();
      void showStartupError(new DesktopRuntimeError("已阻止客户端加载非本机页面。请检查中央服务配置。"));
    }
  };
  mainWindow.webContents.on("will-navigate", blockExternalNavigation);
  mainWindow.webContents.on("will-redirect", blockExternalNavigation);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  return mainWindow;
}

async function startDesktop() {
  const window = createMainWindow();
  try {
    const clientRoot = resolveClientRoot();
    const clientExe = path.join(clientRoot, "DrawFlowClient.exe");
    runtime = createDesktopRuntime({ clientExe, centralUrl: readCentralUrl(clientRoot) });
    await runtime.ensureRunning();
    await window.loadURL(GATEWAY_URL);
  } catch (error) {
    await showStartupError(error);
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(async () => {
    app.setAppUserModelId("com.drawflow.desktop");
    await startDesktop();
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", (event) => {
    if (isQuitting || !runtime) return;
    event.preventDefault();
    isQuitting = true;
    void runtime.stopIfOwnedAndIdle().catch(() => false).finally(() => app.quit());
  });
}

module.exports = { resolveClientRoot };
