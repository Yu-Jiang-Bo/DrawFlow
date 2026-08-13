(function () {
  "use strict";
  const { state } = globalThis.DrawFlowV2WorkbenchContext;

  function formRows(containerId, className) {
    return Array.from(document.querySelectorAll(`#${containerId} .${className}`));
  }

  function nodeTarget(row, field) {
    if (!row) return null;
    return {
      row,
      control: field ? row.querySelector(`[data-field="${field}"]`) : null,
      expectsControl: Boolean(field)
    };
  }

  function optionIdentityMatches(node, target) {
    return Boolean(node && node.dataset.output === target.outputKey && node.dataset.group === target.group && node.dataset.option === target.optionKey);
  }

  function currentRuleSelectionMatches(target) {
    if (typeof filteredRuleOptions !== "function") return false;
    const item = filteredRuleOptions()[state.optionRules.selectedIndex];
    return Boolean(item && item.output === target.outputKey && item.group === target.group && item.key === target.optionKey);
  }

  function contentOptionGroupFor(target) {
    return formRows("contentOptionRows", "content-option-group").find((row) => optionIdentityMatches(row, target)) || null;
  }

  function locateValidationTarget(target) {
    if (!target) return null;
    if (["basic", "rescan", "action"].includes(target.kind)) return { row: null, control: $(target.controlId) };
    if (target.kind === "check") {
      return { row: null, control: document.querySelector(`#v2CheckRail .check-item[data-check-key="${target.checkKey}"]`) };
    }
    if (target.kind === "output") {
      return nodeTarget(formRows("outputConfigRows", "output-row")[target.index] || $("outputConfigRows"), target.field);
    }
    if (target.kind === "binding") {
      const row = formRows("fieldBindingRows", "field-binding-row").find((item) => rowValue(item, "binding-field") === target.fieldKey);
      return nodeTarget(row || $("fieldBindingRows"), "binding-column");
    }
    if (target.kind === "mapping") {
      return nodeTarget(formRows("optionMappingRows", "option-mapping-row")[target.index] || $("optionMappingRows"), target.field);
    }
    if (target.kind === "mapping-option") {
      const rows = formRows("optionMappingRows", "option-mapping-row");
      const row = rows.find((item) => {
        const rowGroup = cleanText(rowValue(item, "mapping-group"));
        const rowTarget = safeOptionKey(rowValue(item, "mapping-target"), rowGroup);
        const rowOutput = cleanText(rowValue(item, "mapping-output")) || "Output_main";
        return rowGroup === target.group && rowTarget === target.optionKey && rowOutput === target.outputKey;
      });
      return nodeTarget(row || $("optionMappingRows"), target.field);
    }
    if (target.kind === "style") {
      const row = formRows("styleDimensionRows", "style-dimension-row").find((item) => (
        item.dataset.output === target.outputKey && item.dataset.styleKey === target.optionKey
      ));
      return nodeTarget(row || $("styleDimensionRows"), target.field);
    }
    if (target.kind === "slot") {
      const rows = formRows("contentOptionRows", "content-slot-row").filter((row) => optionIdentityMatches(row, target));
      return nodeTarget(rows[target.slotIndex] || contentOptionGroupFor(target) || $("contentOptionRows"), target.field);
    }
    if (target.kind === "option-preset") {
      if (state.stage === "rules" && currentRuleSelectionMatches(target)) return { row: null, control: $("optionContentPreset") };
      return nodeTarget(contentOptionGroupFor(target) || $("contentOptionRows"), "");
    }
    if (target.kind === "option") {
      const button = formRows("optionRuleList", "option-rule-item").find((item) => optionIdentityMatches(item, target));
      if (button) return { row: null, control: button };
      return nodeTarget(contentOptionGroupFor(target) || $("contentOptionRows"), "");
    }
    if (target.kind === "area") return { row: $(target.areaId), control: null, actionableRow: ["optionMappingRows", "outputConfigRows"].includes(target.areaId) };
    return null;
  }

  function editableValidationControl(node) {
    if (!node) return false;
    const tag = cleanText(node.tagName).toUpperCase();
    const contentEditable = cleanText(node.getAttribute && node.getAttribute("contenteditable")).toLowerCase() === "true";
    if (!contentEditable && !["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return false;
    if (node.disabled === true || node.readOnly === true) return false;
    return cleanText(node.getAttribute && node.getAttribute("aria-readonly")).toLowerCase() !== "true";
  }

  function validationNode(located) {
    if (!located) return null;
    if (located.control && editableValidationControl(located.control)) return located.control;
    if (located.control || located.expectsControl) return null;
    return located.actionableRow ? located.row : null;
  }

  function validationActionLabel(target) {
    if (!target) return "";
    const renderedNode = validationNode(locateValidationTarget(target));
    if (!renderedNode && !latentEditableValidationTarget(target)) return "";
    if (target.kind === "rescan") return "重新扫描";
    if (target.kind === "check") return "前往核验";
    if (target.controlId === "rerunTrialRenderBtn") return "重新试渲染";
    return "前往修改";
  }

  function latentEditableValidationTarget(target) {
    const item = objectOf(target);
    if (item.kind === "mapping-option") {
      return Boolean(item.optionKey && item.group && item.outputKey && item.field === "mapping-source");
    }
    if (item.stage !== "rules") return false;
    const option = validationOptionConfig(item.outputIndex, item.group, item.optionIndex);
    if (!cleanText(option.key || option.name || option.label)) return false;
    if (item.kind === "option-preset") return true;
    if (item.kind !== "slot") return false;
    const slots = Array.isArray(option.slots) ? option.slots : [];
    if (!objectOf(slots[Number(item.slotIndex)]).key) return false;
    return ["slot-source-field", "slot-preset", "slot-required", "slot-font-dependencies", "slot-color-binding"].includes(cleanText(item.field));
  }

  function clearValidationHighlights() {
    document.querySelectorAll(".v2-validation-control-error, .v2-validation-row-error").forEach((node) => {
      const hasOriginalTitle = Object.prototype.hasOwnProperty.call(node.dataset, "validationOriginalTitle");
      if (hasOriginalTitle) {
        const originalTitle = node.dataset.validationOriginalTitle;
        if (originalTitle) node.setAttribute("title", originalTitle);
        else node.removeAttribute("title");
        delete node.dataset.validationOriginalTitle;
      }
      node.removeAttribute("aria-invalid");
      node.classList.remove("v2-validation-control-error", "v2-validation-row-error");
    });
  }

  function markValidationTarget(issue) {
    const target = validationTargetForIssue(issue);
    const located = locateValidationTarget(target);
    const node = validationNode(located);
    if (!node) return target;
    if (!Object.prototype.hasOwnProperty.call(node.dataset, "validationOriginalTitle")) {
      node.dataset.validationOriginalTitle = node.getAttribute("title") || "";
    }
    node.setAttribute("title", validationDisplayReason(issue));
    node.setAttribute("aria-invalid", "true");
    node.classList.add(located && located.control === node ? "v2-validation-control-error" : "v2-validation-row-error");
    return target;
  }

  function syncValidationHighlights(validation) {
    clearValidationHighlights();
    publicationValidationIssues(validation).forEach((issue) => markValidationTarget(issue));
  }

  function prepareValidationTarget(target) {
    if (!target || target.stage !== "rules" || !target.optionKey || typeof ruleOptionItems !== "function") return false;
    const items = ruleOptionItems();
    const index = items.findIndex((item) => item.output === target.outputKey && item.group === target.group && item.key === target.optionKey);
    if (index < 0) return false;
    const changed = state.optionRules.pendingOnly || state.optionRules.selectedIndex !== index || Boolean(valueOf("optionRuleSearch"));
    state.optionRules.pendingOnly = false;
    state.optionRules.selectedIndex = index;
    if (valueOf("optionRuleSearch")) setValue("optionRuleSearch", "");
    return changed;
  }

  function focusValidationIssue(issue) {
    const target = validationTargetForIssue(issue);
    if (!target) return;
    const refreshRules = prepareValidationTarget(target);
    if (state.stage !== target.stage && typeof setWorkbenchStage === "function") {
      setWorkbenchStage(target.stage);
    } else if (refreshRules && target.stage === "rules" && typeof setWorkbenchStage === "function") {
      setWorkbenchStage(target.stage);
    }
    const located = locateValidationTarget(target);
    const node = validationNode(located);
    if (!node) return;
    markValidationTarget(issue);
    if (typeof node.scrollIntoView === "function") node.scrollIntoView({ block: "center", behavior: "smooth" });
    if (typeof node.focus === "function") node.focus({ preventScroll: true });
  }

  Object.assign(globalThis, {
    locateValidationTarget,
    editableValidationControl,
    validationNode,
    validationActionLabel,
    latentEditableValidationTarget,
    clearValidationHighlights,
    markValidationTarget,
    syncValidationHighlights,
    prepareValidationTarget,
    focusValidationIssue
  });
})();
