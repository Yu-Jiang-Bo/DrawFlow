import json
import subprocess

from src.service.web_page_multi_template import MULTI_TEMPLATE_RENDER_SCRIPT
from src.service.web_page_multi_template_view import MULTI_TEMPLATE_RENDER_VIEW_SCRIPT


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
global.renderMultiTemplateResult = () => {{}};
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


def test_multi_template_browser_actions_use_parent_job_and_refresh_result():
    program = f'''
const vm = require("vm");
const script = {json.dumps(MULTI_TEMPLATE_RENDER_SCRIPT)};
const elements = {{
  renderMode: {{ value: "multi" }},
  multiTemplateExecuteBtn: {{ disabled: false }},
  multiTemplateRetryBtn: {{ disabled: false }},
  multiTemplateResumeBtn: {{ disabled: false }}
}};
global.document = {{
  body: {{ dataset: {{ multiTemplateRenderEnabled: "true" }} }},
  getElementById: (id) => elements[id]
}};
global.state = {{ multiTemplateParentJobId: "parent-1", multiTemplatePreflight: null, multiTemplatePollTimer: null, multiTemplatePollGeneration: 0 }};
global.hideRenderError = () => {{}};
global.showRenderError = () => {{ throw new Error("unexpected error dialog"); }};
global.setTaskRunning = () => {{}};
global.setRenderButtonsDisabled = () => {{}};
let progressKind = "";
global.showProgress = (kind) => {{ progressKind = kind; }};
global.completeProgress = (success) => {{ if (!success) throw new Error("completed result marked failed"); }};
global.failProgress = () => {{ throw new Error("unexpected action failure"); }};
global.hideRenderProgress = () => {{}};
global.loadJobs = async () => {{}};
let polledUrl = "";
let resolvePoll;
global.getJson = (url) => {{
  polledUrl = url;
  return new Promise(resolve => {{ resolvePoll = resolve; }});
}};
let clearedTimer = null;
global.setInterval = () => "poll-timer";
global.clearInterval = (timer) => {{ clearedTimer = timer; }};
let displayed = null;
global.renderMultiTemplateResult = (result) => {{ displayed = result; }};
const calls = [];
global.postJson = async (url, payload) => {{
  calls.push([url, payload]);
  return {{ job_id: "parent-1", status: "completed_with_errors", actions: {{ can_retry_failed: true }} }};
}};
vm.runInThisContext(script);

(async () => {{
  await submitMultiTemplateAction("retry-failed");
  if (progressKind !== "multiRender") throw new Error("action did not show render progress");
  if (calls.length !== 1 || calls[0][0] !== "/local/render/multi/parent-1/retry-failed") throw new Error("retry endpoint contract changed");
  if (JSON.stringify(calls[0][1]) !== "{{}}") throw new Error("retry payload must be empty");
  if (displayed?.status !== "completed_with_errors" || state.multiTemplatePreflight !== displayed) throw new Error("action response was not retained");
  resolvePoll({{ job_id: "parent-1", status: "running" }});
  await Promise.resolve();
  if (displayed?.status !== "completed_with_errors") throw new Error("stale progress response overwrote the completed result");
  if (polledUrl !== "/api/jobs/parent-1" || clearedTimer !== "poll-timer" || state.multiTemplatePollTimer !== null) throw new Error("execution progress polling was not cleaned up");
  let resolveAction;
  global.postJson = () => new Promise(resolve => {{ resolveAction = resolve; }});
  state.multiTemplateParentJobId = "old-parent";
  const staleAction = submitMultiTemplateAction("execute");
  invalidateMultiTemplatePreflight();
  resolveAction({{ job_id: "old-parent", status: "completed" }});
  await staleAction;
  if (state.multiTemplateParentJobId || state.multiTemplatePreflight || displayed !== null) throw new Error("stale action resurrected invalidated parent");
  if (Object.values(elements).some(button => button.disabled)) throw new Error("action buttons remained disabled");
}})().catch(error => {{ console.error(error.stack); process.exit(1); }});
'''

    subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)


def test_multi_template_browser_result_lists_partial_delivery_scope_and_controls():
    program = f'''
const vm = require("vm");
const script = {json.dumps(MULTI_TEMPLATE_RENDER_VIEW_SCRIPT)};
function node() {{
  return {{
    hidden: false, disabled: false, className: "", textContent: "", children: [],
    replaceChildren(...items) {{ this.children = items; }},
    append(...items) {{ this.children.push(...items); }},
    appendChild(item) {{ this.children.push(item); }}
  }};
}}
const elements = {{
  multiTemplateResultPanel: node(), multiTemplateResultSummary: node(), multiTemplateIssueList: node(), multiTemplateGroupList: node(),
  multiTemplateExecuteBtn: node(), multiTemplateRetryBtn: node(), multiTemplateResumeBtn: node(),
  multiTemplatePrimaryDownloadBtn: node(), multiTemplatePartialDownloadBtn: node()
}};
global.document = {{ getElementById: id => elements[id], createElement: () => node() }};
vm.runInThisContext(script);

renderMultiTemplateResult({{
  status: "completed_with_errors", order_count: 3, template_count: 2,
  group_counts: {{ succeeded: 1, failed: 1, unstarted: 0, interrupted: 0, running: 0 }},
  issues: [{{ template_id: "T-B", excel_row: 5, order_no: "ORDER-5", message: "模板运行配置不完整。", suggestion: "请修正模板。" }}],
  template_summaries: [
    {{ template_id: "T-A", order_count: 1, excel_rows: [2], template_version: "v1", canary_status: "succeeded", status: "succeeded", canary_representative: {{ excel_row: 2, order_no: "ORDER-2" }} }},
    {{ template_id: "T-B", order_count: 2, excel_rows: [5, 6], template_version: "v3", canary_status: "succeeded", status: "failed", error: "模板组渲染未完成，请检查模板配置和订单数据后重试。" }}
  ],
  actions: {{ execute: false, can_retry_failed: true, can_resume: false, can_download_partial: true }},
  outputs: {{ primary_output_available: false, partial_output_available: true }}
}});
if (elements.multiTemplateResultPanel.hidden) throw new Error("result panel was not shown");
if (!elements.multiTemplateIssueList.className.includes("error")) throw new Error("partial delivery warning was not marked");
const warning = elements.multiTemplateIssueList.children.map(item => item.textContent).join("\\n");
if (!warning.includes("T-B（Excel 第 5、6 行）")) throw new Error("missing delivery scope did not include template and rows");
const failedGroup = elements.multiTemplateGroupList.children[1].children[1].textContent;
if (!failedGroup.includes("Excel 第 5、6 行") || !failedGroup.includes("原因：")) throw new Error("group detail omitted rows or reason");
if (elements.multiTemplateRetryBtn.hidden || elements.multiTemplatePartialDownloadBtn.hidden) throw new Error("recoverable controls were hidden");
if (!elements.multiTemplatePrimaryDownloadBtn.hidden) throw new Error("complete package must remain hidden for partial delivery");

renderMultiTemplateResult({{ status: "interrupted", group_counts: {{ succeeded: 1, failed: 0, unstarted: 1, interrupted: 1, running: 0 }}, template_summaries: [], actions: {{ can_resume: true }}, outputs: {{}} }});
if (!elements.multiTemplateResultSummary.textContent.includes("已成功模板不会重复渲染") || elements.multiTemplateResumeBtn.hidden) throw new Error("interrupted recovery notice was incomplete");

renderMultiTemplateResult({{ status: "completed", group_counts: {{}}, template_summaries: [], actions: {{}}, outputs: {{ primary_output_available: true }} }});
if (!elements.multiTemplateIssueList.className || elements.multiTemplatePartialDownloadBtn.hidden !== true || elements.multiTemplatePrimaryDownloadBtn.hidden !== false) throw new Error("complete delivery controls did not replace partial delivery");
'''

    subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
