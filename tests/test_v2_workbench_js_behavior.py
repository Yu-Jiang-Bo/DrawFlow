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
  "publishBlockerText", "draftSaveStatusText", "scanRunningOverlay", "scanRunningMessage", "scanFailedOverlay", "scanFailedMessage", "retryScanBtn", "closeScanFailedBtn",
  "optionRuleSearch", "optionRuleList", "optionRuleStats", "optionRuleCount", "pendingOnlyBtn", "selectedOptionTitle",
  "selectedOptionPendingBadge", "optionContentPreset", "assetBindingRows", "templateCapabilityPanel",
  "capabilityEvidenceRows", "colorRuleRows", "dimensionRuleRows", "fontDependencyRows", "confirmStageBtn", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "preflightFailedOverlay", "preflightFailedMessage",
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
  getAttribute(name) {
    return this.attributes[name];
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
  ["optionContentPreset"].forEach((id) => { elements[id].tagName = "SELECT"; });
  ["scanTemplateBtn", "rescanTemplateBtn", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn", "retryScanBtn", "closeScanFailedBtn", "toggleDesignsBtn", "toggleFontsBtn", "pendingOnlyBtn", "confirmStageBtn", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "closePreflightFailedBtn", "returnToSampleDataBtn"].forEach((id) => { elements[id].tagName = "BUTTON"; });
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

function createApp(fetchImpl, fileNames) {
  const { document, elements } = makeDocument();
  global.document = document;
  global.window = global;
  global.FormData = FakeFormData;
  global.fetch = fetchImpl;
  (fileNames || [
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
    "workbench-structure-tree.js",
    "workbench-draft-actions.js",
    "workbench-scan-actions.js"
  ]).forEach((fileName) => {
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


def test_v2_workbench_upload_survives_missing_structure_tree_bundle():
    run_node(
        r"""
        (async () => {
          const files = [
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
          ];
          async function fakeFetch(url, options = {}) {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          }
          const app = createApp(fakeFetch, files);
          await flush();
          app.elements.templateId.value = "STALEHTML";
          app.elements.templateName.value = "Stale HTML Demo";
          app.elements.templateId.dispatch("input");
          app.elements.templateName.dispatch("input");
          app.elements.aiFile.dispatch("change", { target: { files: [{ name: "demo.ai" }] } });
          await flush();
          global.DrawFlowV2WorkbenchContext.state.scan = {
            "$schema": "custom-renderer/v2-template-scan",
            outputs: [{
              key: "Output_main",
              design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }] }] },
              font: { options: [{ key: "F1", slots: [{ key: "slot_name" }] }] },
              style: { options: [] },
              summary: { designs: 1, fonts: 1, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 5 }
            }]
          };
          assert.strictEqual(typeof global.renderStructureTree, "function");
          assert.strictEqual(app.elements.scanTemplateBtn.disabled, false);
          global.renderStructureTree();
          assert(app.elements.structureTree.textContent.includes("Template"));
          assert(app.elements.structureTree.textContent.includes("Design01"));
          assert(app.elements.structureTree.textContent.includes("F1"));
          assert(app.elements.structureTree.textContent.includes("未命名固定对象"));
          assert(app.elements.structureTree.textContent.includes("5"));
          assert(!app.elements.structureTree.textContent.includes("页面脚本未完整加载"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_structure_stage_uses_nested_template_tree():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2TREE", name: "Tree Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2TREE", name: "Tree Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [
                      { key: "Design01", slots: [{ key: "slot_name" }], anchors: [{ key: "anchor_name" }], tails: [] },
                      { key: "Design02", slots: [{ key: "slot_name1" }, { key: "slot_name2" }], anchors: [], tails: [{ key: "tail_name1_last_m" }] }
                    ] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 2, fonts: 0, styles: 0, slots: 3, anchors: 1, tails: 1, assets: 0, fixed_objects: 5 }
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
          global.setWorkbenchStage("structure");
          await flush();

          const rows = document.querySelectorAll("#structureTree .structure-tree-row");
          assert(rows.length >= 5);
          const templateRow = rows.find((row) => row.className.includes("depth-0") && row.textContent.includes("Template"));
          assert(templateRow);
          assert.strictEqual(templateRow.getAttribute("aria-expanded"), "true");
          assert(rows.some((row) => row.dataset.nodeKind === "output" && row.textContent.includes("Output_main")));
          assert(rows.some((row) => row.textContent.includes("Design")));
          assert(rows.some((row) => row.textContent.includes("Design01") && row.textContent.includes("slot_name")));
          assert(app.elements.structureTree.textContent.includes("未命名固定对象"));
          assert(!app.elements.structureTree.textContent.includes("槽位（"));

          const outputRow = rows.find((row) => row.dataset.nodeKind === "output");
          outputRow.dispatch("click");
          await flush();
          const collapsedRows = document.querySelectorAll("#structureTree .structure-tree-row");
          const collapsedOutput = collapsedRows.find((row) => row.dataset.nodeKind === "output");
          assert.strictEqual(collapsedOutput.getAttribute("aria-expanded"), "false");
          assert(!app.elements.structureTree.textContent.includes("Design01"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_field_bindings_do_not_list_each_design_option():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2FIELDS", name: "Fields Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2FIELDS", name: "Fields Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [
                      { key: "Design01", slots: [{ key: "slot_name" }] },
                      { key: "Design02", slots: [{ key: "slot_name1" }, { key: "slot_name2" }] }
                    ] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 2, fonts: 0, styles: 0, slots: 3, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
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
          global.setWorkbenchStage("structure");
          await flush();

          const fields = document.querySelectorAll("#fieldBindingRows .field-binding-row")
            .map((row) => row.querySelector('[data-field="binding-field"]').value);
          assert(fields.includes("design"));
          assert(fields.includes("name"));
          assert(fields.includes("name1"));
          assert(fields.includes("name2"));
          assert(!fields.includes("Design01"));
          assert(!fields.includes("Design02"));
          assert(fields.length <= 5);
          assert(app.elements.fieldBindingRows.textContent.includes("待确认"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_single_output_does_not_invent_style_or_font_fields():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SIMPLE", name: "Simple Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2SIMPLE", name: "Simple Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }, { key: "slot_name2" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
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
          global.setWorkbenchStage("structure");
          await flush();

          const outputRows = document.querySelectorAll("#outputConfigRows .output-row");
          assert.strictEqual(outputRows.length, 1);
          const outputRow = outputRows[0];
          assert.strictEqual(outputRow.querySelector('[data-field="output-component"]').value, "main");
          assert.strictEqual(outputRow.querySelector('[data-field="output-style-field"]'), null);
          assert.strictEqual(outputRow.querySelector('[data-field="output-design-field"]'), null);
          assert.strictEqual(outputRow.querySelector('[data-field="output-font-field"]'), null);
          assert.strictEqual(document.querySelectorAll("#styleDimensionRows .style-dimension-row").length, 0);
          const mappingRows = document.querySelectorAll("#optionMappingRows .option-mapping-row");
          assert(mappingRows.length > 0);
          assert(mappingRows.every((row) => row.querySelector('[data-field="mapping-output"]') === null));

          const config = buildControlledConfig();
          assert.strictEqual(config.outputs[0].style.field, "");
          assert.strictEqual(config.outputs[0].font.field, "");
          assert.strictEqual(config.outputs[0].design.field, "design");
          assert.strictEqual(config.outputs[0].style.options.length, 0);
          assert.strictEqual(config.outputs[0].font.options.length, 0);
          assert.strictEqual(config.outputs[0].design.options[0].key, "Design01");
          assert(config.option_mappings.every((mapping) => mapping.output === "Output_main"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_stale_style_font_config_does_not_pollute_scan_structure():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2STALE", name: "Stale Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2STALE", name: "Stale Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {
                  field_bindings: { name: "Name", design: "Design", style: "Size", font: "Font" },
                  option_mappings: [
                    { field: "style", source_value: "small", target: "style1", output: "Output_main", group: "style" },
                    { field: "font", source_value: "F10", target: "F10", output: "Output_main", group: "font" }
                  ],
                  outputs: [{
                    key: "Output_main",
                    display_name: "Old Main",
                    component_key: "main",
                    style: { field: "style", options: [{ key: "style1", dimensions: { mode: "fixed", width_mm: 80, height_mm: 50, tolerance_mm: 0.007 } }] },
                    design: { field: "design", options: [] },
                    font: { field: "font", options: [{ key: "F10", slots: [{ key: "slot_name", source_field: "name" }] }] }
                  }]
                },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }, { key: "slot_name2" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
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
          global.setWorkbenchStage("structure");
          await flush();

          const model = scanModel(global.DrawFlowV2WorkbenchContext.state.scan, global.DrawFlowV2WorkbenchContext.state.draft.config);
          assert.strictEqual(model.styles.length, 0, "scan model must not include stale style config");
          assert.strictEqual(model.fonts.length, 0, "scan model must not include stale font config");
          assert(!app.elements.structureTree.textContent.includes("style1"));
          assert(!app.elements.structureTree.textContent.includes("F10"));
          assert.strictEqual(document.querySelectorAll("#styleDimensionRows .style-dimension-row").length, 0, "style dimensions must not render stale config rows");

          const fields = document.querySelectorAll("#fieldBindingRows .field-binding-row")
            .map((row) => row.querySelector('[data-field="binding-field"]').value);
          assert(fields.includes("design"));
          assert(!fields.includes("style"));
          assert(!fields.includes("font"));
          const mappingGroups = document.querySelectorAll("#optionMappingRows .option-mapping-row")
            .map((row) => row.querySelector('[data-field="mapping-group"]').value);
          assert(mappingGroups.includes("design"));
          assert(!mappingGroups.includes("style"));
          assert(!mappingGroups.includes("font"));

          const config = buildControlledConfig();
          assert.strictEqual(config.outputs[0].style.field, "");
          assert.strictEqual(config.outputs[0].font.field, "");
          assert.strictEqual(config.outputs[0].style.options.length, 0, "saved config must drop stale style options");
          assert.strictEqual(config.outputs[0].font.options.length, 0, "saved config must drop stale font options");
          assert.strictEqual(config.field_bindings.style, undefined);
          assert.strictEqual(config.field_bindings.font, undefined);
          assert.strictEqual(config.field_bindings.design, "Design");
          assert(!config.option_mappings.some((item) => item.group === "style" || item.group === "font"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_inferred_option_mappings_keep_output_scope():
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
            outputs: [
              {
                key: "Output_SideA",
                design: { options: [{ key: "Design08", slots: [{ key: "slot_name" }] }] },
                font: { options: [] },
                style: { options: [] },
                summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
              },
              {
                key: "Output_SideB",
                design: { options: [] },
                font: { options: [{ key: "F1", slots: [{ key: "slot_name" }] }] },
                style: { options: [] },
                summary: { designs: 0, fonts: 1, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
              }
            ]
          };
          global.DrawFlowV2WorkbenchContext.state.scan = scan;
          const mappings = inferredMappings();
          const design = mappings.find((item) => item.target === "Design08");
          const font = mappings.find((item) => item.target === "F1");
          assert.strictEqual(design.output, "Output_SideA");
          assert.strictEqual(font.output, "Output_SideB");
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
          designGroup.dataset.contentPreset = "split_by_pipe";
          fontGroup.dataset.contentPreset = "path_text";

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


def test_v2_workbench_rules_stage_shows_only_selected_option_content():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SELECTED", name: "Selected Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2SELECTED", name: "Selected Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [
                      {
                        key: "Design01",
                        slots: [{ key: "slot_name", source_field: "name" }],
                        assets: [{ asset_key: "initial_top", slot: "slot_name", supported_values: ["A"] }]
                      },
                      {
                        key: "Design02",
                        slots: [{ key: "slot_title", source_field: "title" }, { key: "slot_subtitle", source_field: "subtitle" }],
                        assets: [{ asset_key: "badge", slot: "slot_title", supported_values: ["B"] }, { asset_key: "ornament", slot: "slot_subtitle", supported_values: ["C"] }]
                      }
                    ] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 2, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 2, fixed_objects: 0 }
                  }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "主效果图",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
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
          global.setWorkbenchStage("rules");
          await flush();

          let groups = document.querySelectorAll("#contentOptionRows .content-option-group");
          assert.strictEqual(groups.length, 1);
          assert.strictEqual(groups[0].dataset.option, "Design01");
          assert(app.elements.contentOptionRows.textContent.includes("slot_name"));
          assert(!app.elements.contentOptionRows.textContent.includes("Design02"));
          assert(!app.elements.contentOptionRows.textContent.includes("slot_title"));
          assert(app.elements.assetBindingRows.textContent.includes("initial_top"));
          assert(!app.elements.assetBindingRows.textContent.includes("badge"));
          assert(app.elements.capabilityEvidenceRows.textContent.includes("1 个可控槽位"));
          assert(app.elements.capabilityEvidenceRows.textContent.includes("1 个可替换资产"));

          global.selectRuleOption(1);
          await flush();

          groups = document.querySelectorAll("#contentOptionRows .content-option-group");
          assert.strictEqual(groups.length, 1);
          assert.strictEqual(groups[0].dataset.option, "Design02");
          assert(!app.elements.contentOptionRows.textContent.includes("Design01"));
          assert(app.elements.contentOptionRows.textContent.includes("slot_title"));
          assert(!app.elements.contentOptionRows.textContent.includes("slot_name"));
          assert(app.elements.assetBindingRows.textContent.includes("badge"));
          assert(!app.elements.assetBindingRows.textContent.includes("initial_top"));
          assert(app.elements.capabilityEvidenceRows.textContent.includes("2 个可控槽位"));
          assert(app.elements.capabilityEvidenceRows.textContent.includes("2 个可替换资产"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_rules_prefill_anchor_dimensions_and_preserve_tail_proof():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ANCHOR", name: "Anchor Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2ANCHOR", name: "Anchor Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design02",
                      recommended_preset: "tail_text",
                      slots: [
                        { key: "slot_name1", source_field: "name", tails: [{ key: "tail_name1_last_m", pua_base: 61440 }] },
                        { key: "slot_name2", source_field: "name" }
                      ],
                      anchors: [
                        { key: "anchor_name1", dimensions: { width_mm: 31, height_mm: 7 } },
                        { key: "anchor_name2", dimensions: { width_mm: 28, height_mm: 6 } }
                      ],
                      tails: [{ key: "tail_name1_last_m", pua_base: 61440 }]
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 2, tails: 1, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
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
          global.setWorkbenchStage("rules");
          await flush();

          const rows = document.querySelectorAll("#contentOptionRows .content-slot-row");
          const slot1 = rows.find((row) => row.dataset.slotKey === "slot_name1");
          const slot2 = rows.find((row) => row.dataset.slotKey === "slot_name2");
          assert(slot1);
          assert(slot2);
          assert.strictEqual(slot1.dataset.anchor, "anchor_name1");
          assert.strictEqual(slot2.dataset.anchor, "anchor_name2");
          assert.strictEqual(String(slot1.querySelector('[data-field="slot-width-mm"]').value), "31");
          assert.strictEqual(String(slot1.querySelector('[data-field="slot-height-mm"]').value), "7");
          assert.strictEqual(String(slot2.querySelector('[data-field="slot-width-mm"]').value), "28");
          assert.strictEqual(String(slot2.querySelector('[data-field="slot-height-mm"]').value), "6");
          const tailLast = slot1.querySelector('[data-field="slot-tail-last"]');
          assert.strictEqual(tailLast.value, "m");
          assert.strictEqual(tailLast.readOnly, true);

          const config = buildControlledConfig();
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          const saved1 = option.slots.find((slot) => slot.key === "slot_name1");
          const saved2 = option.slots.find((slot) => slot.key === "slot_name2");
          assert.strictEqual(option.content_preset, "tail_text");
          assert.strictEqual(saved1.preset, "tail_text");
          assert.strictEqual(saved1.anchor, "anchor_name1");
          assert.strictEqual(saved2.anchor, "anchor_name2");
          assert.strictEqual(saved1.dimension_rule.width_mm, 31);
          assert.strictEqual(saved1.dimension_rule.height_mm, 7);
          assert.strictEqual(saved2.dimension_rule.width_mm, 28);
          assert.strictEqual(saved2.dimension_rule.height_mm, 6);
          assert.deepStrictEqual(saved1.tails, [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_split_pipe_recommendation_saves_slot_presets():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SPLIT", name: "Split Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2SPLIT", name: "Split Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design02",
                      recommended_preset: "split_by_pipe",
                      slots: [
                        { key: "slot_name1", source_field: "name" },
                        { key: "slot_name2", source_field: "name" }
                      ],
                      anchors: [],
                      tails: []
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  field_bindings: { name: "Name", design: "Design" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
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
          global.setWorkbenchStage("rules");
          await flush();

          const config = buildControlledConfig();
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          assert.strictEqual(option.content_preset, "split_by_pipe");
          assert.deepStrictEqual(option.slots.map((slot) => [slot.key, slot.source_field, slot.preset]), [
            ["slot_name1", "name", "split_by_pipe"],
            ["slot_name2", "name", "split_by_pipe"]
          ]);

          app.elements.optionContentPreset.value = "direct_text";
          app.elements.optionContentPreset.dispatch("change");
          await flush();
          app.elements.optionContentPreset.value = "split_by_pipe";
          app.elements.optionContentPreset.dispatch("change");
          await flush();
          const rows = document.querySelectorAll("#contentOptionRows .content-slot-row");
          assert(rows.every((row) => row.querySelector('[data-field="slot-preset"]').value === "split_by_pipe"));
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

          const mappingRows = document.querySelectorAll("#optionMappingRows .option-mapping-row");
          assert.strictEqual(mappingRows.length, 3);
          assert(mappingRows.every((row) => row.querySelector('[data-field="mapping-output"]')));
          const outputSelect = mappingRows[0].querySelector('[data-field="mapping-output"]');
          assert.deepStrictEqual(outputSelect.children.map((option) => option.value), ["Output_SideA", "Output_SideB"]);
          assert.strictEqual(outputSelect.children[0].textContent, currentDraft.config.outputs[0].display_name);

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
          assert.strictEqual(sideA.style.field, "style");
          assert.strictEqual(sideB.font.field, "font");
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
          assert.deepStrictEqual(backOption.slots[0].tails, [{ key: "tail_back_last_z", position: "last", sample: "z" }]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_rules_stage_filters_pending_and_saves_next_option():
    run_node(
        r"""
        (async () => {
          let saveCount = 0;
          let savedConfig = null;
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
                  designs: [{ key: "Design03" }, { key: "Design08" }, { key: "Design09" }],
                  fonts: [{ key: "F1" }]
                },
                config: savedConfig || {
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
              savedConfig = JSON.parse(options.body).config;
              if (saveCount === 1) savedConfig.outputs[0].design.options = savedConfig.outputs[0].design.options.filter((item) => item.key !== "Design09");
              return response({ draft: {
                metadata: { template_id: "V2RULES", name: "Rules Demo", shop_name: "" },
                manifest: {},
                config: savedConfig,
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
          app.elements.optionContentPreset.value = "split_by_pipe";
          app.elements.optionContentPreset.dispatch("change");
          await flush();
          const selectedGroup = document.querySelectorAll("#contentOptionRows .content-option-group").find((row) => row.dataset.group === "design" && row.dataset.option === "Design03");
          assert.strictEqual(selectedGroup.dataset.contentPreset, "split_by_pipe");
          assert.strictEqual(selectedGroup.querySelector('[data-field="option-content-preset"]'), null);
          assert(app.elements.contentOptionRows.textContent.includes("\u6309\u9700\u8986\u76d6"));
          app.elements.pendingOnlyBtn.dispatch("click");
          await flush();
          assert.strictEqual(app.elements.pendingOnlyBtn.attributes["aria-pressed"], "true");
          assert(!app.elements.optionRuleList.textContent.includes("Design03"));
          assert(app.elements.optionRuleList.textContent.includes("Design08"));
          assert(app.elements.optionRuleList.textContent.includes("Design09"));
          app.elements.saveAndNextOptionBtn.dispatch("click");
          for (let index = 0; index < 6; index += 1) await flush();
          assert.strictEqual(saveCount, 1);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "rules");
          assert(app.elements.selectedOptionTitle.textContent.includes("Design09"));
          app.elements.saveAndNextOptionBtn.dispatch("click");
          for (let index = 0; index < 6; index += 1) await flush();
          assert.strictEqual(saveCount, 2);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "preview");
          assert.strictEqual(app.elements.saveAndNextOptionBtn.hidden, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_next_from_structure_enters_rules_and_strips_manual_reason_nesting():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let saveCount = 0;
          const manualPrefix = "\u4eba\u5de5\u6838\u9a8c\u9879\u8fd8\u6ca1\u6709\u786e\u8ba4\uff1a";
          const pendingText = "\u7b49\u5f85\u4eba\u5de5\u6838\u9a8c";
          const nestedReason = manualPrefix + manualPrefix + pendingText;
          const checks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((result, key) => {
            result[key] = { status: key === "output" ? "pending" : "confirmed", reason: key === "output" ? nestedReason : "" };
            return result;
          }, {});
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2NEXT", name: "Next Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2NEXT", name: "Next Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  checks,
                  field_bindings: { name: "Name", design: "Design" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: false, checks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              saveCount += 1;
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: {
                metadata: { template_id: "V2NEXT", name: "Next Demo", shop_name: "" },
                manifest: { draft_revision: "d0002" },
                config: draftSaveBody.config,
                scan: global.DrawFlowV2WorkbenchContext.state.scan
              }});
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          app.elements.saveAndNextOptionBtn.dispatch("click");
          for (let index = 0; index < 6; index += 1) await flush();

          assert.strictEqual(saveCount, 1);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "rules");
          assert(app.elements.selectedOptionTitle.textContent.includes("Design01"));
          assert.strictEqual(draftSaveBody.config.checks.output.status, "confirmed");
          assert.strictEqual(draftSaveBody.config.checks.output.reason, "\u5355 Output_main \u81ea\u52a8\u786e\u8ba4");
          assert(!draftSaveBody.config.checks.output.reason.includes(manualPrefix));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_validation_reasons_do_not_accumulate_as_manual_reasons():
    run_node(
        r"""
        (async () => {
          const repeated = "\u69fd\u4f4d\u5185\u5bb9\u6765\u6e90 name \u8fd8\u6ca1\u6709\u7ed1\u5b9a\u5230\u771f\u5b9e\u8868\u5934\u3002";
          const checks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((result, key) => {
            result[key] = { status: "confirmed", reason: "" };
            return result;
          }, {});
          checks.fields = {
            status: "pending",
            reasons: [
              "\u8ba2\u5355\u5b57\u6bb5 design \u8fd8\u6ca1\u6709\u7ed1\u5b9a\u5230\u771f\u5b9e\u8868\u5934\u3002",
              repeated,
              repeated,
              "\u69fd\u4f4d\u5185\u5bb9\u6765\u6e90 name1 \u8fd8\u6ca1\u6709\u7ed1\u5b9a\u5230\u771f\u5b9e\u8868\u5934\u3002",
              "\u69fd\u4f4d\u5185\u5bb9\u6765\u6e90 name2 \u8fd8\u6ca1\u6709\u7ed1\u5b9a\u5230\u771f\u5b9e\u8868\u5934\u3002"
            ]
          };
          const validateBodies = [];
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2DEDUP", name: "Dedup Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2DEDUP", name: "Dedup Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  checks: {},
                  field_bindings: { name: "Name", design: "" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { field: "", options: [] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) {
              validateBodies.push(JSON.parse(options.body));
              return response({ validation: { can_save: true, can_publish: false, checks } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();
          await global.validateCurrentConfig(false);
          await flush();

          const fieldsCheck = app.elements.v2CheckRail.children.find((item) => item.dataset.checkKey === "fields");
          assert.strictEqual(fieldsCheck.dataset.reason, "");
          assert(fieldsCheck.title.includes("\u8ba2\u5355\u5b57\u6bb5 design"));
          assert(fieldsCheck.title.includes("\u53e6\u6709 1 \u9879"));
          assert(validateBodies.length >= 2);
          const lastBody = validateBodies[validateBodies.length - 1];
          assert.strictEqual(lastBody.config.checks.fields.status, "pending");
          assert.strictEqual(lastBody.config.checks.fields.reason, "");
          assert(!app.elements.publishBlockerText.textContent.includes("\u771f\u5b9e\u8868\u5934"));
          assert(app.elements.publishBlockerText.textContent.length < 80);
          assert(app.elements.blockerList.children.length <= 8);
          assert(app.elements.blockerList.textContent.length < 260);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_validation_preserves_legitimate_manual_check_reason():
    run_node(
        r"""
        (async () => {
          const manualReason = "\u5b57\u6bb5\u6620\u5c04\u5df2\u7531\u674e\u5de5\u590d\u6838";
          const checks = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"].reduce((result, key) => {
            result[key] = { status: "confirmed", reason: "" };
            return result;
          }, {});
          checks.fields = {
            status: "pending",
            reasons: ["\u8ba2\u5355\u5b57\u6bb5 design \u8fd8\u6ca1\u6709\u7ed1\u5b9a\u5230\u771f\u5b9e\u8868\u5934\u3002"]
          };
          const validateBodies = [];
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2MANUAL", name: "Manual Reason Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2MANUAL", name: "Manual Reason Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  checks: { fields: { status: "pending", reason: manualReason } },
                  field_bindings: { name: "Name", design: "" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { field: "", options: [] }
                  }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) {
              validateBodies.push(JSON.parse(options.body));
              return response({ validation: { can_save: true, can_publish: false, checks } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          assert.strictEqual(global.manualCheckReasonForConfig("\u4eba\u5de5\u6838\u9a8c\u9879\u8fd8\u6ca1\u6709\u786e\u8ba4\u3002"), "");
          assert.strictEqual(global.manualCheckReasonForConfig("\u8ba2\u5355\u5b57\u6bb5\u5df2\u4e0e\u5e97\u94fa\u786e\u8ba4"), "\u8ba2\u5355\u5b57\u6bb5\u5df2\u4e0e\u5e97\u94fa\u786e\u8ba4");
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();
          await global.validateCurrentConfig(false);
          await flush();

          const fieldsCheck = app.elements.v2CheckRail.children.find((item) => item.dataset.checkKey === "fields");
          assert.strictEqual(fieldsCheck.dataset.reason, manualReason);
          assert(fieldsCheck.title.includes("\u8ba2\u5355\u5b57\u6bb5 design"));
          assert(validateBodies.length >= 2);
          const lastBody = validateBodies[validateBodies.length - 1];
          assert.strictEqual(lastBody.config.checks.fields.status, "pending");
          assert.strictEqual(lastBody.config.checks.fields.reason, manualReason);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_normalizes_server_passed_as_confirmed():
    run_node(
        r"""
        (async () => {
          const app = createApp(async () => response({ templates: [] }));
          await flush();
          assert.strictEqual(safeStatus("passed"), "confirmed");
          updateCheckRail({ output: { status: "passed", reason: "" } });
          const outputCheck = app.elements.v2CheckRail.children.find((item) => item.dataset.checkKey === "output");
          assert.strictEqual(outputCheck.dataset.status, "confirmed");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_failure_does_not_navigate_to_preview():
    run_node(
        r"""
        (async () => {
          let saveCount = 0;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2BLOCKED", name: "Blocked Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: {
              metadata: { template_id: "V2BLOCKED", name: "Blocked Demo", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }], designs: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
              config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: false, can_publish: false, checks: {} } });
            if (textUrl.endsWith("/draft") && options.method === "POST") { saveCount += 1; return response({}); }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();
          app.elements.saveAndNextOptionBtn.dispatch("click");
          for (let index = 0; index < 6; index += 1) await flush();
          assert.strictEqual(saveCount, 0);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "rules");
          assert(app.elements.draftSaveStatusText.textContent.includes("\u672a\u4fdd\u5b58"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_stage_confirmation_persists_only_current_stage_checks():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let currentDraft = {
            metadata: { template_id: "V2CONFIRM", name: "Confirm Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_main" }], designs: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
            config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] }, font: { field: "", options: [] } }] }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2CONFIRM", name: "Confirm Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) {
              const checks = JSON.parse(options.body).config.checks;
              return response({ validation: { can_save: true, can_publish: false, checks } });
            }
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
          app.elements.confirmStageBtn.dispatch("click");
          for (let index = 0; index < 8; index += 1) await flush();
          assert(draftSaveBody);
          assert.deepStrictEqual(["output", "fields", "options"].map((key) => draftSaveBody.config.checks[key].status), ["confirmed", "confirmed", "confirmed"]);
          assert.deepStrictEqual(["slots", "content", "dimensions", "colors", "preview"].map((key) => draftSaveBody.config.checks[key].status), ["pending", "pending", "pending", "pending", "pending"]);
          assert.strictEqual(draftSaveBody.config.checks.output.reason, "\u5355 Output_main \u81ea\u52a8\u786e\u8ba4");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_stage_confirmation_rolls_back_when_draft_write_fails():
    run_node(
        r"""
        (async () => {
          let draftPostCount = 0;
          let finishDraftWrite;
          const currentDraft = {
            metadata: { template_id: "V2CONFIRMFAIL", name: "Confirm Fail Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_main" }], designs: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
            config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] }, font: { field: "", options: [] } }] }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2CONFIRMFAIL", name: "Confirm Fail Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) {
              const checks = JSON.parse(options.body).config.checks;
              return response({ validation: { can_save: true, can_publish: false, checks } });
            }
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftPostCount += 1;
              return new Promise((resolve) => { finishDraftWrite = () => resolve(response({ error: { message: "write failed" } }, false)); });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();
          const check = (key) => document.querySelector('#v2CheckRail .check-item[data-check-key="' + key + '"]');
          assert.strictEqual(check("fields").dataset.status, "pending");
          assert.strictEqual(check("options").dataset.status, "pending");
          app.elements.confirmStageBtn.dispatch("click");
          await flush();
          assert.strictEqual(draftPostCount, 1);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.isSavingDraft, true);
          assert.strictEqual(app.elements.confirmStageBtn.disabled, true);
          app.elements.confirmStageBtn.dispatch("click");
          await flush();
          assert.strictEqual(draftPostCount, 1);
          finishDraftWrite();
          for (let index = 0; index < 8; index += 1) await flush();
          assert.strictEqual(check("output").dataset.status, "confirmed");
          assert.strictEqual(check("fields").dataset.status, "pending");
          assert.strictEqual(check("options").dataset.status, "pending");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.isSavingDraft, false);
          assert.strictEqual(app.elements.confirmStageBtn.disabled, false);
          assert(app.elements.draftSaveStatusText.textContent.includes("\u4fdd\u5b58\u5931\u8d25"));
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
