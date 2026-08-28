"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { URL } = require("node:url");

class DesktopConfigError extends Error {}

function readCentralUrl(clientRoot) {
  const configPath = path.join(clientRoot, "drawflow-client.json");
  let config;
  try {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (error) {
    throw new DesktopConfigError("桌面客户端配置损坏或缺失。请重新安装 DrawFlow。", { cause: error });
  }
  const value = String(config.central_url || "").trim();
  let parsed;
  try {
    parsed = new URL(value);
  } catch (error) {
    throw new DesktopConfigError("中央服务地址无效。请联系管理员重新配置客户端。", { cause: error });
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    throw new DesktopConfigError("中央服务地址不安全或格式无效。请联系管理员重新配置客户端。");
  }
  return parsed.toString().replace(/\/$/, "");
}

module.exports = { DesktopConfigError, readCentralUrl };
