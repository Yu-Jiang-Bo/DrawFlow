(function () {
  "use strict";
  const ctx = globalThis.DrawFlowV2WorkbenchContext;
  const { state, CHECK_KEYS, CHECK_LABELS, STATUS_LABELS, STATUS_CLASS } = ctx;

  function updateCheckRail(checks) {
    const normalized = normalizeChecks(checks);
    CHECK_KEYS.forEach((key) => {
      const item = document.querySelector(`#v2CheckRail .check-item[data-check-key="${key}"]`);
      const check = normalized[key] || { status: "pending", reason: "" };
      if (!item) return;
      const hasExplicitReason = checkHasExplicitReason(checks, key);
      const preservedReason = hasExplicitReason ? "" : manualReasonForCheck(item.dataset.reason || "");
      const reason = check.reason || preservedReason;
      item.dataset.status = check.status;
      item.dataset.reason = reason;
      item.classList.remove("passed", "pending", "warn", "blocked", "confirmed", "success");
      item.classList.add(STATUS_CLASS[check.status] || "pending");
      const label = item.querySelector(".check-label, span");
      const status = item.querySelector(".check-status, strong");
      if (label) label.textContent = CHECK_LABELS[key] || key;
      if (status) status.textContent = STATUS_LABELS[check.status] || "待校验";
      if (!label && !status) item.textContent = `${CHECK_LABELS[key] || key}：${STATUS_LABELS[check.status] || "待校验"}`;
      item.title = check.displayReason || reason || STATUS_LABELS[check.status] || "";
    });
  }

  function checkHasExplicitReason(checks, key) {
    const raw = objectOf(checks)[key];
    return Boolean(raw && typeof raw === "object" && !Array.isArray(raw) && Object.prototype.hasOwnProperty.call(raw, "reason"));
  }

  function normalizeChecks(checks) {
    const result = defaultChecks();
    Object.keys(objectOf(checks)).forEach((key) => {
      if (!CHECK_KEYS.includes(key)) return;
      const raw = checks[key];
      const rawObject = objectOf(raw);
      const status = typeof raw === "string" ? raw : objectOf(raw).status;
      const manualReason = typeof raw === "string" ? "" : manualReasonForCheck(rawObject.reason || "");
      const validationReasons = typeof raw === "string" ? [] : validationReasonsForCheck(rawObject);
      const displayReasons = unique([manualReason, ...validationReasons].map((item) => cleanText(item))).filter(Boolean);
      result[key] = {
        status: safeStatus(status),
        reason: manualReason,
        reasons: displayReasons,
        displayReason: compactReasons(displayReasons)
      };
    });
    return result;
  }

  function validationDisplayReason(value, fallback) {
    const issue = objectOf(value);
    const mapped = validationReasonForCode(cleanText(issue.code));
    if (mapped) return mapped;
    const raw = cleanText(issue.reason || (typeof value === "string" ? value : ""));
    const safeFallback = hasTechnicalValidationDetail(fallback) ? "" : cleanText(fallback);
    if (!raw) return safeFallback || (fallback === undefined ? "请检查标红的设置。" : "");
    if (!hasTechnicalValidationDetail(raw)) return raw;
    return safeFallback || "请检查标红的设置。";
  }

  function validationReasonForCode(code) {
    const reasons = {
      duplicate_name: "同一范围内存在重复名称，请修改标红的项目后重试。",
      duplicate_path: "同一范围内存在重复名称，请修改标红的项目后重试。",
      output_key: "同一范围内存在重复名称，请修改标红的项目后重试。",
      anchor_belongs_to_slot: "定位框与当前槽位不对应，请修正模板标注后重新扫描。",
      tail_belongs_to_slot: "尾巴样本与当前槽位不对应，请修正模板标注后重新扫描。",
      asset_slot_mismatch: "素材与当前槽位不对应，请修正模板标注后重新扫描。",
      asset_missing: "当前槽位缺少对应素材，请修正模板标注后重新扫描。",
      asset_slot_missing: "当前素材缺少对应槽位，请修正模板标注后重新扫描。",
      tail_sample_missing: "尾巴文字需要提供尾巴样本，请检查标红的槽位。",
      tail_glyph_coverage_missing: "尾巴样本需要可确认的首字或尾字覆盖证据。",
      option_preset_invalid: "素材替换仅用于素材槽位，请重新选择处理方式。",
      direct_text_slot_preset_invalid: "直接单槽替换只能使用替换文本槽位。",
      split_by_pipe_slot_preset_invalid: "按 | 顺序拆分只能使用替换文本槽位。",
      path_text_requires_scanned_slot: "路径文字保留需要包含一个已识别的路径文字槽位。"
    };
    return reasons[code] || "";
  }

  function hasTechnicalValidationDetail(value) {
    const text = cleanText(value);
    if (!text) return false;
    if (typeof containsSensitive === "function" && containsSensitive(text)) return true;
    return /(?:\$\.[A-Za-z_][\w.[\]]*|(?:^|[\s；：])Template\/|(?:图层|配置|磁盘|文件)\s*路径|\b(?:layer|json|object|file)[_-]?path\b|\b(?:JSON|J\u0053X|COM|Traceback|stack|schema|contract)\b|\b(?:tail|slot|anchor|asset)_[A-Za-z0-9_]*\b|\b(?:asset_replace|direct_text|split_by_pipe|path_text|tail_text|mixed_slots)\b|\bOutput_(?:main|Side[A-Z])\b)/i.test(text);
  }

  function validationReasonsForCheck(check) {
    const result = [];
    if (Array.isArray(check.reasons)) result.push(...check.reasons.map((reason) => validationDisplayReason(reason, "")));
    if (Array.isArray(check.issues)) {
      check.issues.forEach((issue) => {
        const reason = objectOf(issue).reason;
        if (reason) result.push(validationDisplayReason(issue, ""));
      });
    }
    return result;
  }

  function manualReasonForCheck(value) {
    let reason = cleanText(value);
    const emptySentences = ["人工核验项还没有确认", "人工核验项还没有确认。", "人工核验项被标记为阻断", "人工核验项被标记为阻断。"];
    const prefixes = ["人工核验项还没有确认：", "人工核验项还没有确认:", "人工核验项被标记为阻断：", "人工核验项被标记为阻断:"];
    let changed = true;
    while (changed) {
      if (emptySentences.includes(reason)) return "";
      changed = false;
      prefixes.forEach((prefix) => {
        if (reason.indexOf(prefix) === 0) {
          reason = cleanText(reason.slice(prefix.length));
          changed = true;
        }
      });
    }
    if (emptySentences.includes(reason)) return "";
    return looksLikeValidationReason(reason) ? "" : validationDisplayReason(reason, "");
  }

  function looksLikeValidationReason(reason) {
    if (!reason) return false;
    const markers = ["还没有绑定到真实表头", "还没有映射到订单原值", "发布前预览缺少", "缺少代表性测试数据"];
    if (markers.some((marker) => reason.includes(marker))) return true;
    const pairs = [
      ["槽位内容来源", "真实表头"],
      ["订单字段", "真实表头"],
      ["颜色扫描值", "还没有"],
      ["素材范围", "还没有"],
      ["最终边界", "还没有"],
      ["最终边界", "不允许"],
      ["同一作用域", "重复"],
      ["同一作用域", "不允许"]
    ];
    return pairs.some(([left, right]) => reason.includes(left) && reason.includes(right));
  }

  function compactReasons(reasons) {
    const items = unique((Array.isArray(reasons) ? reasons : []).map((item) => cleanText(item))).filter(Boolean);
    if (!items.length) return "";
    const visible = items.slice(0, 3);
    const suffix = items.length > visible.length ? `；另有 ${items.length - visible.length} 项` : "";
    return trimLongReason(visible.join("；") + suffix);
  }

  function trimLongReason(text) {
    const value = cleanText(text);
    return value.length > 180 ? `${value.slice(0, 177)}…` : value;
  }

  function publicationValidationIssues(validation) {
    const issues = Array.isArray(objectOf(validation).issues) ? objectOf(validation).issues : [];
    const active = issues.map((item) => objectOf(item)).filter((item) => ["pending", "blocked"].includes(safeStatus(item.status)));
    const checksWithSpecificIssues = new Set(active
      .filter((item) => !["manual_check_pending", "manual_check_blocked"].includes(cleanText(item.code)))
      .map(validationCheckForIssue));
    return active.filter((item) => (
      !["manual_check_pending", "manual_check_blocked"].includes(cleanText(item.code))
      || !checksWithSpecificIssues.has(validationCheckForIssue(item))
    ));
  }

  function validationCheckForIssue(issue) {
    const check = cleanText(objectOf(issue).check);
    return CHECK_KEYS.includes(check) ? check : "output";
  }

  function validationConfig() {
    const latest = objectOf(state.lastValidatedConfig);
    if (Array.isArray(latest.outputs)) return latest;
    return objectOf(state.draft && state.draft.config);
  }

  function validationOutputConfig(index) {
    const outputs = Array.isArray(validationConfig().outputs) ? validationConfig().outputs : [];
    return objectOf(outputs[Number(index)]);
  }

  function validationOutputKey(index) {
    const output = validationOutputConfig(index);
    const raw = cleanText(output.key || output.name);
    return raw || (Number(index) ? `Output_Side${String.fromCharCode(65 + Number(index))}` : "Output_main");
  }

  function validationOptionConfig(outputIndex, group, optionIndex) {
    const section = objectOf(validationOutputConfig(outputIndex)[group]);
    const options = Array.isArray(section.options) ? section.options : [];
    return objectOf(options[Number(optionIndex)]);
  }

  function validationOptionTarget(outputIndex, group, optionIndex) {
    const option = validationOptionConfig(outputIndex, group, optionIndex);
    const raw = cleanText(option.key || option.name || option.label);
    return {
      outputIndex: Number(outputIndex),
      outputKey: validationOutputKey(outputIndex),
      group,
      optionIndex: Number(optionIndex),
      optionKey: safeOptionKey(raw, group) || raw
    };
  }

  Object.assign(globalThis, {
    updateCheckRail,
    normalizeChecks,
    validationDisplayReason,
    validationReasonForCode,
    hasTechnicalValidationDetail,
    validationReasonsForCheck,
    manualReasonForCheck,
    looksLikeValidationReason,
    compactReasons,
    publicationValidationIssues,
    validationCheckForIssue,
    validationConfig,
    validationOutputConfig,
    validationOutputKey,
    validationOptionConfig,
    validationOptionTarget
  });
})();
