"""Embedded DOM view for the gated multi-template trial flow."""

MULTI_TEMPLATE_RENDER_VIEW_SCRIPT = r'''
    function renderMultiTemplateResult(result) {
      const panel = document.getElementById("multiTemplateResultPanel");
      if (!result) {
        panel.hidden = true;
        return;
      }
      panel.hidden = false;
      const counts = result.group_counts || {};
      const summary = [
        `订单 ${Number(result.order_count || 0)} 条`,
        `模板 ${Number(result.template_count || 0)} 个`,
        `成功 ${Number(counts.succeeded || 0)} 个`,
        `失败 ${Number(counts.failed || 0)} 个`,
        `未开始 ${Number(counts.unstarted || 0)} 个`,
        `中断 ${Number(counts.interrupted || 0)} 个`,
        `运行中 ${Number(counts.running || 0)} 个`
      ];
      const resumeNotice = result.status === "interrupted" && Number(counts.succeeded || 0) > 0
        ? "；已成功模板不会重复渲染"
        : "";
      document.getElementById("multiTemplateResultSummary").textContent = `${multiTemplateStatusText(result.status)}：${summary.join("；")}${resumeNotice}`;
      renderMultiTemplateIssues(result);
      renderMultiTemplateGroups(result.template_summaries || []);
      renderMultiTemplateActions(result);
    }

    function renderMultiTemplateIssues(result) {
      const target = document.getElementById("multiTemplateIssueList");
      target.replaceChildren();
      const issues = result.issues || [];
      const incompleteGroups = (result.template_summaries || []).filter(group => group.status !== "succeeded");
      target.className = issues.length || incompleteGroups.length ? "message error" : "message";
      issues.forEach(issue => {
        const row = document.createElement("p");
        const location = [issue.template_id, issue.excel_row ? `Excel 第 ${issue.excel_row} 行` : "", issue.order_no].filter(Boolean).join(" · ");
        row.textContent = [location, issue.message, issue.suggestion].filter(Boolean).join("：");
        target.appendChild(row);
      });
      if (incompleteGroups.length) {
        const missing = document.createElement("p");
        const details = incompleteGroups.map(group => {
          const rows = (group.excel_rows || []).filter(Number.isFinite).join("、");
          return `${group.template_id || "未识别模板"}${rows ? `（Excel 第 ${rows} 行）` : ""}`;
        });
        missing.textContent = `完整 ZIP 尚未生成。以下模板订单尚未交付：${details.join("；")}。`;
        target.appendChild(missing);
      }
    }

    function renderMultiTemplateGroups(groups) {
      const target = document.getElementById("multiTemplateGroupList");
      target.replaceChildren();
      groups.forEach(group => {
        const row = document.createElement("div");
        row.className = "template-row";
        const title = document.createElement("strong");
        title.textContent = group.template_id || "未识别模板";
        const detail = document.createElement("span");
        const representative = group.canary_representative || {};
        const canary = representative.excel_row ? `代表订单 Excel 第 ${representative.excel_row} 行${representative.order_no ? `（${representative.order_no}）` : ""}` : "代表订单待选择";
        const rows = (group.excel_rows || []).filter(Number.isFinite).join("、");
        detail.textContent = [
          `${Number(group.order_count || 0)} 条订单`,
          rows ? `Excel 第 ${rows} 行` : "",
          group.template_version ? `版本 ${group.template_version}` : "版本待确认",
          `试渲染：${multiTemplateStatusText(group.canary_status)}`,
          `正式：${multiTemplateStatusText(group.status)}`,
          canary,
          group.error ? `原因：${group.error}` : ""
        ].filter(Boolean).join(" · ");
        row.append(title, detail);
        target.appendChild(row);
      });
    }

    function renderMultiTemplateActions(result) {
      const actions = result.actions || {};
      const outputs = result.outputs || {};
      document.getElementById("multiTemplateExecuteBtn").hidden = !actions.execute;
      document.getElementById("multiTemplateRetryBtn").hidden = !actions.can_retry_failed;
      document.getElementById("multiTemplateResumeBtn").hidden = !actions.can_resume;
      document.getElementById("multiTemplatePrimaryDownloadBtn").hidden = !outputs.primary_output_available;
    }

    function multiTemplateStatusText(status) {
      return {
        preflight_failed: "预检未通过",
        ready: "预检通过，等待执行",
        canary_running: "代表订单试渲染中",
        running: "正式渲染中",
        completed: "全部完成",
        completed_with_errors: "部分完成",
        failed: "执行失败",
        interrupted: "系统中断",
        pending: "待开始",
        canary_failed: "试渲染失败",
        succeeded: "已完成"
      }[String(status || "")] || "处理中";
    }
'''.strip()


__all__ = ["MULTI_TEMPLATE_RENDER_VIEW_SCRIPT"]
