(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { API_ROOT, state } = ctx;

  async function loadTemplates(preferredId) {
    const payload = await getJson(API_ROOT, "模板列表加载失败，请稍后重试。");
    state.templates = Array.isArray(payload.templates) ? payload.templates : [];
    renderTemplateList();
    const id = preferredId || state.selectedTemplateId;
    if (id && state.templates.some((item) => templateIdOf(item) === id)) {
      await selectTemplate(id);
    } else if (!state.templates.length) {
      clearDraftView();
    }
  }


  async function selectTemplate(templateId) {
    if (!templateId) return;
    state.selectedTemplateId = templateId;
    renderTemplateList();
    setDraftStatus("读取草稿中", "pending");
    try {
      const payload = await getJson(`${API_ROOT}/${encodeURIComponent(templateId)}/draft`, "草稿读取失败，请确认模板是否已创建。");
      state.draft = payload.draft || null;
      state.scan = normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, templateId);
      renderAll();
    } catch (error) {
      state.draft = null;
      state.scan = {};
      fillDraftFields(null, templateId);
      renderAll();
      showScanFailure(friendlyError(error, "草稿读取失败，请确认模板是否已创建。"));
    }
  }


  function clearDraftView() {
    state.selectedTemplateId = "";
    state.draft = null;
    state.scan = {};
    fillDraftFields(null, "");
    renderAll();
  }


  function renderAll() {
    renderScanSummary();
    renderStructureTree();
    renderTables();
    validateCurrentConfig(false).catch(() => updateCheckRail(configChecks()));
    updateDraftButtons();
  }


  async function saveDraft() {
    const basics = formBasics();
    if (!basics.template_id || !basics.name) {
      showScanFailure("请先填写模板 ID 和模板名称。");
      return;
    }
    setDraftStatus("正在保存", "pending");
    try {
      await ensureDraftExists();
      const config = buildControlledConfig();
      const validation = await validateConfig(config);
      state.validation = validation;
      updateCheckRail(validation.checks || config.checks);
      if (validation.can_save === false) {
        updateBlockers(validation);
        setDraftStatus("配置未通过校验", "blocked");
        return;
      }
      const payload = await postJson(`${API_ROOT}/${encodeURIComponent(basics.template_id)}/draft`, {
        name: basics.name,
        shop_name: basics.shop_name,
        config
      }, "草稿保存失败，请检查当前配置。");
      state.draft = payload.draft || state.draft;
      state.scan = normalizeScanFromDraft(state.draft);
      await loadTemplates(basics.template_id);
      setDraftStatus("草稿已保存", "confirmed");
      renderAll();
    } catch (error) {
      setDraftStatus("保存失败", "blocked");
      showScanFailure(friendlyError(error, "草稿保存失败，请检查当前配置。"));
    }
  }


  async function validateCurrentConfig(showErrors) {
    const config = buildControlledConfig();
    try {
      const validation = await validateConfig(config);
      state.validation = validation;
      updateCheckRail(validation.checks || config.checks);
      updateBlockers(validation);
      return validation;
    } catch (error) {
      if (showErrors) showScanFailure(friendlyError(error, "配置校验失败，请检查字段和选项。"));
      updateCheckRail(config.checks);
      updateBlockers(null);
      return null;
    }
  }


  async function validateConfig(config) {
    const payload = await postJson(`${API_ROOT}/${encodeURIComponent(config.template.template_id)}/validate`, { config }, "配置校验失败，请检查字段和选项。");
    return payload.validation || payload;
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
      const payload = await getJson(`${API_ROOT}/${encodeURIComponent(id)}/draft`, "草稿读取失败，请稍后刷新。");
      state.selectedTemplateId = id;
      state.draft = payload.draft || state.draft;
      state.scan = normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, id);
      renderAll();
    } catch (_) {
      renderScanSummary("文件已保存，等待扫描结果。");
    }
  }



  Object.assign(globalThis, {
    loadTemplates,
    selectTemplate,
    clearDraftView,
    renderAll,
    saveDraft,
    validateCurrentConfig,
    validateConfig,
    ensureDraftExists,
    safeRefreshDraft
  });
})();
