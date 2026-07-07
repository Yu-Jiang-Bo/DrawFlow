"""Small local HTTP server for the renderer MVP."""

from __future__ import annotations

import argparse
import json
import uuid
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .job_store import JobStore
from .llm_rule_parser import LlmRuleParser
from .paths import SERVICE_UPLOADS_DIR
from .render_service import RenderService
from .rule_center import build_template_rule_draft, check_template_definition
from .rule_store import DepartmentRuleStore
from .template_registry import TemplateRegistry
from .web_page import INDEX_HTML as WORKBENCH_HTML


LEGACY_INDEX_HTML = """<!doctype html>
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
    .template-manager {
      margin-top: 18px;
    }
    .template-manager textarea {
      min-height: 150px;
      resize: vertical;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      line-height: 1.55;
    }
    .form-hint {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .save-message {
      margin-top: 12px;
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    .save-message.ok { color: var(--success); }
    .save-message.error { color: var(--danger); }
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
        <span class="badge" id="templateTypeBadge">未选择</span>
      </div>
      <div class="panel-body">
        <div class="form-grid">
          <div class="field-full">
            <label for="template">模板</label>
            <select id="template"></select>
          </div>
          <div class="field-full">
            <label for="orderFile">订单表格</label>
            <input id="orderFile" type="file" accept=".xlsx,.xls,.csv" />
            <div class="form-hint">支持 Excel/CSV。渲染完成后会自动下载 AI 文件。</div>
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
  <section class="panel template-manager">
    <div class="panel-header">
      <h2 class="panel-title">模板管理</h2>
      <span class="badge">本地 JSON 注册表</span>
    </div>
    <div class="panel-body">
      <div class="form-grid">
        <div>
          <label for="managerTemplateId">模板 ID</label>
          <input id="managerTemplateId" placeholder="JJMB202607030001" />
        </div>
        <div>
          <label for="managerName">模板名称</label>
          <input id="managerName" placeholder="例如：皮质钥匙扣纯文字模板" />
        </div>
        <div>
          <label for="managerType">模板类型</label>
          <select id="managerType">
            <option value="pure_text_color_design">纯文字颜色/设计位置模板</option>
            <option value="pure_text_style">纯文字作图区模板</option>
          </select>
        </div>
        <div>
          <label for="managerStatus">状态</label>
          <select id="managerStatus">
            <option value="active">active</option>
            <option value="draft">draft</option>
            <option value="disabled">disabled</option>
          </select>
        </div>
        <div class="field-full">
          <label for="templateAiFile">上传模板 AI 文件</label>
          <input id="templateAiFile" type="file" accept=".ai" />
          <div class="form-hint">上传后会复制到 custom-renderer/templates/&lt;模板ID&gt;/template.ai。</div>
        </div>
        <div class="field-full">
          <label for="templateRulesJson">模板特有规则 JSON</label>
          <textarea id="templateRulesJson" placeholder='{"template_id":"JJMB...","defaults":{"design":"Design2","color":"Gold"}}'></textarea>
        </div>
      </div>
      <div class="actions">
        <button class="btn-secondary" id="clearTemplateBtn">清空</button>
        <button class="btn-primary" id="saveTemplateBtn">保存模板</button>
      </div>
      <div class="save-message" id="templateSaveResult">等待编辑</div>
    </div>
  </section>
  <section class="panel result-panel">
    <div class="panel-header">
      <h2 class="panel-title">任务结果</h2>
      <span class="badge" id="jobId">暂无任务</span>
    </div>
    <div class="panel-body">
      <div class="result-grid">
        <div class="result-cell"><span>任务编号</span><strong id="jobIdCell">-</strong></div>
        <div class="result-cell"><span>渲染状态</span><strong id="jobStatusCell">待提交</strong></div>
        <div class="result-cell"><span>下载状态</span><strong id="downloadStatus">-</strong></div>
      </div>
      <pre id="result">等待提交</pre>
    </div>
  </section>
</main>
<script>
let templateData = [];
let templateConfigLoadToken = 0;
async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function postForm(url, body) {
  const res = await fetch(url, { method: "POST", body });
  const text = await res.text();
  if (!res.ok) throw new Error(text);
  return JSON.parse(text);
}
async function init() {
  await checkHealth();
  await loadTemplates();
  renderRules(await getJson("/api/rules/department"));
}
async function loadTemplates(selectedId) {
  const templates = await getJson("/api/templates");
  templateData = templates.templates || [];
  const select = document.getElementById("template");
  const targetId = selectedId || select.value;
  select.innerHTML = "";
  templateData.forEach(t => {
    const option = document.createElement("option");
    option.value = t.template_id;
    option.textContent = `${t.template_id} | ${t.name}`;
    select.appendChild(option);
  });
  if (targetId && templateData.some(t => t.template_id === targetId)) {
    select.value = targetId;
  }
  syncTemplateSelection();
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
  const selected = templateData.find(t => t.template_id === select.value);
  document.getElementById("currentTemplate").textContent = selected ? selected.template_id.replace("JJMB", "") : "-";
  document.getElementById("templateTypeBadge").textContent = selected ? displayTemplateType(selected.template_type) : "未选择";
  renderTemplateSummary(selected);
  prefillTemplateForm(selected);
  loadTemplateConfigForEditor(selected);
}
function prefillTemplateForm(template) {
  if (!template) return;
  document.getElementById("managerTemplateId").value = template.template_id || "";
  document.getElementById("managerName").value = template.name || "";
  document.getElementById("managerType").value = template.template_type || "";
  document.getElementById("managerStatus").value = template.status || "active";
  document.getElementById("templateAiFile").value = "";
}
async function loadTemplateConfigForEditor(template) {
  const token = ++templateConfigLoadToken;
  const editor = document.getElementById("templateRulesJson");
  if (!template || !template.template_config) {
    editor.value = "";
    return;
  }
  try {
    const payload = await getJson(`/api/templates/${encodeURIComponent(template.template_id)}/config`);
    if (token !== templateConfigLoadToken) return;
    editor.value = payload.config ? JSON.stringify(payload.config, null, 2) : "";
  } catch (err) {
    if (token !== templateConfigLoadToken) return;
    editor.value = "";
  }
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
    ["类型", displayTemplateType(template.template_type)],
    ["状态", template.status],
    ["模板文件", template.template_ai ? "已配置" : "未配置"],
    ["模板规则", template.template_config ? "已配置" : "运行时导出"]
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
    const title = rule.display_name || `${departments} 部门`;
    const description = rule.description || describeDepartmentRule(rule);
    return `<div class="rule-item"><div class="rule-name"><span>${escapeHtml(title)}</span><span>${escapeHtml(departments)}</span></div><div class="rule-lines">${escapeHtml(description)}</div></div>`;
  }).join("");
}
function describeDepartmentRule(rule) {
  const parts = [];
  parts.push(rule.show_frame ? "输出带框效果图" : "输出无框效果图");
  parts.push(rule.apply_color_to_artwork ? "效果图应用字体颜色" : "字体颜色只作为文字标注");
  parts.push(`标注内容：${displayLabelFields(rule.label_fields || [])}`);
  return parts.join("；");
}
function displayLabelFields(fields) {
  const names = {
    order_no: "订单号",
    color_option: "字体颜色",
    text: "定制信息",
    product_name: "产品名称"
  };
  return fields.map(field => names[field] || field).join("、");
}
function resetResult() {
  document.getElementById("jobStatus").textContent = "待提交";
  document.getElementById("itemCount").textContent = "-";
  document.getElementById("jobId").textContent = "暂无任务";
  document.getElementById("jobIdCell").textContent = "-";
  document.getElementById("jobStatusCell").textContent = "待提交";
  document.getElementById("downloadStatus").textContent = "-";
  document.getElementById("result").textContent = "等待提交";
}
function renderJobResult(result) {
  document.getElementById("jobStatus").textContent = result.status || "-";
  document.getElementById("itemCount").textContent = result.stats && result.stats.items !== undefined ? result.stats.items : "-";
  document.getElementById("jobId").textContent = result.job_id || "暂无任务";
  document.getElementById("jobIdCell").textContent = result.job_id || "-";
  document.getElementById("jobStatusCell").textContent = result.status || "-";
  document.getElementById("downloadStatus").textContent = result.status === "completed" ? "准备下载" : "-";
  document.getElementById("result").textContent = renderResultMessage(result);
  if (result.status === "completed" && result.job_id && result.outputs && result.outputs.output_ai) {
    downloadOutput(result.job_id);
  }
}
function renderResultMessage(result) {
  if (result.status === "failed") {
    return result.error || "渲染失败";
  }
  if (result.status === "completed") {
    return `渲染完成，共 ${result.stats && result.stats.items !== undefined ? result.stats.items : "-"} 项，AI 文件已开始下载。`;
  }
  return JSON.stringify(result, null, 2);
}
function downloadOutput(jobId) {
  document.getElementById("downloadStatus").textContent = "下载中";
  window.location.href = `/api/jobs/${encodeURIComponent(jobId)}/download/output_ai`;
}
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
async function saveTemplate() {
  setTemplateSaveMessage("保存中", "");
  const form = new FormData();
  form.append("template_id", document.getElementById("managerTemplateId").value.trim());
  form.append("name", document.getElementById("managerName").value.trim());
  form.append("template_type", document.getElementById("managerType").value.trim());
  form.append("status", document.getElementById("managerStatus").value);
  form.append("template_rules_json", document.getElementById("templateRulesJson").value.trim());
  const file = document.getElementById("templateAiFile").files[0];
  if (file) form.append("template_ai", file);
  try {
    const result = await postForm("/api/templates", form);
    await loadTemplates(result.template.template_id);
    setTemplateSaveMessage(`已保存模板：${result.template.template_id}`, "ok");
  } catch (err) {
    setTemplateSaveMessage(String(err), "error");
  }
}
function clearTemplateForm() {
  document.getElementById("managerTemplateId").value = "";
  document.getElementById("managerName").value = "";
  document.getElementById("managerType").value = "pure_text_color_design";
  document.getElementById("managerStatus").value = "active";
  document.getElementById("templateAiFile").value = "";
  document.getElementById("templateRulesJson").value = "";
  setTemplateSaveMessage("等待编辑", "");
}
function setTemplateSaveMessage(text, state) {
  const target = document.getElementById("templateSaveResult");
  target.className = `save-message ${state || ""}`.trim();
  target.textContent = text;
}
document.getElementById("template").addEventListener("change", () => {
  syncTemplateSelection();
});
document.getElementById("saveTemplateBtn").addEventListener("click", saveTemplate);
document.getElementById("clearTemplateBtn").addEventListener("click", clearTemplateForm);
document.getElementById("renderBtn").addEventListener("click", async () => {
  const file = document.getElementById("orderFile").files[0];
  if (!file) {
    document.getElementById("result").textContent = "请先上传订单表格。";
    return;
  }
  const payload = new FormData();
  payload.append("template_id", document.getElementById("template").value);
  payload.append("order_file", file);
  document.getElementById("jobStatus").textContent = "运行中";
  document.getElementById("jobStatusCell").textContent = "运行中";
  document.getElementById("downloadStatus").textContent = "-";
  document.getElementById("result").textContent = "运行中";
  try {
    const result = await postForm("/api/render", payload);
    renderJobResult(result);
  } catch (err) {
    document.getElementById("jobStatus").textContent = "失败";
    document.getElementById("jobStatusCell").textContent = "失败";
    document.getElementById("result").textContent = String(err);
  }
});
document.getElementById("resetBtn").addEventListener("click", resetResult);
init().catch(err => {
  document.getElementById("jobStatus").textContent = "异常";
  document.getElementById("result").textContent = String(err);
});
function displayTemplateType(value) {
  const names = {
    pure_text_color_design: "纯文字颜色/设计位置模板",
    pure_text_style: "纯文字作图区模板"
  };
  return names[value] || value || "-";
}
</script>
</body>
</html>
"""


class RenderRequestHandler(BaseHTTPRequestHandler):
    registry = TemplateRegistry()
    jobs = JobStore()
    service = RenderService(registry=registry, jobs=jobs)
    rule_store = DepartmentRuleStore()
    llm_parser = LlmRuleParser()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(WORKBENCH_HTML)
            return
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if path == "/api/templates":
            self._send_json({"templates": [self._template_payload(item) for item in self.registry.list_templates()]})
            return
        if path.startswith("/api/templates/") and path.endswith("/rules/status"):
            template_id = unquote(path.split("/")[3])
            try:
                template = self.registry.get_template(template_id)
                self._send_json(check_template_definition(template))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path.startswith("/api/templates/") and path.endswith("/config"):
            template_id = unquote(path.split("/")[3])
            try:
                self._send_json(self._read_template_config(template_id))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path.startswith("/api/templates/") and path.endswith("/download/template_ai"):
            template_id = unquote(path.split("/")[3])
            try:
                self._send_template_ai(template_id)
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path == "/api/rules/department":
            self._send_json(self._read_department_rules())
            return
        if path == "/api/jobs":
            self._send_json({"jobs": self.jobs.list_recent(30)})
            return
        if path.startswith("/api/jobs/") and "/download/" in path:
            parts = path.strip("/").split("/")
            if len(parts) == 5 and parts[3] == "download" and parts[4] in {"output_ai", "render_task"}:
                self._send_job_output(parts[2], parts[4])
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
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
        if path == "/api/templates":
            try:
                fields, files = self._read_template_payload()
                template = self._register_template(fields, files)
                self._send_json({"template": self._template_payload(template)})
            except Exception as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/rules/department/draft":
            try:
                self._send_json(self._save_department_rule_draft(self._read_json()))
            except Exception as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/rules/department/parse":
            try:
                self._send_json(self._parse_department_rule_draft(self._read_json()))
            except Exception as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/rules/department/publish":
            try:
                self._send_json(self._publish_department_rule(self._read_json()))
            except Exception as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/templates/rules/draft":
            try:
                self._send_json(self._build_template_rule_draft(self._read_json()))
            except Exception as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path != "/api/render":
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            payload = self._read_render_payload()
            self._send_json(self.service.submit(payload))
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(body or "{}")

    def _read_template_payload(self) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self._read_multipart(content_type)
        payload = self._read_json()
        return {key: str(value) for key, value in payload.items()}, {}

    def _read_render_payload(self) -> dict[str, object]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self._read_json()
        fields, files = self._read_multipart(content_type)
        upload = self._first_file(files, "order_file")
        if not upload or not upload.get("content"):
            raise ValueError("请上传订单表格")
        order_file = self._save_uploaded_order(
            str(upload.get("filename", "")),
            upload["content"],  # type: ignore[arg-type]
        )
        payload: dict[str, object] = dict(fields)
        payload["order_file"] = str(order_file)
        return payload

    def _read_multipart(self, content_type: str) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        message = BytesParser(policy=policy.default).parsebytes(header + body)
        fields: dict[str, str] = {}
        files: dict[str, list[dict[str, object]]] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            data = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                files.setdefault(name, []).append({"filename": filename, "content": data})
            else:
                charset = part.get_content_charset() or "utf-8"
                fields[name] = data.decode(charset, errors="replace")
        return fields, files

    def _first_file(self, files: dict[str, list[dict[str, object]]], name: str) -> dict[str, object] | None:
        uploads = files.get(name, [])
        return uploads[0] if uploads else None

    def _template_payload(self, template: object) -> dict[str, object]:
        payload = template.to_json_dict()
        payload["rule_check"] = check_template_definition(template)
        return payload

    def _build_template_rule_draft(self, payload: dict[str, object]) -> dict[str, object]:
        template_id = str(payload.get("template_id", "")).strip()
        template_type = str(payload.get("template_type", "")).strip()
        natural_text = str(payload.get("natural_text", "")).strip()
        asset_count = int(payload.get("asset_count", 0) or 0)
        context: dict[str, object] = {}
        if template_id:
            try:
                template = self.registry.get_template(template_id)
                template_type = template_type or template.template_type
                asset_count = asset_count or len(template.assets)
                context = self._template_payload(template)
            except KeyError:
                pass
        if not template_id:
            raise ValueError("缺少 template_id")
        if not natural_text:
            raise ValueError("缺少自然语言规则说明")
        fallback = build_template_rule_draft(template_id, template_type, natural_text, asset_count)
        draft = self.llm_parser.parse(
            kind="template_rule",
            natural_text=natural_text,
            context={
                "template_id": template_id,
                "template_type": template_type,
                "asset_count": asset_count,
                "template": context,
            },
            fallback=fallback,
        )
        return {"draft": draft}

    def _register_template(self, fields: dict[str, str], files: dict[str, list[dict[str, object]]]) -> object:
        template_id = fields.get("template_id", "").strip()
        existing = None
        if template_id:
            try:
                existing = self.registry.get_template(template_id)
            except KeyError:
                existing = None

        template_ai = self._resolve_template_ai(fields, files, template_id, existing)
        assets = list(existing.assets) if existing else []
        assets.extend(self.registry.save_uploaded_assets(template_id, files.get("template_assets", [])))
        template_config = self._save_template_rules(fields, template_id, existing, len(assets))
        item = {
            "template_id": template_id,
            "name": fields.get("name", "").strip() or (existing.name if existing else ""),
            "template_type": fields.get("template_type", "").strip() or (existing.template_type if existing else ""),
            "pipeline": fields.get("pipeline", "").strip() or (existing.pipeline if existing else ""),
            "status": fields.get("status", "").strip() or (existing.status if existing else "draft"),
            "template_ai": template_ai,
            "default_columns": fields.get("default_columns", existing.default_columns if existing else 4),
            "default_hide_boxes": fields.get("default_hide_boxes", existing.default_hide_boxes if existing else True),
            "assets": assets,
        }
        if template_config:
            item["template_config"] = template_config
        return self.registry.upsert_template(item)

    def _resolve_template_ai(
        self,
        fields: dict[str, str],
        files: dict[str, list[dict[str, object]]],
        template_id: str,
        existing: object | None,
    ) -> str:
        upload = self._first_file(files, "template_ai")
        if upload and upload.get("content"):
            output_path = self.registry.save_uploaded_ai(template_id, str(upload.get("filename", "")), upload["content"])  # type: ignore[arg-type]
            return self.registry.to_config_path(output_path)
        path_text = fields.get("template_ai_path", "").strip() or fields.get("template_ai", "").strip()
        if path_text:
            candidate = Path(path_text)
            resolved = candidate if candidate.is_absolute() else (Path(__file__).resolve().parents[2] / candidate)
            if not resolved.exists():
                raise ValueError(f"模板 AI 文件不存在: {resolved}")
            return self.registry.to_config_path(resolved)
        if existing:
            return str(existing.template_ai)
        raise ValueError("请上传 .ai 模板文件")

    def _save_template_rules(
        self,
        fields: dict[str, str],
        template_id: str,
        existing: object | None,
        asset_count: int = 0,
    ) -> str:
        rules_text = fields.get("template_rules_json", "").strip()
        natural_text = fields.get("template_rules_text", "").strip()
        template_type = fields.get("template_type", "").strip() or (existing.template_type if existing else "")
        if not rules_text and natural_text:
            rules_text = json.dumps(
                self.llm_parser.parse(
                    kind="template_rule",
                    natural_text=natural_text,
                    context={
                        "template_id": template_id,
                        "template_type": template_type,
                        "asset_count": asset_count,
                    },
                    fallback=build_template_rule_draft(
                        template_id=template_id,
                        template_type=template_type,
                        natural_text=natural_text,
                        asset_count=asset_count,
                    ),
                ),
                ensure_ascii=False,
            )
        if rules_text:
            config_path = self.registry.save_template_config(template_id, rules_text)
            return self.registry.to_config_path(config_path) if config_path else ""
        if existing and existing.template_config:
            return self.registry.to_config_path(existing.template_config)
        return ""

    def _save_department_rule_draft(self, payload: dict[str, object]) -> dict[str, object]:
        return self.rule_store.save_draft(payload)

    def _parse_department_rule_draft(self, payload: dict[str, object]) -> dict[str, object]:
        natural_text = str(payload.get("natural_text", "")).strip()
        if not natural_text:
            raise ValueError("缺少自然语言规则说明")
        fallback = self.rule_store.build_draft_from_text(payload)
        draft = self.llm_parser.parse(
            kind="department_rule",
            natural_text=natural_text,
            context={
                "current_rules": self.rule_store.read().get("rules", []),
                "manual_fields": payload,
            },
            fallback=fallback,
        )
        return {"draft": draft}

    def _publish_department_rule(self, payload: dict[str, object]) -> dict[str, object]:
        return self.rule_store.publish(payload)

    def _read_department_rules(self) -> dict[str, object]:
        return self.rule_store.read()

    def _read_template_config(self, template_id: str) -> dict[str, object]:
        template = self.registry.get_template(template_id)
        if not template.template_config:
            return {"template_id": template_id, "path": "", "config": None}
        if not template.template_config.exists():
            return {"template_id": template_id, "path": str(template.template_config), "config": None}
        return {
            "template_id": template_id,
            "path": str(template.template_config),
            "config": json.loads(template.template_config.read_text(encoding="utf-8")),
        }

    def _send_template_ai(self, template_id: str) -> None:
        template = self.registry.get_template(template_id)
        if not template.template_ai.exists():
            self._send_error(HTTPStatus.NOT_FOUND, "模板 AI 文件不存在")
            return
        data = template.template_ai.read_bytes()
        download_name = _safe_download_name(f"{template.template_id}.ai")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _save_uploaded_order(self, filename: str, content: bytes) -> Path:
        if not content:
            raise ValueError("上传的订单表格为空")
        extension = Path(filename).suffix.lower()
        if extension not in {".xlsx", ".xls", ".csv"}:
            raise ValueError("订单表格只支持 .xlsx、.xls、.csv")
        SERVICE_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = SERVICE_UPLOADS_DIR / f"{uuid.uuid4().hex[:12]}-{_safe_download_name(filename)}"
        output_path.write_bytes(content)
        return output_path

    def _send_job_output(self, job_id: str, key: str) -> None:
        try:
            record = self.jobs.load(job_id)
        except KeyError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        output_path = Path(record.get("outputs", {}).get(key, ""))
        if not output_path.exists():
            self._send_error(HTTPStatus.NOT_FOUND, "输出文件不存在")
            return
        data = output_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{_safe_download_name(output_path.name)}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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


def _safe_download_name(value: str) -> str:
    chars = []
    for char in Path(value).name:
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("_")
    name = "".join(chars).strip("._")
    return name or "file"


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RenderRequestHandler)
    print(f"Renderer service listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
