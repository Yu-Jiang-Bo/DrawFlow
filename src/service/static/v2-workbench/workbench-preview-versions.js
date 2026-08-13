(function () {
  "use strict";
  const { API_ROOT, state } = globalThis.DrawFlowV2WorkbenchContext;

  async function loadTemplateVersions(templateId) {
    const id = cleanText(templateId || state.selectedTemplateId);
    if (!id) return [];
    const requestId = ++state.versionRequestId;
    state.versionsStatus = "loading";
    state.versionsError = "";
    state.versionsTemplateId = id;
    renderVersionSummary();
    try {
      const payload = await getJson(`${API_ROOT}/${encodeURIComponent(id)}/versions`, "模板版本读取失败，请稍后重试。");
      if (!versionRequestIsCurrent(requestId, id)) return null;
      state.versions = Array.isArray(payload.versions) ? payload.versions : (Array.isArray(payload) ? payload : []);
      if (payload.publication) state.publication = objectOf(payload.publication);
      state.versionsStatus = "success";
      renderVersionSummary();
      return state.versions;
    } catch (error) {
      if (!versionRequestIsCurrent(requestId, id)) return null;
      state.versions = [];
      state.versionsStatus = "error";
      state.versionsError = friendlyError(error, "版本信息读取失败，请重试。");
      renderVersionSummary();
      throw new Error(state.versionsError);
    }
  }

  function versionRequestIsCurrent(requestId, templateId) {
    const currentTemplateId = cleanText(state.selectedTemplateId || formBasics().template_id);
    return requestId === state.versionRequestId
      && cleanText(templateId) === cleanText(state.versionsTemplateId)
      && cleanText(templateId) === currentTemplateId;
  }

  function renderVersionSummary() {
    const manifest = objectOf(state.draft && state.draft.manifest);
    const revision = cleanText(manifest.draft_revision || manifest.version);
    setText("draftVersionSummary", revision ? `${revision} · 待发布` : "尚未保存草稿");
    const trial = objectOf(state.trial);
    setText("draftTrialSummary", trialSucceeded() ? trialTimeText(trial.rendered_at) : "未试渲染");
    if (state.versionsStatus === "loading") {
      setText("currentVersionSummary", "正在读取版本信息…");
      setText("currentVersionMeta", "请稍候");
      setText("rollbackVersionSummary", "正在读取回滚版本…");
      setText("rollbackVersionMeta", "请稍候");
      renderPreviewStatus(trial);
      return;
    }
    if (state.versionsStatus === "error") {
      setText("currentVersionSummary", "版本信息读取失败");
      setText("currentVersionMeta", state.versionsError || "请重试读取版本信息。");
      setText("rollbackVersionSummary", "暂时无法确认回滚版本");
      setText("rollbackVersionMeta", "请重试后再发布。");
      renderPreviewStatus(trial);
      return;
    }
    const publication = objectOf(state.publication);
    const versions = Array.isArray(state.versions) ? state.versions.map(objectOf) : [];
    const currentVersion = cleanText(publication.current_version);
    const rollbackVersion = cleanText(publication.previous_version || publication.rollback_version);
    const currentRecord = versionRecord(versions, currentVersion, true);
    const rollbackRecord = versionRecord(versions, rollbackVersion, false, currentRecord);
    setText("currentVersionSummary", currentVersion || versionName(currentRecord) || "尚未发布正式版本");
    setText("currentVersionMeta", versionMeta(currentRecord, currentVersion ? "正在生产使用" : ""));
    setText("rollbackVersionSummary", rollbackVersion || versionName(rollbackRecord) || "暂无可回滚版本");
    setText("rollbackVersionMeta", versionMeta(rollbackRecord, rollbackRecord ? "可用于回滚" : ""));
    renderPreviewStatus(trial);
  }

  function renderPreviewStatus(trial) {
    if (state.versionsStatus === "loading") setStatusPill("versionPublishStatus", "正在读取版本", "warn");
    else if (state.versionsStatus === "error") setStatusPill("versionPublishStatus", "版本读取失败，可重试", "blocked");
    else if (state.isPublishing) setStatusPill("versionPublishStatus", "正在发布", "warn");
    else if (trialSucceeded() && state.validation && state.validation.can_publish === true) setStatusPill("versionPublishStatus", "满足发布条件", "success");
    else if (trialSucceeded()) setStatusPill("versionPublishStatus", "发布核验未完成", "blocked");
    else setStatusPill("versionPublishStatus", "等待真实试渲染", "warn");
    setText("previewRuntimeBadge", trialSucceeded() ? "真实试渲染已完成" : (state.isTrialRendering ? "正在试渲染" : "未试渲染"));
    setText("previewTrialStatus", trialSucceeded() ? trialTimeText(trial.rendered_at) : (state.previewMessage || "填写样例订单数据后开始试渲染。"));
  }

  function versionRecord(versions, version, current, excluded) {
    if (version) return versions.find((item) => versionName(item) === version) || {};
    return versions.find((item) => item !== excluded && (current ? item.is_current === true : item.can_rollback === true)) || {};
  }

  function versionName(record) {
    const item = objectOf(record);
    return cleanText(item.version || item.version_id || item.name);
  }

  function versionMeta(record, fallback) {
    const item = objectOf(record);
    return [formatBusinessTime(item.published_at || item.created_at), fallback].filter(Boolean).join(" · ");
  }

  function trialTimeText(value) {
    const time = formatBusinessTime(value);
    return time ? `试渲染完成于 ${time}` : "真实试渲染已完成";
  }

  function formatBusinessTime(value) {
    const text = cleanText(value);
    if (!text) return "";
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function setStatusPill(id, text, status) {
    const node = $(id);
    if (!node) return;
    node.className = `stage-status-pill ${status || ""}`.trim();
    node.textContent = text;
  }

  Object.assign(globalThis, { loadTemplateVersions, versionRequestIsCurrent, renderVersionSummary });
})();
