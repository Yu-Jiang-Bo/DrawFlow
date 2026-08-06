(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;

  async function getJson(url, fallback) {
    return fetchJson(url, { method: "GET" }, fallback);
  }


  async function postJson(url, payload, fallback) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    }, fallback);
  }


  async function postForm(url, form, signal, fallback) {
    return fetchJson(url, { method: "POST", body: form, signal }, fallback);
  }


  async function fetchJson(url, options, fallback) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new Error(friendlyError(error, fallback));
    }
    const text = await response.text();
    const payload = parseJson(text);
    if (!response.ok) throw new Error(errorFromPayload(payload, fallback));
    return payload === null ? {} : payload;
  }


  function errorFromPayload(payload, fallback) {
    const error = objectOf(payload && payload.error);
    const parts = [error.reason, error.message, error.suggestion, payload && payload.reason, payload && payload.message].filter(Boolean);
    return sanitizeMessage(parts.join(" ") || fallback || "请求失败，请稍后重试。", fallback);
  }


  function friendlyError(error, fallback) {
    if (isAbort(error)) return "操作已取消。";
    const text = error && error.message ? String(error.message) : String(error || "");
    if (/failed to fetch|networkerror|load failed/i.test(text)) {
      return sanitizeMessage(fallback || "无法连接服务，请确认本地客户端或中央服务已启动。", fallback);
    }
    return sanitizeMessage(text, fallback || "操作失败，请稍后重试。");
  }


  function sanitizeMessage(value, fallback) {
    const text = cleanText(value);
    if (!text || containsSensitive(text)) return fallback || "操作失败，技术详情已隐藏，请稍后重试。";
    return text.replace(/\s+/g, " ").slice(0, 180);
  }


  function containsSensitive(text) {
    return /(?:[A-Za-z]:[\\/]|\\\\|Traceback|File ".+?", line \d+|line \d+, in |HTTP\/\d|(?:GET|POST|PUT|DELETE)\s+\/|Host:|Authorization:|Cookie:|COMError|com_error|HRESULT|0x8[0-9A-F]{7}|-2147\d{6}|stack:)/i.test(text);
  }


  function showScanFailure(message) {
    setText("scanFailedMessage", sanitizeMessage(message, "扫描失败，请检查本地客户端后重试。"));
    setHidden("scanFailedOverlay", false);
    const overlay = $("scanFailedOverlay");
    if (overlay) overlay.setAttribute("aria-hidden", "false");
  }


  function closeScanFailure() {
    setHidden("scanFailedOverlay", true);
    const overlay = $("scanFailedOverlay");
    if (overlay) overlay.setAttribute("aria-hidden", "true");
  }


  function setScanningUi(active, message) {
    if (globalThis.renderScanProgress) {
      globalThis.renderScanProgress(message, active ? "active" : "idle");
    } else {
      setText("scanProgress", message);
    }
    setText("uploadScanBadge", active ? "扫描中" : message);
    setDisabled("scanTemplateBtn", active);
    setDisabled("rescanTemplateBtn", active);
    setDisabled("saveDraftBtn", active);
    setDisabled("cancelScanBtn", !active);
  }



  Object.assign(globalThis, {
    getJson,
    postJson,
    postForm,
    fetchJson,
    errorFromPayload,
    friendlyError,
    sanitizeMessage,
    containsSensitive,
    showScanFailure,
    closeScanFailure,
    setScanningUi
  });
})();
