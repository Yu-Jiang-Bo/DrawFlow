"""Embedded browser state machine for the gated multi-template trial flow."""

MULTI_TEMPLATE_RENDER_SCRIPT = r'''
    function multiTemplateFeatureEnabled() {
      return document.body.dataset.multiTemplateRenderEnabled === "true";
    }

    function multiTemplateModeSelected() {
      return multiTemplateFeatureEnabled() && document.getElementById("renderMode").value === "multi";
    }

    function syncMultiTemplateMode() {
      const enabled = multiTemplateFeatureEnabled();
      const modeField = document.getElementById("renderModeField");
      const mode = document.getElementById("renderMode");
      if (!enabled) mode.value = "single";
      modeField.hidden = !enabled;
      const multi = multiTemplateModeSelected();
      document.getElementById("renderTemplateField").hidden = multi;
      document.getElementById("renderTemplate").disabled = multi;
      document.getElementById("multiTemplateHint").hidden = !multi;
      document.getElementById("renderBtn").textContent = multi ? "检查订单模板" : "生成效果图";
      document.getElementById("renderTemplateBadge").textContent = multi ? "按订单自动匹配" : selectedTemplateBadgeText();
      if (!multi) invalidateMultiTemplatePreflight();
    }

    function selectedTemplateBadgeText() {
      const template = selectedTemplate();
      return template ? displayType(template.template_type) : "未选择模板";
    }

    function invalidateMultiTemplatePreflight() {
      stopMultiTemplateJobPolling();
      state.multiTemplateInputRevision += 1;
      state.multiTemplateParentJobId = "";
      state.multiTemplatePreflight = null;
      renderMultiTemplateResult(null);
    }

    async function submitMultiTemplatePreflight() {
      hideRenderError();
      const file = document.getElementById("orderFile").files[0];
      if (!file) {
        showRenderError("请先上传订单表格。");
        return;
      }
      const requestRevision = state.multiTemplateInputRevision;
      const payload = new FormData();
      payload.append("order_file", file);
      const sheetName = document.getElementById("sheetName").value.trim();
      if (sheetName) payload.append("sheet_name", sheetName);
      setTaskRunning(false);
      showProgress("multiPreflight");
      try {
        const result = await postForm("/local/render/multi/preflight", payload);
        if (requestRevision !== state.multiTemplateInputRevision || !multiTemplateModeSelected()) {
          hideRenderProgress();
          await loadJobs();
          return;
        }
        completeProgress(result.status === "ready");
        state.multiTemplateParentJobId = String(result.job_id || "");
        state.multiTemplatePreflight = result;
        renderMultiTemplateResult(result);
        if (result.status !== "ready") showRenderError(result.error || "订单模板预检未通过。");
        await loadJobs();
      } catch (error) {
        if (requestRevision !== state.multiTemplateInputRevision || !multiTemplateModeSelected()) {
          hideRenderProgress();
          await loadJobs().catch(() => {});
          return;
        }
        failProgress();
        showRenderError(error);
        await loadJobs().catch(() => {});
      } finally {
        setRenderButtonsDisabled(false);
      }
    }

    async function submitMultiTemplateAction(action) {
      const jobId = state.multiTemplateParentJobId;
      if (!jobId) {
        showRenderError("请先完成当前订单表格的模板预检。");
        return;
      }
      hideRenderError();
      setTaskRunning(false);
      setMultiTemplateActionButtonsDisabled(true);
      showProgress("multiRender");
      const requestRevision = state.multiTemplateInputRevision;
      startMultiTemplateJobPolling(jobId);
      try {
        const result = await postJson(`/local/render/multi/${encodeURIComponent(jobId)}/${action}`, {});
        stopMultiTemplateJobPolling();
        if (requestRevision !== state.multiTemplateInputRevision || !multiTemplateModeSelected()) {
          hideRenderProgress();
          await loadJobs();
          return;
        }
        state.multiTemplateParentJobId = String(result.job_id || jobId);
        state.multiTemplatePreflight = result;
        renderMultiTemplateResult(result);
        completeProgress(["completed", "completed_with_errors"].includes(result.status));
        if (!["completed", "completed_with_errors"].includes(result.status)) {
          showRenderError(result.error || "多模板批量渲染未完成。");
        }
        await loadJobs();
      } catch (error) {
        stopMultiTemplateJobPolling();
        if (requestRevision !== state.multiTemplateInputRevision || !multiTemplateModeSelected()) {
          hideRenderProgress();
          await loadJobs().catch(() => {});
          return;
        }
        failProgress();
        showRenderError(error);
        await loadJobs().catch(() => {});
      } finally {
        stopMultiTemplateJobPolling();
        setRenderButtonsDisabled(false);
        setMultiTemplateActionButtonsDisabled(false);
      }
    }

    function setMultiTemplateActionButtonsDisabled(disabled) {
      ["multiTemplateExecuteBtn", "multiTemplateRetryBtn", "multiTemplateResumeBtn"].forEach(id => {
        document.getElementById(id).disabled = disabled;
      });
    }

    function startMultiTemplateJobPolling(jobId) {
      stopMultiTemplateJobPolling();
      const generation = state.multiTemplatePollGeneration;
      refreshMultiTemplateJob(jobId, generation);
      state.multiTemplatePollTimer = setInterval(() => refreshMultiTemplateJob(jobId, generation), 1000);
    }

    function stopMultiTemplateJobPolling() {
      if (state.multiTemplatePollTimer !== null) clearInterval(state.multiTemplatePollTimer);
      state.multiTemplatePollTimer = null;
      state.multiTemplatePollGeneration += 1;
    }

    async function refreshMultiTemplateJob(jobId, generation) {
      try {
        const result = await getJson(`/api/jobs/${encodeURIComponent(jobId)}`);
        if (state.multiTemplateParentJobId !== jobId || state.multiTemplatePollGeneration !== generation) return;
        state.multiTemplatePreflight = result;
        renderMultiTemplateResult(result);
      } catch (_) {
        // A transient detail request must not replace the in-flight render result.
      }
    }

    function downloadMultiTemplateOutput() {
      const jobId = state.multiTemplateParentJobId;
      if (!jobId) return;
      window.location.href = `/local/jobs/${encodeURIComponent(jobId)}/output`;
    }
'''.strip()


__all__ = ["MULTI_TEMPLATE_RENDER_SCRIPT"]
