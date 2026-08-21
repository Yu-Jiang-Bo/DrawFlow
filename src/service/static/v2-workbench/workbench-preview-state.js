(function () {
  "use strict";
  const { state } = globalThis.DrawFlowV2WorkbenchContext;

  function previewSampleIdentity(row) {
    const source = objectOf(row);
    const normalized = {};
    Object.keys(source).sort().forEach((key) => {
      normalized[key] = String(source[key] == null ? "" : source[key]);
    });
    return JSON.stringify(normalized);
  }

  function beginTrialRequest(sampleRow, templateId) {
    const request = {
      id: ++state.trialRequestId,
      generation: Number(state.trialGeneration || 0),
      templateId: cleanText(templateId),
      sampleIdentity: previewSampleIdentity(sampleRow),
      savedRevision: ""
    };
    state.activeTrialRequestId = request.id;
    state.isTrialRendering = true;
    return request;
  }

  function trialRequestIsCurrent(request) {
    const item = objectOf(request);
    if (!item.id || item.id !== state.activeTrialRequestId) return false;
    if (Number(item.generation) !== Number(state.trialGeneration || 0)) return false;
    const templateId = cleanText(state.selectedTemplateId || formBasics().template_id);
    if (!templateId || templateId !== cleanText(item.templateId)) return false;
    if (previewSampleIdentity(state.previewSampleValues) !== cleanText(item.sampleIdentity)) return false;
    if (item.savedRevision && currentDraftRevision(state.draft) !== cleanText(item.savedRevision)) return false;
    return true;
  }

  function finishTrialRequest(request) {
    if (objectOf(request).id !== state.activeTrialRequestId) return false;
    state.activeTrialRequestId = 0;
    state.isTrialRendering = false;
    return true;
  }

  function invalidateTrialResult(message) {
    state.trialGeneration = Number(state.trialGeneration || 0) + 1;
    const wasRunning = Boolean(state.isTrialRendering);
    state.activeTrialRequestId = 0;
    state.isTrialRendering = false;
    const hadVisibleProof = Boolean(state.trial || state.previewMessage);
    state.trial = null;
    state.previewOutputIndex = 0;
    if (!hadVisibleProof && !wasRunning) return;
    state.previewMessage = message || "配置已修改，请重新试渲染。";
    if (state.validation) {
      const checks = { ...objectOf(state.validation.checks), preview: { status: "pending", reason: "请重新完成真实样例试渲染。" } };
      state.validation = { ...state.validation, can_publish: false, checks };
    }
    renderPreviewOutputs();
    renderPreviewValidationRows();
    renderVersionSummary();
    updatePreviewActionButtons();
    updateBlockers(state.validation);
  }

  function resetPreviewState() {
    state.trialGeneration = Number(state.trialGeneration || 0) + 1;
    state.activeTrialRequestId = 0;
    state.isTrialRendering = false;
    state.trial = null;
    state.publication = null;
    state.versions = [];
    state.versionRequestId = Number(state.versionRequestId || 0) + 1;
    state.versionsStatus = "idle";
    state.versionsError = "";
    state.versionsTemplateId = "";
    state.previewOutputIndex = 0;
    state.previewSampleValues = {};
    state.previewMessage = "";
  }

  Object.assign(globalThis, {
    previewSampleIdentity,
    beginTrialRequest,
    trialRequestIsCurrent,
    finishTrialRequest,
    invalidateTrialResult,
    resetPreviewState
  });
})();
