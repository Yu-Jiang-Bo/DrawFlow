"use strict";

const http = require("node:http");
const { spawn } = require("node:child_process");

const DEFAULT_HEALTH_URL = "http://127.0.0.1:8766/health";

class DesktopRuntimeError extends Error {}

function requestHealth(url = DEFAULT_HEALTH_URL, timeoutMs = 1500) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        body += chunk;
        if (body.length > 16 * 1024) {
          request.destroy(new Error("health response is too large"));
        }
      });
      response.on("end", () => {
        if (response.statusCode !== 200) {
          reject(new Error(`health returned HTTP ${response.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(new Error("health response is not JSON", { cause: error }));
        }
      });
    });
    request.on("timeout", () => request.destroy(new Error("health request timed out")));
    request.on("error", reject);
  });
}

function isHealthyGateway(payload) {
  return Boolean(payload && payload.ok === true && payload.role === "local-client");
}

function defaultDelay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function createDesktopRuntime({
  clientExe,
  centralUrl,
  healthUrl = DEFAULT_HEALTH_URL,
  startupAttempts = 30,
  startupIntervalMs = 1000,
  spawnProcess = spawn,
  healthCheck = requestHealth,
  delay = defaultDelay,
  environment = process.env,
}) {
  let ownedChild = null;
  let childStartError = null;

  async function checkHealth() {
    try {
      const payload = await healthCheck(healthUrl);
      return isHealthyGateway(payload) ? payload : null;
    } catch {
      return null;
    }
  }

  async function waitForHealthyGateway() {
    for (let attempt = 0; attempt < startupAttempts; attempt += 1) {
      if (childStartError) {
        throw new DesktopRuntimeError(`本地渲染服务无法启动：${childStartError.message}`);
      }
      const health = await checkHealth();
      if (health) {
        return health;
      }
      if (attempt < startupAttempts - 1) {
        await delay(startupIntervalMs);
      }
    }
    throw new DesktopRuntimeError("本地渲染服务启动超时，请查看 %LOCALAPPDATA%\\DrawFlow\\logs\\drawflow-client.log。");
  }

  async function ensureRunning() {
    const existingHealth = await checkHealth();
    if (existingHealth) {
      return { health: existingHealth, reused: true };
    }
    if (!clientExe) {
      throw new DesktopRuntimeError("桌面客户端缺少本地渲染服务文件。请重新安装 DrawFlow。");
    }
    childStartError = null;
    ownedChild = spawnProcess(
      clientExe,
      ["--no-open", "--host", "127.0.0.1", "--port", "8766", "--central-url", centralUrl],
      { env: environment, stdio: "ignore", windowsHide: true },
    );
    ownedChild.once("error", (error) => {
      childStartError = error;
    });
    return { health: await waitForHealthyGateway(), reused: false };
  }

  async function stopIfOwnedAndIdle() {
    if (!ownedChild || ownedChild.exitCode !== null || ownedChild.killed) {
      return false;
    }
    const health = await checkHealth();
    if (health && health.render_in_progress === true) {
      return false;
    }
    ownedChild.kill();
    ownedChild = null;
    return true;
  }

  return {
    ensureRunning,
    stopIfOwnedAndIdle,
  };
}

module.exports = {
  DEFAULT_HEALTH_URL,
  DesktopRuntimeError,
  createDesktopRuntime,
  isHealthyGateway,
  requestHealth,
};
