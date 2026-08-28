import subprocess
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


HARNESS = r"""
const assert = require("assert");
const fs = require("fs");

const ids = [
  "v2CheckRail", "templateList", "templateSearch", "templateId", "templateName", "shopName",
  "v2LocalHealthText", "v2CentralHealthText",
  "newTemplateBtn", "refreshTemplatesBtn", "templateListStats", "currentTemplateContext", "backToUploadBtn", "draftStatusBadge", "draftVersion", "createDraftFromPublishedBtn",
  "uploadScanBadge", "scanSummaryMetrics", "scanSummaryWarning", "enterStructureBtn",
  "aiDropzone", "aiFile", "scanTemplateBtn", "rescanTemplateBtn", "scanProgress",
  "scanSummary", "scanEmptyState", "structureSearch", "structureTree", "toggleDesignsBtn",
  "toggleFontsBtn", "outputConfigRows", "outlineTextToggle", "pathfinderMergeToggle", "fieldBindingRows", "optionMappingRows", "selectedNodeSummary",
  "styleDimensionRows", "contentOptionRows", "blockerList", "draftSummary", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn",
  "publishBlockerText", "draftSaveStatusText", "scanRunningOverlay", "scanRunningMessage", "scanFailedOverlay", "scanFailedMessage", "retryScanBtn", "closeScanFailedBtn",
  "optionRuleSearch", "optionRuleList", "optionRuleStats", "optionRuleCount", "pendingOnlyBtn", "selectedOptionTitle",
  "selectedOptionPendingBadge", "optionContentPreset", "optionProcessingHelp", "assetBindingRows", "templateCapabilityPanel",
  "capabilityEvidenceRows", "colorRuleTitle", "colorRuleRows", "dimensionRuleRows", "fontDependencyRows", "confirmStageBtn", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "preflightFailedOverlay", "preflightFailedMessage",
  "preflightIssueList", "closePreflightFailedBtn", "returnToSampleDataBtn", "previewSampleRows", "previewValidationRows"
  , "previewSideTabs", "previewArtworkPane", "previewRuntimeBadge", "previewTrialStatus", "previewWarningList", "previewValidationStatus",
  "versionPublishStatus", "draftVersionSummary", "draftTrialSummary", "currentVersionSummary", "currentVersionMeta", "rollbackVersionSummary", "rollbackVersionMeta", "publishNotes"
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
  removeAttribute(name) {
    delete this.attributes[name];
  }
  focus() {
    this.focused = true;
  }
  scrollIntoView() {
    this.scrolled = true;
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
  ["aiFile", "outlineTextToggle", "pathfinderMergeToggle"].forEach((id) => { elements[id].tagName = "INPUT"; });
  ["templateSearch", "templateId", "templateName", "shopName", "structureSearch", "optionRuleSearch", "publishNotes"].forEach((id) => { elements[id].tagName = "INPUT"; });
  ["optionContentPreset"].forEach((id) => { elements[id].tagName = "SELECT"; });
  ["scanTemplateBtn", "rescanTemplateBtn", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn", "retryScanBtn", "closeScanFailedBtn", "toggleDesignsBtn", "toggleFontsBtn", "pendingOnlyBtn", "confirmStageBtn", "saveAndNextOptionBtn", "rerunTrialRenderBtn", "closePreflightFailedBtn", "returnToSampleDataBtn", "refreshTemplatesBtn", "createDraftFromPublishedBtn"].forEach((id) => { elements[id].tagName = "BUTTON"; });
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
    getElementById: (id) => elements[id] || Object.values(elements).flatMap((root) => allDescendants(root)).find((node) => node.id === id) || null,
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
      const parts = selector.split(",").map((item) => item.trim());
      const classNames = parts.map((item) => {
        const match = item.match(/^\.([A-Za-z0-9_-]+)$/);
        return match ? match[1] : "";
      });
      if (classNames.length && classNames.every(Boolean)) {
        const nodes = Array.from(new Set(Object.values(elements).flatMap((root) => [root, ...allDescendants(root)])));
        return nodes.filter((child) => classNames.some((name) => (child.className || "").split(/\s+/).includes(name)));
      }
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

function createApp(fetchImpl, fileNames, locationSearch) {
  const { document, elements } = makeDocument();
  global.document = document;
  global.window = global;
  global.window.location = { search: locationSearch || "" };
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
    "workbench-preview-state.js",
    "workbench-preview-versions.js",
    "workbench-preview.js",
    "workbench-preview-actions.js",
    "workbench-view-tables.js",
    "workbench-validation-checks.js",
    "workbench-validation-targets.js",
    "workbench-validation-navigation.js",
    "workbench-validation-blockers.js",
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


def run_node(script: str, *, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        ["node", "-e", HARNESS + "\n" + textwrap.dedent(script)],
        cwd=cwd or "C:/Users/Administrator/Desktop/image/custom-renderer-v2-template-workbench",
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


def test_v2_workbench_header_marks_both_services_ready_after_existing_template_request():
    run_node(
        r"""
        (async () => {
          let requests = 0;
          const app = createApp(async (url) => {
            requests += 1;
            assert.strictEqual(url, "/api/v2/templates");
            return response({ templates: [] });
          });
          await flush();
          assert.strictEqual(requests, 1);
          assert.strictEqual(app.elements.v2LocalHealthText.textContent, "本机已就绪");
          assert.strictEqual(app.elements.v2CentralHealthText.textContent, "中央服务已连接");
          assert(!app.elements.v2CentralHealthText.classList.contains("is-error"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """,
        cwd=PROJECT_ROOT,
    )


def test_v2_workbench_header_marks_central_unreachable_when_existing_template_request_fails():
    run_node(
        r"""
        (async () => {
          const app = createApp(async () => {
            throw new Error("Failed to fetch");
          });
          await flush();
          assert.strictEqual(app.elements.v2LocalHealthText.textContent, "本机已就绪");
          assert.strictEqual(app.elements.v2CentralHealthText.textContent, "中央服务不可达");
          assert(app.elements.v2CentralHealthText.classList.contains("is-error"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """,
        cwd=PROJECT_ROOT,
    )


def test_v2_workbench_opens_the_published_shared_template_requested_by_direct_link():
    run_node(
        r"""
        (async () => {
          const requests = [];
          const sharedTemplate = {
            metadata: { template_id: "SHARED001", name: "同事共享模板", shop_name: "Demo Shop" },
                manifest: { version: "v0003" },
            config: {
              template: { template_id: "SHARED001" },
              outputs: [{ key: "Output_main", display_name: "主效果图" }],
              field_bindings: { slot_name: "Personalization" },
              option_mappings: [],
              checks: {}
            },
            scan: {
              outputs: [{
                key: "Output_main",
                design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }] }] },
                font: { options: [] },
                style: { options: [] }
              }]
            }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            requests.push({ url: textUrl, method: options.method || "GET" });
            if (textUrl === "/api/v2/templates") {
              return response({ templates: [{ template_id: "OTHER001", name: "其他模板" }, { template_id: "SHARED001", name: "同事共享模板", publication: { status: "active", current_version: "v0003" } }] });
            }
            if (textUrl === "/api/v2/templates/SHARED001/published") return response({ published: sharedTemplate });
            if (textUrl === "/api/v2/templates/SHARED001/draft-from-published" && options.method === "POST") {
              return response({ draft: { ...sharedTemplate, manifest: { draft_revision: "d0008", source_version: "v0003" } } });
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            throw new Error(`unexpected request ${textUrl}`);
          }
          const app = createApp(fakeFetch, undefined, "?template_id=SHARED001");
          const state = global.DrawFlowV2WorkbenchContext.state;
          for (let index = 0; index < 4 && state.stage !== "structure"; index += 1) await flush();
          assert.strictEqual(state.selectedTemplateId, "SHARED001");
          assert.strictEqual(state.stage, "structure");
          assert.strictEqual(state.isPublishedView, true);
          assert.strictEqual(state.draft.config.field_bindings.slot_name, "Personalization");
          assert.strictEqual(state.scan.outputs[0].design.options[0].key, "Design01");
          assert(requests.some((item) => item.url === "/api/v2/templates/SHARED001/published" && item.method === "GET"));
          assert(!requests.some((item) => item.url === "/api/v2/templates/SHARED001/draft"));
          assert.strictEqual(app.elements.templateName.disabled, true);
          assert.strictEqual(app.elements.saveDraftBtn.disabled, true);
          assert(app.elements.scanProgress.textContent.includes("共享配置已加载"));
          assert(app.elements.scanSummaryWarning.textContent.includes("只读查看"));
          assert.strictEqual(app.elements.createDraftFromPublishedBtn.hidden, false);
          global.setWorkbenchStage("rules");
          await flush();
          assert.strictEqual(app.elements.optionContentPreset.disabled, true);
          app.elements.createDraftFromPublishedBtn.dispatch("click");
          await flush();
          assert.strictEqual(state.isPublishedView, false);
          assert.strictEqual(state.draft.manifest.source_version, "v0003");
          assert.strictEqual(app.elements.templateName.disabled, false);
          assert.strictEqual(app.elements.createDraftFromPublishedBtn.hidden, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_v2_workbench_keeps_the_upload_stage_when_the_shared_configuration_cannot_be_read():
    run_node(
        r"""
        (async () => {
          let publishedRequested = 0;
          const publishedTemplate = {
            metadata: { template_id: "SHARED001", name: "同事共享模板" },
            manifest: { version: "v0003" },
            config: { template: { template_id: "SHARED001" } },
            scan: { outputs: [{ key: "Output_main" }] }
          };
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "SHARED001", name: "同事共享模板", publication: { status: "active", current_version: "v0003" } }] });
            if (textUrl === "/api/v2/templates/SHARED001/published") {
              publishedRequested += 1;
              if (publishedRequested === 1) return response({ error: { message: "共享配置不存在" } }, false);
              return response({ published: publishedTemplate });
            }
            throw new Error(`unexpected request ${textUrl}`);
          }
          const app = createApp(fakeFetch, undefined, "?template_id=SHARED001");
          const state = global.DrawFlowV2WorkbenchContext.state;
          for (let index = 0; index < 4 && !publishedRequested; index += 1) await flush();
          await flush();
          assert.strictEqual(state.selectedTemplateId, "SHARED001");
          assert.strictEqual(state.draft, null);
          assert.strictEqual(state.stage, "upload");
          assert(app.elements.scanFailedMessage.textContent.includes("共享配置不存在"));
          app.elements.retryScanBtn.dispatch("click");
          await flush();
          assert.strictEqual(publishedRequested, 2);
          assert.strictEqual(state.isPublishedView, true);
          assert.strictEqual(state.draft.scan.outputs[0].key, "Output_main");
        })().catch((error) => { console.error(error); process.exit(1); });
        """,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_v2_workbench_style_dimensions_are_displayed_as_integers():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let currentDraft = null;
          async function fakeFetch(url, options = {}) {
            if (url === "/api/v2/templates") return response({ templates: [{ template_id: "V2STYLEINT", name: "Style integer" }] });
            if (String(url).endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              currentDraft = { ...currentDraft, config: draftSaveBody.config, manifest: { draft_revision: "d0002" } };
              return response({ draft: currentDraft });
            }
            if (String(url).endsWith("/draft")) {
              currentDraft = {
                metadata: { template_id: "V2STYLEINT", name: "Style integer", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {},
                scan: {
                  outputs: [{ key: "Output_main" }],
                  styles: [
                    { key: "style1", output: "Output_main", dimensions: { width_mm: 50.28, height_mm: 30.28 } },
                    { key: "style2", output: "Output_main", dimensions: { width_mm: 200.398, height_mm: 50.398 } }
                  ]
                }
              };
              return response({ draft: currentDraft });
            }
            if (String(url).endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const rows = document.querySelectorAll("#styleDimensionRows .style-dimension-row");
          assert.strictEqual(rows.length, 2);
          assert.strictEqual(rows[0].querySelector('[data-field="style-width-mm"]').value, "50");
          assert.strictEqual(rows[0].querySelector('[data-field="style-height-mm"]').value, "30");
          assert.strictEqual(rows[1].querySelector('[data-field="style-width-mm"]').value, "200");
          assert.strictEqual(rows[1].querySelector('[data-field="style-height-mm"]').value, "50");

          app.elements.saveDraftBtn.dispatch("click");
          for (let index = 0; index < 16; index += 1) await flush();
          assert(draftSaveBody);
          const savedStyle = draftSaveBody.config.outputs[0].style.options.find((option) => option.key === "style1");
          assert.strictEqual(savedStyle.dimensions.width_mm, 50);
          assert.strictEqual(savedStyle.dimensions.height_mm, 30);
          const savedStyle2 = draftSaveBody.config.outputs[0].style.options.find((option) => option.key === "style2");
          assert.strictEqual(savedStyle2.dimensions.width_mm, 200);
          assert.strictEqual(savedStyle2.dimensions.height_mm, 50);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_confirm_structure_stage_saves_and_opens_rules():
    run_node(
        r"""
        (async () => {
          const confirmedChecks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          let draftSaveBody = null;
          let currentDraft = {
            metadata: { template_id: "V2NEXT", name: "Next stage", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_main" }], fields: [] },
            config: { outputs: [], field_bindings: { name: "Name" }, option_mappings: [], checks: {} }
          };
          async function fakeFetch(url, options = {}) {
            if (url === "/api/v2/templates") return response({ templates: [{ template_id: "V2NEXT", name: "Next stage" }] });
            if (String(url).endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (String(url).endsWith("/validate")) return response({ validation: { can_save: true, checks: confirmedChecks } });
            if (String(url).endsWith("/draft") && options.method === "POST") {
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
          for (let index = 0; index < 16; index += 1) await flush();

          assert(draftSaveBody, "confirm must save the current draft");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "rules");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_field_bindings_accept_chinese_order_headers():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          async function fakeFetch(url, options = {}) {
            if (url === "/api/v2/templates") return response({ templates: [{ template_id: "V2CNFIELD", name: "Chinese field" }] });
            if (String(url).endsWith("/draft") && (!options.method || options.method === "GET")) {
              return response({ draft: {
                metadata: { template_id: "V2CNFIELD", name: "Chinese field", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: { outputs: [{ key: "Output_main" }] },
                config: { outputs: [], field_bindings: { name: "定制信息" }, option_mappings: [], checks: {} }
              }});
            }
            if (String(url).endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (String(url).endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: { metadata: { template_id: "V2CNFIELD", name: "Chinese field", shop_name: "" }, manifest: { draft_revision: "d0002" }, config: draftSaveBody.config, scan: { outputs: [{ key: "Output_main" }] } } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();
          const nameRow = document.querySelectorAll("#fieldBindingRows .field-binding-row")
            .find((row) => row.querySelector('[data-field="binding-field"]').value === "name");
          assert(nameRow);
          assert.strictEqual(nameRow.querySelector('[data-field="binding-column"]').value, "定制信息");
          app.elements.saveDraftBtn.dispatch("click");
          await flush();

          assert(draftSaveBody);
          assert.strictEqual(draftSaveBody.config.field_bindings.name, "定制信息");
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
          assert.strictEqual(model.outputs.length, 1);
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


def test_v2_workbench_legacy_page_scripts_keep_upload_available_without_view_tables():
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
          assert.strictEqual(typeof global.renderTemplateList, "function");
          assert.strictEqual(typeof global.renderTables, "function");
          let filePickerOpened = false;
          app.elements.aiFile.click = () => { filePickerOpened = true; };
          app.elements.aiDropzone.dispatch("click");
          assert.strictEqual(filePickerOpened, true, "点击上传区必须打开文件选择器");
          assert.doesNotThrow(() => app.elements.templateSearch.dispatch("input"));
          app.elements.templateId.value = "LEGACYVIEW";
          app.elements.templateName.value = "Legacy View Demo";
          app.elements.templateId.dispatch("input");
          app.elements.templateName.dispatch("input");
          app.elements.aiFile.dispatch("change", { target: { files: [{ name: "legacy.ai" }] } });
          await flush();
          assert.strictEqual(app.elements.scanTemplateBtn.disabled, false);
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
            "workbench-preview-state.js",
            "workbench-preview-versions.js",
            "workbench-preview.js",
            "workbench-preview-actions.js",
            "workbench-view-tables.js",
            "workbench-validation-checks.js",
            "workbench-validation-targets.js",
            "workbench-validation-navigation.js",
            "workbench-validation-blockers.js",
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
              path: "Template/Output_main",
              design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }] }] },
              font: { options: [{ key: "F1", slots: [{ key: "slot_name" }] }] },
              style: { options: [] },
              summary: { designs: 1, fonts: 1, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 5 }
            }]
          };
          global.DrawFlowV2WorkbenchContext.state.draft = {
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
          };
          assert.strictEqual(typeof global.renderStructureTree, "function");
          assert.strictEqual(app.elements.scanTemplateBtn.disabled, false);
          global.renderStructureTree();
          const outputRows = document.querySelectorAll("#structureTree .structure-tree-row").filter((row) => row.dataset.nodeKind === "output");
          assert.strictEqual(outputRows.length, 1);
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


def test_v2_workbench_existing_option_mappings_are_completed_from_scan():
    run_node(
        r"""
        (async () => {
          const scannedDesigns = Array.from({ length: 22 }, (_, index) => ({
            key: `Design${String(index + 1).padStart(2, "0")}`,
            slots: [{ key: "slot_name" }]
          }));
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2AUTOMAP", name: "Auto Map Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2AUTOMAP", name: "Auto Map Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                config: {
                  field_bindings: { name: "Name", design: "Design" },
                  option_mappings: [
                    { field: "design", source_value: "1", target: "Design01", output: "Output_main", group: "design" },
                    { field: "design", source_value: "01", target: "Design01", output: "Output_main", group: "design" }
                  ],
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "", options: [] }
                  }]
                },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: scannedDesigns },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 22, fonts: 0, styles: 0, slots: 22, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
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

          const rows = document.querySelectorAll("#optionMappingRows .option-mapping-row");
          assert.strictEqual(rows.length, 23);
          assert.strictEqual(rows[0].querySelector('[data-field="mapping-source"]').value, "1");
          assert.strictEqual(rows[1].querySelector('[data-field="mapping-source"]').value, "01");
          assert.strictEqual(rows[1].querySelector('[data-field="mapping-target"]').value, "Design01");
          assert.strictEqual(rows[22].querySelector('[data-field="mapping-source"]').value, "22");
          assert.strictEqual(rows[22].querySelector('[data-field="mapping-target"]').value, "Design22");

          const config = buildControlledConfig();
          assert.strictEqual(config.option_mappings.length, 23);
          assert.deepStrictEqual(config.option_mappings.slice(0, 2).map((item) => item.source_value), ["1", "01"]);
          assert.strictEqual(config.option_mappings[22].source_value, "22");
          assert.deepStrictEqual(config.outputs[0].design.options.map((item) => item.key), scannedDesigns.map((item) => item.key));
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
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true, "真实试渲染完成前禁止发布");
          assert(app.elements.publishBlockerText.textContent.includes("发布核验已完成"));
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


def test_v2_workbench_saves_all_single_slot_font_options_from_scan_defaults():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let validateBody = null;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2FONT12", name: "Font Demo" }] });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: {
                metadata: draftSaveBody.metadata,
                manifest: { draft_revision: "d0002" },
                config: draftSaveBody.config,
                scan: global.DrawFlowV2WorkbenchContext.state.scan
              }});
            }
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2FONT12", name: "Font Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  outputs: [{
                    key: "Output_main",
                    font: { options: Array.from({ length: 12 }, (_, index) => ({
                      key: `F${index + 1}`,
                      path: `Template/Output_main/Font/F${index + 1}`,
                      fixed_object_count: 0,
                      fixed_objects: [],
                      slots: [{
                        key: "slot_name",
                        path: `Template/Output_main/Font/F${index + 1}/slot_name`,
                        type: "TextFrame",
                        text_kind: "point_text",
                        source_field: "name",
                        visible_bounds: [1, 2, 3, 4],
                        dimensions: { width_mm: 15.619, height_mm: 8.49 }
                      }]
                    })) },
                    design: { options: [] },
                    style: { options: [] },
                    summary: { designs: 0, fonts: 12, styles: 0, slots: 12, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "主效果图",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "", options: [] },
                    font: { field: "font", options: [] }
                  }],
                  field_bindings: { name: "定制信息", font: "Font" },
                  option_mappings: Array.from({ length: 12 }, (_, index) => ({
                    field: "font",
                    source_value: `F${index + 1}`,
                    target: `F${index + 1}`,
                    output: "Output_main",
                    group: "font"
                  }))
                }
              }});
            }
            if (textUrl.endsWith("/validate")) {
              validateBody = JSON.parse(options.body);
              return response({ validation: { can_save: true, can_publish: true, checks: {} } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();

          assert.strictEqual(document.querySelectorAll("#contentOptionRows .content-option-group").length, 1);
          const currentSlot = document.querySelectorAll("#contentOptionRows .content-slot-row")[0];
          assert.strictEqual(currentSlot.dataset.group, "font");
          assert.strictEqual(currentSlot.dataset.option, "F1");
          currentSlot.querySelector('[data-field="slot-source-field"]').value = "name";
          currentSlot.querySelector('[data-field="slot-preset"]').value = "direct_text";
          currentSlot.querySelector('[data-field="slot-required"]').value = "required";

          await global.saveDraft();
          await flush();

          const fonts = draftSaveBody.config.outputs[0].font.options;
          const validatedFonts = validateBody.config.outputs[0].font.options;
          assert.strictEqual(fonts.length, 12);
          fonts.forEach((font, index) => {
            assert.strictEqual(font.key, `F${index + 1}`);
            assert.strictEqual(font.content_preset, "direct_text");
            assert.deepStrictEqual(font.font_dependencies, []);
            assert.strictEqual(font.slots.length, 1);
            assert.strictEqual(font.slots[0].key, "slot_name");
            assert.strictEqual(font.slots[0].source_field, "name");
            assert.strictEqual(font.slots[0].preset, "direct_text");
            assert.strictEqual(font.slots[0].required, true);
            assert.deepStrictEqual(font.slots[0].font_dependencies, []);
            ["path", "type", "text_kind", "visible_bounds", "dimensions"].forEach((key) => {
              assert.strictEqual(Object.prototype.hasOwnProperty.call(font.slots[0], key), false);
              assert.strictEqual(Object.prototype.hasOwnProperty.call(validatedFonts[index].slots[0], key), false);
            });
          });
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_label_only_color_field_out_of_slot_rules():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2COLORNOTE", name: "Color Note Demo" }] });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftSaveBody = JSON.parse(options.body);
              return response({ draft: {
                metadata: { template_id: "V2COLORNOTE", name: "Color Note Demo", shop_name: "" },
                manifest: { draft_revision: "d0002" },
                config: draftSaveBody.config,
                scan: global.DrawFlowV2WorkbenchContext.state.scan
              }});
            }
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2COLORNOTE", name: "Color Note Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }],
                  colors: []
                },
                config: {
                  field_bindings: { name: "Name", design: "Design", color: "Color" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "主效果图",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", preset: "direct_text" }] }] },
                    font: { field: "", options: [] }
                  }],
                  option_mappings: [{ field: "design", source_value: "01", target: "Design01", output: "Output_main", group: "design" }]
                }
              }});
            }
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();

          const colorBindingRow = document.querySelectorAll("#fieldBindingRows .field-binding-row")
            .find((row) => row.querySelector('[data-field="binding-field"]').value === "color");
          assert(colorBindingRow, "label-only color field must stay editable");
          assert.strictEqual(colorBindingRow.querySelector('[data-field="binding-column"]').value, "Color");
          assert.strictEqual(app.elements.colorRuleRows.hidden, true);
          assert.strictEqual(app.elements.colorRuleTitle.hidden, true);
          assert.strictEqual(document.querySelector('[data-field="slot-color-binding"]'), null);

          await global.saveDraft();
          await flush();

          assert.strictEqual(draftSaveBody.config.field_bindings.color, "Color");
          assert.deepStrictEqual(draftSaveBody.config.colors, []);
          const savedSlot = draftSaveBody.config.outputs[0].design.options[0].slots[0];
          assert.strictEqual(savedSlot.color_binding, "");
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
          assert(slot1.textContent.includes("尾字 m"));
          assert.strictEqual(slot1.querySelector('[data-field="slot-tail-last"]'), null);

          const config = buildControlledConfig();
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          const saved1 = option.slots.find((slot) => slot.key === "slot_name1");
          const saved2 = option.slots.find((slot) => slot.key === "slot_name2");
              assert.strictEqual(option.content_preset, "mixed_slots");
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


def test_v2_workbench_rules_prefer_anchor_dimensions_over_saved_slot_dimensions():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ANCHOROLD", name: "Anchor Old Slot Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2ANCHOROLD", name: "Anchor Old Slot Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design05",
                      recommended_preset: "tail_text",
                      slots: [{
                        key: "slot_name",
                        source_field: "name",
                        anchor: "anchor_name",
                        dimensions: { width_mm: 163.657, height_mm: 85.03 }
                      }],
                      anchors: [{ key: "anchor_name", dimensions: { width_mm: 150.231, height_mm: 47.231 } }],
                      tails: []
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 1, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: {
                      field: "design",
                      options: [{
                        key: "Design05",
                        content_preset: "tail_text",
                        slots: [{
                          key: "slot_name",
                          source_field: "name",
                          preset: "tail_text",
                          anchor: "anchor_name",
                          dimension_rule: { mode: "slot", width_mm: 163.657, height_mm: 85.03, tolerance_mm: 0.007 }
                          // Historical drafts may retain the retired field. It
                          // must not recreate the control or be written back.
                          , fit_mode: "fill_width", preserve_composition: true
                        }]
                      }]
                    },
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

          const slot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.option === "Design05" && row.dataset.slotKey === "slot_name");
          assert(slot);
          assert.strictEqual(slot.dataset.anchor, "anchor_name");
          const width = slot.querySelector('[data-field="slot-width-mm"]');
          const height = slot.querySelector('[data-field="slot-height-mm"]');
          assert.strictEqual(String(width.value), "150");
          assert.strictEqual(String(height.value), "47");
          assert.strictEqual(width.dataset.rawValue, "150.231");
          assert.strictEqual(height.dataset.rawValue, "47.231");
          assert(width.title.includes("精确边界"));
          assert.strictEqual(slot.querySelector('[data-field="slot-fit-mode"]').value, "fill_width");
          assert.strictEqual(slot.querySelector('[data-field="slot-preserve-composition"]'), null);

          const config = buildControlledConfig();
          const savedSlot = config.outputs[0].design.options.find((item) => item.key === "Design05").slots[0];
          assert.strictEqual(savedSlot.anchor, "anchor_name");
          assert.strictEqual(savedSlot.dimension_rule.mode, "anchor");
          assert.strictEqual(savedSlot.dimension_rule.width_mm, 150.231);
          assert.strictEqual(savedSlot.dimension_rule.height_mm, 47.231);
          assert.strictEqual(savedSlot.fit_mode, "fill_width");
          assert.strictEqual(Object.prototype.hasOwnProperty.call(savedSlot, "preserve_composition"), false);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_reverts_unverified_tail_samples_to_safe_preset():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2TAILHINT", name: "Tail Hint Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2TAILHINT", name: "Tail Hint Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design01",
                      slots: [{ key: "slot_name", source_field: "name", tails: [{ key: "tail_name_last_m" }] }],
                      tails: [{ key: "tail_name_last_m" }]
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 1, anchors: 0, tails: 1, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  field_bindings: { name: "Name", design: "Design" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "主效果图",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{
                      key: "Design01",
                      content_preset: "tail_text",
                      slots: [{ key: "slot_name", source_field: "name", preset: "tail_text" }]
                    }] },
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

          const group = document.querySelectorAll("#contentOptionRows .content-option-group")[0];
          const slot = document.querySelectorAll("#contentOptionRows .content-slot-row")[0];
          const slotPreset = slot.querySelector('[data-field="slot-preset"]');
          const directOption = app.elements.optionContentPreset.children.find((option) => option.value === "direct_text");
          assert.strictEqual(group.dataset.contentPreset, "direct_text");
          assert(group.textContent.includes("尾巴样式"));
          assert(group.textContent.includes("无需手动填写样本"));
          assert.strictEqual(slotPreset.value, "direct_text");
          assert(slotPreset.children.find((option) => option.value === "direct_text").textContent.includes("尾巴文字（已识别）"));
          assert(directOption.textContent.includes("尾巴文字（已识别）"));
          assert.strictEqual(slotPreset.children.find((option) => option.value === "tail_text"), undefined);
          assert.strictEqual(app.elements.optionContentPreset.children.find((option) => option.value === "tail_text"), undefined);
          assert(slot.textContent.includes("尾字 m"));
          assert.strictEqual(slot.querySelector('[data-field="slot-tail-last"]'), null);
          assert.strictEqual(slot.querySelector('[data-field="slot-color-binding"]'), null);
          assert.strictEqual(app.elements.colorRuleRows.hidden, true);
          assert.strictEqual(app.elements.colorRuleTitle.hidden, true);

          const saved = buildControlledConfig().outputs[0].design.options[0];
          assert.strictEqual(saved.content_preset, "direct_text");
          assert.strictEqual(saved.slots[0].preset, "direct_text");
          assert.deepStrictEqual(saved.slots[0].tails, [{ key: "tail_name_last_m", position: "last", sample: "m" }]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_requires_complete_valid_tail_proof_before_recommending_tail_text():
    run_node(
        r"""
        createApp(async () => response({ templates: [] }));
        const partialGlyphMap = { a: 57344 };
        const completeGlyphMap = "abcdefghijklmnopqrstuvwxyz".split("").reduce((result, letter, index) => {
          result[letter] = 57344 + index;
          return result;
        }, {});
        const optionWith = (tail) => ({
          recommended_preset: "direct_text",
          slots: [{ key: "slot_name", tails: [tail] }]
        });

        assert.strictEqual(global.recommendedPresetForOption(optionWith({ key: "tail_name_last_m", glyph_map: partialGlyphMap })), "direct_text");
        assert.strictEqual(global.recommendedPresetForOption(optionWith({ key: "tail_name_last_m", pua_base: 1 })), "direct_text");
        assert.strictEqual(global.recommendedPresetForOption(optionWith({ key: "tail_name_last_m", pua_base: 57344 })), "tail_text");
        assert.strictEqual(global.recommendedPresetForOption(optionWith({ key: "tail_name_last_m", glyph_map: completeGlyphMap })), "tail_text");
        """
    )


def test_v2_workbench_migrates_proven_slot_sources_and_removes_orphan_title_binding():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2TITLEFIELD", name: "Title Field Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2TITLEFIELD", name: "Title Field Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design02",
                      slots: [
                        { key: "slot_name1", source_field: "name", tails: [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }] },
                        { key: "slot_name2", source_field: "name2" }
                      ]
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  field_bindings: { name: "Name", design: "Design", name1: "Name", name2: "Title", title: "Title" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: {
                      field: "design",
                      options: [{
                        key: "Design02",
                        content_preset: "direct_text",
                        slots: [
                          { key: "slot_name1", source_field: "name", preset: "direct_text", tails: [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }] },
                          { key: "slot_name2", source_field: "title" }
                        ]
                      }]
                    },
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
          global.setWorkbenchStage("structure");
          await flush();

          const rows = document.querySelectorAll("#fieldBindingRows .field-binding-row");
          const fields = rows.map((row) => row.querySelector('[data-field="binding-field"]').value);
          assert(fields.includes("name"));
          assert(fields.includes("name1"));
          assert(fields.includes("name2"));
          assert(!fields.includes("title"));

          const config = buildControlledConfig();
          assert.deepStrictEqual(config.field_bindings, { name: "Name", design: "Design", name1: "Name", name2: "Title" });
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          assert.deepStrictEqual(option.slots.map((slot) => [slot.key, slot.source_field, slot.preset]), [
            ["slot_name1", "name1", "tail_text"],
            ["slot_name2", "name2", "direct_text"]
          ]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_slot_source_migration_requires_matching_scan_option_and_slot():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const state = global.DrawFlowV2WorkbenchContext.state;
          const configured = {
            field_bindings: { name: "Name", name1: "Name", name2: "Title", title: "Title", design: "Design" },
            outputs: [{
              key: "Output_main",
              design: { field: "design", options: [{
                key: "Design02",
                content_preset: "mixed_slots",
                slots: [
                  { key: "slot_name1", source_field: "name", tails: [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }] },
                  { key: "slot_name2", source_field: "title" }
                ]
              }] },
              font: { field: "", options: [] },
              style: { field: "", options: [] }
            }]
          };
          state.draft = { config: configured };

          state.scan = {};
          assert.deepStrictEqual(global.configuredSlotSourceFields(), ["name", "title"]);

          state.scan = { outputs: [{
            key: "Output_main",
            design: { options: [{ key: "Design04", slots: [{ key: "slot_name1" }, { key: "slot_name2" }] }] },
            font: { options: [] },
            style: { options: [] }
          }] };
          assert.deepStrictEqual(global.configuredSlotSourceFields(), ["name", "title"]);

          state.scan = { outputs: [{
            key: "Output_main",
            design: { options: [{ key: "Design02", slots: [{ key: "slot_name1" }, { key: "slot_other" }] }] },
            font: { options: [] },
            style: { options: [] }
          }] };
          assert.deepStrictEqual(global.configuredSlotSourceFields(), ["name1", "title"]);

          state.scan.outputs[0].design.options[0].slots[1] = { key: "slot_name2" };
          assert.deepStrictEqual(global.configuredSlotSourceFields(), ["name1", "name2"]);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_rescan_adds_new_slot_field_and_preserves_it_in_config():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2INCREMENTAL", name: "Incremental" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2INCREMENTAL", name: "Incremental", shop_name: "Demo" },
              manifest: { draft_revision: "d0002" },
              scan: { outputs: [{
                key: "Output_main",
                design: { options: [{
                  key: "Design02",
                  slots: [{ key: "slot_name" }, { key: "slot_extra" }],
                  anchors: [], tails: [], assets: []
                }] },
                font: { options: [] }, style: { options: [] }
              }] },
              config: {
                field_bindings: { name: "Name", design: "Design" },
                outputs: [{
                  key: "Output_main", display_name: "Main", component_key: "main",
                  style: { field: "", options: [] },
                  design: { field: "design", options: [{
                    key: "Design02", content_preset: "mixed_slots",
                    slots: [{ key: "slot_name", source_field: "name", preset: "direct_text" }],
                    assets: []
                  }] },
                  font: { field: "", options: [] }
                }]
              }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const rows = document.querySelectorAll("#fieldBindingRows .field-binding-row");
          const byField = Object.fromEntries(rows.map((row) => [row.querySelector('[data-field="binding-field"]').value, row]));
          assert(byField.name);
          assert(byField.extra, "new scanned slot must appear in field bindings");
          byField.extra.querySelector('[data-field="binding-column"]').value = "Title";

          const config = buildControlledConfig();
          assert.strictEqual(config.field_bindings.extra, "Title");
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          assert.deepStrictEqual(option.slots.map((slot) => [slot.key, slot.source_field]), [
            ["slot_name", "name"],
            ["slot_extra", "extra"]
          ]);
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


def test_v2_workbench_locks_mixed_summary_and_preserves_name1_name2_contract():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2MIXED", name: "Mixed Demo" }] });
            if (textUrl.endsWith("/draft")) {
              return response({ draft: {
                metadata: { template_id: "V2MIXED", name: "Mixed Demo", shop_name: "" },
                manifest: { draft_revision: "d0001" },
                scan: {
                  "$schema": "custom-renderer/v2-template-scan",
                  outputs: [{
                    key: "Output_main",
                    design: { options: [{
                      key: "Design02",
                      slots: [
                        { key: "slot_name1", tails: [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }] },
                        { key: "slot_name2" }
                      ],
                      anchors: [],
                      tails: [{ key: "tail_name1_last_m", position: "last", sample: "m" }],
                      assets: []
                    }] },
                    font: { options: [] },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 0, styles: 0, slots: 2, anchors: 0, tails: 1, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  field_bindings: { name: "Name", name1: "Name", name2: "Title", title: "Title", design: "Design" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [{
                      key: "Design02",
                      content_preset: "direct_text",
                      slots: [
                        { key: "slot_name1", source_field: "name", preset: "direct_text", tails: [{ key: "tail_name1_last_m", position: "last", sample: "m", pua_base: 61440 }] },
                        { key: "slot_name2", source_field: "title", preset: "direct_text" }
                      ],
                      assets: []
                    }] },
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

          const select = app.elements.optionContentPreset;
          const group = document.querySelectorAll("#contentOptionRows .content-option-group")[0];
          assert.strictEqual(select.value, "mixed_slots");
          assert.strictEqual(select.disabled, true);
          assert.strictEqual(select.children.length, 1);
          assert.strictEqual(group.dataset.contentPreset, "mixed_slots");
          assert(app.elements.optionProcessingHelp.textContent.includes("只读汇总"));
          assert(app.elements.optionProcessingHelp.textContent.includes("自己的订单字段"));
          assert(!select.classList.contains("v2-validation-control-error"));
          assert.strictEqual(select.getAttribute("aria-invalid"), undefined);

          select.value = "split_by_pipe";
          select.dispatch("change");
          await flush();
          const rows = document.querySelectorAll("#contentOptionRows .content-slot-row");
          assert.strictEqual(group.dataset.contentPreset, "mixed_slots");
          assert.deepStrictEqual(rows.map((row) => [
            row.querySelector('[data-field="slot-source-field"]').value,
            row.querySelector('[data-field="slot-preset"]').value
          ]), [["name1", "tail_text"], ["name2", "direct_text"]]);

          const config = buildControlledConfig();
          const option = config.outputs[0].design.options.find((item) => item.key === "Design02");
          assert.strictEqual(option.content_preset, "mixed_slots");
          assert.deepStrictEqual(option.slots.map((slot) => [slot.source_field, slot.preset]), [["name1", "tail_text"], ["name2", "direct_text"]]);
          assert.strictEqual(config.field_bindings.title, undefined);

          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.content = { status: "blocked", reason: "请确认当前槽位处理。" };
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [{ path: "$.outputs[0].design.options[0].content_preset", check: "content", status: "blocked", code: "contract_invalid", reason: "请确认当前槽位处理。" }]
          });
          const lowerPreset = document.querySelectorAll("#contentOptionRows .content-slot-row")[0].querySelector('[data-field="slot-preset"]');
          assert(!select.classList.contains("v2-validation-control-error"));
          assert.strictEqual(select.getAttribute("aria-invalid"), undefined);
          assert(lowerPreset.classList.contains("v2-validation-control-error"));
          const jump = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(jump);
          jump.dispatch("click");
          assert.strictEqual(lowerPreset.focused, true);

          const lowerSource = document.querySelectorAll("#contentOptionRows .content-slot-row")[0].querySelector('[data-field="slot-source-field"]');
          const latest = buildControlledConfig();
          latest.outputs[0].design.options[0].slots[0].source_field = "";
          global.DrawFlowV2WorkbenchContext.state.lastValidatedConfig = latest;
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [{ path: "$.outputs[0].design.options[0].slots", check: "content", status: "blocked", code: "mixed_slots_source_missing", reason: "每个槽位都必须选择内容来源。" }]
          });
          assert(lowerSource.classList.contains("v2-validation-control-error"));
          let slotAction = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(slotAction);
          assert.strictEqual(slotAction.textContent, "前往修改");
          assert(!app.elements.blockerList.textContent.includes("重新扫描"));
          slotAction.dispatch("click");
          assert.strictEqual(lowerSource.focused, true);

          latest.outputs[0].design.options[0].slots[0].source_field = "name1";
          latest.outputs[0].design.options[0].slots[0].preset = "asset_replace";
          latest.outputs[0].design.options[0].slots[0].asset_key = "initial";
          global.DrawFlowV2WorkbenchContext.state.lastValidatedConfig = latest;
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [{ path: "$.outputs[0].design.options[0].slots", check: "content", status: "blocked", code: "mixed_slots_preset_invalid", reason: "请修改不适用的槽位处理方式。" }]
          });
          assert(lowerPreset.classList.contains("v2-validation-control-error"));
          slotAction = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(slotAction);
          assert.strictEqual(slotAction.textContent, "前往修改");
          assert(!app.elements.blockerList.textContent.includes("重新扫描"));
          slotAction.dispatch("click");
          assert.strictEqual(lowerPreset.focused, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_routes_scan_owned_issues_to_real_rescan_action():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2RESCAN", name: "Rescan Demo" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2RESCAN", name: "Rescan Demo", shop_name: "Demo" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{
                key: "Output_main",
                design: { options: [{
                  key: "Design02",
                  slots: [{ key: "slot_name1", anchor: "anchor_name1", tails: [{ key: "tail_name1_last_m" }] }],
                  assets: [{ asset_key: "icon", slot: "slot_icon", supported_values: ["star"] }]
                }] },
                font: { options: [] }, style: { options: [] }
              }] },
              config: {
                field_bindings: { name1: "Name", design: "Design" },
                outputs: [{
                  key: "Output_main", display_name: "Main", component_key: "main",
                  style: { field: "", options: [] },
                  design: { field: "design", options: [{
                    key: "Design02", content_preset: "tail_text",
                    slots: [{
                      key: "slot_name1", source_field: "name1", preset: "tail_text",
                      anchor: "anchor_name1", asset_key: "icon",
                      dimension_rule: { mode: "anchor", width_mm: 20, height_mm: 10, tolerance_mm: 0.007 },
                      tails: [{ key: "tail_name1_last_m" }]
                    }],
                    assets: [{ asset_key: "icon", slot: "slot_icon", supported_values: ["star"] }]
                  }] },
                  font: { field: "", options: [] }
                }]
              }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();

          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.slots = { status: "blocked", reason: "模板扫描结果需要修正。" };
          checks.dimensions = { status: "blocked", reason: "槽位边界需要重新确认。" };
          const validation = {
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [
              { path: "$.outputs[0].design.options[0].slots[0].asset_key", check: "slots", status: "blocked", code: "asset_missing", reason: "素材范围需要重新扫描。" },
              { path: "$.outputs[0].design.options[0].slots[0].dimension_rule", check: "dimensions", status: "blocked", code: "dimension_tolerance_invalid", reason: "槽位边界需要重新扫描。" },
              { path: "$.outputs[0].design.options[0].slots[0].tails[0].key", check: "slots", status: "blocked", code: "tail_belongs_to_slot", reason: "尾巴样本需要重新扫描。" }
            ]
          };
          global.updateBlockers(validation);

          const slotRow = document.querySelectorAll("#contentOptionRows .content-slot-row")[0];
          const assetInput = slotRow.querySelector('[data-field="slot-asset-key"]');
          const widthInput = slotRow.querySelector('[data-field="slot-width-mm"]');
          assert(!slotRow.classList.contains("v2-validation-row-error"));
          assert(!assetInput.classList.contains("v2-validation-control-error"));
          assert(!widthInput.classList.contains("v2-validation-control-error"));
          assert(app.elements.rescanTemplateBtn.classList.contains("v2-validation-control-error"));
          assert(!app.elements.blockerList.textContent.includes("前往修改"));
          const actions = app.elements.blockerList.children.map((item) => item.children.find((child) => child.tagName === "BUTTON"));
          assert(actions.every((button) => button && button.textContent === "重新扫描"));
          actions[0].dispatch("click");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "upload");
          assert.strictEqual(app.elements.rescanTemplateBtn.focused, true);

          app.elements.rescanTemplateBtn.disabled = true;
          global.updateBlockers(validation);
          assert(app.elements.blockerList.children.every((item) => !item.children.some((child) => child.tagName === "BUTTON")));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_distinct_rescan_business_locations():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          app.elements.rescanTemplateBtn.disabled = false;
          global.DrawFlowV2WorkbenchContext.state.lastValidatedConfig = {
            outputs: [{
              key: "Output_main",
              design: { options: ["Design02", "Design04"].map((key) => ({
                key,
                content_preset: "asset_replace",
                slots: [{ key: "slot_icon", source_field: "name", preset: "asset_replace", asset_key: "icon" }]
              })) },
              font: { options: [] }, style: { options: [] }
            }]
          };
          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.slots = { status: "blocked", reason: "当前槽位缺少对应素材。" };
          const first = {
            path: "$.outputs[0].design.options[0].slots[0].asset_key",
            check: "slots", status: "blocked", code: "asset_missing", reason: "当前槽位缺少对应素材。"
          };
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [
              first,
              { ...first },
              { ...first, path: "$.outputs[0].design.options[1].slots[0].asset_key" }
            ]
          });

          assert.strictEqual(app.elements.blockerList.children.length, 2, "same location dedupes, distinct options remain separate");
          assert(app.elements.blockerList.textContent.includes("Design02 的第 1 个槽位"));
          assert(app.elements.blockerList.textContent.includes("Design04 的第 1 个槽位"));
          assert(!app.elements.blockerList.textContent.includes("$.outputs"));
          app.elements.blockerList.children.forEach((item) => {
            const button = item.children.find((child) => child.tagName === "BUTTON");
            assert(button);
            assert.strictEqual(button.textContent, "重新扫描");
          });
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_jumps_to_editable_slot_in_an_unselected_option():
    run_node(
        r"""
        (async () => {
          const options = ["Design02", "Design04"].map((key, index) => ({
            key,
            content_preset: "direct_text",
            slots: [{ key: `slot_name${index + 1}`, source_field: `name${index + 1}`, preset: index ? "path_text" : "direct_text" }]
          }));
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2CROSSOPTION", name: "Cross option" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2CROSSOPTION", name: "Cross option", shop_name: "Demo" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{
                key: "Output_main",
                design: { options: options.map((option) => ({ key: option.key, slots: option.slots })) },
                font: { options: [] }, style: { options: [] }
              }] },
              config: {
                field_bindings: { design: "Design", name1: "Name", name2: "Title" },
                outputs: [{
                  key: "Output_main", display_name: "Main", component_key: "main",
                  style: { field: "", options: [] },
                  design: { field: "design", options },
                  font: { field: "", options: [] }
                }]
              }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();
          assert(app.elements.selectedOptionTitle.textContent.includes("Design02"));

          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.content = { status: "blocked", reason: "请修改槽位处理。" };
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [{
              path: "$.outputs[0].design.options[1].slots[0].preset",
              check: "content", status: "blocked", code: "direct_text_slot_preset_invalid", reason: "请修改槽位处理。"
            }]
          });

          const jump = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(jump, "unselected option still needs an actionable jump");
          assert.strictEqual(jump.textContent, "前往修改");
          jump.dispatch("click");
          assert(app.elements.selectedOptionTitle.textContent.includes("Design04"));
          const preset = document.querySelectorAll("#contentOptionRows .content-slot-row")[0].querySelector('[data-field="slot-preset"]');
          assert.strictEqual(preset.value, "path_text");
          assert.strictEqual(preset.focused, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_pending_field_and_mapping_issues_actionable():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2PENDING", name: "Pending" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2PENDING", name: "Pending", shop_name: "Demo" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{
                key: "Output_main",
                design: { options: [{ key: "Design02", slots: [{ key: "slot_name1" }] }] },
                font: { options: [] }, style: { options: [] }
              }] },
              config: {
                field_bindings: { design: "Design" },
                option_mappings: [],
                outputs: [{
                  key: "Output_main", display_name: "Main", component_key: "main",
                  style: { field: "", options: [] },
                  design: { field: "design", options: [{
                    key: "Design02", content_preset: "direct_text",
                    slots: [{ key: "slot_name1", source_field: "name1", preset: "direct_text" }]
                  }] },
                  font: { field: "", options: [] }
                }]
              }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.fields = { status: "pending", reason: "字段尚未绑定。" };
          checks.options = { status: "pending", reason: "选项尚未映射。" };
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [
              { path: "$.outputs[0].design.options[0].slots[0].source_field", check: "fields", status: "pending", code: "field_binding_missing", reason: "槽位内容来源还没有绑定到真实表头。" },
              { path: "$.checks.fields", check: "fields", status: "pending", code: "manual_check_pending", reason: "人工核验项还没有确认。" },
              { path: "$.outputs[0].design.options[0].key", check: "options", status: "pending", code: "option_mapping_missing", reason: "当前选项还没有订单原值映射。" },
              { path: "$.checks.options", check: "options", status: "pending", code: "manual_check_pending", reason: "人工核验项还没有确认。" }
            ]
          });

          assert.strictEqual(app.elements.blockerList.children.length, 2, "specific pending issues suppress generic manual rows");
          const bindingRow = document.querySelectorAll("#fieldBindingRows .field-binding-row")
            .find((row) => row.querySelector('[data-field="binding-field"]').value === "name1");
          const bindingColumn = bindingRow.querySelector('[data-field="binding-column"]');
          const mappingRow = document.querySelectorAll("#optionMappingRows .option-mapping-row")
            .find((row) => row.querySelector('[data-field="mapping-target"]').value === "Design02");
          const mappingSource = mappingRow.querySelector('[data-field="mapping-source"]');
          assert(bindingColumn.classList.contains("v2-validation-control-error"));
          assert(mappingSource.classList.contains("v2-validation-control-error"));
          assert(app.elements.blockerList.textContent.includes("字段 name1"));
          assert(app.elements.blockerList.textContent.includes("Design02 的订单原值"));
          const actions = app.elements.blockerList.children.map((item) => item.children.find((child) => child.tagName === "BUTTON"));
          assert(actions.every((button) => button && button.textContent === "前往修改"));
          actions[0].dispatch("click");
          assert.strictEqual(bindingColumn.focused, true);
          actions[1].dispatch("click");
          assert.strictEqual(mappingSource.focused, true);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_routes_pending_scan_color_and_manual_checks_to_real_actions():
    run_node(
        r"""
        (async () => {
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ACTIONS", name: "Actions" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2ACTIONS", name: "Actions", shop_name: "Demo" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main", design: { options: [{ key: "Design02", slots: [{ key: "slot_name" }] }] }, font: { options: [] }, style: { options: [] } }] },
              config: {
                field_bindings: { design: "Design", name: "Name", color: "Color" },
                outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "design", options: [{ key: "Design02", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", preset: "direct_text", color_binding: "color" }] }] }, font: { field: "", options: [] } }]
              }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("rules");
          await flush();

          const confirmed = () => Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          let checks = confirmed();
          checks.colors = { status: "pending", reason: "请确认颜色处理。" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [{ path: "$.colors", check: "colors", status: "pending", code: "color_samples_pending", reason: "没有扫描到可配置颜色样本。" }]
          });
          let action = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(action);
          assert.strictEqual(action.textContent, "前往修改");
          action.dispatch("click");
          const noColorButton = document.getElementById("confirmNoColorRulesBtn");
          assert(noColorButton);
          assert.strictEqual(noColorButton.focused, true);

          checks = confirmed();
          checks.slots = { status: "pending", reason: "素材范围等待扫描。" };
          checks.dimensions = { status: "pending", reason: "尺寸等待扫描。" };
          checks.colors = { status: "blocked", reason: "颜色名称重复。" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [
              { path: "$.outputs[0].design.options[0].assets[0].supported_values", check: "slots", status: "pending", code: "asset_range_pending", reason: "素材范围还没有扫描确认。" },
              { path: "$.outputs", check: "dimensions", status: "pending", code: "dimension_pending", reason: "尺寸边界还没有扫描确认。" },
              { path: "$.colors", check: "colors", status: "blocked", code: "duplicate_color", reason: "颜色样本存在重复名称。" }
            ]
          });
          assert.strictEqual(app.elements.blockerList.children.length, 3);
          assert(app.elements.rescanTemplateBtn.classList.contains("v2-validation-control-error"));
          assert(!app.elements.colorRuleRows.classList.contains("v2-validation-row-error"));
          assert(app.elements.blockerList.children.every((item) => {
            const button = item.children.find((child) => child.tagName === "BUTTON");
            return button && button.textContent === "重新扫描";
          }));

          checks = confirmed();
          checks.preview = { status: "pending", reason: "请完成样例核验。" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [{ path: "$.checks.preview", check: "preview", status: "pending", code: "manual_check_pending", reason: "人工核验项还没有确认。" }]
          });
          action = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(action);
          assert.strictEqual(action.textContent, "前往核验");
          action.dispatch("click");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "preview");
          const previewCheck = app.elements.v2CheckRail.children.find((item) => item.dataset.checkKey === "preview");
          assert.strictEqual(previewCheck.focused, true);
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
          assert(designSlot.textContent.includes("首字 a"));
          assert.strictEqual(designSlot.querySelector('[data-field="slot-tail-first"]'), null);
          assert.strictEqual(designSlot.querySelector('[data-field="slot-width-mm"]').readOnly, true);
          assert.strictEqual(designSlot.querySelector('[data-field="slot-height-mm"]').readOnly, true);
          assert.strictEqual(designSlot.querySelector('[data-field="slot-font-dependencies"]').value, "Cinzel Decorative");
          assert.strictEqual(designSlot.querySelector('[data-field="slot-color-binding"]').value, "color");
          const assetSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideA" && row.dataset.option === "Design03" && row.dataset.slotKey === "slot_initial_top");
          assert(assetSlot);
          assert.strictEqual(assetSlot.querySelector('[data-field="slot-asset-key"]').value, "initial_top");
          assert.strictEqual(assetSlot.querySelector('[data-field="slot-asset-key"]').readOnly, true);

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
          assert.deepStrictEqual(sideB.font.options[0].font_dependencies, []);
          assert.deepStrictEqual(sideB.font.options[0].slots[0].font_dependencies, []);
          assert(draftSaveBody.config.option_mappings.some((item) => item.output === "Output_SideB" && item.group === "font" && item.target === "F10"));

          const reloadedSlot = document.querySelectorAll("#contentOptionRows .content-slot-row").find((row) => row.dataset.output === "Output_SideA" && row.dataset.option === "Design03" && row.dataset.slotKey === "slot_name");
          assert(reloadedSlot);
          assert(reloadedSlot.textContent.includes("首字 a"));
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
                    tails: [{ key: "tail_back_last_z", position: "last", sample: "z", pua_base: 57344 }]
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
          assert(backSlot.textContent.includes("尾字 z"));

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
          assert.deepStrictEqual(backOption.slots[0].tails, [{ key: "tail_back_last_z", position: "last", sample: "z", pua_base: 57344 }]);
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
          const fontScanOptions = Array.from({ length: 12 }, (_, index) => ({
            key: `F${index + 1}`,
            path: `Template/Output_main/Font/F${index + 1}`,
            fixed_object_count: 0,
            fixed_objects: [],
            slots: [{
              key: "slot_name",
              path: `Template/Output_main/Font/F${index + 1}/slot_name`,
              type: "TextFrame",
              text_kind: "point_text",
              source_field: "name",
              visible_bounds: [1, 2, 3, 4],
              dimensions: { width_mm: 15.619, height_mm: 8.49 }
            }]
          }));
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
                    font: { options: fontScanOptions },
                    style: { options: [] },
                    summary: { designs: 1, fonts: 12, styles: 0, slots: 13, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
                  }]
                },
                config: {
                  checks,
                  field_bindings: { name: "Name", design: "Design", font: "Font" },
                  outputs: [{
                    key: "Output_main",
                    display_name: "Main",
                    component_key: "main",
                    style: { field: "", options: [] },
                    design: { field: "design", options: [] },
                    font: { field: "font", options: [] }
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
          assert.strictEqual(app.elements.confirmStageBtn.hidden, true);
          assert.strictEqual(app.elements.saveAndNextOptionBtn.textContent, "\u786e\u8ba4\u5e76\u5f00\u59cb\u914d\u7f6e\u9009\u9879");

          app.elements.saveAndNextOptionBtn.dispatch("click");
          for (let index = 0; index < 6; index += 1) await flush();

          assert.strictEqual(saveCount, 1);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "rules");
          assert(app.elements.selectedOptionTitle.textContent.includes("Design01"));
          assert.strictEqual(draftSaveBody.config.checks.output.status, "confirmed");
          assert.strictEqual(draftSaveBody.config.checks.output.reason, "\u5355 Output_main \u81ea\u52a8\u786e\u8ba4");
          assert.strictEqual(draftSaveBody.config.checks.fields.status, "confirmed");
          assert.strictEqual(draftSaveBody.config.checks.options.status, "confirmed");
          assert(!draftSaveBody.config.checks.output.reason.includes(manualPrefix));
          const fonts = draftSaveBody.config.outputs[0].font.options;
          assert.strictEqual(fonts.length, 12);
          fonts.forEach((font, index) => {
            assert.strictEqual(font.key, `F${index + 1}`);
            assert.deepStrictEqual(font.font_dependencies, []);
            assert.strictEqual(font.slots[0].key, "slot_name");
            assert.strictEqual(font.slots[0].source_field, "name");
            assert.deepStrictEqual(font.slots[0].font_dependencies, []);
            ["path", "type", "text_kind", "visible_bounds", "dimensions"].forEach((key) => {
              assert.strictEqual(Object.prototype.hasOwnProperty.call(font.slots[0], key), false);
            });
          });
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


def test_v2_workbench_preview_cannot_be_manually_confirmed_without_real_trial():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let currentDraft = {
            metadata: { template_id: "V2PREVIEWCONFIRM", name: "Preview Confirm Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_main" }], designs: [{ key: "Design01", slots: [{ key: "slot_name", source_field: "name" }] }] },
            config: {
              checks: ["output", "fields", "options", "slots", "content", "dimensions", "colors"].reduce((result, key) => {
                result[key] = { status: "confirmed", reason: "" };
                return result;
              }, { preview: { status: "pending", reason: "" } }),
              outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name" }] }] }, font: { field: "", options: [] } }]
            }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2PREVIEWCONFIRM", name: "Preview Confirm Demo" }] });
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
          global.setWorkbenchStage("preview");
          await flush();

          assert.strictEqual(app.elements.confirmStageBtn.hidden, true);
          assert.strictEqual(app.elements.saveAndNextOptionBtn.hidden, true);
          global.markCurrentStageConfirmed();
          assert.strictEqual(global.collectChecks().preview.status, "pending");
          assert.strictEqual(draftSaveBody, null);
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
def test_v2_workbench_marks_and_clears_the_exact_blocking_control():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          function confirmedChecks() {
            return Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          }
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2HIGHLIGHT", name: "Highlight Demo" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2HIGHLIGHT", name: "Highlight Demo", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }] },
              config: { outputs: [{ key: "Output_main", display_name: "主效果图", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/validate")) {
              const config = JSON.parse(options.body).config;
              const invalid = config.outputs[0].key !== "Output_main";
              const checks = confirmedChecks();
              if (invalid) checks.output = { status: "blocked", reason: "效果图编号填写有误，请检查标红的效果图编号。" };
              return response({ validation: {
                can_save: !invalid,
                can_publish: !invalid,
                checks,
                issues: invalid ? [{
                  path: "$.outputs[0].key",
                  check: "output",
                  status: "blocked",
                  code: "contract_invalid",
                  reason: "效果图编号填写有误，请检查标红的效果图编号。"
                }] : []
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

          const outputRow = document.querySelectorAll("#outputConfigRows .output-row")[0];
          const outputInput = outputRow.querySelector('[data-field="output-key"]');
          outputInput.value = "WrongOutput";
          outputInput.dispatch("input");
          await flush();

          assert(outputInput.classList.contains("v2-validation-control-error"));
          assert.strictEqual(outputInput.getAttribute("aria-invalid"), "true");
          assert(outputInput.getAttribute("title").includes("效果图编号"));
          const blocker = app.elements.blockerList.children[0];
          const jump = blocker.children.find((child) => child.tagName === "BUTTON");
          assert(jump);
          assert.strictEqual(jump.textContent, "前往修改");
          jump.dispatch("click");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "structure");
          assert.strictEqual(outputInput.focused, true);

          outputInput.value = "Output_main";
          outputInput.dispatch("input");
          await flush();
          assert(!outputInput.classList.contains("v2-validation-control-error"));
          assert.strictEqual(outputInput.getAttribute("aria-invalid"), undefined);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_groups_stale_mixed_contract_failures_without_readonly_jump():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const options = Array.from({ length: 10 }, (_, index) => ({
            key: `Design${String((index + 1) * 2).padStart(2, "0")}`,
            content_preset: "mixed_slots",
            slots: [{ key: "slot_name1", source_field: "name1" }, { key: "slot_name2", source_field: "name2" }]
          }));
          global.DrawFlowV2WorkbenchContext.state.lastValidatedConfig = {
            outputs: [{ key: "Output_main", design: { options }, font: { options: [] }, style: { options: [] } }]
          };
          app.elements.optionContentPreset.disabled = true;
          app.elements.optionContentPreset.setAttribute("aria-readonly", "true");
          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.output = { status: "blocked", reason: "请检查标红的设置。" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: options.map((_, index) => ({
              path: `$.outputs[0].design.options[${index}].content_preset`,
              check: "output",
              status: "blocked",
              code: "contract_invalid",
              reason: "配置契约无效。"
            }))
          });

          assert.strictEqual(app.elements.blockerList.children.length, 1);
          assert(app.elements.blockerList.textContent.includes("重启 DrawFlow"));
          assert(app.elements.publishBlockerText.textContent.includes("还有 1 项"));
          assert(!app.elements.blockerList.textContent.includes("mixed_slots"));
          assert(!app.elements.blockerList.textContent.includes("$.outputs"));
          assert(!app.elements.blockerList.children[0].children.some((child) => child.tagName === "BUTTON"));
          assert(!app.elements.optionContentPreset.classList.contains("v2-validation-control-error"));
          assert.strictEqual(app.elements.optionContentPreset.getAttribute("aria-invalid"), undefined);
          assert.strictEqual(document.querySelectorAll(".v2-validation-control-error").length, 0);
          assert.strictEqual(document.querySelectorAll(".v2-validation-row-error").length, 0);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_dedupes_same_business_target_but_keeps_distinct_options():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          global.DrawFlowV2WorkbenchContext.state.lastValidatedConfig = {
            outputs: [{ key: "Output_main", design: { options: [
              { key: "Design02", content_preset: "direct_text", slots: [] },
              { key: "Design04", content_preset: "direct_text", slots: [] }
            ] }, font: { options: [] }, style: { options: [] } }]
          };
          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.content = { status: "blocked", reason: "请选择内容处理方式。" };
          const first = { path: "$.outputs[0].design.options[0].content_preset", check: "content", status: "blocked", code: "content_preset_missing", reason: "请选择内容处理方式。" };
          global.updateBlockers({
            can_publish: false,
            service_contract: { version: 2, capabilities: ["mixed_slot_processing", "editable_validation_targets"] },
            checks,
            issues: [
              first,
              { ...first, code: "contract_invalid" },
              { ...first, path: "$.outputs[0].design.options[1].content_preset" },
              { ...first, reason: "请确认字体依赖。" }
            ]
          });

          assert.strictEqual(app.elements.blockerList.children.length, 3);
          assert(app.elements.blockerList.textContent.includes("Design02"));
          assert(app.elements.blockerList.textContent.includes("Design04"));
          assert(app.elements.blockerList.textContent.includes("请选择内容处理方式"));
          assert(app.elements.blockerList.textContent.includes("请确认字体依赖"));
          assert(app.elements.publishBlockerText.textContent.includes("还有 3 项"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )

def test_v2_workbench_marks_template_basics_and_mapping_area_from_root_validation_paths():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          const outputChecks = confirmedChecks();
          outputChecks.output = { status: "blocked", reason: "模板信息未填写完整。" };
          global.updateBlockers({
            can_publish: false,
            checks: outputChecks,
            issues: [
              { path: "$.template.template_id", check: "output", status: "blocked", code: "contract_invalid", reason: "模板编号未填写。" },
              { path: "$.template.name", check: "output", status: "blocked", code: "contract_invalid", reason: "模板名称未填写。" },
              { path: "$.template.shop_name", check: "output", status: "blocked", code: "contract_invalid", reason: "店铺名称未填写。" }
            ]
          });
          [app.elements.templateId, app.elements.templateName, app.elements.shopName].forEach((control) => {
            assert(control.classList.contains("v2-validation-control-error"));
            assert.strictEqual(control.getAttribute("aria-invalid"), "true");
          });
          const nameJump = app.elements.blockerList.children[1].children.find((child) => child.tagName === "BUTTON");
          assert(nameJump);
          nameJump.dispatch("click");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.stage, "upload");
          assert.strictEqual(app.elements.templateName.focused, true);

          const mappingChecks = confirmedChecks();
          mappingChecks.options = { status: "blocked", reason: "订单映射需要补充。" };
          global.updateBlockers({
            can_publish: false,
            checks: mappingChecks,
            issues: [{ path: "$.option_mappings", check: "options", status: "blocked", code: "contract_invalid", reason: "订单映射填写有误。" }]
          });
          assert(app.elements.optionMappingRows.classList.contains("v2-validation-row-error"));
          const mappingJump = app.elements.blockerList.children[0].children.find((child) => child.tagName === "BUTTON");
          assert(mappingJump);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_clears_old_feedback_before_a_delayed_validation_returns():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          let resolveUpdatedValidation;
          let validationCalls = 0;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2DELAY", name: "Delay Demo" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2DELAY", name: "Delay Demo", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }] },
              config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/validate")) {
              validationCalls += 1;
              if (validationCalls === 1) {
                const checks = confirmedChecks();
                checks.output = { status: "blocked", reason: "效果图编号填写有误，请检查标红的效果图编号。" };
                return response({ validation: {
                  can_save: false,
                  can_publish: false,
                  checks,
                  issues: [{ path: "$.outputs[0].key", check: "output", status: "blocked", code: "contract_invalid", reason: "效果图编号填写有误，请检查标红的效果图编号。" }]
                }});
              }
              return new Promise((resolve) => { resolveUpdatedValidation = resolve; });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const input = document.querySelectorAll("#outputConfigRows .output-row")[0].querySelector('[data-field="output-key"]');
          assert(input.classList.contains("v2-validation-control-error"));
          assert(app.elements.blockerList.textContent.includes("效果图编号填写有误"));

          input.value = "Output_main";
          input.dispatch("input");
          assert(!input.classList.contains("v2-validation-control-error"));
          assert.strictEqual(input.getAttribute("aria-invalid"), undefined);
          assert(!app.elements.blockerList.textContent.includes("效果图编号填写有误"));
          assert(resolveUpdatedValidation);

          resolveUpdatedValidation(response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks(), issues: [] } }));
          await flush();
          assert(!input.classList.contains("v2-validation-control-error"));
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true, "只有真实试渲染才能解锁发布");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_ignores_an_older_validation_response_after_a_newer_result():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          let resolveOlderValidation;
          let resolveNewerValidation;
          let validationCalls = 0;
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ORDER", name: "Order Demo" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2ORDER", name: "Order Demo", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }] },
              config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/validate")) {
              validationCalls += 1;
              if (validationCalls === 1) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks(), issues: [] } });
              if (validationCalls === 2) return new Promise((resolve) => { resolveOlderValidation = resolve; });
              return new Promise((resolve) => { resolveNewerValidation = resolve; });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const input = document.querySelectorAll("#outputConfigRows .output-row")[0].querySelector('[data-field="output-key"]');
          input.value = "First change";
          input.dispatch("input");
          input.value = "Second change";
          input.dispatch("input");
          assert(resolveOlderValidation);
          assert(resolveNewerValidation);

          resolveNewerValidation(response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks(), issues: [] } }));
          await flush();
          resolveOlderValidation(response({ validation: {
            can_save: false,
            can_publish: false,
            checks: { ...confirmedChecks(), output: { status: "blocked", reason: "旧结果" } },
            issues: [{ path: "$.outputs[0].key", check: "output", status: "blocked", code: "contract_invalid", reason: "旧结果" }]
          }}));
          await flush();

          assert(!input.classList.contains("v2-validation-control-error"));
          assert(!app.elements.blockerList.textContent.includes("旧结果"));
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true, "只有真实试渲染才能解锁发布");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
def test_v2_workbench_marks_ambiguous_output_issue_on_output_section():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2MULTI", name: "Multi" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2MULTI", name: "Multi", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }, { key: "Output_SideA" }] },
              config: { outputs: [
                { key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } },
                { key: "Output_SideA", display_name: "Side A", component_key: "side_a", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }
              ] }
            }});
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks(), issues: [] } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("structure");
          await flush();

          const checks = confirmedChecks();
          checks.output = { status: "blocked", reason: "Output list needs review" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [{ path: "$.outputs", check: "output", status: "blocked", reason: "Output list needs review" }]
          });

          const keys = document.querySelectorAll("#outputConfigRows .output-row").map((row) => row.querySelector('[data-field="output-key"]'));
          assert.strictEqual(keys.length, 2);
          assert(!keys[0].classList.contains("v2-validation-control-error"));
          assert(!keys[1].classList.contains("v2-validation-control-error"));
          assert(app.elements.outputConfigRows.classList.contains("v2-validation-row-error"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_a_cleared_output_key_after_rerender():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2BLANK", name: "Blank" }] });
            if (textUrl.endsWith("/draft")) return response({ draft: {
              metadata: { template_id: "V2BLANK", name: "Blank", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }] },
              config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/validate")) {
              const config = JSON.parse(options.body).config;
              const invalid = config.outputs[0].key === "";
              const checks = confirmedChecks();
              if (invalid) checks.output = { status: "blocked", reason: "Output key is required" };
              return response({ validation: {
                can_save: !invalid,
                can_publish: !invalid,
                checks,
                issues: invalid ? [{ path: "$.outputs[0].key", check: "output", status: "blocked", reason: "Output key is required" }] : []
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

          const input = document.querySelectorAll("#outputConfigRows .output-row")[0].querySelector('[data-field="output-key"]');
          input.value = "";
          input.dispatch("input");
          await flush();
          assert.strictEqual(global.buildControlledConfig().outputs[0].key, "");

          global.setWorkbenchStage("rules");
          await flush();
          const rerendered = document.querySelectorAll("#outputConfigRows .output-row")[0].querySelector('[data-field="output-key"]');
          assert.strictEqual(rerendered.value, "");
          assert.strictEqual(global.buildControlledConfig().outputs[0].key, "");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_clears_old_validation_feedback_before_next_draft_loads():
    run_node(
        r"""
        (async () => {
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const confirmedChecks = () => Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          let resolveB;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [
              { template_id: "V2A", name: "Template A" },
              { template_id: "V2B", name: "Template B" }
            ] });
            if (textUrl.endsWith("/V2A/draft")) return response({ draft: {
              metadata: { template_id: "V2A", name: "Template A", shop_name: "" },
              manifest: { draft_revision: "d0001" },
              scan: { outputs: [{ key: "Output_main" }] },
              config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
            }});
            if (textUrl.endsWith("/V2B/draft")) return new Promise((resolve) => { resolveB = resolve; });
            if (textUrl.endsWith("/validate")) {
              const config = JSON.parse(options.body).config;
              const invalid = config.template.template_id === "V2A";
              const checks = confirmedChecks();
              if (invalid) checks.output = { status: "blocked", reason: "Old blocker" };
              return response({ validation: {
                can_save: !invalid,
                can_publish: !invalid,
                checks,
                issues: invalid ? [{ path: "$.outputs[0].key", check: "output", status: "blocked", reason: "Old blocker" }] : []
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
          const oldInput = document.querySelectorAll("#outputConfigRows .output-row")[0].querySelector('[data-field="output-key"]');
          assert(oldInput.classList.contains("v2-validation-control-error"));
          assert(app.elements.blockerList.textContent.includes("Old blocker"));

          app.elements.templateList.children[1].dispatch("click");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.selectedTemplateId, "V2B");
          assert(!oldInput.classList.contains("v2-validation-control-error"));
          assert.strictEqual(oldInput.getAttribute("aria-invalid"), undefined);
          assert(!app.elements.blockerList.textContent.includes("Old blocker"));
          assert(!app.elements.publishBlockerText.textContent.includes("Old blocker"));
          assert(resolveB);

          resolveB(response({ draft: {
            metadata: { template_id: "V2B", name: "Template B", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_SideA" }] },
            config: { outputs: [{ key: "Output_SideA", display_name: "Side A", component_key: "side_a", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
          }}));
          await flush();
          assert.strictEqual(app.elements.templateId.value, "V2B");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_ignores_an_out_of_order_draft_response():
    run_node(
        r"""
        (async () => {
          let resolveA;
          let resolveB;
          const draftA = {
            metadata: { template_id: "V2A", name: "Template A", shop_name: "" },
            manifest: { draft_revision: "a0001" },
            scan: { outputs: [{ key: "Output_main" }] },
            config: { outputs: [{ key: "Output_main", display_name: "Main", component_key: "main", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
          };
          const draftB = {
            metadata: { template_id: "V2B", name: "Template B", shop_name: "" },
            manifest: { draft_revision: "b0001" },
            scan: { outputs: [{ key: "Output_SideA" }] },
            config: { outputs: [{ key: "Output_SideA", display_name: "Side A", component_key: "side_a", style: { field: "", options: [] }, design: { field: "", options: [] }, font: { field: "", options: [] } }] }
          };
          async function fakeFetch(url) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [
              { template_id: "V2A", name: "Template A" },
              { template_id: "V2B", name: "Template B" }
            ] });
            if (textUrl.endsWith("/V2A/draft")) return new Promise((resolve) => { resolveA = resolve; });
            if (textUrl.endsWith("/V2B/draft")) return new Promise((resolve) => { resolveB = resolve; });
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          app.elements.templateList.children[1].dispatch("click");
          await flush();
          assert(resolveA);
          assert(resolveB);

          resolveB(response({ draft: draftB }));
          await flush();
          resolveA(response({ draft: draftA }));
          await flush();

          const state = global.DrawFlowV2WorkbenchContext.state;
          assert.strictEqual(state.selectedTemplateId, "V2B");
          assert.strictEqual(state.draft.metadata.template_id, "V2B");
          assert.strictEqual(app.elements.templateId.value, "V2B");
          assert.strictEqual(app.elements.templateName.value, "Template B");
          assert.strictEqual(state.scan.outputs[0].key, "Output_SideA");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )

def test_v2_workbench_uses_business_language_for_internal_validation_identifiers():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const checks = Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.slots = { status: "blocked", reason: "anchor_name 与 slot_name 不对应" };
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [{
              path: "$.outputs[0].design.options[0].slots[0].anchor",
              check: "slots",
              status: "blocked",
              code: "anchor_belongs_to_slot",
              reason: "定位框必须归属同一槽位：Template/Output_main/Design/Design03/slot_name 只能引用 anchor_name。"
            }]
          });
          assert(app.elements.blockerList.textContent.includes("定位框与当前槽位不对应"));
          assert(app.elements.blockerList.textContent.includes("重新扫描"));
          ["Template/", "Output_main", "slot_name", "anchor_name"].forEach((value) => assert(!app.elements.blockerList.textContent.includes(value)));
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
def test_v2_workbench_hides_technical_validation_details_in_blockers_and_tooltips():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          assert.strictEqual(global.hasTechnicalValidationDetail("layer_path=opaque-value"), true);
          const checkKeys = ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"];
          const checks = Object.fromEntries(checkKeys.map((key) => [key, { status: "confirmed", reason: "" }]));
          checks.output = { status: "blocked", reason: "Duplicate item" };
          const unsafeReason = "同一作用域内名称重复：slot_name；冲突图层路径：Template/Output_main/Design/Design03/slot_name ($.outputs[0].design.options[0].slots[1])。";
          global.updateBlockers({
            can_publish: false,
            checks,
            issues: [{ path: "$.outputs", check: "output", status: "blocked", code: "duplicate_name", reason: unsafeReason }]
          });
          assert(app.elements.blockerList.textContent.includes("同一范围内存在重复名称"));
          assert(!app.elements.blockerList.textContent.includes("Template/"));
          assert(!app.elements.blockerList.textContent.includes("$.outputs"));
          assert(!app.elements.outputConfigRows.getAttribute("title").includes("Template/"));
          assert(!app.elements.outputConfigRows.getAttribute("title").includes("$.outputs"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_real_trial_render_keeps_selected_template_id_when_list_case_differs():
    run_node(
        r"""
        (async () => {
          let currentDraft = {
            metadata: { template_id: "test", name: "Real Preview", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{
              key: "Output_main",
              style: { options: [{ key: "style1" }] },
              design: { options: [{ key: "Design02", slots: [{ key: "slot_name1" }, { key: "slot_name2" }] }] },
              font: { options: [] },
              summary: { designs: 1, fonts: 0, styles: 1, slots: 2, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
            }] },
            config: {
              outputs: [{
                key: "Output_main", display_name: "主效果图", component_key: "main",
                style: { field: "style", options: [{ key: "style1" }] },
                design: { field: "design", options: [{ key: "Design02", content_preset: "mixed_slots", slots: [
                  { key: "slot_name1", source_field: "name1", preset: "tail_text" },
                  { key: "slot_name2", source_field: "name2", preset: "direct_text", path: "Template/Output_main/Design/Design02/slot_name2" }
                ] }] },
                font: { field: "", options: [] }
              }],
              field_bindings: { style: "Size", design: "Design", name1: "Name", name2: "Title" },
              option_mappings: [
                { field: "style", source_value: "Small", group: "style", target: "style1", output: "Output_main" },
                { field: "design", source_value: "2", group: "design", target: "Design02", output: "Output_main" }
              ],
              checks: {}, preview: { sample_rows: [] }
            }
          };
          let draftPostBody = null;
          let trialBody = null;
          let publicationBody = null;
          const urls = [];
          const confirmedChecks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            urls.push(textUrl);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "Test", name: "Real Preview" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: false, checks: { ...confirmedChecks, preview: { status: "pending", reason: "请试渲染" } } } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              draftPostBody = JSON.parse(options.body);
              currentDraft = { ...currentDraft, config: draftPostBody.config, manifest: { draft_revision: "d0002" } };
              return response({ draft: currentDraft });
            }
            if (textUrl.endsWith("/trial-render")) {
              trialBody = JSON.parse(options.body);
              const proofDraft = { ...currentDraft, manifest: { draft_revision: "d0003" } };
              return response({
                trial: { id: "t1", status: "succeeded", rendered_at: "2026-08-13T10:00:00Z", outputs: [{ key: "Output_main", display_name: "主效果图", preview_url: "/local/previews/t1/main.png", warnings: [] }] },
                draft: proofDraft,
                validation: { can_save: true, can_publish: true, checks: confirmedChecks },
                publication: { current_version: "v3", previous_version: "v2" },
                versions: [{ version: "v3", published_at: "2026-08-12T10:00:00Z" }, { version: "v2", published_at: "2026-08-10T10:00:00Z" }]
              });
            }
            if (textUrl.endsWith("/publication-check")) {
              publicationBody = JSON.parse(options.body);
              return response({ validation: { can_save: true, can_publish: true, checks: confirmedChecks }, publication: { current_version: "v3", previous_version: "v2" }, versions: [] });
            }
            if (textUrl.endsWith("/versions")) return response({ versions: [{ version: "v3" }, { version: "v2" }] });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("preview");
          await flush();

          const sampleInputs = allDescendants(app.elements.previewSampleRows).filter((node) => node.dataset.sampleHeader);
          assert.deepStrictEqual(sampleInputs.map((input) => input.dataset.sampleHeader), ["Size", "Design", "Name", "Title"]);
          assert.deepStrictEqual(sampleInputs.map((input) => input.value), ["Small", "2", "", ""]);
          sampleInputs.find((input) => input.dataset.sampleHeader === "Name").value = "Ava";
          sampleInputs.find((input) => input.dataset.sampleHeader === "Title").value = "My title";
          app.elements.trialRenderBtn.dispatch("click");
          for (let index = 0; index < 16; index += 1) await flush();

          assert(draftPostBody, "trial render must save draft first");
          assert(trialBody, "trial render endpoint must be called");
          assert.strictEqual(draftPostBody.config.template.template_id, "Test");
          assert.deepStrictEqual(draftPostBody.config.field_bindings, { style: "Size", design: "Design", name1: "Name", name2: "Title" });
          assert.deepStrictEqual(draftPostBody.config.option_mappings, currentDraft.config.option_mappings);
          assert.deepStrictEqual(draftPostBody.config.outputs[0].design.options[0].slots.map((slot) => slot.source_field), ["name1", "name2"]);
          assert.strictEqual(Object.prototype.hasOwnProperty.call(draftPostBody.config.outputs[0].design.options[0].slots[1], "path"), false);
          assert.strictEqual(trialBody.expected_draft_revision, "d0002");
          assert.deepStrictEqual(trialBody.sample_row, { Size: "Small", Design: "2", Name: "Ava", Title: "My title" });
          assert.deepStrictEqual(publicationBody, { expected_draft_revision: "d0003" });
          assert.strictEqual(global.currentDraftRevision(global.DrawFlowV2WorkbenchContext.state.draft), "d0003");
          assert(urls.indexOf("/api/v2/templates/Test/draft") < urls.indexOf("/local/v2/templates/Test/trial-render"));
          const proofIndex = urls.indexOf("/local/v2/templates/Test/trial-render");
          const publicationIndex = urls.indexOf("/api/v2/templates/Test/publication-check");
          const versionsIndex = urls.findIndex((url, index) => index > publicationIndex && url === "/api/v2/templates/Test/versions");
          assert(proofIndex < publicationIndex && publicationIndex < versionsIndex);
          assert.strictEqual(app.elements.previewSideTabs.hidden, true);
          const images = allDescendants(app.elements.previewArtworkPane).filter((node) => node.tagName === "IMG");
          assert.strictEqual(images.length, 1);
          assert.strictEqual(images[0].src, "/local/previews/t1/main.png");
          assert.strictEqual(images[0].alt, "试渲染效果图");
          assert.strictEqual(app.elements.currentVersionSummary.textContent, "v3");
          assert.strictEqual(app.elements.rollbackVersionSummary.textContent, "v2");
          assert.strictEqual(app.elements.publishVersionBtn.disabled, false);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_clears_busy_preview_when_saved_draft_supersedes_request():
    run_node(
        r"""
        (async () => {
          let currentDraft = {
            metadata: { template_id: "V2STALE", name: "Stale Preview", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{
              key: "Output_main",
              style: { options: [{ key: "style1" }] },
              design: { options: [{ key: "Design01", slots: [{ key: "slot_name" }] }] },
              font: { options: [] },
              summary: { designs: 1, fonts: 0, styles: 1, slots: 1, anchors: 0, tails: 0, assets: 0, fixed_objects: 0 }
            }] },
            config: {
              outputs: [{
                key: "Output_main", display_name: "主效果图", component_key: "main",
                style: { field: "", options: [{ key: "style1" }] },
                design: { field: "design", options: [{ key: "Design01", content_preset: "mixed_slots", slots: [
                  { key: "slot_name", source_field: "name", preset: "direct_text" }
                ] }] },
                font: { field: "", options: [] }
              }],
              field_bindings: { design: "Design", name: "Name" },
              option_mappings: [{ field: "design", source_value: "1", group: "design", target: "Design01", output: "Output_main" }],
              checks: {}, preview: { sample_rows: [] }
            }
          };
          let trialCalls = 0;
          const confirmedChecks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2STALE", name: "Stale Preview" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, can_publish: false, checks: confirmedChecks } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              currentDraft = { ...currentDraft, manifest: { draft_revision: "d0002" } };
              global.DrawFlowV2WorkbenchContext.state.trialGeneration += 1;
              return response({ draft: currentDraft });
            }
            if (textUrl.endsWith("/trial-render")) {
              trialCalls += 1;
              return response({});
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("preview");
          await flush();
          const sampleInputs = allDescendants(app.elements.previewSampleRows).filter((node) => node.dataset.sampleHeader);
          sampleInputs.find((input) => input.dataset.sampleHeader === "Name").value = "Meiyi";
          app.elements.trialRenderBtn.dispatch("click");
          for (let index = 0; index < 12; index += 1) await flush();

          assert.strictEqual(trialCalls, 0, "superseded requests must not call Illustrator");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.isTrialRendering, false);
          assert(app.elements.previewTrialStatus.textContent.includes("未开始"));
          assert(!app.elements.previewTrialStatus.textContent.includes("正在保存草稿"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_multi_output_labels_and_publish_use_real_responses():
    run_node(
        r"""
        (async () => {
          const checks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          let publishBody = null;
          let versionsCalls = 0;
          const urls = [];
          const app = createApp(async (url, options = {}) => {
            const textUrl = String(url);
            urls.push(textUrl);
            if (textUrl === "/api/v2/templates") return response({ templates: [] });
            if (textUrl.endsWith("/publication-check")) return response({ validation: { can_publish: true, checks }, publication: { current_version: "v7", previous_version: "v6" }, versions: [], draft_revision: "d0100" });
            if (textUrl.endsWith("/publish")) {
              publishBody = JSON.parse(options.body);
              return response({ publication: { current_version: "v8", previous_version: "v7" }, versions: [{ version: "v8" }, { version: "v7" }] });
            }
            if (textUrl.endsWith("/versions")) {
              versionsCalls += 1;
              if (versionsCalls === 1) return response({ error: { reason: "版本信息暂时读取失败" } }, false);
              return response({ versions: [{ version: "v8" }, { version: "v7" }] });
            }
            return response({});
          });
          await flush();
          const state = global.DrawFlowV2WorkbenchContext.state;
          state.selectedTemplateId = "V2MULTI";
          state.draft = { metadata: { template_id: "V2MULTI" }, manifest: { draft_revision: "d0099" }, config: { field_bindings: {}, outputs: [] } };
          state.validation = { can_publish: true, checks };
          state.trial = { status: "succeeded", outputs: [
            { key: "Output_SideA", display_name: "正面", preview_url: "/a.png" },
            { key: "Output_SideB", display_name: "背面", preview_url: "/b.png" }
          ] };
          state.publication = { current_version: "v7", previous_version: "v6" };
          app.elements.publishNotes.value = "更新文字规则";
          global.renderPreviewStage();
          global.updateBlockers(state.validation);
          assert.strictEqual(app.elements.previewSideTabs.hidden, false);
          assert.deepStrictEqual(app.elements.previewSideTabs.children.map((node) => node.textContent), ["正面", "背面"]);
          app.elements.previewSideTabs.children[1].dispatch("click");
          const image = allDescendants(app.elements.previewArtworkPane).find((node) => node.tagName === "IMG");
          assert.strictEqual(image.src, "/b.png");
          await global.publishCurrentDraft();
          assert.strictEqual(publishBody, null, "版本读取失败必须阻断 publish");
          assert.strictEqual(state.versionsStatus, "error");
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true);
          assert(app.elements.currentVersionSummary.textContent.includes("读取失败"));
          const failedUrls = urls.filter((url) => /\/(publication-check|versions|publish)$/.test(url));
          assert.deepStrictEqual(failedUrls, [
            "/api/v2/templates/V2MULTI/publication-check",
            "/api/v2/templates/V2MULTI/versions"
          ]);
          const retryStart = urls.length;
          await global.publishCurrentDraft();
          assert.deepStrictEqual(publishBody, { expected_draft_revision: "d0100", note: "更新文字规则" });
          const publicationUrls = urls.slice(retryStart).filter((url) => /\/(publication-check|versions|publish)$/.test(url));
          assert.deepStrictEqual(publicationUrls.slice(0, 3), [
            "/api/v2/templates/V2MULTI/publication-check",
            "/api/v2/templates/V2MULTI/versions",
            "/api/v2/templates/V2MULTI/publish"
          ]);
          assert.strictEqual(state.publication.current_version, "v8");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_preview_confirmed_checks_hide_stale_failure_reason():
    run_node(
        r"""
        (async () => {
          const app = createApp(async (url) => {
            if (String(url) === "/api/v2/templates") return response({ templates: [] });
            return response({});
          });
          await flush();
          const state = global.DrawFlowV2WorkbenchContext.state;
          const staleReason = "操作失败，技术详情已隐藏，请稍后重试。";
          state.trial = { status: "succeeded", outputs: [] };
          state.validation = {
            can_publish: true,
            checks: Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
              .map((key) => [key, { status: "confirmed", reason: staleReason }]))
          };
          global.renderPreviewStage();
          const text = app.elements.previewValidationRows.textContent;
          assert(!text.includes(staleReason), "confirmed rows must not show stale failure reason");
          assert(text.includes("已通过"), "confirmed rows should show a successful plain-language detail");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_late_trial_response_cannot_override_edited_sample_or_new_request():
    run_node(
        r"""
        (async () => {
          const confirmedChecks = Object.fromEntries(["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]
            .map((key) => [key, { status: "confirmed", reason: "" }]));
          let currentDraft = {
            metadata: { template_id: "V2RACE", name: "Race Demo", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            scan: { outputs: [{ key: "Output_main" }], designs: [{ key: "Design01", slots: [{ key: "slot_name" }] }] },
            config: {
              outputs: [{
                key: "Output_main", display_name: "主效果图", component_key: "main",
                style: { field: "", options: [] },
                design: { field: "design", options: [{ key: "Design01", content_preset: "direct_text", slots: [{ key: "slot_name", source_field: "name", preset: "direct_text" }] }] },
                font: { field: "", options: [] }
              }],
              field_bindings: { design: "Design", name: "Name" },
              option_mappings: [{ field: "design", source_value: "1", target: "Design01", output: "Output_main", group: "design" }],
              checks: confirmedChecks
            }
          };
          let revisionNumber = 1;
          let resolveA = null;
          let resolveB = null;
          const trialBodies = [];
          const app = createApp(async (url, options = {}) => {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2RACE", name: "Race Demo" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: {
              can_save: true,
              can_publish: false,
              checks: { ...confirmedChecks, preview: { status: "pending", reason: "请重新试渲染" } }
            } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              revisionNumber += 1;
              currentDraft = { ...currentDraft, config: JSON.parse(options.body).config, manifest: { draft_revision: `d${String(revisionNumber).padStart(4, "0")}` } };
              return response({ draft: currentDraft });
            }
            if (textUrl.endsWith("/trial-render")) {
              const body = JSON.parse(options.body);
              trialBodies.push(body);
              return new Promise((resolve) => {
                if (body.sample_row.Name === "A") resolveA = resolve;
                else resolveB = resolve;
              });
            }
            if (textUrl.endsWith("/versions")) return response({ versions: [] });
            return response({});
          });
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          global.setWorkbenchStage("preview");
          await flush();
          const state = global.DrawFlowV2WorkbenchContext.state;
          let nameInput = allDescendants(app.elements.previewSampleRows).find((node) => node.dataset.sampleHeader === "Name");
          nameInput.value = "A";
          nameInput.dispatch("input");
          app.elements.trialRenderBtn.dispatch("click");
          for (let index = 0; index < 20 && !resolveA; index += 1) await flush();
          assert(resolveA, "A request must be in flight");
          assert.strictEqual(trialBodies[0].expected_draft_revision, "d0002");

          nameInput = allDescendants(app.elements.previewSampleRows).find((node) => node.dataset.sampleHeader === "Name");
          nameInput.value = "B";
          nameInput.dispatch("input");
          assert.strictEqual(state.trial, null);
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true);
          app.elements.trialRenderBtn.dispatch("click");
          for (let index = 0; index < 20 && !resolveB; index += 1) await flush();
          assert(resolveB, "B request must replace A");
          const activeBRequestId = state.activeTrialRequestId;
          assert.strictEqual(state.isTrialRendering, true);
          assert.strictEqual(trialBodies[1].expected_draft_revision, "d0003");

          resolveA(response({
            draft: { ...currentDraft, manifest: { draft_revision: "d0999" } },
            trial: { status: "succeeded", outputs: [{ preview_url: "/late-a.png" }] },
            validation: { can_publish: true, checks: confirmedChecks }
          }));
          await flush();
          assert.strictEqual(state.trial, null, "迟到的 A proof 必须丢弃");
          assert.strictEqual(global.currentDraftRevision(state.draft), "d0003");
          assert.strictEqual(state.activeTrialRequestId, activeBRequestId);
          assert.strictEqual(state.isTrialRendering, true, "A 的 finally 不得清除 B 的 busy 状态");
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true);

          resolveB(response({
            draft: { ...currentDraft, manifest: { draft_revision: "d0004" } },
            trial: { status: "failed", outputs: [] },
            validation: { can_publish: false, checks: { ...confirmedChecks, preview: { status: "blocked", reason: "试渲染失败" } } }
          }));
          await flush();
          assert.strictEqual(state.isTrialRendering, false);
          assert.strictEqual(global.trialSucceeded(), false);
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_output_policy_toggles_round_trip_through_config():
    run_node(
        r"""
        (async () => {
          let draftSaveBody = null;
          let currentDraft = {
            metadata: { template_id: "V2OUTPUTPOLICY", name: "Output policy", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            config: { output: { outline_text: false, pathfinder_merge: true } },
            scan: { outputs: [{ key: "Output_main" }] }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2OUTPUTPOLICY", name: "Output policy" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
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
          assert.strictEqual(app.elements.outlineTextToggle.checked, false);
          assert.strictEqual(app.elements.pathfinderMergeToggle.checked, true);

          app.elements.outlineTextToggle.checked = true;
          app.elements.pathfinderMergeToggle.checked = false;
          await global.saveDraft();
          assert(draftSaveBody, "保存草稿请求必须发送输出处理配置");
          assert.deepStrictEqual(draftSaveBody.config.output, {
            outline_text: true,
            pathfinder_merge: false
          });
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_keeps_scan_when_response_draft_omits_scan():
    run_node(
        r"""
        (async () => {
          let saveCount = 0;
          const scanned = {
            "$schema": "custom-renderer/v2-template-scan",
            outputs: [{
              key: "Output_main",
              design: { options: [
                { key: "Design01", slots: [{ key: "slot_name" }] },
                { key: "Design02", slots: [{ key: "slot_name" }] }
              ] },
              font: { options: [] },
              style: { options: [] }
            }]
          };
          let currentDraft = {
            metadata: { template_id: "V2SCANRETAIN", name: "Scan retention", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} },
            scan: scanned
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SCANRETAIN", name: "Scan retention" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              saveCount += 1;
              currentDraft = {
                metadata: currentDraft.metadata,
                manifest: { draft_revision: `d000${saveCount + 1}` },
                config: JSON.parse(options.body).config
              };
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
          assert(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].design.options.length === 2);

          await global.saveDraft();
          assert.strictEqual(saveCount, 1);
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].design.options.length, 2);
          global.setWorkbenchStage("rules");
          await flush();
          assert.strictEqual(document.querySelectorAll("#optionRuleList .option-rule-item").length, 2);
          global.setWorkbenchStage("upload");
          await flush();
          assert(app.elements.scanSummary.textContent.includes("设计 2"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_keeps_scan_when_existing_template_id_is_edited():
    run_node(
        r"""
        (async () => {
          const scanned = { outputs: [{ key: "Output_A", design: { options: [{ key: "Design01" }] } }] };
          let currentDraft = {
            metadata: { template_id: "V2SCAN-A", name: "Template A", shop_name: "" },
            config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} },
            scan: scanned
          };
          let saveBody = null;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SCAN-A", name: "Template A" }, { template_id: "V2SCAN-B", name: "Template B" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (textUrl.endsWith("/draft") && options.method === "POST") {
              saveBody = JSON.parse(options.body);
              return response({ draft: { metadata: { template_id: "V2SCAN-A", name: "Template B", shop_name: "" }, config: saveBody.config } });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          app.elements.templateId.value = "V2SCAN-B";
          app.elements.templateName.value = "Template B";
          await global.saveDraft();
          assert(saveBody, "必须发送保存请求");
          assert.strictEqual(saveBody.config.template.template_id, "V2SCAN-A");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].key, "Output_A", "已有模板不能因编辑 ID 而丢失扫描结构");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_invalid_scan_response_does_not_replace_valid_scan():
    run_node(
        r"""
        (async () => {
          const scanned = { outputs: [{ key: "Output_main", design: { options: [{ key: "Design01" }] } }] };
          let currentDraft = {
            metadata: { template_id: "V2SCANVALID", name: "Valid scan", shop_name: "" },
            config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} },
            scan: scanned
          };
          let responseScan = { outputs: [] };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2SCANVALID", name: "Valid scan" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft: currentDraft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (textUrl.endsWith("/draft") && options.method === "POST") return response({ draft: { ...currentDraft, scan: responseScan, config: JSON.parse(options.body).config } });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          await global.saveDraft();
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].key, "Output_main");
          responseScan = { unexpected: true };
          await global.saveDraft();
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].key, "Output_main");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_save_response_does_not_overwrite_newly_selected_template():
    run_node(
        r"""
        (async () => {
          let resolveSave;
          const draftA = { metadata: { template_id: "V2ASYNC-A", name: "Template A", shop_name: "" }, config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} }, scan: { outputs: [{ key: "Output_A" }] } };
          const draftB = { metadata: { template_id: "V2ASYNC-B", name: "Template B", shop_name: "" }, config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} }, scan: { outputs: [{ key: "Output_B" }] } };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2ASYNC-A", name: "Template A" }, { template_id: "V2ASYNC-B", name: "Template B" }] });
            if (textUrl.endsWith("V2ASYNC-A/draft") && (!options.method || options.method === "GET")) return response({ draft: draftA });
            if (textUrl.endsWith("V2ASYNC-B/draft") && (!options.method || options.method === "GET")) return response({ draft: draftB });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (textUrl.endsWith("V2ASYNC-A/draft") && options.method === "POST") return new Promise((resolve) => { resolveSave = () => resolve(response({ draft: draftA })); });
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          const saving = global.saveDraft();
          await flush();
          assert(resolveSave, "保存请求必须仍在等待回包");
          app.elements.templateList.children[1].dispatch("click");
          await flush();
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.selectedTemplateId, "V2ASYNC-B");
          resolveSave();
          const result = await saving;
          assert.strictEqual(result.failure, "stale");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.draft.metadata.template_id, "V2ASYNC-B");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].key, "Output_B");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_refresh_ignores_draft_returned_for_another_template():
    run_node(
        r"""
        (async () => {
          const currentDraft = { metadata: { template_id: "V2REFRESH-A", name: "Template A", shop_name: "" }, config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} }, scan: { outputs: [{ key: "Output_A" }] } };
          const wrongDraft = { metadata: { template_id: "V2REFRESH-B", name: "Template B", shop_name: "" }, config: {}, scan: { outputs: [{ key: "Output_B" }] } };
          let refreshRequest = false;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2REFRESH-A", name: "Template A" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              if (refreshRequest) return response({ draft: wrongDraft });
              return response({ draft: currentDraft });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          refreshRequest = true;
          await global.safeRefreshDraft("V2REFRESH-A");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.draft.metadata.template_id, "V2REFRESH-A");
          assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].key, "Output_A");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_refresh_keeps_scan_for_missing_or_invalid_scan_response():
    run_node(
        r"""
        (async () => {
          const currentDraft = { metadata: { template_id: "V2REFRESHSCAN", name: "Refresh scan", shop_name: "" }, config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} }, scan: { outputs: [{ key: "Output_main", design: { options: [{ key: "Design01" }] } }] } };
          let responseScan;
          let loaded = false;
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "V2REFRESHSCAN", name: "Refresh scan" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) {
              const draft = { ...currentDraft };
              if (loaded) {
                if (responseScan !== undefined) draft.scan = responseScan;
                else delete draft.scan;
              }
              loaded = true;
              return response({ draft });
            }
            return response({});
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          for (const scan of [undefined, { outputs: [] }, { unexpected: true }]) {
            responseScan = scan;
            await global.safeRefreshDraft("V2REFRESHSCAN");
            assert.strictEqual(global.DrawFlowV2WorkbenchContext.state.scan.outputs[0].design.options[0].key, "Design01");
          }
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_keeps_existing_template_identity_when_display_name_changes():
    run_node(
        r"""
        (async () => {
          const urls = [];
          let savedBody = null;
          const draft = {
            metadata: { template_id: "TEST", name: "Original name", shop_name: "" },
            manifest: { draft_revision: "d0001" },
            config: { outputs: [], field_bindings: {}, option_mappings: [], checks: {} },
            scan: { outputs: [{ key: "Output_main" }] }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            urls.push({ url: textUrl, method: options.method || "GET" });
            if (textUrl === "/api/v2/templates") return response({ templates: [{ template_id: "TEST", name: "Original name" }] });
            if (textUrl.endsWith("/draft") && (!options.method || options.method === "GET")) return response({ draft });
            if (textUrl.endsWith("/validate")) return response({ validation: { can_save: true, checks: {} } });
            if (textUrl === "/api/v2/templates/TEST/draft" && options.method === "POST") {
              savedBody = JSON.parse(options.body);
              return response({ draft: { ...draft, metadata: { ...draft.metadata, name: savedBody.name }, config: savedBody.config } });
            }
            throw new Error(`unexpected request ${textUrl}`);
          }
          const app = createApp(fakeFetch);
          await flush();
          app.elements.templateList.children[0].dispatch("click");
          await flush();
          assert.strictEqual(app.elements.templateId.disabled, true, "已有模板的 ID 必须锁定");
          app.elements.templateId.value = "NEW-TEMPLATE";
          app.elements.templateName.value = "Renamed display name";
          assert.strictEqual(global.formBasics().template_id, "TEST");
          await global.saveDraft();
          assert.strictEqual(savedBody.name, "Renamed display name");
          assert.strictEqual(savedBody.config.template.template_id, "TEST");
          assert(urls.some((item) => item.url === "/api/v2/templates/TEST/draft" && item.method === "POST"));
          assert(!urls.some((item) => item.url === "/api/v2/templates" && item.method === "POST"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
