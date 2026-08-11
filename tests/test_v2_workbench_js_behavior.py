import subprocess
import textwrap


HARNESS = r"""
const assert = require("assert");
const fs = require("fs");

const ids = [
  "v2CheckRail", "templateList", "templateSearch", "templateId", "templateName", "shopName",
  "newTemplateBtn", "templateListStats", "currentTemplateContext", "backToUploadBtn", "draftStatusBadge", "draftVersion",
  "uploadScanBadge", "scanSummaryMetrics", "scanSummaryWarning", "enterStructureBtn",
  "aiDropzone", "aiFile", "scanTemplateBtn", "rescanTemplateBtn", "scanProgress",
  "scanSummary", "scanEmptyState", "structureSearch", "structureTree", "toggleDesignsBtn",
  "toggleFontsBtn", "outputConfigRows", "fieldBindingRows", "optionMappingRows", "selectedNodeSummary",
  "styleDimensionRows", "contentOptionRows", "blockerList", "draftSummary", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn",
  "publishBlockerText", "scanRunningOverlay", "scanRunningMessage", "scanFailedOverlay", "scanFailedMessage", "retryScanBtn", "closeScanFailedBtn",
  "optionRuleSearch", "optionRuleList", "optionRuleStats", "optionRuleCount", "pendingOnlyBtn", "selectedOptionTitle",
  "selectedOptionPendingBadge", "optionContentPreset", "optionContentSeparator", "assetBindingRows", "templateCapabilityPanel",
  "capabilityEvidenceRows", "colorRuleRows", "dimensionRuleRows", "fontDependencyRows", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "preflightFailedOverlay", "preflightFailedMessage",
  "preflightIssueList", "closePreflightFailedBtn", "returnToSampleDataBtn", "previewSampleRows", "previewValidationRows"
];

function makeClassList(element) {
  return {
    add: (...names) => {
      const set = new Set((element.className || "").split(/\s+/).filter(Boolean));
      names.forEach((name) => set.add(name));
      element.className = Array.from(set).join(" ");
    },
    remove: (...names) => {
      const remove = new Set(names);
      element.className = (element.className || "").split(/\s+/).filter((name) => !remove.has(name)).join(" ");
    },
    contains: (name) => (element.className || "").split(/\s+/).includes(name)
    ,
    toggle: (name, force) => {
      const set = new Set((element.className || "").split(/\s+/).filter(Boolean));
      const shouldAdd = force === undefined ? !set.has(name) : Boolean(force);
      if (shouldAdd) set.add(name);
      else set.delete(name);
      element.className = Array.from(set).join(" ");
      return shouldAdd;
    }
  };
}

class Element {
  constructor(tag, id = "") {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.handlers = {};
    this.attributes = {};
    this.className = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.files = [];
    this._text = "";
    this.classList = makeClassList(this);
  }
  set textContent(value) {
    this._text = String(value == null ? "" : value);
    this.children = [];
  }
  get textContent() {
    return this._text + this.children.map((child) => child.textContent || "").join("");
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  append(...children) {
    children.forEach((child) => this.appendChild(child));
  }
  replaceChildren(...children) {
    this.children = [];
    this._text = "";
    children.forEach((child) => this.appendChild(child));
  }
  addEventListener(type, handler) {
    (this.handlers[type] ||= []).push(handler);
  }
  dispatch(type, event = {}) {
    for (const handler of this.handlers[type] || []) {
      handler({
        target: this,
        preventDefault() {},
        dataTransfer: null,
        ...event
      });
    }
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  querySelector(selector) {
    if (selector.includes("span")) return this.children.find((child) => child.tagName === "SPAN") || null;
    if (selector.includes("strong")) return this.children.find((child) => child.tagName === "STRONG") || null;
    if (selector.startsWith("[data-field=")) {
      return allDescendants(this).find((child) => child.dataset.field === selector.match(/"([^"]+)"/)[1]) || null;
    }
    return null;
  }
}

function allDescendants(root) {
  const result = [];
  for (const child of root.children || []) {
    result.push(child, ...allDescendants(child));
  }
  return result;
}

function makeDocument() {
  const elements = {};
  ids.forEach((id) => { elements[id] = new Element("div", id); });
  ["aiFile"].forEach((id) => { elements[id].tagName = "INPUT"; });
  ["templateSearch", "templateId", "templateName", "shopName", "structureSearch", "optionRuleSearch"].forEach((id) => { elements[id].tagName = "INPUT"; });
  ["optionContentPreset", "optionContentSeparator"].forEach((id) => { elements[id].tagName = "SELECT"; });
  ["scanTemplateBtn", "rescanTemplateBtn", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn", "retryScanBtn", "closeScanFailedBtn", "toggleDesignsBtn", "toggleFontsBtn", "pendingOnlyBtn", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "closePreflightFailedBtn", "returnToSampleDataBtn"].forEach((id) => { elements[id].tagName = "BUTTON"; });
  const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
  checkKeys.forEach((key) => {
    const item = new Element("button");
    item.className = "check-item";
    item.dataset.checkKey = key;
    item.appendChild(new Element("span"));
    item.appendChild(new Element("strong"));
    elements.v2CheckRail.appendChild(item);
  });
  const readyHandlers = [];
  const document = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => new Element(tag),
    addEventListener: (type, handler) => {
      if (type === "DOMContentLoaded") readyHandlers.push(handler);
    },
    querySelector: (selector) => {
      const match = selector.match(/^#v2CheckRail \.check-item\[data-check-key="([^"]+)"\]$/);
      if (match) {
        return elements.v2CheckRail.children.find((child) => child.dataset.checkKey === match[1]) || null;
      }
      return null;
    },
    querySelectorAll: (selector) => {
      const match = selector.match(/^#([^ ]+) \.([A-Za-z0-9_-]+)$/);
      if (!match || !elements[match[1]]) return [];
      return allDescendants(elements[match[1]]).filter((child) => (child.className || "").split(/\s+/).includes(match[2]));
    },
    fireReady: () => readyHandlers.forEach((handler) => handler())
  };
  return { document, elements };
}

class FakeFormData {
  constructor() { this.items = []; }
  append(key, value, fileName) { this.items.push([key, value, fileName]); }
}

function response(payload, ok = true) {
  return { ok, text: async () => JSON.stringify(payload || {}) };
}

async function flush() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

function createApp(fetchImpl) {
  const { document, elements } = makeDocument();
  global.document = document;
  global.window = global;
  global.FormData = FakeFormData;
  global.fetch = fetchImpl;
  [
    "workbench.js",
    "workbench-dom.js",
    "workbench-api.js",
    "workbench-scan-model.js",
    "workbench-form-model.js",
    "workbench-config.js",
    "workbench-content.js",
    "workbench-style-dimensions.js",
    "workbench-option-rules.js",
    "workbench-rule-evidence.js",
    "workbench-stage-view.js",
    "workbench-view.js",
    "workbench-draft-actions.js",
    "workbench-scan-actions.js"
  ].forEach((fileName) => {
    eval(fs.readFileSync(`src/service/static/v2-workbench/${fileName}`, "utf8"));
  });
  document.fireReady();
  return { elements };
}
"""


def run_node(script: str) -> None:
    completed = subprocess.run(
        ["node", "-e", HARNESS + "\n" + textwrap.dedent(script)],
        cwd="C:/Users/Administrator/Desktop/image/custom-renderer-v2-template-workbench",
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_v2_workbench_renders_scan_structure_groups_from_draft():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            if (url === "/api/v2/templates") return response({ templates: [{ template_id: "V2BEHAVIOR", name: "Demo" }] });
            if (String(url).endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2BEHAVIOR", name: "Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: {
                  outputs: [{ key: "Output_main" }],
                  anchors: [{ name: "anchor_name" }],
                  tails: [{ name: "tail_name" }],
                  fixed_objects: [{ name: "fixed art", count: 4 }]
                }
              }});
            }
            if (String(url).endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          assert.strictEqual(app.elements.outputConfigRows.children.length, 0);
          global.setWorkbenchStage("structure");
          await flush();
          const tree = app.elements.structureTree.textContent;
          assert(tree.includes("定位框"));
          assert(tree.includes("anchor_name"));
          assert(tree.includes("尾巴样本"));
          assert(tree.includes("tail_name"));
          assert(tree.includes("固定对象汇总"));
          assert(app.elements.scanSummary.textContent.includes("固定对象 1"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_scan_summary_does_not_double_count_v2_aliases():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const duplicatedDesigns = [
            { key: "Design01", slots: [{ key: "slot_name", path: "Template/Output_main/Design/Design01/slot_name" }], anchors: [{ key: "anchor_name" }], tails: [] },
            { key: "Design02", slots: [{ key: "slot_name1" }, { key: "slot_name2" }], anchors: [{ key: "anchor_name1" }, { key: "anchor_name2" }], tails: [{ key: "tail_name1_last_m" }] }
          ];
          const scan = {
            "$schema": "custom-renderer/v2-template-scan",
            outputs: [{
              key: "Output_main",
              design: { options: duplicatedDesigns },
              designs: duplicatedDesigns,
              font: { options: [] },
              fonts: [],
              summary: { styles: 0, designs: 2, fonts: 0, slots: 3, anchors: 3, tails: 1, assets: 0, fixed_objects: 0 }
            }],
            dependencies: {
              fonts: [
                { scope: "option", path: "Template/Output_main/Design/Design01", font_name: "Winterhome" },
                { scope: "slot", path: "Template/Output_main/Design/Design01/slot_name", font_name: "Winterhome" },
                { scope: "option", path: "Template/Output_main/Design/Design02", font_name: "TimesNewRomanPSMT" },
                { scope: "slot", path: "Template/Output_main/Design/Design02/slot_name2", font_name: "TimesNewRomanPSMT" }
              ]
            }
          };
          global.DrawFlowV2WorkbenchContext.state.scan = scan;
          const model = scanModel(scan, {});
          const summary = scanSummary(scan);
          assert.strictEqual(model.designs.length, 2);
          assert.strictEqual(model.fonts.length, 0);
          assert.strictEqual(model.slots.length, 3);
          assert.strictEqual(model.anchors.length, 3);
          assert.strictEqual(model.tails.length, 1);
          assert.strictEqual(summary.designs, 2);
          assert.strictEqual(summary.fonts, 0);
          assert.strictEqual(summary.slots, 3);
          renderScanSummary();
          const metricValues = app.elements.scanSummaryMetrics.children.map((node) => node.children[1].textContent);
          assert.deepStrictEqual(metricValues, ["1", "2", "0", "3", "0"]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_scan_summary_dedupes_matching_scan_and_config_options():
    run_node(
        r"""
        (async () => {
          createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const scan = {
            "$schema": "custom-renderer/v2-template-scan",
            outputs: [{
              key: "Output_main",
              design: { options: [{ key: "Design01", slots: [{ key: "slot_name", path: "Template/Output_main/Design/Design01/slot_name" }] }] },
              font: { options: [{ key: "F10", slots: [{ key: "slot_name", path: "Template/Output_main/Font/F10/slot_name" }] }] },
              summary: { styles: 0, designs: 1, fonts: 1, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
            }]
          };
          const config = {
            outputs: [{
              key: "Output_main",
              design: { options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] },
              font: { options: [{ key: "F10", content_preset: "path_text", slots: [{ key: "slot_name", source_field: "name" }] }] },
              style: { options: [] }
            }]
          };
          global.DrawFlowV2WorkbenchContext.state.draft = { config };
          const model = scanModel(scan, config);
          const summary = scanSummary(scan);
          assert.deepStrictEqual(model.designs.map((item) => `${item.output}:${item.group}:${item.key}`), ["Output_main:design:Design01"]);
          assert.deepStrictEqual(model.fonts.map((item) => `${item.output}:${item.group}:${item.key}`), ["Output_main:font:F10"]);
          assert.deepStrictEqual(model.slots.map((item) => `${item.output}:${item.group}:${item.option}:${item.key}`), [
            "Output_main:design:Design01:slot_name",
            "Output_main:font:F10:slot_name"
          ]);
          assert.strictEqual(summary.designs, 1);
          assert.strictEqual(summary.fonts, 1);
          assert.strictEqual(summary.slots, 2);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_draft_does_not_submit_scan_payload():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          const confirmedChecks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((checks, key) => {
            checks[key] = { status: "confirmed", reason: "" };
            return checks;
          }, {});
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2BEHAVIOR", name: "Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2BEHAVIOR", name: "Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: { scan_version: "trusted-server-scan" }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: { metadata: { template_id: "V2BEHAVIOR", name: "Demo", shop_name: "" }, manifest: {}, config: {}, scan: { scan_version: "trusted-server-scan" } } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();
          app.elements.saveDraftBtn.dispatch("click");
          await flush();
          assert(draftSaveBody);
          assert(!Object.prototype.hasOwnProperty.call(draftSaveBody, "scan"));
          assert(!Object.prototype.hasOwnProperty.call(draftSaveBody, "scan_result"));
          assert.strictEqual(draftSaveBody.config.audit.scan_version, "");
          assert.strictEqual(draftSaveBody.config.audit.template_sha256, "");
          assert.deepStrictEqual(Object.keys(draftSaveBody.config.checks), ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]);
          assert.strictEqual(app.elements.publishVersionBtn.disabled, false);
          assert(app.elements.publishBlockerText.textContent.includes("发布接口未接入"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_same_slot_independent_per_design_and_font_option():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2CONTENT", name: "Content Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2CONTENT", name: "Content Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  outputs: [{ key: "Output_main" }],
                  slots: [{ key: "slot_name", source_field: "name" }],
                  designs: [{ key: "Design03", slots: [{ key: "slot_name", source_field: "name" }] }],
                  fonts: [{ key: "F1", slots: [{ key: "slot_name", source_field: "name" }] }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "主效果图",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design03", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", preset: "direct_text", required: true }] }] },
                    font: { field: "font", options: [{ key: "F1", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", preset: "direct_text", required: true }] }] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          assert.strictEqual(app.elements.outputConfigRows.children.length, 0);
          global.setWorkbenchStage("structure");
          await flush();

          const outputRow = document.querySelectorAll("#outputConfigRows .output-row")[0];
          assert(outputRow);
          assert.strictEqual(outputRow.querySelector('[data-field="output-component"]').value, "main");
          outputRow.querySelector('[data-field="output-component"]').value = "inside";

          const groups = document.querySelectorAll("#contentOptionRows .content-option-group");
          const designGroup = groups.find((row) => row.dataset.group === "design" && row.dataset.option === "Design03");
          const fontGroup = groups.find((row) => row.dataset.group === "font" && row.dataset.option === "F1");
          assert(designGroup);
          assert(fontGroup);
          designGroup.querySelector('[data-field="option-content-preset"]').value = "split_by_pipe";
          fontGroup.querySelector('[data-field="option-content-preset"]').value = "path_text";

          const slotRows = document.querySelectorAll("#contentOptionRows .content-slot-row");
          const designSlot = slotRows.find((row) => row.dataset.group === "design" && row.dataset.option === "Design03" && row.dataset.slotKey === "slot_name");
          const fontSlot = slotRows.find((row) => row.dataset.group === "font" && row.dataset.option === "F1" && row.dataset.slotKey === "slot_name");
          assert(designSlot);
          assert(fontSlot);
          designSlot.querySelector('[data-field="slot-source-field"]').value = "design_name";
          designSlot.querySelector('[data-field="slot-preset"]').value = "split_by_pipe";
          designSlot.querySelector('[data-field="slot-required"]').value = "required";
          fontSlot.querySelector('[data-field="slot-source-field"]').value = "font_name";
          fontSlot.querySelector('[data-field="slot-preset"]').value = "path_text";
          fontSlot.querySelector('[data-field="slot-required"]').value = "optional";

          const config = buildControlledConfig();
          const output = config.outputs[0];
          assert.strictEqual(output.component_key, "inside");
          const designOption = output.design.options.find((item) => item.key === "Design03");
          const fontOption = output.font.options.find((item) => item.key === "F1");
          assert.strictEqual(designOption.content_preset, "split_by_pipe");
          assert.strictEqual(designOption.slots[0].key, "slot_name");
          assert.strictEqual(designOption.slots[0].source_field, "design_name");
          assert.strictEqual(designOption.slots[0].preset, "split_by_pipe");
          assert.strictEqual(designOption.slots[0].required, true);
          assert.strictEqual(fontOption.content_preset, "path_text");
          assert.strictEqual(fontOption.slots[0].key, "slot_name");
          assert.strictEqual(fontOption.slots[0].source_field, "font_name");
          assert.strictEqual(fontOption.slots[0].preset, "path_text");
          assert.strictEqual(fontOption.slots[0].required, false);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_roundtrips_multi_output_dimensions_assets_tails_fonts_colors():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          const confirmedChecks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((checks, key) => {
            checks[key] = { status: "confirmed", reason: "" };
            return checks;
          }, {});
          let currentDraft = {
            metadata: { template_id: "V2ROUNDTRIP", name: "Roundtrip Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: {
              outputs: [{ key: "Output_SideA" }, { key: "Output_SideB" }],
              styles: [{ key: "style1", dimensions: { mode: "style", width_mm: 80, height_mm: 50, tolerance_mm: 0.007 } }],
              designs: [{ key: "Design03", slots: [{ key: "slot_initial_top", preset: "asset_replace" }, { key: "slot_name" }] }],
              fonts: [{ key: "F10", slots: [{ key: "slot_name" }] }],
              assets: [{ asset_key: "initial_top", slot: "slot_initial_top", supported_values: ["A", "B", "C"] }],
              colors: [{ key: "Black", zh_name: "黑色", space: "RGB", value: [0, 0, 0], allow_recolor: true }]
            },
            config: {
              checks: confirmedChecks,
              field_bindings: { style: "Size", design: "Design", font: "Font", name: "Name", initial: "Initial", color: "Color" },
              option_mappings: [
                { field: "style", source_value: "small", target: "style1", output: "Output_SideA", group: "style" },
                { field: "design", source_value: "03", target: "Design03", output: "Output_SideA", group: "design" },
                { field: "font", source_value: "F10", target: "F10", output: "Output_SideB", group: "font" }
              ],
              outputs: [
                {
                  key: "Output_SideA",
                  display_name: "外部设计",
                  component_key: "front",
                  style: { field: "style", options: [{ key: "style1", dimensions: { mode: "style", width_mm: 80, height_mm: 50, tolerance_mm: 0.007 } }] },
                  design: { field: "design", options: [{
                    key: "Design03",
                    content_preset: "initial_with_text",
                    font_dependencies: ["Cinzel Decorative"],
                    slots: [
                      { key: "slot_initial_top", source_field: "initial", preset: "asset_replace", asset_key: "initial_top", dimension_rule: { mode: "slot", width_mm: 12, height_mm: 12, tolerance_mm: 0.007 } },
                      { key: "slot_name", source_field: "name", preset: "tail_text", tails: [{ key: "tail_name_first_a", position: "first", sample: "a" }], dimension_rule: { mode: "slot", width_mm: 42, height_mm: 8, tolerance_mm: 0.007 }, font_dependencies: ["Cinzel Decorative"], color_binding: "color" }
                    ],
                    assets: [{ asset_key: "initial_top", slot: "slot_initial_top", supported_values: ["A", "B", "C"] }]
                  }] },
                  font: { field: "", options: [] }
                },
                {
                  key: "Output_SideB",
                  display_name: "内部文字",
                  component_key: "inside",
                  style: { field: "", options: [] },
                  design: { field: "", options: [] },
                  font: { field: "font", options: [{ key: "F10", content_preset: "direct_text", font_dependencies: ["F10"], slots: [{ key: "slot_name", source_field: "name", preset: "direct_text", dimension_rule: { mode: "slot", width_mm: 38, height_mm: 6, tolerance_mm: 0.007 }, font_dependencies: ["F10"], color_binding: "color" }] }] }
                }
              ]
            }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ROUNDTRIP", name: "Roundtrip Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              currentDraft = { ...currentDraft, config: draftSaveBody.config, manifest: { draft_revision: "d0002" } };
              return response({ draft: currentDraft });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const styleRow = document.querySelectorAll("#styleDimensionRows .style-dimension-row")[0];
          assert(styleRow);
          assert.strictEqual(styleRow.dataset.output, "Output_SideA");
          assert.strictEqual(document.querySelectorAll('#styleDimensionRows .style-dimension-row[data-output="Output_SideB"]').length, 0);
          assert.strictEqual(String(styleRow.querySelector('[data-field="style-width-mm"]').value), "80");
          const designSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideA" && row.dataset.option === "Design03" && row.dataset.slotKey === "slot_name");
          assert(designSlot);
          assert.strictEqual(designSlot.querySelector('[data-field="slot-tail-first"]').value, "a");
          assert.strictEqual(designSlot.querySelector('[data-field="slot-font-dependencies"]').value, "Cinzel Decorative");
          assert.strictEqual(designSlot.querySelector('[data-field="slot-color-binding"]').value, "color");

          app.elements.saveDraftBtn.dispatch("click");
          await flush();
          assert(draftSaveBody);
          const sideA = draftSaveBody.config.outputs.find((output) => output.key === "Output_SideA");
          const sideB = draftSaveBody.config.outputs.find((output) => output.key === "Output_SideB");
          assert.strictEqual(sideA.style.options[0].dimensions.tolerance_mm, 0.007);
          const option = sideA.design.options.find((item) => item.key === "Design03");
          assert.deepStrictEqual(option.assets[0].supported_values, ["A", "B", "C"]);
          const savedSlot = option.slots.find((slot) => slot.key === "slot_name");
          assert.deepStrictEqual(savedSlot.tails, [{ key: "tail_name_first_a", position: "first", sample: "a" }]);
          assert.deepStrictEqual(savedSlot.font_dependencies, ["Cinzel Decorative"]);
          assert.strictEqual(savedSlot.color_binding, "color");
          assert.strictEqual(savedSlot.dimension_rule.tolerance_mm, 0.007);
          assert.strictEqual(sideB.style.options.length, 0);
          assert.strictEqual(sideB.design.options.length, 0);
          assert.strictEqual(sideB.font.options[0].key, "F10");
          assert(draftSaveBody.config.option_mappings.some((item) => item.output === "Output_SideB" && item.group === "font" && item.target === "F10"));

          const reloadedSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideA" && row.dataset.option === "Design03" && row.dataset.slotKey === "slot_name");
          assert(reloadedSlot);
          assert.strictEqual(reloadedSlot.querySelector('[data-field="slot-tail-first"]').value, "a");
          assert.strictEqual(String(reloadedSlot.querySelector('[data-field="slot-width-mm"]').value), "42");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_scopes_same_design_slots_by_output():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          const confirmedChecks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((checks, key) => {
            checks[key] = { status: "confirmed", reason: "" };
            return checks;
          }, {});
          const currentDraft = {
            metadata: { template_id: "V2SCOPED", name: "Scoped Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: {
              outputs: [{ key: "Output_SideA" }, { key: "Output_SideB" }],
              designs: [
                {
                  key: "Design03",
                  output: "Output_SideA",
                  recommended_preset: "initial_with_text",
                  slots: [{
                    key: "slot_front_name",
                    source_field: "front_name",
                    preset: "initial_with_text",
                    asset_key: "front_letters",
                    dimension_rule: { mode: "slot", width_mm: 30, height_mm: 9, tolerance_mm: 0.007 },
                    font_dependencies: ["Front Serif"],
                    color_binding: "front_color"
                  }]
                },
                {
                  key: "Design03",
                  output: "Output_SideB",
                  recommended_preset: "tail_text",
                  slots: [{
                    key: "slot_back_name",
                    source_field: "back_name",
                    preset: "tail_text",
                    asset_key: "back_letters",
                    dimension_rule: { mode: "slot", width_mm: 44, height_mm: 11, tolerance_mm: 0.007 },
                    tails: [{ key: "tail_back_last_z", position: "last", sample: "z" }]
                  }]
                }
              ],
              assets: [
                { asset_key: "front_letters", output: "Output_SideA", supported_values: ["A", "B"] },
                { asset_key: "back_letters", output: "Output_SideB", supported_values: ["X", "Z"] }
              ]
            },
            config: {
              checks: confirmedChecks,
              field_bindings: { design: "Design", front_name: "Front Name", back_name: "Back Name" },
              option_mappings: [
                { field: "design", source_value: "03", target: "Design03", output: "Output_SideA", group: "design" },
                { field: "design", source_value: "03", target: "Design03", output: "Output_SideB", group: "design" }
              ],
              outputs: [
                {
                  key: "Output_SideA",
                  display_name: "Front",
                  component_key: "front",
                  style: { field: "", options: [] },
                  design: { field: "design", options: [] },
                  font: { field: "", options: [] }
                },
                {
                  key: "Output_SideB",
                  display_name: "Back",
                  component_key: "back",
                  style: { field: "", options: [] },
                  design: { field: "design", options: [] },
                  font: { field: "", options: [] }
                }
              ]
            }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SCOPED", name: "Scoped Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: { ...currentDraft, config: draftSaveBody.config } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const frontSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideA" && row.dataset.slotKey === "slot_front_name");
          const backSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideB" && row.dataset.slotKey === "slot_back_name");
          assert(frontSlot);
          assert(backSlot);
          assert.strictEqual(frontSlot.querySelector('[data-field="slot-asset-key"]').value, "front_letters");
          assert.strictEqual(backSlot.querySelector('[data-field="slot-asset-key"]').value, "back_letters");
          assert.strictEqual(backSlot.querySelector('[data-field="slot-tail-last"]').value, "z");

          global.setWorkbenchStage("rules");
          await flush();
          const sideBIndex = global.ruleOptionItems().findIndex((item) => item.output === "Output_SideB" && item.group === "design" && item.key === "Design03");
          assert(sideBIndex >= 0);
          global.selectRuleOption(sideBIndex);
          await flush();
          assert(app.elements.assetBindingRows.textContent.includes("back_letters"));
          assert(!app.elements.assetBindingRows.textContent.includes("front_letters"));

          app.elements.saveDraftBtn.dispatch("click");
          await flush();
          const sideA = draftSaveBody.config.outputs.find((output) => output.key === "Output_SideA");
          const sideB = draftSaveBody.config.outputs.find((output) => output.key === "Output_SideB");
          const frontOption = sideA.design.options.find((item) => item.key === "Design03");
          const backOption = sideB.design.options.find((item) => item.key === "Design03");
          assert.strictEqual(frontOption.content_preset, "initial_with_text");
          assert.strictEqual(backOption.content_preset, "tail_text");
          assert.strictEqual(frontOption.slots[0].key, "slot_front_name");
          assert.strictEqual(backOption.slots[0].key, "slot_back_name");
          assert.deepStrictEqual(frontOption.assets[0].supported_values, ["A", "B"]);
          assert.deepStrictEqual(backOption.assets[0].supported_values, ["X", "Z"]);
          assert.strictEqual(frontOption.slots[0].color_binding, "front_color");
          assert.deepStrictEqual(backOption.slots[0].tails, [{ key: "tail_back_name_last_z", position: "last", sample: "z" }]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_rules_stage_filters_pending_and_saves_next_option():
    run_node(
        r"""
        (async () => {
          let saveCount = 0;
          const confirmedChecks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((checks, key) => {
            checks[key] = { status: "confirmed", reason: "" };
            return checks;
          }, {});
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2RULES", name: "Rules Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2RULES", name: "Rules Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  outputs: [{ key: "Output_main" }],
                  slots: [{ key: "slot_name", source_field: "name" }],
                  designs: [{ key: "Design03" }, { key: "Design08" }],
                  fonts: [{ key: "F1" }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "涓绘晥鏋滃浘",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design03", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { field: "font", options: [{ key: "F1", content_preset: "path_text", slots: [{ key: "slot_name", source_field: "name" }] }] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              saveCount += 1;
              return response({ draft: {
                metadata: { template_id: "V2RULES", name: "Rules Demo", shop_name: "" },
                manifest: {},
                config: JSON.parse(options.body).config,
                scan: global.DrawFlowV2WorkbenchContext.state.scan
              }});
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();
          assert(app.elements.optionRuleList.textContent.includes("Design03"));
          assert(app.elements.optionRuleList.textContent.includes("Design08"));
          assert(app.elements.optionRuleList.textContent.includes("F1"));
          app.elements.optionContentSeparator.value = "pipe";
          app.elements.optionContentSeparator.dispatch("change");
          await flush();
          const selectedGroup = document.querySelectorAll("#contentOptionRows .content-option-group").find((row) => row.dataset.group === "design" && row.dataset.option === "Design03");
          assert.strictEqual(selectedGroup.querySelector('[data-field="option-content-preset"]').value, "split_by_pipe");
          app.elements.pendingOnlyBtn.dispatch("click");
          await flush();
          assert.strictEqual(app.elements.pendingOnlyBtn.attributes["aria-pressed"], "true");
          assert(!app.elements.optionRuleList.textContent.includes("Design03"));
          assert(app.elements.optionRuleList.textContent.includes("Design08"));
          const firstTitle = app.elements.selectedOptionTitle.textContent;
          app.elements.saveAndNextOptionBtn.dispatch("click");
          await flush();
          assert.strictEqual(saveCount, 1);
          assert.notStrictEqual(app.elements.selectedOptionTitle.textContent, "");
          assert(app.elements.selectedOptionTitle.textContent === firstTitle || app.elements.selectedOptionTitle.textContent.includes("Design08"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_can_confirm_label_only_color_rules_without_samples():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          const checks = ["output", "fields", "options", "slots", "content", "dimensions", "preview"].reduce((result, key) => {
            result[key] = { status: "confirmed", reason: "" };
            return result;
          }, { colors: { status: "pending", reason: "等待颜色核验" } });
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2COLOR", name: "Color Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2COLOR", name: "Color Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  outputs: [{ key: "Output_main" }],
                  slots: [{ key: "slot_name", source_field: "name" }],
                  designs: [{ key: "Design03" }],
                  colors: []
                },
                config: {
                  checks,
                  field_bindings: { name: "Name", design: "Design", color: "Color" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "涓绘晥鏋滃浘",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design03", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", color_binding: "color" }] }] },
                    font: { field: "", options: [] }
                  }],
                  option_mappings: [{ field: "design", source_value: "03", target: "Design03", output: "Output_main", group: "design" }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) {
              const submitted = JSON.parse(options.body).config;
              return response({ validation: { can_save: true, can_publish: false, checks: submitted.checks } });
            }
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: { metadata: { template_id: "V2COLOR", name: "Color Demo", shop_name: "" }, manifest: {}, config: draftSaveBody.config, scan: global.DrawFlowV2WorkbenchContext.state.scan } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();
          assert(app.elements.colorRuleRows.textContent.includes("无可配置颜色样本"));
          const confirmButton = allDescendants(app.elements.colorRuleRows).find((item) => item.tagName === "BUTTON");
          assert(confirmButton);
          confirmButton.dispatch("click");
          await flush();
          assert.strictEqual(document.querySelector('#v2CheckRail .check-item[data-check-key="colors"]').dataset.status, "confirmed");
          app.elements.saveDraftBtn.dispatch("click");
          await flush();
          assert(draftSaveBody);
          assert.deepStrictEqual(draftSaveBody.config.colors, []);
          assert.strictEqual(draftSaveBody.config.checks.colors.status, "confirmed");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_preflight_modal_sanitizes_issue_details():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          showPreflightFailure({ issues: [{ title: "C:\\secret\\order.xlsx COMError", detail: "Traceback at C:\\tmp", hint: "修正测试数据" }] });
          assert.strictEqual(app.elements.preflightFailedOverlay.hidden, false);
          assert(!app.elements.preflightIssueList.textContent.includes("C:\\"));
          assert(!app.elements.preflightIssueList.textContent.includes("COMError"));
          assert(app.elements.preflightIssueList.textContent.includes("修正测试数据"));
          app.elements.closePreflightFailedBtn.dispatch("click");
          assert.strictEqual(app.elements.preflightFailedOverlay.hidden, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_local_scan_failure_does_not_upload_ai_to_central_assets():
    run_node(
        r"""
        (async () => {
          const urls = [];
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            urls.push({ url: textUrl, method: options.method || "GET" });
            if (textUrl === "/api/v2/templates" && options.method === "POST") {
              return response({ state: { template_id: "V2FAILSCAN", template: { template_id: "V2FAILSCAN", name: "Fail Demo" } } });
            }
            if (textUrl === "/api/v2/templates") return response({ templates: [] });
            if (textUrl === "/local/templates/scan") {
              return response({ error: { message: "本地扫描未完成，请重新扫描。" } }, false);
            }
            if (textUrl.endsWith("/draft")) {
              return response({ draft: { metadata: { template_id: "V2FAILSCAN", name: "Fail Demo", shop_name: "" }, manifest: {}, config: {}, scan: {} } });
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateId.value = "V2FAILSCAN";
          app.elements.templateName.value = "Fail Demo";
          app.elements.aiFile.files = [{ name: "failed.ai", type: "application/illustrator" }];
          app.elements.aiFile.dispatch("change", { target: app.elements.aiFile });
          app.elements.scanTemplateBtn.dispatch("click");
          await flush();
          await flush();
          assert(!urls.some((entry) => entry.url.includes("/assets/")));
          assert(app.elements.scanFailedMessage.textContent.includes("草稿已保留"));
          assert(app.elements.scanFailedMessage.textContent.includes("重新扫描"));
          assert(!app.elements.scanFailedMessage.textContent.includes("文件已保存"));
          assert.strictEqual(app.elements.scanRunningOverlay.hidden, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_sanitizes_sensitive_failures_and_scanning_overlay():
    run_node(
        r"""
        (async () => {
          const app = createApp(async () => { throw new Error("C:\\secret\\template.ai Traceback COMError 0x80070005"); });
          await flush();
          assert.strictEqual(app.elements.scanFailedMessage.textContent, "模板列表加载失败，请稍后重试。");
          assert(!app.elements.scanFailedMessage.textContent.includes("C:\\"));
          assert(!app.elements.scanFailedMessage.textContent.includes("COM"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )

    run_node(
        r"""
        (async () => {
          let finishScan;
          let localScanForm = null;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates" && options.method === "POST") return response({ state: { template_id: "V2CANCEL", template: { template_id: "V2CANCEL", name: "Cancel Demo" } } });
            if (textUrl === "/api/v2/templates") return response({ templates: [] });
            if (textUrl === "/local/templates/scan") {
              localScanForm = options.body;
              return new Promise((resolve) => {
                finishScan = () => resolve(response({ draft: {
                  metadata: { template_id: "V2CANCEL", name: "Cancel Demo", shop_name: "" },
                  manifest: {},
                  config: {},
                  scan: { outputs: [{ key: "Output_main" }] }
                }}));
              });
            }
            if (textUrl.endsWith("/draft")) return response({ draft: { metadata: { template_id: "V2CANCEL", name: "Cancel Demo", shop_name: "" }, manifest: {}, config: {}, scan: {} } });
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateId.value = "V2CANCEL";
          app.elements.templateName.value = "Cancel Demo";
          app.elements.aiFile.files = [{ name: "demo.ai", type: "application/illustrator" }];
          app.elements.aiFile.dispatch("change", { target: app.elements.aiFile });
          app.elements.scanTemplateBtn.dispatch("click");
          await flush();
          assert(!Object.prototype.hasOwnProperty.call(app.elements, "cancelScanBtn"));
          assert.strictEqual(app.elements.scanRunningOverlay.hidden, false);
          assert(app.elements.scanRunningMessage.textContent.includes("Illustrator"));
          assert(app.elements.scanRunningMessage.textContent.includes("Template"));
          assert.strictEqual(app.elements.scanTemplateBtn.disabled, true);
          assert.strictEqual(app.elements.rescanTemplateBtn.disabled, true);
          assert.strictEqual(app.elements.saveDraftBtn.disabled, true);
          const fields = Object.fromEntries(localScanForm.items.filter((item) => item.length >= 2).map(([key, value]) => [key, value]));
          assert.strictEqual(fields.shop_name, "");
          assert.strictEqual(fields.template_type, "pure_text");
          assert.strictEqual(fields.scan_contract_version, "v2-template-scan/1");
          finishScan();
          await flush();
          assert.strictEqual(app.elements.scanRunningOverlay.hidden, true);
          assert(app.elements.scanProgress.textContent.includes("扫描完成"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
