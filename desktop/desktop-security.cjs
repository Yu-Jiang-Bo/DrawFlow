"use strict";

const GATEWAY_ORIGIN = "http://127.0.0.1:8766";

const DESKTOP_WEB_PREFERENCES = Object.freeze({
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
});

function isAllowedGatewayNavigation(value) {
  try {
    const url = new URL(value);
    return url.origin === GATEWAY_ORIGIN;
  } catch {
    return false;
  }
}

module.exports = {
  DESKTOP_WEB_PREFERENCES,
  GATEWAY_ORIGIN,
  isAllowedGatewayNavigation,
};
