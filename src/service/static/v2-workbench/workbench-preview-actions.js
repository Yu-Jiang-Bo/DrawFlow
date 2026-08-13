(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { API_ROOT, state } = ctx;

  function currentDraftRevision(draft) {
    const manifest = objectOf(draft && draft.manifest);
    return cleanText(manifest.draft_revision || manifest.version);
  }

  function canonicalPreviewConfig() {
    const config = typeof buildControlledConfig === "function"
      ? buildControlledConfig()
      : objectOf(state.draft && state.draft.config);
    const basics = formBasics();
    return {
      ...config,
      template: {
        ...objectOf(config.template),
        template_id: basics.template_id,
        name: basics.name,
        shop_name: basics.shop_name
      },
      checks: collectChecks()
    };
  }

  function applyWorkbenchResponse(payload) {
    const response = objectOf(payload);
    if (response.draft) {
      state.draft = response.draft;
      state.scan = normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, state.selectedTemplateId);
    }
    if (response.validation) {
      state.validationRequestId += 1;
      state.validation = objectOf(response.validation);
    }
    if (response.publication) state.publication = objectOf(response.publication);
    if (Array.isArray(response.versions)) state.versions = response.versions;
    if (state.validation) {
      updateCheckRail(state.validation.checks || configChecks());
      updateBlockers(state.validation);
    }
  }

  async function trialRenderCurrentDraft() {
    if (state.isTrialRendering || state.isSavingDraft || state.isPublishing) return;
    if (!state.draft) {
      showTransientStatus("请先选择模板并保存草稿。");
      return;
    }
    const sampleRow = collectPreviewSampleRow();
    if (!Object.keys(sampleRow).length) {
      showTransientStatus("当前模板还没有可用于试渲染的订单字段，请先完成字段绑定。");
      return;
    }
    state.previewSampleValues = { ...sampleRow };
    const request = beginTrialRequest(sampleRow, state.selectedTemplateId || formBasics().template_id);
    state.previewMessage = "正在保存草稿并执行真实试渲染。";
    renderPreviewStage();
    try {
      const saved = await saveDraft({ configOverride: canonicalPreviewConfig() });
      if (!saved || !saved.saved) {
        if (trialRequestIsCurrent(request)) {
          state.previewMessage = "草稿未保存，试渲染没有开始。";
          renderPreviewStage();
        }
        return;
      }
      const savedDraft = saved.draft;
      const revision = currentDraftRevision(savedDraft);
      const templateId = cleanText(objectOf(savedDraft && savedDraft.metadata).template_id || state.selectedTemplateId || formBasics().template_id);
      if (!templateId || !revision) throw new Error("草稿还没有可用于试渲染的版本，请重新保存草稿。");
      request.savedRevision = revision;
      if (templateId !== request.templateId || !trialRequestIsCurrent(request)) return;
      state.previewSampleValues = { ...sampleRow };
      const payload = await postJson(`/local/v2/templates/${encodeURIComponent(templateId)}/trial-render`, {
        expected_draft_revision: revision,
        sample_row: sampleRow
      }, "试渲染失败，请检查样例订单数据后重试。");
      if (!trialRequestIsCurrent(request)) return;
      const responseDraft = objectOf(payload.draft);
      const responseTemplateId = cleanText(objectOf(responseDraft.metadata).template_id);
      if (responseTemplateId && responseTemplateId !== request.templateId) return;
      const responseRevision = currentDraftRevision(responseDraft);
      if (responseRevision) request.savedRevision = responseRevision;
      applyWorkbenchResponse(payload);
      if (!trialRequestIsCurrent(request)) return;
      state.trial = objectOf(payload.trial);
      state.previewOutputIndex = 0;
      state.previewMessage = trialSucceeded() ? "" : "试渲染没有成功完成，请按提示修改后重试。";
      if (!trialSucceeded()) {
        const issues = Array.isArray(payload.issues) ? payload.issues : (Array.isArray(state.trial.issues) ? state.trial.issues : []);
        if (issues.length) showPreflightFailure({ issues });
      } else {
        await checkPublicationCurrentDraft(false, request);
      }
      if (!trialRequestIsCurrent(request)) return;
      renderPreviewStage();
    } catch (error) {
      if (!trialRequestIsCurrent(request)) return;
      state.trial = null;
      state.previewMessage = friendlyError(error, "试渲染失败，请检查样例订单数据后重试。");
      showTransientStatus(state.previewMessage);
      renderPreviewStage();
    } finally {
      if (finishTrialRequest(request)) {
        updatePreviewActionButtons();
        updateBlockers(state.validation);
        renderVersionSummary();
      }
    }
  }

  function publicationContextIsCurrent(templateId, revision, generation, trialRequest) {
    if (Number(generation) !== Number(state.trialGeneration || 0)) return false;
    if (cleanText(state.selectedTemplateId || formBasics().template_id) !== cleanText(templateId)) return false;
    if (currentDraftRevision(state.draft) !== cleanText(revision)) return false;
    return !trialRequest || trialRequestIsCurrent(trialRequest);
  }

  async function checkPublicationCurrentDraft(showErrors, trialRequest) {
    if (state.isPublicationChecking) return state.validation;
    const templateId = cleanText(state.selectedTemplateId || formBasics().template_id);
    let revision = currentDraftRevision(state.draft);
    if (!templateId || !revision) return null;
    const generation = Number(state.trialGeneration || 0);
    state.isPublicationChecking = true;
    try {
      const payload = await postJson(`${API_ROOT}/${encodeURIComponent(templateId)}/publication-check`, {
        expected_draft_revision: revision
      }, "发布核验失败，请稍后重试。");
      if (!publicationContextIsCurrent(templateId, revision, generation, trialRequest)) return null;
      applyWorkbenchResponse(payload);
      if (cleanText(payload.draft_revision) && state.draft) {
        revision = cleanText(payload.draft_revision);
        if (trialRequest) trialRequest.savedRevision = revision;
        state.draft = { ...state.draft, manifest: { ...objectOf(state.draft.manifest), draft_revision: revision } };
      }
      const versions = await loadTemplateVersions(templateId);
      if (versions === null || !publicationContextIsCurrent(templateId, revision, generation, trialRequest)) return null;
      renderPreviewStage();
      return state.validation;
    } catch (error) {
      if (!publicationContextIsCurrent(templateId, revision, generation, trialRequest)) return null;
      if (showErrors) showTransientStatus(friendlyError(error, "发布核验失败，请稍后重试。"));
      return null;
    } finally {
      state.isPublicationChecking = false;
      updatePreviewActionButtons();
      updateBlockers(state.validation);
    }
  }

  async function publishCurrentDraft() {
    if (state.isPublishing || state.isTrialRendering || state.isSavingDraft) return;
    if (!trialSucceeded()) {
      showTransientStatus("请先使用当前样例完成真实试渲染。");
      return;
    }
    const generation = Number(state.trialGeneration || 0);
    const templateBeforeCheck = cleanText(state.selectedTemplateId || formBasics().template_id);
    state.isPublishing = true;
    renderVersionSummary();
    updatePreviewActionButtons();
    try {
      const validation = await checkPublicationCurrentDraft(true);
      if (!validation || validation.can_publish !== true) {
        showTransientStatus("发布核验尚未通过，请先完成页面列出的待办项。");
        return;
      }
      if (generation !== Number(state.trialGeneration || 0)
        || templateBeforeCheck !== cleanText(state.selectedTemplateId || formBasics().template_id)
        || !trialSucceeded()) {
        showTransientStatus("模板、配置或样例已修改，本次发布已取消，请重新试渲染。");
        return;
      }
      const templateId = cleanText(state.selectedTemplateId || formBasics().template_id);
      const revision = currentDraftRevision(state.draft);
      const payload = await postJson(`${API_ROOT}/${encodeURIComponent(templateId)}/publish`, {
        expected_draft_revision: revision,
        note: cleanText(valueOf("publishNotes"))
      }, "模板发布失败，请按页面提示处理后重试。");
      if (generation !== Number(state.trialGeneration || 0) || templateId !== cleanText(state.selectedTemplateId || formBasics().template_id)) return;
      applyWorkbenchResponse(payload);
      await loadTemplateVersions(templateId);
      await refreshTemplateList();
      setValue("publishNotes", "");
      showTransientStatus("模板新版本已发布。");
      renderPreviewStage();
    } catch (error) {
      showTransientStatus(friendlyError(error, "模板发布失败，请按页面提示处理后重试。"));
    } finally {
      state.isPublishing = false;
      renderVersionSummary();
      updatePreviewActionButtons();
    }
  }

  Object.assign(globalThis, {
    trialRenderCurrentDraft,
    checkPublicationCurrentDraft,
    publishCurrentDraft,
    currentDraftRevision,
    applyWorkbenchResponse
  });
})();
