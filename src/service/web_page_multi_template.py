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
      state.multiTemplateInputRevision += 1;
      state.multiTemplateParentJobId = "";
      state.multiTemplatePreflight = null;
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
        state.multiTemplateParentJobId = result.status === "ready" ? String(result.job_id || "") : "";
        state.multiTemplatePreflight = result.status === "ready" ? result : null;
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
'''.strip()


__all__ = ["MULTI_TEMPLATE_RENDER_SCRIPT"]
