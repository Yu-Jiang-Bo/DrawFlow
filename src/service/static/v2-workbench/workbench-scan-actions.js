(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { API_ROOT, state } = ctx;

  function uploadSelectedAiFile(rescan) {
    const file = state.uploadFile || fileOf("aiFile");
    if (!file) {
      showScanFailure("请先选择 .ai 模板文件。");
      return;
    }
    uploadTemplateFile(file, rescan).catch((error) => showScanFailure(friendlyError(error, "扫描失败，请检查本地客户端后重试。")));
  }


  async function uploadTemplateFile(file, rescan) {
    if (!isAiFile(file)) {
      showScanFailure("只能上传 .ai 模板文件。");
      return;
    }
    state.lastUploadFile = file;
    state.isScanning = true;
    state.scanController = new AbortController();
    setScanningUi(true, rescan ? "正在重新扫描 .ai 模板" : "正在扫描 .ai 模板");
    try {
      await ensureDraftExists();
      const localResult = await tryLocalScan(file, state.scanController.signal);
      await refreshDraftAfterScan(localResult);
      setScanningUi(false, "扫描完成，请核对结构和绑定。");
    } catch (scanError) {
      if (isAbort(scanError)) {
        setScanningUi(false, "扫描已取消。");
        return;
      }
      const scanMessage = friendlyError(scanError, "本地扫描接口未就绪，文件将先保存到中央草稿。");
      try {
        await uploadAssetToCentral(file, state.scanController.signal);
        setScanningUi(false, "文件已保存，等待本地扫描。");
        setText("scanSummary", "文件已保存，等待本地扫描结果。");
        await safeRefreshDraft(formBasics().template_id);
        showScanFailure(`${scanMessage} 文件已保存，等待本地扫描。`);
      } catch (uploadError) {
        setScanningUi(false, "上传失败，请重试。");
        showScanFailure(friendlyError(uploadError, "文件上传失败，请稍后重试。"));
      }
    } finally {
      state.isScanning = false;
      state.scanController = null;
      updateDraftButtons();
    }
  }


  async function tryLocalScan(file, signal) {
    const basics = formBasics();
    const form = new FormData();
    form.append("template_id", basics.template_id);
    form.append("name", basics.name);
    form.append("shop_name", basics.shop_name);
    form.append("template_type", "pure_text");
    form.append("template_ai", file, file.name);
    return postForm("/local/templates/scan", form, signal, "本地扫描接口未就绪，请确认本地客户端已启动。");
  }


  async function uploadAssetToCentral(file, signal) {
    const id = formBasics().template_id;
    const headers = { "Content-Type": file.type || "application/illustrator", "X-DrawFlow-Asset-Role": "template" };
    const payload = await fetchJson(`${API_ROOT}/${encodeURIComponent(id)}/assets/${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers,
      body: file,
      signal
    }, "文件上传失败，请稍后重试。");
    if (payload.draft) {
      state.draft = payload.draft;
      state.scan = normalizeScanFromDraft(state.draft);
    }
    return payload;
  }


  async function refreshDraftAfterScan(result) {
    const id = String(result && (result.template_id || result.id) || formBasics().template_id);
    if (result && result.draft) {
      state.draft = result.draft;
      state.scan = normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, id);
      renderAll();
      return;
    }
    if (result && result.scan) state.scan = objectOf(result.scan);
    await safeRefreshDraft(id);
  }


  function cancelScan() {
    if (state.scanController) state.scanController.abort();
  }


  function retryScan() {
    closeScanFailure();
    if (state.lastUploadFile) {
      uploadTemplateFile(state.lastUploadFile, true).catch((error) => showScanFailure(friendlyError(error, "扫描失败，请重试。")));
    } else {
      const input = $("aiFile");
      if (input) input.click();
    }
  }


  function handleFileInput(event) {
    const file = event.target && event.target.files && event.target.files[0];
    if (file) setUploadFile(file);
  }


  function bindDropzone() {
    const zone = $("aiDropzone");
    const input = $("aiFile");
    if (!zone) return;
    zone.addEventListener("click", () => input && input.click());
    ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("dragover");
    }));
    ["dragleave", "drop"].forEach((type) => zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.remove("dragover");
    }));
    zone.addEventListener("drop", (event) => {
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) setUploadFile(file);
    });
  }


  function setUploadFile(file) {
    state.uploadFile = file;
    renderScanProgress(isAiFile(file) ? `已选择：${safeFileName(file.name)}` : "请选择 .ai 文件。", "idle");
    renderScanSummary();
    updateDraftButtons();
  }


  function toggleSection(key) {
    state.expanded[key] = !state.expanded[key];
    renderStructureTree();
  }


  function updateDraftButtons() {
    const hasBasics = Boolean(formBasics().template_id && formBasics().name);
    setDisabled("saveDraftBtn", !hasBasics || state.isScanning);
    setDisabled("scanTemplateBtn", !hasBasics || !state.uploadFile || state.isScanning);
    setDisabled("rescanTemplateBtn", !hasBasics || state.isScanning);
    setDisabled("cancelScanBtn", !state.isScanning);
    const hasScan = scanSummary(state.scan || {}).total > 0 || Object.keys(state.scan || {}).length > 0;
    setDisabled("enterStructureBtn", !hasScan);
  }



  Object.assign(globalThis, {
    uploadSelectedAiFile,
    uploadTemplateFile,
    tryLocalScan,
    uploadAssetToCentral,
    refreshDraftAfterScan,
    cancelScan,
    retryScan,
    handleFileInput,
    bindDropzone,
    setUploadFile,
    toggleSection,
    updateDraftButtons
  });
})();
