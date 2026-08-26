import json
import subprocess

from src.service.web_page_multi_template import MULTI_TEMPLATE_RENDER_SCRIPT


def test_multi_template_browser_state_machine_discards_stale_preflight_and_omits_template_id():
    program = f'''
const vm = require("vm");
const script = {json.dumps(MULTI_TEMPLATE_RENDER_SCRIPT)};
const elements = {{
  renderMode: {{ value: "multi" }},
  renderModeField: {{ hidden: true }},
  renderTemplateField: {{ hidden: false }},
  renderTemplate: {{ disabled: false }},
  multiTemplateHint: {{ hidden: true }},
  renderBtn: {{ textContent: "" }},
  renderTemplateBadge: {{ textContent: "" }},
  orderFile: {{ files: [{{ name: "orders.xlsx" }}] }},
  sheetName: {{ value: "订单" }}
}};
global.document = {{
  body: {{ dataset: {{ multiTemplateRenderEnabled: "true" }} }},
  getElementById: (id) => elements[id]
}};
global.state = {{ multiTemplateParentJobId: "", multiTemplatePreflight: null, multiTemplateInputRevision: 0 }};
global.FormData = class {{
  constructor() {{ this.values = []; }}
  append(key, value) {{ this.values.push([key, value]); }}
}};
global.hideRenderError = () => {{}};
global.setTaskRunning = () => {{}};
global.showProgress = () => {{}};
global.completeProgress = () => {{}};
global.failProgress = () => {{ throw new Error("unexpected current-request failure"); }};
global.showRenderError = () => {{ throw new Error("unexpected stale error dialog"); }};
let hidden = 0;
global.hideRenderProgress = () => {{ hidden += 1; }};
global.setRenderButtonsDisabled = () => {{}};
global.loadJobs = async () => {{}};
let resolveRequest;
const calls = [];
global.postForm = (url, payload) => {{
  calls.push([url, payload.values]);
  return new Promise(resolve => {{ resolveRequest = resolve; }});
}};
vm.runInThisContext(script);

(async () => {{
  syncMultiTemplateMode();
  if (elements.renderTemplateField.hidden !== true || elements.renderTemplate.disabled !== true || elements.multiTemplateHint.hidden !== false) throw new Error("multi mode UI not applied");
  const stale = submitMultiTemplatePreflight();
  invalidateMultiTemplatePreflight();
  resolveRequest({{ status: "ready", job_id: "stale-parent" }});
  await stale;
  if (state.multiTemplateParentJobId || state.multiTemplatePreflight || hidden !== 1) throw new Error("stale preflight was retained");
  const current = submitMultiTemplatePreflight();
  resolveRequest({{ status: "ready", job_id: "current-parent" }});
  await current;
  if (state.multiTemplateParentJobId !== "current-parent") throw new Error("current preflight was not retained");
  const entries = calls[1][1];
  if (calls[1][0] !== "/local/render/multi/preflight" || entries.some(([key]) => key === "template_id")) throw new Error("multi preflight request contract changed");
  if (!entries.some(([key]) => key === "order_file") || !entries.some(([key, value]) => key === "sheet_name" && value === "订单")) throw new Error("multi preflight payload incomplete");
}})().catch(error => {{ console.error(error.stack); process.exit(1); }});
'''

    subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
