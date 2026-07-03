"""Small local HTTP server for the renderer MVP."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..jjmb_202508_main import DEPARTMENT_RULES_PATH
from .job_store import JobStore
from .render_service import RenderService
from .template_registry import TemplateRegistry


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>制图渲染服务</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f5f7;
      --surface: #ffffff;
      --surface-2: #f8fafc;
      --text: #1f2933;
      --muted: #687482;
      --line: #d9e0e7;
      --line-strong: #bdc8d3;
      --primary: #1f5eff;
      --primary-dark: #184bd0;
      --success: #16835b;
      --warning: #9a6700;
      --danger: #b42318;
      --shadow: 0 10px 24px rgba(31, 41, 51, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, "Microsoft YaHei", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }
    .topbar {
      background: #1f2933;
      color: #fff;
      border-bottom: 1px solid #111827;
    }
    .topbar-inner {
      width: min(1280px, calc(100vw - 40px));
      margin: 0 auto;
      min-height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .brand-title {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .brand-subtitle {
      color: #b8c2cc;
      font-size: 12px;
    }
    .service-status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 4px;
      background: rgba(255,255,255,0.06);
      font-size: 13px;
      color: #dbe4ee;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #7dd3a7;
    }
    main {
      width: min(1280px, calc(100vw - 40px));
      margin: 24px auto 36px;
    }
    .summary-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px 16px;
      box-shadow: 0 1px 2px rgba(31, 41, 51, 0.04);
    }
    .metric-label {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }
    .metric-value {
      font-size: 20px;
      font-weight: 700;
      color: var(--text);
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(520px, 1.35fr) minmax(360px, 0.9fr);
      gap: 18px;
      align-items: start;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      box-shadow: var(--shadow);
    }
    .panel-header {
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .panel-title {
      margin: 0;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .panel-body {
      padding: 18px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px 16px;
    }
    .field-full { grid-column: 1 / -1; }
    label {
      display: block;
      margin-bottom: 6px;
      font-size: 12px;
      font-weight: 700;
      color: #394756;
    }
    input, select, button, textarea {
      font: inherit;
    }
    input, select, textarea {
      width: 100%;
      min-height: 38px;
      padding: 8px 10px;
      border: 1px solid var(--line-strong);
      border-radius: 4px;
      background: #fff;
      color: var(--text);
      outline: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(31, 94, 255, 0.12);
    }
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 16px;
      align-items: center;
      margin-top: 2px;
    }
    .check {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
      color: #394756;
    }
    .check input {
      width: 16px;
      min-height: 16px;
      height: 16px;
      accent-color: var(--primary);
    }
    .actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
    }
    button {
      min-height: 38px;
      padding: 8px 14px;
      border-radius: 4px;
      border: 1px solid transparent;
      cursor: pointer;
      font-weight: 700;
    }
    .btn-primary {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-secondary {
      background: #fff;
      color: #263442;
      border-color: var(--line-strong);
    }
    .sidebar-stack {
      display: grid;
      gap: 18px;
    }
    .definition-list {
      display: grid;
      gap: 10px;
    }
    .definition {
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 12px;
      align-items: start;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }
    .definition:last-child {
      border-bottom: 0;
      padding-bottom: 0;
    }
    .definition dt {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .definition dd {
      margin: 0;
      color: var(--text);
      overflow-wrap: anywhere;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 4px;
      background: #e8efff;
      color: #214bb8;
      font-size: 12px;
      font-weight: 700;
    }
    .result-panel {
      margin-top: 18px;
    }
    .result-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .result-cell {
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 10px;
      background: var(--surface-2);
      min-height: 66px;
    }
    .result-cell span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .result-cell strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    pre {
      margin: 0;
      max-height: 330px;
      overflow: auto;
      white-space: pre-wrap;
      background: #0f1720;
      color: #dce7f2;
      border-radius: 4px;
      padding: 12px;
      font-size: 12px;
      line-height: 1.55;
    }
    .rules-list {
      display: grid;
      gap: 10px;
    }
    .rule-item {
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 10px 12px;
      background: var(--surface-2);
    }
    .rule-name {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
      font-weight: 700;
    }
    .rule-lines {
      color: var(--muted);
      font-size: 12px;
    }
    .message {
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 900px) {
      .topbar-inner, main { width: min(100vw - 24px, 1280px); }
      .summary-row, .workspace, .form-grid, .result-grid {
        grid-template-columns: 1fr;
      }
      .actions {
        justify-content: stretch;
      }
      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <h1 class="brand-title">制图渲染服务</h1>
      <div class="brand-subtitle">模板管理 / 订单解析 / AI8 渲染</div>
    </div>
    <div class="service-status"><span class="status-dot"></span><span id="healthText">服务检查中</span></div>
  </div>
</header>
<main>
  <section class="summary-row">
    <div class="metric"><div class="metric-label">模板数量</div><div class="metric-value" id="templateCount">0</div></div>
    <div class="metric"><div class="metric-label">当前模板</div><div class="metric-value" id="currentTemplate">-</div></div>
    <div class="metric"><div class="metric-label">任务状态</div><div class="metric-value" id="jobStatus">待提交</div></div>
    <div class="metric"><div class="metric-label">渲染项数</div><div class="metric-value" id="itemCount">-</div></div>
  </section>
  <div class="workspace">
    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">渲染任务</h2>
        <span class="badge" id="pipelineBadge">未选择</span>
      </div>
      <div class="panel-body">
        <div class="form-grid">
          <div class="field-full">
            <label for="template">模板</label>
            <select id="template"></select>
          </div>
          <div class="field-full">
            <label for="orderFile">订单表格路径</label>
            <input id="orderFile" placeholder="C:\\Users\\Administrator\\Desktop\\image\\test\\ai测试\\20260703111921_SoIaKp.xlsx" />
          </div>
          <div>
            <label for="outputName">输出文件名</label>
            <input id="outputName" value="web-render.ai" />
          </div>
          <div>
            <label for="columns">排版列数</label>
            <input id="columns" type="number" min="1" value="5" />
          </div>
          <div class="field-full checks">
            <label class="check"><input id="hideBoxes" type="checkbox" checked />正式无框输出</label>
            <label class="check"><input id="dryRun" type="checkbox" />只生成任务</label>
          </div>
        </div>
        <div class="actions">
          <button class="btn-secondary" id="resetBtn">重置</button>
          <button class="btn-primary" id="renderBtn">开始渲染</button>
        </div>
      </div>
    </section>
    <aside class="sidebar-stack">
      <section class="panel">
        <div class="panel-header"><h2 class="panel-title">模板摘要</h2></div>
        <div class="panel-body">
          <dl class="definition-list" id="templateSummary"></dl>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header"><h2 class="panel-title">部门规则</h2></div>
        <div class="panel-body">
          <div class="rules-list" id="rulesList"><div class="message">加载中</div></div>
        </div>
      </section>
    </aside>
  </div>
  <section class="panel result-panel">
    <div class="panel-header">
      <h2 class="panel-title">任务结果</h2>
      <span class="badge" id="jobId">暂无任务</span>
    </div>
    <div class="panel-body">
      <div class="result-grid">
        <div class="result-cell"><span>输出 AI</span><strong id="outputAi">-</strong></div>
        <div class="result-cell"><span>Render Task</span><strong id="renderTask">-</strong></div>
        <div class="result-cell"><span>Job 记录</span><strong id="jobPath">-</strong></div>
      </div>
      <pre id="result">等待提交</pre>
    </div>
  </section>
</main>
<script>
let templateData = [];
async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function postJson(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const text = await res.text();
  if (!res.ok) throw new Error(text);
  return JSON.parse(text);
}
async function init() {
  await checkHealth();
  const templates = await getJson("/api/templates");
  templateData = templates.templates || [];
  const select = document.getElementById("template");
  select.innerHTML = "";
  templateData.forEach(t => {
    const option = document.createElement("option");
    option.value = t.template_id;
    option.textContent = `${t.template_id} | ${t.name}`;
    option.dataset.columns = t.default_columns;
    option.dataset.hideBoxes = t.default_hide_boxes;
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    syncTemplateSelection();
  });
  syncTemplateSelection();
  renderRules(await getJson("/api/rules/department"));
  document.getElementById("templateCount").textContent = templateData.length;
}
async function checkHealth() {
  try {
    await getJson("/api/health");
    document.getElementById("healthText").textContent = "服务在线";
  } catch (err) {
    document.getElementById("healthText").textContent = "服务异常";
    throw err;
  }
}
function syncTemplateSelection() {
  const select = document.getElementById("template");
  const option = select.selectedOptions[0];
  const selected = templateData.find(t => t.template_id === select.value);
  if (option) {
    document.getElementById("columns").value = option.dataset.columns || 4;
    document.getElementById("hideBoxes").checked = option.dataset.hideBoxes === "true";
  }
  document.getElementById("currentTemplate").textContent = selected ? selected.template_id.replace("JJMB", "") : "-";
  document.getElementById("pipelineBadge").textContent = selected ? selected.pipeline : "未选择";
  renderTemplateSummary(selected);
}
function renderTemplateSummary(template) {
  const target = document.getElementById("templateSummary");
  if (!template) {
    target.innerHTML = '<div class="message">未选择模板</div>';
    return;
  }
  const rows = [
    ["模板 ID", template.template_id],
    ["名称", template.name],
    ["类型", template.template_type],
    ["Pipeline", template.pipeline],
    ["状态", template.status],
    ["AI 文件", template.template_ai],
    ["配置", template.template_config || "运行时导出"]
  ];
  target.innerHTML = rows.map(([key, value]) => `<div class="definition"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value || "-"))}</dd></div>`).join("");
}
function renderRules(rules) {
  const target = document.getElementById("rulesList");
  const list = rules.rules || [];
  if (!list.length) {
    target.innerHTML = '<div class="message">暂无规则</div>';
    return;
  }
  target.innerHTML = list.map(rule => {
    const departments = (rule.departments || []).join(" / ");
    const lines = (rule.label_lines || []).map(formatRuleLine).join("<br>");
    return `<div class="rule-item"><div class="rule-name"><span>${escapeHtml(rule.name || departments)}</span><span>${escapeHtml(departments)}</span></div><div class="rule-lines">${lines}</div></div>`;
  }).join("");
}
function formatRuleLine(line) {
  if (Array.isArray(line)) {
    return line.map(part => escapeHtml(part)).join(" + ");
  }
  return escapeHtml(line);
}
function resetResult() {
  document.getElementById("jobStatus").textContent = "待提交";
  document.getElementById("itemCount").textContent = "-";
  document.getElementById("jobId").textContent = "暂无任务";
  document.getElementById("outputAi").textContent = "-";
  document.getElementById("renderTask").textContent = "-";
  document.getElementById("jobPath").textContent = "-";
  document.getElementById("result").textContent = "等待提交";
}
function renderJobResult(result) {
  document.getElementById("jobStatus").textContent = result.status || "-";
  document.getElementById("itemCount").textContent = result.stats && result.stats.items !== undefined ? result.stats.items : "-";
  document.getElementById("jobId").textContent = result.job_id || "暂无任务";
  document.getElementById("outputAi").textContent = result.outputs && result.outputs.output_ai ? result.outputs.output_ai : "-";
  document.getElementById("renderTask").textContent = result.outputs && result.outputs.render_task ? result.outputs.render_task : "-";
  document.getElementById("jobPath").textContent = result.job_dir || "-";
  document.getElementById("result").textContent = JSON.stringify(result, null, 2);
}
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
document.getElementById("renderBtn").addEventListener("click", async () => {
  const payload = {
    template_id: document.getElementById("template").value,
    order_file: document.getElementById("orderFile").value,
    output_name: document.getElementById("outputName").value,
    columns: Number(document.getElementById("columns").value || 4),
    hide_boxes: document.getElementById("hideBoxes").checked,
    dry_run: document.getElementById("dryRun").checked
  };
  document.getElementById("jobStatus").textContent = "运行中";
  document.getElementById("result").textContent = "运行中";
  try {
    const result = await postJson("/api/render", payload);
    renderJobResult(result);
  } catch (err) {
    document.getElementById("jobStatus").textContent = "失败";
    document.getElementById("result").textContent = String(err);
  }
});
document.getElementById("resetBtn").addEventListener("click", resetResult);
init().catch(err => {
  document.getElementById("jobStatus").textContent = "异常";
  document.getElementById("result").textContent = String(err);
});
</script>
</body>
</html>
"""


class RenderRequestHandler(BaseHTTPRequestHandler):
    registry = TemplateRegistry()
    jobs = JobStore()
    service = RenderService(registry=registry, jobs=jobs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if path == "/api/templates":
            self._send_json({"templates": [item.to_json_dict() for item in self.registry.list_templates()]})
            return
        if path == "/api/rules/department":
            self._send_json(json.loads(DEPARTMENT_RULES_PATH.read_text(encoding="utf-8")))
            return
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            try:
                self._send_json(self.jobs.load(job_id))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/render":
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            payload = self._read_json()
            self._send_json(self.service.submit(payload))
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动本地制图渲染 Web/API 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RenderRequestHandler)
    print(f"Renderer service listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
