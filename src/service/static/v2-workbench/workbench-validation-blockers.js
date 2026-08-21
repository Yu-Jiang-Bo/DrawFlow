(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, CHECK_KEYS, CHECK_LABELS, STATUS_LABELS } = ctx;

  function clearValidationFeedback(message) {
    clearValidationHighlights();
    const target = $("blockerList");
    if (target) target.replaceChildren();
    setDisabled("publishVersionBtn", true);
    setText("publishBlockerText", message || "请先完成草稿配置与人工核验。");
  }

  function blockerEntries(validation, checks) {
    if (requiresWorkbenchServiceRefresh(validation)) {
      return [{
        text: "服务状态：本地服务尚未加载当前模板能力，请重启 DrawFlow 并刷新页面后重试。",
        issue: null,
        target: null
      }];
    }
    const entries = [];
    const representedChecks = new Set();
    const seen = new Set();
    publicationValidationIssues(validation).forEach((issue) => {
      const check = validationCheckForIssue(issue);
      const reason = validationDisplayReason(issue, checks[check].displayReason || checks[check].reason || "请检查标红的设置。");
      const issueTarget = validationTargetForIssue(issue);
      const location = validationLocationLabel(issueTarget);
      const key = `${check}:${validationTargetKey(issueTarget) || "unlocated"}:${reason}`;
      representedChecks.add(check);
      if (seen.has(key)) return;
      seen.add(key);
      entries.push({ text: `${CHECK_LABELS[check]}${location ? ` · ${location}` : ""}：${reason}`, issue, target: issueTarget });
    });
    CHECK_KEYS.forEach((key) => {
      if (checks[key].status === "confirmed" || representedChecks.has(key)) return;
      const text = `${CHECK_LABELS[key]}：${checks[key].displayReason || checks[key].reason || STATUS_LABELS[checks[key].status]}`;
      if (!seen.has(text)) {
        seen.add(text);
        entries.push({ text, issue: null, target: null });
      }
    });
    return entries;
  }

  function requiresWorkbenchServiceRefresh(validation) {
    const capabilities = Array.isArray(objectOf(objectOf(validation).service_contract).capabilities)
      ? objectOf(objectOf(validation).service_contract).capabilities.map(cleanText)
      : [];
    if (capabilities.includes("mixed_slot_processing")) return false;
    return publicationValidationIssues(validation).some((issue) => {
      if (cleanText(issue.code) !== "contract_invalid") return false;
      const match = cleanText(issue.path).match(/^\$\.outputs\[(\d+)\]\.(style|design|font)\.options\[(\d+)\]\.content_preset$/);
      if (!match) return false;
      return cleanText(validationOptionConfig(Number(match[1]), match[2], Number(match[3])).content_preset) === "mixed_slots";
    });
  }

  function validationTargetKey(target) {
    const item = objectOf(target);
    if (!item.kind) return "";
    return [item.stage, item.kind, item.controlId, item.areaId, item.checkKey, item.fieldKey, item.outputIndex, item.outputKey, item.group, item.optionIndex, item.optionKey, item.slotIndex, item.index, item.field, item.scanItemKind, item.scanItemIndex]
      .map((value) => cleanText(value))
      .join(":");
  }

  function validationLocationLabel(target) {
    const item = objectOf(target);
    if (item.kind === "rescan") {
      const option = cleanText(item.optionKey);
      if (option && item.scanItemKind === "slot" && Number(item.scanItemIndex) >= 0) return `${option} 的第 ${Number(item.scanItemIndex) + 1} 个槽位`;
      if (option && item.scanItemKind === "asset" && Number(item.scanItemIndex) >= 0) return `${option} 的第 ${Number(item.scanItemIndex) + 1} 个素材`;
      if (option) return option;
      if (cleanText(item.group)) return `${groupValidationLabel(item.group)}扫描结果`;
      return "模板扫描";
    }
    if (item.kind === "check") return CHECK_LABELS[item.checkKey] || "人工核验";
    if (item.kind === "action") return item.controlId === "rerunTrialRenderBtn" ? "样例试渲染" : "样例数据";
    if (item.kind === "basic") return ({ templateId: "模板编号", templateName: "模板名称", shopName: "店铺名称" })[item.controlId] || "模板信息";
    if (item.kind === "binding") return item.fieldKey ? `字段 ${item.fieldKey}` : "字段绑定";
    if (item.kind === "mapping") return `第 ${Number(item.index) + 1} 条选项映射`;
    if (item.kind === "mapping-option") return `${cleanText(item.optionKey) || "当前选项"} 的订单原值`;
    if (item.kind === "output") return cleanText(validationOutputConfig(item.index).display_name) || `第 ${Number(item.index) + 1} 个效果图`;
    if (["style", "slot", "option", "option-preset"].includes(item.kind)) {
      const option = cleanText(item.optionKey) || "当前选项";
      return item.kind === "slot" ? `${option} 的第 ${Number(item.slotIndex) + 1} 个槽位` : option;
    }
    const areas = {
      optionMappingRows: "选项映射",
      colorRuleRows: "颜色规则",
      previewValidationRows: "样例预览",
      outputConfigRows: "效果图设置"
    };
    return areas[item.areaId] || "";
  }

  function groupValidationLabel(group) {
    return ({ style: "Style", design: "Design", font: "字体" })[cleanText(group)] || "选项";
  }

  function updateBlockers(validation) {
    const target = $("blockerList");
    const checks = normalizeChecks(validation && validation.checks ? validation.checks : configChecks());
    if (requiresWorkbenchServiceRefresh(validation)) clearValidationHighlights();
    else syncValidationHighlights(validation);
    const entries = blockerEntries(validation, checks);
    const blockers = entries.map((entry) => entry.text);
    if (target) {
      target.replaceChildren();
      (entries.length ? entries : [{ text: "已完成核验，可进入下一步。", issue: null, target: null }]).forEach((entry) => {
        const item = document.createElement("li");
        const text = document.createElement("span");
        text.textContent = entry.text;
        item.appendChild(text);
        const actionLabel = entry.issue ? validationActionLabel(entry.target) : "";
        if (actionLabel) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "blocker-jump";
          button.textContent = actionLabel;
          button.addEventListener("click", () => focusValidationIssue(entry.issue));
          item.appendChild(button);
        }
        target.appendChild(item);
      });
    }
    const ready = validation && validation.can_publish === true && !entries.length;
    const busy = Boolean(state.isTrialRendering || state.isPublicationChecking || state.isPublishing);
    const hasRealTrial = typeof trialSucceeded === "function" && trialSucceeded();
    const versionsReady = state.versionsStatus !== "loading" && state.versionsStatus !== "error";
    setDisabled("publishVersionBtn", !ready || !hasRealTrial || !versionsReady || busy);
    setDisabled("trialRenderBtn", !state.draft || busy);
    setText("publishBlockerText", ready ? "发布核验已完成，可以发布新版本。" : blockerSummary(blockers));
  }

  function blockerSummary(blockers) {
    const items = unique(Array.isArray(blockers) ? blockers : []);
    if (!items.length) return "请先完成草稿配置与人工核验。";
    const labels = items.map((item) => cleanText(item).split("：")[0]).filter(Boolean);
    const visible = labels.slice(0, 4).join("、");
    const suffix = labels.length > 4 ? "等" : "";
    return `还有 ${labels.length} 项发布核验未完成：${visible}${suffix}。`;
  }

  function setDraftStatus(text, status) {
    const el = $("draftStatusBadge");
    if (!el) return;
    el.textContent = text;
    el.dataset.status = status || "pending";
  }

  function showTransientStatus(text) {
    setText("publishBlockerText", text);
  }

  Object.assign(globalThis, {
    clearValidationFeedback,
    blockerEntries,
    requiresWorkbenchServiceRefresh,
    validationTargetKey,
    validationLocationLabel,
    updateBlockers,
    setDraftStatus,
    showTransientStatus
  });
})();
