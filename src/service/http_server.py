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
    body { font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }
    main { max-width: 980px; margin: 0 auto; }
    label { display: block; margin: 12px 0 6px; font-weight: 600; }
    input, select, button, textarea { font: inherit; box-sizing: border-box; }
    input, select, textarea { width: 100%; padding: 8px; border: 1px solid #bbb; border-radius: 4px; }
    button { margin-top: 14px; padding: 9px 14px; border: 1px solid #333; background: #222; color: #fff; border-radius: 4px; cursor: pointer; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    pre { white-space: pre-wrap; background: #f5f5f5; border: 1px solid #ddd; padding: 12px; border-radius: 4px; }
    .muted { color: #666; font-size: 13px; }
  </style>
</head>
<body>
<main>
  <h1>制图渲染服务</h1>
  <p class="muted">本地 MVP：选择模板，填写订单 Excel 路径，后端生成 render task 并调用 Illustrator。</p>
  <div class="grid">
    <section>
      <label>模板</label>
      <select id="template"></select>
      <label>订单表格路径</label>
      <input id="orderFile" placeholder="C:\\Users\\Administrator\\Desktop\\image\\test\\ai测试\\20260703111921_SoIaKp.xlsx" />
      <label>输出文件名</label>
      <input id="outputName" value="web-render.ai" />
      <label>列数</label>
      <input id="columns" type="number" min="1" value="5" />
      <label><input id="hideBoxes" type="checkbox" checked style="width:auto" /> 正式无框输出</label>
      <label><input id="dryRun" type="checkbox" style="width:auto" /> 只生成任务，不调用 Illustrator</label>
      <button id="renderBtn">开始渲染</button>
    </section>
    <section>
      <h2>通用规则</h2>
      <pre id="rules">加载中...</pre>
    </section>
  </div>
  <h2>任务结果</h2>
  <pre id="result">等待提交...</pre>
</main>
<script>
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
  const templates = await getJson("/api/templates");
  const select = document.getElementById("template");
  templates.templates.forEach(t => {
    const option = document.createElement("option");
    option.value = t.template_id;
    option.textContent = `${t.template_id} - ${t.name}`;
    option.dataset.columns = t.default_columns;
    option.dataset.hideBoxes = t.default_hide_boxes;
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    const option = select.selectedOptions[0];
    document.getElementById("columns").value = option.dataset.columns || 4;
    document.getElementById("hideBoxes").checked = option.dataset.hideBoxes === "true";
  });
  select.dispatchEvent(new Event("change"));
  document.getElementById("rules").textContent = JSON.stringify(await getJson("/api/rules/department"), null, 2);
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
  document.getElementById("result").textContent = "运行中...";
  try {
    const result = await postJson("/api/render", payload);
    document.getElementById("result").textContent = JSON.stringify(result, null, 2);
  } catch (err) {
    document.getElementById("result").textContent = String(err);
  }
});
init().catch(err => document.getElementById("result").textContent = String(err));
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
