"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { DesktopRuntimeError, createDesktopRuntime, isHealthyGateway } = require("../desktop-runtime.cjs");
const { DesktopConfigError, readCentralUrl } = require("../desktop-config.cjs");
const { DESKTOP_WEB_PREFERENCES, isAllowedGatewayNavigation } = require("../desktop-security.cjs");

function childProcess() {
  const child = new EventEmitter();
  child.exitCode = null;
  child.killed = false;
  child.kill = () => { child.killed = true; };
  return child;
}

test("recognizes only the expected loopback gateway health payload", () => {
  assert.equal(isHealthyGateway({ ok: true, role: "local-client" }), true);
  assert.equal(isHealthyGateway({ ok: true, role: "central" }), false);
  assert.equal(isHealthyGateway({ ok: false, role: "local-client" }), false);
});

test("keeps the Electron renderer sandboxed and allows navigation only to the local gateway", () => {
  assert.deepEqual(DESKTOP_WEB_PREFERENCES, {
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
  });
  assert.equal(isAllowedGatewayNavigation("http://127.0.0.1:8766/v2/templates/workbench"), true);
  assert.equal(isAllowedGatewayNavigation("http://localhost:8766/"), false);
  assert.equal(isAllowedGatewayNavigation("https://central.example/"), false);
});

test("reads only credential-free central service addresses from packaged config", () => {
  const clientRoot = fs.mkdtempSync(path.join(os.tmpdir(), "drawflow-desktop-config-"));
  const configPath = path.join(clientRoot, "drawflow-client.json");
  try {
    fs.writeFileSync(configPath, JSON.stringify({ central_url: "http://central.example:8765/" }));
    assert.equal(readCentralUrl(clientRoot), "http://central.example:8765");
    fs.writeFileSync(configPath, JSON.stringify({ central_url: "https://user:password@central.example" }));
    assert.throws(() => readCentralUrl(clientRoot), DesktopConfigError);
    fs.writeFileSync(configPath, JSON.stringify({ central_url: "https://central.example?token=secret" }));
    assert.throws(() => readCentralUrl(clientRoot), DesktopConfigError);
  } finally {
    fs.rmSync(clientRoot, { recursive: true, force: true });
  }
});

test("reuses an already healthy local gateway without spawning", async () => {
  let spawned = false;
  const runtime = createDesktopRuntime({
    clientExe: "DrawFlowClient.exe",
    centralUrl: "http://central.example:8765",
    healthCheck: async () => ({ ok: true, role: "local-client" }),
    spawnProcess: () => { spawned = true; return childProcess(); },
  });
  const result = await runtime.ensureRunning();
  assert.equal(result.reused, true);
  assert.equal(spawned, false);
});

test("starts the local gateway with loopback-only arguments and waits for health", async () => {
  const child = childProcess();
  let invocation;
  let checks = 0;
  const runtime = createDesktopRuntime({
    clientExe: "C:/client/DrawFlowClient.exe",
    centralUrl: "http://central.example:8765",
    startupAttempts: 3,
    startupIntervalMs: 0,
    healthCheck: async () => {
      checks += 1;
      if (checks < 3) throw new Error("not ready");
      return { ok: true, role: "local-client" };
    },
    delay: async () => {},
    spawnProcess: (...args) => { invocation = args; return child; },
  });
  const result = await runtime.ensureRunning();
  assert.equal(result.reused, false);
  assert.deepEqual(invocation[1], ["--no-open", "--host", "127.0.0.1", "--port", "8766", "--central-url", "http://central.example:8765"]);
  assert.equal(invocation[2].windowsHide, true);
});

test("reports a startup timeout instead of loading an unready client", async () => {
  const runtime = createDesktopRuntime({
    clientExe: "DrawFlowClient.exe",
    centralUrl: "http://central.example:8765",
    startupAttempts: 2,
    startupIntervalMs: 0,
    healthCheck: async () => { throw new Error("offline"); },
    delay: async () => {},
    spawnProcess: () => childProcess(),
  });
  await assert.rejects(runtime.ensureRunning(), DesktopRuntimeError);
});

test("stops only an idle gateway process started by this desktop instance", async () => {
  const child = childProcess();
  let health = { ok: true, role: "local-client" };
  let checks = 0;
  const runtime = createDesktopRuntime({
    clientExe: "DrawFlowClient.exe",
    centralUrl: "http://central.example:8765",
    startupIntervalMs: 0,
    delay: async () => {},
    healthCheck: async () => {
      checks += 1;
      if (checks === 1) throw new Error("not running yet");
      return health;
    },
    spawnProcess: () => child,
  });
  await runtime.ensureRunning();
  health = { ok: true, role: "local-client", render_in_progress: true };
  assert.equal(await runtime.stopIfOwnedAndIdle(), false);
  assert.equal(child.killed, false);
  health = { ok: true, role: "local-client", render_in_progress: false };
  assert.equal(await runtime.stopIfOwnedAndIdle(), true);
  assert.equal(child.killed, true);
});
