(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { API_ROOT, state } = ctx;

  async function loadTemplates(preferredId) {
    await refreshTemplateList();
    const id = preferredId || state.selectedTemplateId;
    if (id && state.templates.some((item) => templateIdOf(item) === id)) {
      return selectTemplate(id);
    } else if (!state.templates.length) {
      clearDraftView();
    }
    return false;
  }


  async function refreshTemplateList() {
    globalThis.setV2RuntimeStatus("v2LocalHealthText", "本机已就绪");
    globalThis.setV2RuntimeStatus("v2CentralHealthText", "中央服务连接中", "busy");
    try {
      const payload = await getJson(API_ROOT, "模板列表加载失败，请稍后重试。");
      state.templates = Array.isArray(payload.templates) ? payload.templates : [];
      renderTemplateList();
      globalThis.setV2RuntimeStatus("v2CentralHealthText", "中央服务已连接");
    } catch (error) {
      globalThis.setV2RuntimeStatus("v2CentralHealthText", "中央服务不可达", "error");
      throw error;
    }
  }


  async function refreshSharedTemplates() {
    const selectedTemplateId = state.selectedTemplateId;
    await refreshTemplateList();
    if (selectedTemplateId && state.templates.some((item) => templateIdOf(item) === selectedTemplateId)) {
      return selectTemplate(selectedTemplateId);
    }
    return true;
  }

  function clearDraftView() {
    state.validation = null;
    state.lastValidatedConfig = null;
    state.validationRequestId += 1;
    state.selectedTemplateId = "";
    state.draftLoadRequestId += 1;
    state.draft = null;
    state.isPublishedView = false;
    state.publishedDraftCompatibility = false;
    state.scan = {};
    setDisabled("templateId", false);
    if (typeof resetPreviewState === "function") resetPreviewState();
    if (typeof clearValidationFeedback === "function") clearValidationFeedback();
    if (typeof updateCheckRail === "function" && typeof defaultChecks === "function") updateCheckRail(defaultChecks());
    fillDraftFields(null, "");
    renderAll();
  }


  function renderAll() {
    renderScanSummary();
    if (state.stage === "structure" || state.stage === "rules") {
      renderStructureTree();
      renderTables();
      if (state.stage === "rules" && typeof renderOptionRuleStage === "function") renderOptionRuleStage();
      updateCheckRail(configChecks());
      validateCurrentConfig(false).catch(() => updateCheckRail(configChecks()));
    } else if (state.stage === "preview") {
      renderTables();
      renderPreviewStage();
      updateCheckRail(configChecks());
      validateCurrentConfig(false).catch(() => updateCheckRail(configChecks()));
    } else {
      updateCheckRail(defaultChecks());
    }
    updateDraftButtons();
  }


  async function saveDraft(options) {
    if (state.isPublishedView) {
      const message = "已发布模板为只读配置；需要修改请先创建新草稿。";
      setDraftStatus("已发布 · 只读", "confirmed");
      setText("draftSaveStatusText", message);
      showScanFailure(message);
      return { saved: false, failure: "readonly" };
    }
    const basics = formBasics();
    if (!basics.template_id || !basics.name) {
      showScanFailure("请先填写模板 ID 和模板名称。");
      setText("draftSaveStatusText", "草稿未保存：请先填写模板 ID 和名称。");
      return { saved: false, failure: "basics" };
    }
    if (state.isSavingDraft) return { saved: false, failure: "busy" };
    prepareSaveTarget(basics.template_id);
    state.isSavingDraft = true;
    updateDraftButtons();
    setDraftStatus("正在保存", "pending");
    try {
      await ensureDraftExists();
      const configOverride = objectOf(options).configOverride;
      const config = Array.isArray(objectOf(configOverride).outputs) ? configOverride : buildControlledConfig();
      const validationRequestId = ++state.validationRequestId;
      state.lastValidatedConfig = config;
      const validation = await validateConfig(config);
      if (validationRequestId !== state.validationRequestId) return { saved: false, failure: "stale" };
      state.validation = validation;
      updateCheckRail(validation.checks || config.checks);
      if (validation.can_save === false) {
        updateBlockers(validation);
        setDraftStatus("配置未通过校验", "blocked");
        setText("draftSaveStatusText", "草稿未保存：当前配置未通过保存校验。");
        return { saved: false, failure: "validation" };
      }
      const previousScan = objectOf(state.scan);
      const payload = await postJson(`${API_ROOT}/${encodeURIComponent(basics.template_id)}/draft`, {
        name: basics.name,
        shop_name: basics.shop_name,
        config
      }, "草稿保存失败，请检查当前配置。");
      const responseDraft = objectOf(payload.draft);
      if (!isCurrentTemplateResponse(responseDraft, basics.template_id)) return { saved: false, failure: "stale" };
      const responseScan = normalizeScanFromDraft(responseDraft);
      const retainedScan = hasScanEvidence(responseScan)
        ? responseScan
        : canRetainPreviousScan(previousScan, basics.template_id) ? previousScan : {};
      state.draft = payload.draft
        ? { ...responseDraft, ...(hasScanEvidence(retainedScan) ? { scan: retainedScan } : {}) }
        : state.draft;
      const savedDraft = state.draft;
      state.scan = hasScanEvidence(retainedScan) ? retainedScan : normalizeScanFromDraft(state.draft);
      await refreshTemplateList();
      setDraftStatus("草稿已保存", "confirmed");
      setText("draftSaveStatusText", "草稿已保存；发布核验状态见下方。");
      renderAll();
      return { saved: true, failure: "", draft: savedDraft };
    } catch (error) {
      setDraftStatus("保存失败", "blocked");
      setText("draftSaveStatusText", "草稿保存失败，请按错误提示修正后重试。");
      showScanFailure(friendlyError(error, "草稿保存失败，请检查当前配置。"));
      return { saved: false, failure: "request" };
    } finally {
      state.isSavingDraft = false;
      updateDraftButtons();
    }
  }

  async function confirmCurrentStage() {
    if (state.isSavingDraft) return;
    const stageBeforeSave = state.stage;
    const previousChecks = collectChecks();
    markCurrentStageConfirmed();
    updateCheckRail(collectChecks());
    const result = await saveDraft();
    if (result && result.saved && stageBeforeSave === "structure" && typeof globalThis.setWorkbenchStage === "function") {
      globalThis.setWorkbenchStage("rules");
      return;
    }
    if ((!result || !result.saved) && (!result || result.failure !== "validation")) updateCheckRail(previousChecks);
  }

  function currentStageCheckKeys() {
    return {
      structure: ["output", "fields", "options"],
      rules: ["slots", "content", "dimensions", "colors"],
      preview: []
    }[state.stage] || [];
  }

  function markCurrentStageConfirmed() {
    currentStageCheckKeys().forEach((key) => {
      const item = document.querySelector('#v2CheckRail .check-item[data-check-key="' + key + '"]');
      if (!item) return;
      item.dataset.status = "confirmed";
      item.dataset.reason = "本页已人工核验";
    });
  }


  async function validateCurrentConfig(showErrors) {
    const config = buildControlledConfig();
    const validationRequestId = ++state.validationRequestId;
    state.validation = null;
    state.lastValidatedConfig = config;
    if (typeof clearValidationFeedback === "function") clearValidationFeedback("正在检查当前配置。");
    try {
      const validation = await validateConfig(config);
      if (validationRequestId !== state.validationRequestId) return null;
      state.validation = validation;
      updateCheckRail(validation.checks || config.checks);
      updateBlockers(validation);
      return validation;
    } catch (error) {
      if (validationRequestId !== state.validationRequestId) return null;
      if (showErrors) showScanFailure(friendlyError(error, "配置校验失败，请检查字段和选项。"));
      updateCheckRail(config.checks);
      updateBlockers(null);
      return null;
    }
  }


  async function validateConfig(config) {
    const payload = await postJson(`${API_ROOT}/${encodeURIComponent(config.template.template_id)}/validate`, { config }, "配置校验失败，请检查字段和选项。");
    const validation = objectOf(payload.validation || payload);
    if (payload.service_contract) validation.service_contract = objectOf(payload.service_contract);
    return validation;
  }


  async function ensureDraftExists() {
    const basics = formBasics();
    if (!basics.template_id || !basics.name) throw new Error("请先填写模板 ID 和模板名称。");
    const known = state.templates.some((item) => templateIdOf(item) === basics.template_id);
    if (known && (state.draft || state.selectedTemplateId === basics.template_id)) return;
    try {
      const payload = await postJson(API_ROOT, basics, "草稿创建失败，请检查模板信息。");
      state.selectedTemplateId = basics.template_id;
      if (payload && payload.state) state.templates = upsertStateSummary(state.templates, payload.state);
    } catch (error) {
      if (!known) throw error;
    }
  }


  async function safeRefreshDraft(id) {
    if (!id) return;
    try {
      const viewAction = state.isPublishedView && !state.publishedDraftCompatibility ? "published" : "draft";
      const fallback = state.isPublishedView ? "共享配置读取失败，请稍后刷新。" : "草稿读取失败，请稍后刷新。";
      const payload = await getJson(`${API_ROOT}/${encodeURIComponent(id)}/${viewAction}`, fallback);
      const responseDraft = objectOf(payload[viewAction]);
      if (!isCurrentTemplateResponse(responseDraft, id)) return;
      const previousScan = objectOf(state.scan);
      const responseScan = normalizeScanFromDraft(responseDraft);
      const retainedScan = hasScanEvidence(responseScan)
        ? responseScan
        : canRetainPreviousScan(previousScan, id) ? previousScan : {};
      state.selectedTemplateId = id;
      state.draft = payload[viewAction]
        ? { ...responseDraft, ...(hasScanEvidence(retainedScan) ? { scan: retainedScan } : {}) }
        : state.draft;
      state.scan = hasScanEvidence(retainedScan) ? retainedScan : normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, id);
      renderAll();
    } catch (_) {
      renderScanSummary("草稿状态未刷新，请稍后重试。");
    }
  }


  Object.assign(globalThis, {
    loadTemplates,
    refreshTemplateList,
    refreshSharedTemplates,
    clearDraftView,
    renderAll,
    saveDraft,
    confirmCurrentStage,
    markCurrentStageConfirmed,
    validateCurrentConfig,
    validateConfig,
    ensureDraftExists,
    safeRefreshDraft
  });
})();
