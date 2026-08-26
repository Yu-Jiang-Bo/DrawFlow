(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { API_ROOT, state } = ctx;

  function uploadSelectedAiFile(rescan) {
    if (state.isPublishedView) {
      showScanFailure("已发布模板为只读配置；需要修改请先创建新草稿。");
      return;
    }
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
    if (typeof globalThis.invalidateTrialResult === "function") globalThis.invalidateTrialResult("模板已重新扫描，请重新试渲染。");
    state.isScanning = true;
    setScanningUi(true, rescan ? "正在重新扫描 .ai 模板" : "正在扫描 .ai 模板");
    try {
      await ensureDraftExists();
      const localResult = await tryLocalScan(file);
      await refreshDraftAfterScan(localResult);
      setScanningUi(false, "扫描完成，请核对结构和绑定。");
    } catch (scanError) {
      if (isAbort(scanError)) {
        setScanningUi(false, "页面已停止等待扫描结果。");
        return;
      }
      const scanMessage = friendlyError(scanError, "本地扫描接口未就绪，请确认本地客户端已启动后重试。");
      setScanningUi(false, "扫描失败，请重试。");
      setText("scanSummary", "扫描未完成，草稿已保留，可重新扫描。");
      await safeRefreshDraft(formBasics().template_id);
      showScanFailure(`${scanMessage} 草稿已保留，可重新扫描。`);
    } finally {
      state.isScanning = false;
      updateDraftButtons();
    }
  }


  async function tryLocalScan(file) {
    const basics = formBasics();
    const form = new FormData();
    form.append("template_id", basics.template_id);
    form.append("name", basics.name);
    form.append("shop_name", basics.shop_name);
    form.append("template_type", "pure_text");
    form.append("scan_contract_version", "v2-template-scan/1");
    form.append("template_ai", file, file.name);
    return postForm("/local/templates/scan", form, null, "本地扫描接口未就绪，请确认本地客户端已启动。");
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


  function retryScan() {
    closeScanFailure();
    const selected = state.templates.find((item) => templateIdOf(item) === state.selectedTemplateId);
    const publication = objectOf(selected && selected.publication);
    if (publication.status === "active" && cleanText(publication.current_version)) {
      refreshSharedTemplates().catch((error) => showScanFailure(friendlyError(error, "共享配置刷新失败，请稍后重试。")));
      return;
    }
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
    const readOnly = Boolean(state.isPublishedView);
    const hasBasics = Boolean(formBasics().template_id && formBasics().name);
    setDisabled("templateId", readOnly || Boolean(state.selectedTemplateId));
    setDisabled("templateName", readOnly);
    setDisabled("shopName", readOnly);
    setDisabled("aiFile", readOnly);
    setDisabled("outlineTextToggle", readOnly);
    setDisabled("pathfinderMergeToggle", readOnly);
    setDisabled("optionContentPreset", readOnly);
    setDisabled("saveDraftBtn", readOnly || !hasBasics || state.isScanning || state.isSavingDraft);
    setDisabled("confirmStageBtn", readOnly || state.isScanning || state.isSavingDraft);
    setDisabled("saveAndNextOptionBtn", readOnly || state.isScanning || state.isSavingDraft);
    setDisabled("scanTemplateBtn", readOnly || !hasBasics || !state.uploadFile || state.isScanning);
    setDisabled("rescanTemplateBtn", readOnly || !hasBasics || state.isScanning);
    setDisabled("trialRenderBtn", readOnly || !state.draft || state.isScanning || state.isSavingDraft);
    setDisabled("rerunTrialRenderBtn", readOnly || !state.draft || state.isScanning || state.isSavingDraft);
    setDisabled("publishVersionBtn", readOnly || !state.draft || state.isScanning || state.isSavingDraft);
    const hasScan = scanSummary(state.scan || {}).total > 0 || Object.keys(state.scan || {}).length > 0;
    setDisabled("enterStructureBtn", !hasScan);
  }



  Object.assign(globalThis, {
    uploadSelectedAiFile,
    uploadTemplateFile,
    tryLocalScan,
    refreshDraftAfterScan,
    retryScan,
    handleFileInput,
    bindDropzone,
    setUploadFile,
    toggleSection,
    updateDraftButtons
  });
})();
