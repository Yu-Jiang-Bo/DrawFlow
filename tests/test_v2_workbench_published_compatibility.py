from pathlib import Path

from test_v2_workbench_js_behavior import run_node


def test_v2_workbench_uses_read_only_draft_compatibility_when_central_lacks_published_route():
    run_node(
        r"""
        (async () => {
          const requests = [];
          const draft = {
            metadata: { template_id: "SHARED001", name: "兼容模板" },
            manifest: { draft_revision: "d0011" },
            config: { template: { template_id: "SHARED001" } },
            scan: { outputs: [{ key: "Output_main" }] }
          };
          async function fakeFetch(url, options = {}) {
            const textUrl = String(url);
            requests.push({ url: textUrl, method: options.method || "GET" });
            if (textUrl === "/api/v2/templates") {
              return response({ templates: [{ template_id: "SHARED001", name: "兼容模板", publication: { status: "active", current_version: "v0003" } }] });
            }
            if (textUrl === "/api/v2/templates/SHARED001/published") {
              return response({ error: { reason: "v2_route_not_found", message: "请求的 V2 模板接口不存在。" } }, false);
            }
            if (textUrl === "/api/v2/templates/SHARED001/draft") return response({ draft });
            if (textUrl.endsWith("/validate")) return response({ validation: { checks: {} } });
            throw new Error(`unexpected request ${textUrl}`);
          }
          const app = createApp(fakeFetch, undefined, "?template_id=SHARED001");
          const state = global.DrawFlowV2WorkbenchContext.state;
          for (let index = 0; index < 4 && state.stage !== "structure"; index += 1) await flush();
          assert.strictEqual(state.selectedTemplateId, "SHARED001");
          assert.strictEqual(state.isPublishedView, true);
          assert.strictEqual(state.publishedDraftCompatibility, true);
          assert.strictEqual(state.draft.manifest.draft_revision, "d0011");
          assert.strictEqual(app.elements.templateName.disabled, true);
          assert.strictEqual(app.elements.createDraftFromPublishedBtn.hidden, true);
          assert(app.elements.scanSummaryWarning.textContent.includes("兼容只读"));
          assert.strictEqual(await global.createDraftFromPublished(), false);
          assert(requests.some((item) => item.url === "/api/v2/templates/SHARED001/published" && item.method === "GET"));
          assert(requests.some((item) => item.url === "/api/v2/templates/SHARED001/draft" && item.method === "GET"));
          assert(!requests.some((item) => item.url.endsWith("/draft-from-published") && item.method === "POST"));
        })().catch((error) => { console.error(error); process.exit(1); });
        """,
        cwd=Path(__file__).resolve().parents[1],
    )
