import subprocess
import textwrap


HARNESS = r"""
const assert = require("assert");
const fs = require("fs");

const ids = [
  "v2CheckRail", "templateList", "templateSearch", "templateId", "templateName", "shopName",
  "templateIdMirror", "templateNameMirror", "shopNameMirror", "draftStatusBadge", "draftVersion",
  "aiDropzone", "aiFile", "scanTemplateBtn", "rescanTemplateBtn", "cancelScanBtn", "scanProgress",
  "scanSummary", "scanEmptyState", "structureSearch", "structureTree", "toggleDesignsBtn",
  "toggleFontsBtn", "outputConfigRows", "fieldBindingRows", "optionMappingRows", "selectedNodeSummary",
  "blockerList", "draftSummary", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn",
  "publishBlockerText", "scanFailedOverlay", "scanFailedMessage", "retryScanBtn", "closeScanFailedBtn"
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
  ["templateSearch", "templateId", "templateName", "shopName", "structureSearch"].forEach((id) => { elements[id].tagName = "INPUT"; });
  ["scanTemplateBtn", "rescanTemplateBtn", "cancelScanBtn", "saveDraftBtn", "trialRenderBtn", "publishVersionBtn", "retryScanBtn", "closeScanFailedBtn", "toggleDesignsBtn", "toggleFontsBtn"].forEach((id) => { elements[id].tagName = "BUTTON"; });
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
          app.elements.saveDraftBtn.dispatch("click");
          await flush();
          assert(draftSaveBody);
          assert(!Object.prototype.hasOwnProperty.call(draftSaveBody, "scan"));
          assert(!Object.prototype.hasOwnProperty.call(draftSaveBody, "scan_result"));
          assert.strictEqual(draftSaveBody.config.audit.scan_version, "");
          assert.strictEqual(draftSaveBody.config.audit.template_sha256, "");
          assert.deepStrictEqual(Object.keys(draftSaveBody.config.checks), ["output", "fields", "options", "slots", "content", "dimensions", "colors", "preview"]);
          assert.strictEqual(app.elements.publishVersionBtn.disabled, true);
          assert(app.elements.publishBlockerText.textContent.includes("发布接口未接入"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )


def test_v2_workbench_sanitizes_sensitive_failures_and_cancel_state():
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
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            if (textUrl === "/api/v2/templates" && options.method === "POST") return response({ state: { template_id: "V2CANCEL", template: { template_id: "V2CANCEL", name: "Cancel Demo" } } });
            if (textUrl === "/api/v2/templates") return response({ templates: [] });
            if (textUrl === "/local/templates/scan") {
              return new Promise((resolve, reject) => {
                options.signal.addEventListener("abort", () => {
                  const error = new Error("aborted");
                  error.name = "AbortError";
                  reject(error);
                });
              });
            }
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
          app.elements.cancelScanBtn.dispatch("click");
          await flush();
          assert.strictEqual(app.elements.scanProgress.textContent, "扫描已取消。");
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
