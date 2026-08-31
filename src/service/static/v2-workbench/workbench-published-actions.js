(function () {
  "use strict";
  const { API_ROOT, state } = globalThis.DrawFlowV2WorkbenchContext;

  async function createDraftFromPublished() {
    const templateId = cleanText(state.selectedTemplateId);
    if (!state.isPublishedView || !templateId) {
      showScanFailure("请先选择一个已发布模板。");
      return false;
    }
    if (state.publishedDraftCompatibility) {
      showScanFailure("中央服务版本较旧，兼容视图只允许查看；请联系管理员升级中央服务后再创建草稿。");
      return false;
    }
    setDraftStatus("正在创建草稿", "pending");
    try {
      const payload = await postJson(
        `${API_ROOT}/${encodeURIComponent(templateId)}/draft-from-published`,
        {},
        "创建草稿失败，请确认该模板的正式版本仍可用。"
      );
      const draft = objectOf(payload.draft);
      if (!isCurrentTemplateResponse(draft, templateId)) return false;
      state.validation = null;
      state.lastValidatedConfig = null;
      state.validationRequestId += 1;
      state.isPublishedView = false;
      state.publishedDraftCompatibility = false;
      state.draft = draft;
      state.scan = normalizeScanFromDraft(draft);
      fillDraftFields(draft, templateId);
      renderAll();
      return true;
    } catch (error) {
      setDraftStatus("创建草稿失败", "blocked");
      showScanFailure(friendlyError(error, "创建草稿失败，请确认该模板的正式版本仍可用。"));
      return false;
    }
  }

  async function selectTemplate(templateId) {
    const draftLoadRequestId = ++state.draftLoadRequestId;
    state.validation = null;
    state.lastValidatedConfig = null;
    state.validationRequestId += 1;
    state.draft = null;
    state.isPublishedView = false;
    state.publishedDraftCompatibility = false;
    state.scan = {};
    if (typeof resetPreviewState === "function") resetPreviewState();
    if (typeof clearValidationFeedback === "function") clearValidationFeedback("正在读取模板配置。");
    state.selectedTemplateId = templateId || "";
    setDisabled("templateId", Boolean(state.selectedTemplateId));
    fillDraftFields(null, templateId);
    if (typeof updateCheckRail === "function" && typeof defaultChecks === "function") updateCheckRail(defaultChecks());
    if (!templateId) return false;
    renderTemplateList();
    const template = state.templates.find((item) => templateIdOf(item) === templateId);
    const publication = objectOf(template && template.publication);
    const sharedVersion = publication.status === "active" ? cleanText(publication.current_version) : "";
    let viewAction = sharedVersion ? "published" : "draft";
    let publishedDraftCompatibility = false;
    const viewLabel = sharedVersion ? "已发布配置" : "草稿";
    setDraftStatus(`读取${viewLabel}中`, "pending");
    try {
      let payload;
      try {
        payload = await getJson(
          `${API_ROOT}/${encodeURIComponent(templateId)}/${viewAction}`,
          sharedVersion ? "共享配置读取失败，请确认模板已发布后重试。" : "草稿读取失败，请确认模板是否已创建。"
        );
      } catch (error) {
        if (!sharedVersion || !publishedRouteUnavailable(error)) throw error;
        viewAction = "draft";
        publishedDraftCompatibility = true;
        payload = await getJson(
          `${API_ROOT}/${encodeURIComponent(templateId)}/draft`,
          "中央服务版本较旧，无法读取兼容草稿。请联系管理员升级中央服务后重试。"
        );
      }
      if (draftLoadRequestId !== state.draftLoadRequestId || state.selectedTemplateId !== templateId) return false;
      state.isPublishedView = Boolean(sharedVersion);
      state.publishedDraftCompatibility = publishedDraftCompatibility;
      state.draft = payload[viewAction] || null;
      state.scan = normalizeScanFromDraft(state.draft);
      fillDraftFields(state.draft, templateId);
      renderAll();
      return true;
    } catch (error) {
      if (draftLoadRequestId !== state.draftLoadRequestId || state.selectedTemplateId !== templateId) return false;
      state.draft = null;
      state.scan = {};
      fillDraftFields(null, templateId);
      renderAll();
      showScanFailure(friendlyError(error, sharedVersion ? "共享配置读取失败，请确认模板已发布后重试。" : "草稿读取失败，请确认模板是否已创建。"));
      return false;
    }
  }

  function publishedRouteUnavailable(error) {
    const message = String(error && error.message || error || "");
    return /v2_route_not_found|V2\s*模板接口不存在/i.test(message);
  }

  Object.assign(globalThis, { createDraftFromPublished, selectTemplate });
})();
