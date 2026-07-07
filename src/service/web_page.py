"""Static HTML for the local renderer workbench."""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>制图渲染工作台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2f6;
      --ink: #17212b;
      --muted: #657385;
      --soft: #f7f9fc;
      --surface: #ffffff;
      --line: #d5dde7;
      --line-strong: #b9c5d2;
      --primary: #1456d9;
      --primary-dark: #0d42ac;
      --success: #16794c;
      --warning: #8a5a00;
      --danger: #ad2b21;
      --shadow: 0 14px 34px rgba(23, 33, 43, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, "Microsoft YaHei", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }
    button, input, select, textarea {
      font: inherit;
    }
    button {
      min-height: 36px;
      padding: 8px 14px;
      border-radius: 5px;
      border: 1px solid transparent;
      font-weight: 700;
      cursor: pointer;
      background: #fff;
    }
    input, select, textarea {
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      padding: 8px 10px;
      color: var(--ink);
      background: #fff;
      outline: none;
    }
    textarea {
      min-height: 148px;
      resize: vertical;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(20, 86, 217, 0.13);
    }
    label {
      display: block;
      margin-bottom: 6px;
      color: #354457;
      font-size: 12px;
      font-weight: 700;
    }
    .app-header {
      background: #17212b;
      color: #fff;
      border-bottom: 1px solid #0d141c;
    }
    .header-inner {
      width: min(1320px, calc(100vw - 40px));
      margin: 0 auto;
      min-height: 66px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    .brand h1 {
      margin: 0 0 2px;
      font-size: 19px;
      letter-spacing: 0;
    }
    .brand p {
      margin: 0;
      color: #b9c5d2;
      font-size: 12px;
    }
    .health {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 5px;
      color: #dbe5f0;
      background: rgba(255, 255, 255, 0.06);
      white-space: nowrap;
    }
    .health-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #8ee0ae;
    }
    .shell {
      width: min(1320px, calc(100vw - 40px));
      margin: 22px auto 36px;
    }
    .tabs {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px;
      margin-bottom: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 1px 2px rgba(23, 33, 43, 0.04);
    }
    .tab {
      color: #405064;
      border-color: transparent;
      background: transparent;
    }
    .tab.active {
      color: #fff;
      background: var(--primary);
      border-color: var(--primary);
    }
    .page { display: none; }
    .page.active { display: block; }
    .grid {
      display: grid;
      gap: 16px;
    }
    .grid.two {
      grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.9fr);
      align-items: start;
    }
    .grid.template-layout {
      grid-template-columns: minmax(260px, 0.7fr) minmax(0, 1.6fr);
      align-items: start;
    }
    .grid.rule-layout {
      grid-template-columns: minmax(240px, 0.56fr) minmax(0, 1.7fr);
      align-items: start;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel-header {
      min-height: 56px;
      padding: 15px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
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
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 15px 16px;
    }
    .field-full { grid-column: 1 / -1; }
    .task-upload {
      min-height: 104px;
      padding: 18px;
      border: 1px dashed var(--line-strong);
      border-radius: 7px;
      background: var(--soft);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 10px;
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid var(--line);
    }
    .btn-primary {
      color: #fff;
      background: var(--primary);
      border-color: var(--primary);
    }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-secondary {
      color: #293847;
      border-color: var(--line-strong);
      background: #fff;
    }
    .btn-subtle {
      color: #405064;
      border-color: var(--line);
      background: var(--soft);
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 4px;
      background: #e8efff;
      color: #214bb8;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .status-badge.success {
      color: var(--success);
      background: #e5f6ed;
    }
    .status-badge.warn {
      color: var(--warning);
      background: #fff5d7;
    }
    .definition-list {
      display: grid;
      gap: 11px;
    }
    .definition {
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 12px;
      padding-bottom: 11px;
      border-bottom: 1px solid var(--line);
    }
    .definition:last-child {
      padding-bottom: 0;
      border-bottom: 0;
    }
    .definition dt {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .definition dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    .result-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }
    .result-cell {
      min-height: 70px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }
    .result-cell span {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .result-cell strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 13px;
    }
    .list {
      display: grid;
      gap: 10px;
    }
    .list-item {
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
    }
    .item-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 5px;
      font-weight: 700;
    }
    .item-meta {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .template-list {
      display: grid;
      gap: 8px;
    }
    .template-row {
      width: 100%;
      min-height: 52px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
      color: var(--ink);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }
    .template-row.active {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(20, 86, 217, 0.12);
    }
    .template-select {
      min-height: 34px;
      padding: 0;
      text-align: left;
      border: 0;
      background: transparent;
      color: var(--ink);
      font-weight: 400;
    }
    .template-select strong {
      display: block;
      margin-bottom: 3px;
      overflow-wrap: anywhere;
    }
    .template-select span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .template-actions {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .template-actions button {
      min-height: 30px;
      padding: 5px 9px;
      font-size: 12px;
    }
    .asset-panel-grid {
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(300px, 1.1fr);
      gap: 16px;
      align-items: stretch;
    }
    .upload-box {
      min-height: 236px;
      padding: 16px;
      border: 1px dashed var(--line-strong);
      border-radius: 7px;
      background: var(--soft);
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .asset-list {
      min-height: 236px;
      border: 1px solid var(--line);
      border-radius: 7px;
      overflow: hidden;
      background: #fff;
    }
    .asset-list-head,
    .asset-row {
      display: grid;
      grid-template-columns: 1.25fr 92px 86px;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }
    .asset-list-head {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      background: #f4f7fa;
    }
    .asset-row:last-child { border-bottom: 0; }
    .asset-name {
      overflow-wrap: anywhere;
      font-weight: 700;
    }
    .preview-box {
      min-height: 154px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfe;
    }
    .preview-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .preview-chip {
      min-height: 54px;
      padding: 10px 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    .preview-chip span {
      display: block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .preview-chip strong {
      display: block;
      overflow-wrap: anywhere;
    }
    .rule-category {
      width: 100%;
      text-align: left;
      min-height: 46px;
      margin-bottom: 8px;
      border: 1px solid var(--line);
      color: #36485a;
      background: var(--soft);
    }
    .rule-category.active {
      color: #fff;
      border-color: var(--primary);
      background: var(--primary);
    }
    .rule-detail-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 0.78fr);
      gap: 16px;
      align-items: start;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #fff;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      background: #f4f7fa;
    }
    td {
      overflow-wrap: anywhere;
    }
    .empty {
      color: var(--muted);
      padding: 12px;
    }
    .message {
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
    }
    .message.ok { color: var(--success); }
    .message.error { color: var(--danger); }
    .download-link {
      color: var(--primary);
      font-weight: 700;
      text-decoration: none;
    }
    .download-link:hover {
      text-decoration: underline;
    }
    @media (max-width: 960px) {
      .header-inner, .shell { width: min(100vw - 24px, 1320px); }
      .tabs { overflow-x: auto; }
      .grid.two,
      .grid.template-layout,
      .grid.rule-layout,
      .form-grid,
      .asset-panel-grid,
      .result-strip,
      .preview-grid,
      .rule-detail-grid {
        grid-template-columns: 1fr;
      }
      .actions {
        justify-content: stretch;
      }
      .actions button {
        width: 100%;
      }
      .asset-list-head, .asset-row {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <div class="header-inner">
      <div class="brand">
        <h1>制图渲染工作台</h1>
        <p>模板资产、订单出图、规则配置</p>
      </div>
      <div class="health"><span class="health-dot"></span><span id="healthText">服务检查中</span></div>
    </div>
  </header>

  <main class="shell">
    <nav class="tabs" aria-label="主导航">
      <button class="tab active" data-page-tab="render">出图任务</button>
      <button class="tab" data-page-tab="templates">模板管理</button>
      <button class="tab" data-page-tab="rules">规则配置</button>
      <button class="tab" data-page-tab="jobs">任务记录</button>
    </nav>

    <section class="page active" id="page-render">
      <div class="grid two">
        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">出图任务</h2>
            <span class="status-badge" id="renderTemplateBadge">未选择模板</span>
          </div>
          <div class="panel-body">
            <div class="form-grid">
              <div class="field-full">
                <label for="renderTemplate">模板</label>
                <select id="renderTemplate"></select>
              </div>
              <div class="field-full task-upload">
                <label for="orderFile">订单表格</label>
                <input id="orderFile" type="file" accept=".xlsx,.xls,.csv" />
              </div>
            </div>
            <div class="actions">
              <button class="btn-secondary" id="resetTaskBtn">重置</button>
              <button class="btn-subtle" id="dryRunBtn">解析测试</button>
              <button class="btn-primary" id="renderBtn">生成效果图</button>
            </div>
            <div class="result-strip">
              <div class="result-cell"><span>任务编号</span><strong id="resultJobId">-</strong></div>
              <div class="result-cell"><span>渲染状态</span><strong id="resultStatus">待提交</strong></div>
              <div class="result-cell"><span>渲染项数</span><strong id="resultItems">-</strong></div>
              <div class="result-cell"><span>下载状态</span><strong id="resultDownload">-</strong></div>
            </div>
            <div class="message" id="taskMessage">等待提交</div>
          </div>
        </section>

        <aside class="grid">
          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">当前模板状态</h2>
              <span class="status-badge" id="templateStatusBadge">-</span>
            </div>
            <div class="panel-body">
              <dl class="definition-list" id="renderTemplateStatus"></dl>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2 class="panel-title">最近任务</h2>
              <button class="btn-subtle" id="refreshJobsBtn">刷新</button>
            </div>
            <div class="panel-body">
              <div class="list" id="recentJobs"></div>
            </div>
          </section>
        </aside>
      </div>
    </section>

    <section class="page" id="page-templates">
      <div class="grid template-layout">
        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">模板列表</h2>
            <span class="status-badge" id="templateCountBadge">0 个</span>
          </div>
          <div class="panel-body">
            <div class="template-list" id="templateList"></div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">新增或编辑模板</h2>
            <span class="status-badge">纯文字模板</span>
          </div>
          <div class="panel-body">
            <div class="form-grid">
              <div>
                <label for="templateId">模板 ID</label>
                <input id="templateId" placeholder="JJMB202607030001" />
              </div>
              <div>
                <label for="templateName">模板名称</label>
                <input id="templateName" placeholder="例如：皮质钥匙扣文字模板" />
              </div>
              <div>
                <label for="templateType">模板类型</label>
                <select id="templateType">
                  <option value="pure_text">纯文字模板</option>
                  <option value="pure_text_color_design">纯文字颜色/设计位置模板</option>
                  <option value="pure_text_style">纯文字作图区模板</option>
                  <option value="curved_title_text">弯曲标题文字模板</option>
                  <option value="annotated_ai">标准标注 AI 模板</option>
                  <option value="asset_split">独立设计资产模板</option>
                </select>
              </div>
              <div>
                <label for="templateStatus">状态</label>
                <select id="templateStatus">
                  <option value="active">启用</option>
                  <option value="draft">草稿</option>
                  <option value="disabled">停用</option>
                </select>
              </div>
              <div class="field-full">
                <label>上传.ai模版</label>
                <div class="asset-panel-grid">
                  <div class="upload-box">
                    <div>
                      <label for="primaryAiFile">主模板文件</label>
                      <input id="primaryAiFile" type="file" accept=".ai" />
                    </div>
                    <div>
                      <label for="assetAiFiles">附加模板文件</label>
                      <input id="assetAiFiles" type="file" accept=".ai" multiple />
                    </div>
                  </div>
                  <div class="asset-list">
                    <div class="asset-list-head"><span>文件</span><span>类型</span><span>状态</span></div>
                    <div id="assetRows"></div>
                  </div>
                </div>
              </div>
              <div class="field-full">
                <label for="templateRuleText">模板特有规则</label>
                <textarea id="templateRuleText" placeholder="例如：未选择颜色默认金色；未选择设计默认 Design2；Design2 字体逆时针旋转 15 度。"></textarea>
              </div>
              <div class="field-full">
                <label>编译后的规则说明</label>
                <div class="preview-box" id="templateRulePreview"></div>
              </div>
            </div>
            <div class="actions">
              <button class="btn-subtle" id="previewTemplateRuleBtn">生成预览</button>
              <button class="btn-primary" id="saveTemplateBtn">保存模板</button>
            </div>
            <div class="message" id="templateSaveMessage">等待编辑</div>
          </div>
        </section>
      </div>
    </section>

    <section class="page" id="page-rules">
      <div class="grid rule-layout">
        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">规则分类</h2>
            <button class="btn-subtle" id="newRuleBtn">新增规则</button>
          </div>
          <div class="panel-body">
            <div id="ruleCategories"></div>
            <div style="margin-top:18px">
              <label>全局/店铺规则摘要</label>
              <div class="preview-box" id="globalRulesSummary"></div>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">规则配置</h2>
            <span class="status-badge" id="ruleStatusBadge">未选择</span>
          </div>
          <div class="panel-body">
            <div class="rule-detail-grid">
              <div>
                <div class="form-grid" id="ruleDefinition">
                  <div>
                    <label for="ruleName">规则名称</label>
                    <input id="ruleName" placeholder="例如：K_T_FK_ZK" />
                  </div>
                  <div>
                    <label for="ruleDisplayName">显示名称</label>
                    <input id="ruleDisplayName" placeholder="例如：K/T/FK/ZK 部门" />
                  </div>
                  <div>
                    <label for="ruleDepartments">适用部门</label>
                    <input id="ruleDepartments" placeholder="多个部门用 / 或 , 分隔" />
                  </div>
                  <div>
                    <label for="ruleMatch">匹配方式</label>
                    <select id="ruleMatch">
                      <option value="exact">精确匹配</option>
                      <option value="contains">包含匹配</option>
                    </select>
                  </div>
                  <div>
                    <label for="ruleLabelFields">标注字段</label>
                    <input id="ruleLabelFields" placeholder="订单号、字体颜色、定制信息" />
                  </div>
                  <div>
                    <label for="ruleShowFrame">输出框</label>
                    <select id="ruleShowFrame">
                      <option value="false">不带框</option>
                      <option value="true">带框</option>
                    </select>
                  </div>
                  <div class="field-full">
                    <label for="ruleColorMode">颜色处理</label>
                    <select id="ruleColorMode">
                      <option value="label">颜色只作为标注</option>
                      <option value="artwork">效果图应用颜色</option>
                    </select>
                  </div>
                </div>
                <div style="margin-top:16px">
                  <label for="ruleNaturalText">自然语言规则</label>
                  <textarea id="ruleNaturalText"></textarea>
                </div>
              </div>
              <div>
                <label>结构化预览</label>
                <div class="preview-box" id="rulePreview"></div>
              </div>
            </div>
            <div class="actions">
              <button class="btn-subtle" id="previewRuleBtn">生成预览</button>
              <button class="btn-primary" id="saveRuleDraftBtn">保存草稿</button>
              <button class="btn-primary" id="publishRuleBtn">保存为发布规则</button>
            </div>
            <div class="message" id="ruleSaveMessage">等待编辑</div>
          </div>
        </section>
      </div>
    </section>

    <section class="page" id="page-jobs">
      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">任务记录</h2>
          <button class="btn-subtle" id="refreshJobsPageBtn">刷新</button>
        </div>
        <div class="panel-body">
          <table>
            <thead>
              <tr>
                <th>任务编号</th>
                <th>模板</th>
                <th>状态</th>
                <th>项数</th>
                <th>创建时间</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody id="jobsTableBody"></tbody>
          </table>
        </div>
      </section>
    </section>
  </main>

  <script>
    const state = {
      templates: [],
      jobs: [],
      departmentRules: [],
      ruleDrafts: [],
      defaultRule: {},
      shopRules: {},
      selectedTemplateId: "",
      selectedRuleName: "",
      ruleMode: "published",
      templateRuleDraft: null,
      templateRulePreviewSignature: ""
    };

    const typeNames = {
      pure_text: "纯文字模板",
      pure_text_color_design: "纯文字颜色/设计位置模板",
      pure_text_style: "纯文字作图区模板",
      curved_title_text: "弯曲标题文字模板",
      annotated_ai: "标准标注 AI 模板",
      asset_split: "独立设计资产模板"
    };
    const statusNames = {
      active: "启用",
      draft: "草稿",
      disabled: "停用",
      completed: "完成",
      failed: "失败",
      running: "运行中",
      queued: "排队中"
    };
    const fieldNames = {
      order_no: "订单号",
      color_option: "字体颜色",
      text: "定制信息",
      product_name: "产品名称"
    };

    async function init() {
      bindEvents();
      await checkHealth();
      await Promise.all([loadTemplates(), loadRules(), loadJobs()]);
      resetTaskResult();
    }

    function bindEvents() {
      document.querySelectorAll("[data-page-tab]").forEach(button => {
        button.addEventListener("click", () => switchPage(button.dataset.pageTab));
      });
      document.getElementById("renderTemplate").addEventListener("change", event => {
        state.selectedTemplateId = event.target.value;
        syncSelectedTemplate();
      });
      document.getElementById("dryRunBtn").addEventListener("click", () => submitRender(true));
      document.getElementById("renderBtn").addEventListener("click", () => submitRender(false));
      document.getElementById("resetTaskBtn").addEventListener("click", resetTaskResult);
      document.getElementById("refreshJobsBtn").addEventListener("click", loadJobs);
      document.getElementById("refreshJobsPageBtn").addEventListener("click", loadJobs);
      document.getElementById("previewTemplateRuleBtn").addEventListener("click", renderTemplateRulePreviewFromServer);
      document.getElementById("saveTemplateBtn").addEventListener("click", saveTemplate);
      document.getElementById("assetAiFiles").addEventListener("change", renderAssetRows);
      document.getElementById("primaryAiFile").addEventListener("change", renderAssetRows);
      document.getElementById("templateRuleText").addEventListener("input", markTemplateRulePreviewStale);
      document.getElementById("previewRuleBtn").addEventListener("click", renderRulePreviewFromServer);
      document.getElementById("saveRuleDraftBtn").addEventListener("click", saveRuleDraft);
      document.getElementById("publishRuleBtn").addEventListener("click", publishRule);
      document.getElementById("newRuleBtn").addEventListener("click", newRuleDraft);
      ["ruleName", "ruleDisplayName", "ruleDepartments", "ruleMatch", "ruleLabelFields", "ruleShowFrame", "ruleColorMode", "ruleNaturalText"].forEach(id => {
        document.getElementById(id).addEventListener("input", renderRulePreview);
        document.getElementById(id).addEventListener("change", renderRulePreview);
      });
    }

    function switchPage(name) {
      document.querySelectorAll("[data-page-tab]").forEach(button => {
        button.classList.toggle("active", button.dataset.pageTab === name);
      });
      document.querySelectorAll(".page").forEach(page => {
        page.classList.toggle("active", page.id === `page-${name}`);
      });
    }

    async function checkHealth() {
      try {
        await getJson("/api/health");
        document.getElementById("healthText").textContent = "服务在线";
      } catch (error) {
        document.getElementById("healthText").textContent = "服务异常";
        throw error;
      }
    }

    async function loadTemplates(selectedId) {
      const payload = await getJson("/api/templates");
      state.templates = payload.templates || [];
      if (selectedId) {
        state.selectedTemplateId = selectedId;
      } else if (!state.selectedTemplateId && state.templates.length) {
        state.selectedTemplateId = state.templates[0].template_id;
      }
      renderTemplateOptions();
      renderTemplateList();
      syncSelectedTemplate();
    }

    async function loadRules() {
      const payload = await getJson("/api/rules/department");
      state.departmentRules = payload.rules || [];
      state.ruleDrafts = payload.drafts || [];
      state.defaultRule = payload.default || {};
      state.shopRules = payload.shop_rules || {};
      if (state.selectedRuleName && !selectedRule()) {
        state.selectedRuleName = "";
        state.ruleMode = "published";
      }
      if (!state.selectedRuleName && state.departmentRules.length) {
        state.selectedRuleName = state.departmentRules[0].name;
        state.ruleMode = "published";
      }
      renderRuleCategories();
      renderGlobalRulesSummary();
      syncSelectedRule();
    }

    async function loadJobs() {
      const payload = await getJson("/api/jobs");
      state.jobs = payload.jobs || [];
      renderRecentJobs();
      renderJobsTable();
    }

    function renderTemplateOptions() {
      const select = document.getElementById("renderTemplate");
      select.innerHTML = "";
      state.templates.forEach(template => {
        const option = document.createElement("option");
        option.value = template.template_id;
        option.textContent = `${template.template_id} | ${template.name}`;
        select.appendChild(option);
      });
      if (state.selectedTemplateId) {
        select.value = state.selectedTemplateId;
      }
    }

    function renderTemplateList() {
      document.getElementById("templateCountBadge").textContent = `${state.templates.length} 个`;
      const target = document.getElementById("templateList");
      if (!state.templates.length) {
        target.innerHTML = '<div class="empty">暂无模板</div>';
        return;
      }
      target.innerHTML = state.templates.map(template => `
        <div class="template-row ${template.template_id === state.selectedTemplateId ? "active" : ""}" data-template-id="${escapeHtml(template.template_id)}">
          <button class="template-select" data-template-select="${escapeHtml(template.template_id)}">
            <strong>${escapeHtml(template.template_id)}</strong>
            <span>${escapeHtml(template.name || "-")}</span>
          </button>
          <div class="template-actions">
            <button class="btn-subtle" data-template-download="${escapeHtml(template.template_id)}">下载</button>
            <button class="btn-secondary" data-template-delete="${escapeHtml(template.template_id)}">删除</button>
          </div>
        </div>
      `).join("");
      target.querySelectorAll("[data-template-select]").forEach(button => {
        button.addEventListener("click", () => {
          state.selectedTemplateId = button.dataset.templateSelect;
          renderTemplateOptions();
          renderTemplateList();
          syncSelectedTemplate();
          switchPage("templates");
        });
      });
      target.querySelectorAll("[data-template-download]").forEach(button => {
        button.addEventListener("click", () => downloadTemplate(button.dataset.templateDownload));
      });
      target.querySelectorAll("[data-template-delete]").forEach(button => {
        button.addEventListener("click", () => deleteTemplate(button.dataset.templateDelete));
      });
    }

    function syncSelectedTemplate() {
      const template = selectedTemplate();
      if (!template) {
        document.getElementById("renderTemplateBadge").textContent = "未选择模板";
        document.getElementById("templateStatusBadge").textContent = "-";
        document.getElementById("renderTemplateStatus").innerHTML = '<div class="empty">暂无模板</div>';
        clearTemplateForm();
        return;
      }
      document.getElementById("renderTemplate").value = template.template_id;
      document.getElementById("renderTemplateBadge").textContent = displayType(template.template_type);
      document.getElementById("templateStatusBadge").textContent = displayStatus(template.status);
      const ruleCheck = template.rule_check || {};
      document.getElementById("renderTemplateStatus").innerHTML = definitionHtml([
        ["模板 ID", template.template_id],
        ["名称", template.name],
        ["状态", displayStatus(template.status)],
        ["类型", displayType(template.template_type)],
        ["主模板", template.template_ai ? "已配置" : "未配置"],
        ["附加模板", `${(template.assets || []).length} 个`],
        ["特有规则", template.template_config ? "已配置" : "未配置"],
        ["规则状态", ruleCheck.complete ? "完整" : "待补充"],
        ["可渲染", ruleCheck.renderable ? "可以" : "不可以"],
        ["缺失规则", displayMissingRules(ruleCheck.missing || [])],
        ["规则提示", (ruleCheck.warnings || []).join("；") || "-"]
      ]);
      fillTemplateForm(template);
      renderTemplateList();
    }

    function fillTemplateForm(template) {
      document.getElementById("templateId").value = template.template_id || "";
      document.getElementById("templateName").value = template.name || "";
      document.getElementById("templateType").value = template.template_type || "pure_text_color_design";
      document.getElementById("templateStatus").value = template.status || "active";
      document.getElementById("primaryAiFile").value = "";
      document.getElementById("assetAiFiles").value = "";
      loadTemplateRuleText(template);
      renderAssetRows();
    }

    async function loadTemplateRuleText(template) {
      const editor = document.getElementById("templateRuleText");
      editor.value = "";
      state.templateRuleDraft = null;
      state.templateRulePreviewSignature = "";
      if (!template || !template.template_config) {
        renderTemplateRulePreview();
        return;
      }
      try {
        const payload = await getJson(`/api/templates/${encodeURIComponent(template.template_id)}/config`);
        const config = payload.config || {};
        editor.value = config.raw_text || config.notes || config.description || "";
        state.templateRuleDraft = payload.config || null;
        state.templateRulePreviewSignature = editor.value.trim();
      } catch (error) {
        editor.value = "";
        state.templateRuleDraft = null;
        state.templateRulePreviewSignature = "";
      }
      renderTemplateRulePreview();
    }

    function renderAssetRows() {
      const template = formTemplate();
      const rows = [];
      if (template && template.template_ai) {
        rows.push({ name: fileName(template.template_ai), type: "主模板", status: "已保存" });
      }
      (template && template.assets ? template.assets : []).forEach(asset => {
        rows.push({ name: asset.file_name || fileName(asset.stored_path), type: "附加模板", status: "已保存" });
      });
      const primary = document.getElementById("primaryAiFile").files[0];
      if (primary) rows.push({ name: primary.name, type: "主模板", status: "待上传" });
      Array.from(document.getElementById("assetAiFiles").files || []).forEach(file => {
        rows.push({ name: file.name, type: "附加模板", status: "待上传" });
      });
      const target = document.getElementById("assetRows");
      if (!rows.length) {
        target.innerHTML = '<div class="empty">暂无 .ai 模板资产</div>';
        return;
      }
      target.innerHTML = rows.map(row => `
        <div class="asset-row">
          <span class="asset-name">${escapeHtml(row.name || "-")}</span>
          <span>${escapeHtml(row.type)}</span>
          <span>${escapeHtml(row.status)}</span>
        </div>
      `).join("");
    }

    function renderTemplateRulePreview() {
      const target = document.getElementById("templateRulePreview");
      const raw = document.getElementById("templateRuleText").value.trim();
      if (!state.templateRuleDraft) {
        target.innerHTML = '<div class="empty">请先输入模板规则并点击“生成预览”。系统会把规则编译成可确认的说明，不需要你查看 JSON。</div>';
        return;
      }
      const stale = raw !== state.templateRulePreviewSignature;
      target.innerHTML = renderReadableTemplateRule(state.templateRuleDraft, stale);
    }

    async function renderTemplateRulePreviewFromServer() {
      const raw = document.getElementById("templateRuleText").value.trim();
      const templateId = document.getElementById("templateId").value.trim();
      if (!templateId || !raw) {
        renderTemplateRulePreview();
        return;
      }
      try {
        setMessage("templateSaveMessage", "正在编译规则", "");
        const payload = await postJson("/api/templates/rules/draft", {
          template_id: templateId,
          template_type: document.getElementById("templateType").value,
          natural_text: raw,
          asset_count: (document.getElementById("assetAiFiles").files || []).length
        });
        const draft = payload.draft || {};
        state.templateRuleDraft = draft;
        state.templateRulePreviewSignature = raw;
        renderTemplateRulePreview();
        setMessage("templateSaveMessage", "规则已编译，请确认说明后保存", "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function markTemplateRulePreviewStale() {
      renderTemplateRulePreview();
      if (document.getElementById("templateRuleText").value.trim()) {
        setMessage("templateSaveMessage", "规则内容已修改，请先生成预览再保存", "");
      }
    }

    function buildTemplateRulePayload() {
      const raw = document.getElementById("templateRuleText").value.trim();
      return {
        template_id: document.getElementById("templateId").value.trim(),
        rule_source: "natural_language",
        raw_text: raw,
        defaults: {
          color: inferColor(raw),
          design: inferDesign(raw)
        },
        transforms: {
          rotation: inferRotation(raw)
        }
      };
    }

    function templateRuleJsonText() {
      return JSON.stringify(state.templateRuleDraft || buildTemplateRulePayload());
    }

    async function saveTemplate() {
      setMessage("templateSaveMessage", "保存中", "");
      const templateId = document.getElementById("templateId").value.trim();
      const name = document.getElementById("templateName").value.trim();
      if (!templateId || !name) {
        setMessage("templateSaveMessage", "请填写模板 ID 和模板名称", "error");
        return;
      }
      const ruleText = document.getElementById("templateRuleText").value.trim();
      if (ruleText && (!state.templateRuleDraft || state.templateRulePreviewSignature !== ruleText)) {
        setMessage("templateSaveMessage", "模板规则已修改，请先点击“生成预览”，确认编译后的规则说明后再保存", "error");
        return;
      }
      const form = new FormData();
      form.append("template_id", templateId);
      form.append("name", name);
      form.append("template_type", document.getElementById("templateType").value);
      form.append("status", document.getElementById("templateStatus").value);
      form.append("template_rules_text", ruleText);
      form.append("template_rules_json", templateRuleJsonText());
      const primary = document.getElementById("primaryAiFile").files[0];
      if (primary) form.append("template_ai", primary);
      Array.from(document.getElementById("assetAiFiles").files || []).forEach(file => {
        form.append("template_assets", file);
      });
      try {
        const result = await postForm("/api/templates", form);
        state.selectedTemplateId = result.template.template_id;
        await loadTemplates(result.template.template_id);
        setMessage("templateSaveMessage", `已保存模板：${result.template.template_id}`, "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function clearTemplateForm() {
      document.getElementById("templateId").value = "";
      document.getElementById("templateName").value = "";
      document.getElementById("templateType").value = "pure_text_color_design";
      document.getElementById("templateStatus").value = "active";
      document.getElementById("primaryAiFile").value = "";
      document.getElementById("assetAiFiles").value = "";
      document.getElementById("templateRuleText").value = "";
      state.templateRuleDraft = null;
      state.templateRulePreviewSignature = "";
      document.getElementById("assetRows").innerHTML = '<div class="empty">暂无 .ai 模板资产</div>';
      renderTemplateRulePreview();
      setMessage("templateSaveMessage", "等待编辑", "");
    }

    function downloadTemplate(templateId) {
      if (!templateId) {
        setMessage("templateSaveMessage", "请先选择模板", "error");
        return;
      }
      window.location.href = `/api/templates/${encodeURIComponent(templateId)}/download/template_ai`;
    }

    async function deleteTemplate(templateId) {
      const template = state.templates.find(item => item.template_id === templateId);
      if (!template) return;
      const confirmed = window.confirm(`确认删除模板 ${template.template_id}？\n\n只会移除系统注册记录，不会删除本地 .ai 文件。`);
      if (!confirmed) return;
      try {
        await deleteJson(`/api/templates/${encodeURIComponent(template.template_id)}`);
        if (state.selectedTemplateId === template.template_id) {
          state.selectedTemplateId = "";
        }
        await loadTemplates();
        setMessage("templateSaveMessage", `已删除模板注册：${template.template_id}`, "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    async function submitRender(dryRun) {
      const file = document.getElementById("orderFile").files[0];
      const templateId = document.getElementById("renderTemplate").value;
      if (!templateId) {
        setMessage("taskMessage", "请先选择模板", "error");
        return;
      }
      if (!file) {
        setMessage("taskMessage", "请上传订单表格", "error");
        return;
      }
      const payload = new FormData();
      payload.append("template_id", templateId);
      payload.append("order_file", file);
      if (dryRun) payload.append("dry_run", "true");
      setTaskRunning(dryRun);
      try {
        const result = await postForm("/api/render", payload);
        renderTaskResult(result);
        await loadJobs();
      } catch (error) {
        document.getElementById("resultStatus").textContent = "失败";
        setMessage("taskMessage", String(error.message || error), "error");
      }
    }

    function setTaskRunning(dryRun) {
      document.getElementById("resultJobId").textContent = "-";
      document.getElementById("resultStatus").textContent = dryRun ? "解析中" : "运行中";
      document.getElementById("resultItems").textContent = "-";
      document.getElementById("resultDownload").textContent = "-";
      setMessage("taskMessage", dryRun ? "正在解析订单和模板规则" : "正在渲染", "");
    }

    function renderTaskResult(result) {
      document.getElementById("resultJobId").textContent = result.job_id || "-";
      document.getElementById("resultStatus").textContent = displayStatus(result.status);
      document.getElementById("resultItems").textContent = result.stats && result.stats.items !== undefined ? result.stats.items : "-";
      if (result.status === "completed" && result.outputs && result.outputs.output_ai) {
        document.getElementById("resultDownload").textContent = "下载中";
        setMessage("taskMessage", "渲染完成，AI 文件开始下载", "ok");
        window.location.href = `/api/jobs/${encodeURIComponent(result.job_id)}/download/output_ai`;
      } else if (result.status === "completed" && result.outputs && result.outputs.render_task) {
        const link = `/api/jobs/${encodeURIComponent(result.job_id)}/download/render_task`;
        document.getElementById("resultDownload").innerHTML = `<a class="download-link" href="${link}">下载解析 JSON</a>`;
        setMessage("taskMessage", "解析测试完成，可下载解析 JSON 检查字段、分组和渲染项", "ok");
      } else if (result.status === "failed") {
        document.getElementById("resultDownload").textContent = "-";
        setMessage("taskMessage", result.error || "渲染失败", "error");
      } else {
        document.getElementById("resultDownload").textContent = "-";
        setMessage("taskMessage", "任务已提交", "");
      }
    }

    function resetTaskResult() {
      document.getElementById("orderFile").value = "";
      document.getElementById("resultJobId").textContent = "-";
      document.getElementById("resultStatus").textContent = "待提交";
      document.getElementById("resultItems").textContent = "-";
      document.getElementById("resultDownload").textContent = "-";
      setMessage("taskMessage", "等待提交", "");
    }

    function renderRecentJobs() {
      const target = document.getElementById("recentJobs");
      const jobs = state.jobs.slice(0, 5);
      if (!jobs.length) {
        target.innerHTML = '<div class="empty">暂无任务</div>';
        return;
      }
      target.innerHTML = jobs.map(job => {
        const request = job.request || {};
        const stats = job.stats || {};
        return `
          <div class="list-item">
            <div class="item-head"><span>${escapeHtml(job.job_id)}</span><span class="status-badge ${job.status === "completed" ? "success" : ""}">${escapeHtml(displayStatus(job.status))}</span></div>
            <div class="item-meta">${escapeHtml(request.template_id || "-")} / ${stats.items !== undefined ? stats.items : "-"} 项</div>
          </div>
        `;
      }).join("");
    }

    function renderJobsTable() {
      const target = document.getElementById("jobsTableBody");
      if (!state.jobs.length) {
        target.innerHTML = '<tr><td colspan="6" class="empty">暂无任务</td></tr>';
        return;
      }
      target.innerHTML = state.jobs.map(job => {
        const request = job.request || {};
        const stats = job.stats || {};
        const hasOutput = job.status === "completed" && job.outputs && job.outputs.output_ai;
        const hasRenderTask = job.status === "completed" && job.outputs && job.outputs.render_task;
        const link = hasOutput
          ? `<a class="download-link" href="/api/jobs/${encodeURIComponent(job.job_id)}/download/output_ai">下载 AI</a>`
          : (hasRenderTask ? `<a class="download-link" href="/api/jobs/${encodeURIComponent(job.job_id)}/download/render_task">下载解析 JSON</a>` : "-");
        return `
          <tr>
            <td>${escapeHtml(job.job_id)}</td>
            <td>${escapeHtml(request.template_id || "-")}</td>
            <td>${escapeHtml(displayStatus(job.status))}</td>
            <td>${stats.items !== undefined ? stats.items : "-"}</td>
            <td>${escapeHtml(formatDate(job.created_at))}</td>
            <td>${link}</td>
          </tr>
        `;
      }).join("");
    }

    function renderRuleCategories() {
      const target = document.getElementById("ruleCategories");
      if (!state.departmentRules.length && !state.ruleDrafts.length) {
        target.innerHTML = '<div class="empty">暂无规则</div>';
        return;
      }
      const published = state.departmentRules.map(rule => `
        <button class="rule-category ${state.ruleMode === "published" && rule.name === state.selectedRuleName ? "active" : ""}" data-rule-mode="published" data-rule-name="${escapeHtml(rule.name)}">${escapeHtml(rule.display_name || rule.name)}</button>
      `).join("");
      const drafts = state.ruleDrafts.map(rule => `
        <button class="rule-category ${state.ruleMode === "draft" && rule.rule_name === state.selectedRuleName ? "active" : ""}" data-rule-mode="draft" data-rule-name="${escapeHtml(rule.rule_name)}">${escapeHtml(rule.display_name || rule.rule_name)}（草稿）</button>
      `).join("");
      target.innerHTML = published + drafts;
      target.querySelectorAll("[data-rule-name]").forEach(button => {
        button.addEventListener("click", () => {
          state.selectedRuleName = button.dataset.ruleName;
          state.ruleMode = button.dataset.ruleMode || "published";
          renderRuleCategories();
          syncSelectedRule();
        });
      });
    }

    function renderGlobalRulesSummary() {
      const target = document.getElementById("globalRulesSummary");
      const requirements = (state.shopRules && state.shopRules.global_requirements) || {};
      const outputs = (state.shopRules && state.shopRules.department_output_requirements) || [];
      const defaults = state.defaultRule || {};
      target.innerHTML = `
        <div class="preview-grid">
          <div class="preview-chip"><span>默认标注字段</span><strong>${escapeHtml(displayLabelFields(defaults.label_fields || []))}</strong></div>
          <div class="preview-chip"><span>默认带框</span><strong>${escapeHtml(defaults.show_frame ? "是" : "否")}</strong></div>
          <div class="preview-chip"><span>转曲要求</span><strong>${escapeHtml(requirements.must_outline_text ? "需要" : "未声明")}</strong></div>
          <div class="preview-chip"><span>合并去重</span><strong>${escapeHtml(requirements.must_pathfinder_merge ? "需要" : "未声明")}</strong></div>
          <div class="preview-chip"><span>部门输出规则</span><strong>${escapeHtml(`${outputs.length} 条`)}</strong></div>
        </div>
      `;
    }

    function renderReadableTemplateRule(draft, stale) {
      const slots = Array.isArray(draft.slots) ? draft.slots : [];
      const slotText = slots.length ? slots.map(describeSlot).join("；") : "暂未识别到明确作图区域";
      const defaults = draft.defaults || {};
      const parser = draft.parser || {};
      return `
        ${stale ? '<div class="message error" style="margin-bottom:10px">规则文字已修改，请重新生成预览后再保存。</div>' : ""}
        <div class="preview-grid">
          <div class="preview-chip"><span>模板类型</span><strong>${escapeHtml(displayType(draft.mode || draft.template_type || ""))}</strong></div>
          <div class="preview-chip"><span>字体选项</span><strong>${escapeHtml(displayOptions(draft.font_options))}</strong></div>
          <div class="preview-chip"><span>款式/尺寸框</span><strong>${escapeHtml(displayOptions(draft.style_options))}</strong></div>
          <div class="preview-chip"><span>设计选项</span><strong>${escapeHtml(displayOptions(draft.design_options))}</strong></div>
          <div class="preview-chip"><span>文字和图片位置</span><strong>${escapeHtml(slotText)}</strong></div>
          <div class="preview-chip"><span>默认内容</span><strong>${escapeHtml(describeDefaults(defaults))}</strong></div>
          <div class="preview-chip"><span>处理能力</span><strong>${escapeHtml(describeCapabilities(draft.capabilities || []))}</strong></div>
          <div class="preview-chip"><span>解析来源</span><strong>${escapeHtml(parser.source === "llm" ? "LLM 编译" : "本地规则编译")}</strong></div>
        </div>
      `;
    }

    function describeSlot(slot) {
      const name = slot.name || "未命名区域";
      const typeNames = {
        text_fit_box: "普通文字按作图框适配",
        text_on_curve: "标题文字按曲线居中",
        place_ai_asset: "放入独立设计文件",
        replace_text: "替换设计内文字",
        image_slot: "填充图片/照片"
      };
      const type = typeNames[slot.type] || slot.type || "未知规则";
      const source = slot.source ? `，来源：${slot.source}` : "";
      const fallback = slot.default ? `，默认：${slot.default}` : "";
      return `${name}：${type}${source}${fallback}`;
    }

    function describeDefaults(defaults) {
      const parts = [];
      if (defaults.color) parts.push(`颜色 ${defaults.color}`);
      if (defaults.design) parts.push(`设计 ${defaults.design}`);
      if (defaults.font) parts.push(`字体 ${defaults.font}`);
      if (defaults.title) parts.push(`标题 ${defaults.title}`);
      return parts.join("；") || "无默认值";
    }

    function describeCapabilities(capabilities) {
      const names = {
        text_fit_box: "文字适配作图框",
        text_on_curve: "文字沿曲线居中",
        replace_text: "替换变量文字",
        place_ai_asset: "放置设计 AI 文件",
        image_slot: "图片槽位",
        scale_to_box: "按尺寸框缩放",
        outline_dedupe: "转曲去重",
        export_ai8: "输出 AI8"
      };
      return (capabilities || []).map(item => names[item] || item).join("；") || "未识别";
    }

    function displayOptions(values) {
      return Array.isArray(values) && values.length ? values.join(" / ") : "未识别";
    }

    function syncSelectedRule() {
      const rule = selectedRule();
      if (!rule) {
        document.getElementById("ruleStatusBadge").textContent = "未选择";
        fillRuleForm(emptyRuleDraft());
        renderRulePreview();
        return;
      }
      document.getElementById("ruleStatusBadge").textContent = state.ruleMode === "draft" ? "草稿" : "已发布";
      fillRuleForm(rule);
      renderRulePreview();
    }

    function newRuleDraft() {
      state.ruleMode = "new";
      state.selectedRuleName = "";
      renderRuleCategories();
      document.getElementById("ruleStatusBadge").textContent = "新增草稿";
      fillRuleForm(emptyRuleDraft());
      setMessage("ruleSaveMessage", "正在新增规则草稿", "");
      renderRulePreview();
    }

    function fillRuleForm(rule) {
      document.getElementById("ruleName").value = rule.rule_name || rule.name || "";
      document.getElementById("ruleDisplayName").value = rule.display_name || "";
      document.getElementById("ruleDepartments").value = (rule.departments || []).join(" / ");
      document.getElementById("ruleMatch").value = rule.match || "exact";
      document.getElementById("ruleLabelFields").value = displayLabelFields(rule.label_fields || []);
      document.getElementById("ruleShowFrame").value = rule.show_frame ? "true" : "false";
      document.getElementById("ruleColorMode").value = rule.apply_color_to_artwork ? "artwork" : "label";
      document.getElementById("ruleNaturalText").value = rule.natural_text || rule.description || "";
    }

    function emptyRuleDraft() {
      return {
        rule_name: "",
        display_name: "",
        departments: [],
        match: "exact",
        label_fields: ["order_no", "text"],
        show_frame: false,
        apply_color_to_artwork: false,
        natural_text: ""
      };
    }

    function renderRulePreview() {
      const draft = buildRuleDraftPayload();
      document.getElementById("rulePreview").innerHTML = `
        <div class="preview-grid">
          <div class="preview-chip"><span>部门范围</span><strong>${escapeHtml(draft.departments.join(" / ") || "-")}</strong></div>
          <div class="preview-chip"><span>输出框</span><strong>${escapeHtml(draft.show_frame ? "带框" : "不带框")}</strong></div>
          <div class="preview-chip"><span>颜色处理</span><strong>${escapeHtml(draft.apply_color_to_artwork ? "效果图应用颜色" : "颜色作为标注")}</strong></div>
          <div class="preview-chip"><span>标注字段</span><strong>${escapeHtml(displayLabelFields(draft.label_fields))}</strong></div>
        </div>
      `;
    }

    async function renderRulePreviewFromServer() {
      const draft = buildRuleDraftPayload();
      if (!draft.natural_text) {
        renderRulePreview();
        return;
      }
      setMessage("ruleSaveMessage", "解析中", "");
      try {
        const payload = await postJson("/api/rules/department/parse", draft);
        const parsed = payload.draft || {};
        fillRuleForm(parsed);
        const source = parsed.parser && parsed.parser.source ? parsed.parser.source : "local";
        renderRulePreview();
        document.getElementById("rulePreview").insertAdjacentHTML(
          "beforeend",
          `<div class="preview-grid" style="margin-top:10px"><div class="preview-chip"><span>解析来源</span><strong>${escapeHtml(source)}</strong></div></div>`
        );
        setMessage("ruleSaveMessage", "已生成结构化预览，请确认后保存", "ok");
      } catch (error) {
        setMessage("ruleSaveMessage", String(error.message || error), "error");
      }
    }

    async function saveRuleDraft() {
      const draft = buildRuleDraftPayload();
      if (!draft.rule_name) {
        setMessage("ruleSaveMessage", "请填写规则名称", "error");
        return;
      }
      setMessage("ruleSaveMessage", "保存中", "");
      try {
        await postJson("/api/rules/department/draft", {
          ...draft,
          preview: document.getElementById("rulePreview").innerText
        });
        state.selectedRuleName = draft.rule_name;
        state.ruleMode = "draft";
        await loadRules();
        setMessage("ruleSaveMessage", "草稿已保存", "ok");
      } catch (error) {
        setMessage("ruleSaveMessage", String(error.message || error), "error");
      }
    }

    async function publishRule() {
      const draft = buildRuleDraftPayload();
      if (!draft.rule_name) {
        setMessage("ruleSaveMessage", "请填写规则名称", "error");
        return;
      }
      setMessage("ruleSaveMessage", "保存发布规则中", "");
      try {
        await postJson("/api/rules/department/publish", draft);
        state.selectedRuleName = draft.rule_name;
        state.ruleMode = "published";
        await loadRules();
        setMessage("ruleSaveMessage", "发布规则已保存", "ok");
      } catch (error) {
        setMessage("ruleSaveMessage", String(error.message || error), "error");
      }
    }

    function buildRuleDraftPayload() {
      return {
        rule_name: document.getElementById("ruleName").value.trim(),
        display_name: document.getElementById("ruleDisplayName").value.trim(),
        departments: parseList(document.getElementById("ruleDepartments").value),
        match: document.getElementById("ruleMatch").value,
        label_fields: normalizeLabelFields(document.getElementById("ruleLabelFields").value),
        show_frame: document.getElementById("ruleShowFrame").value === "true",
        apply_color_to_artwork: document.getElementById("ruleColorMode").value === "artwork",
        natural_text: document.getElementById("ruleNaturalText").value.trim()
      };
    }

    function selectedTemplate() {
      return state.templates.find(template => template.template_id === state.selectedTemplateId) || null;
    }

    function formTemplate() {
      const templateId = document.getElementById("templateId").value.trim();
      return state.templates.find(template => template.template_id === templateId) || null;
    }

    function selectedRule() {
      if (state.ruleMode === "draft") {
        return state.ruleDrafts.find(rule => rule.rule_name === state.selectedRuleName) || null;
      }
      return state.departmentRules.find(rule => rule.name === state.selectedRuleName) || null;
    }

    async function getJson(url) {
      const response = await fetch(url);
      const text = await response.text();
      if (!response.ok) throw new Error(extractError(text));
      return text ? JSON.parse(text) : {};
    }

    async function postForm(url, body) {
      const response = await fetch(url, { method: "POST", body });
      const text = await response.text();
      if (!response.ok) throw new Error(extractError(text));
      return text ? JSON.parse(text) : {};
    }

    async function postJson(url, body) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const text = await response.text();
      if (!response.ok) throw new Error(extractError(text));
      return text ? JSON.parse(text) : {};
    }

    async function deleteJson(url) {
      const response = await fetch(url, { method: "DELETE" });
      const text = await response.text();
      if (!response.ok) throw new Error(extractError(text));
      return text ? JSON.parse(text) : {};
    }

    function extractError(text) {
      try {
        const payload = JSON.parse(text);
        return payload.error || text;
      } catch (error) {
        return text || "请求失败";
      }
    }

    function definitionHtml(rows) {
      return rows.map(([key, value]) => `
        <div class="definition"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value || "-")}</dd></div>
      `).join("");
    }

    function displayType(value) {
      return typeNames[value] || value || "-";
    }

    function displayStatus(value) {
      return statusNames[value] || value || "-";
    }

    function displayLabelFields(fields) {
      return fields.map(field => fieldNames[field] || field).join("、") || "-";
    }

    function displayMissingRules(items) {
      if (!items.length) return "-";
      return items.map(item => item.message || item.code || String(item)).join("；");
    }

    function parseList(value) {
      return String(value || "")
        .split(/[、,，/|\\s]+/)
        .map(item => item.trim())
        .filter(Boolean);
    }

    function normalizeLabelFields(value) {
      const reverseNames = {
        订单号: "order_no",
        字体颜色: "color_option",
        颜色: "color_option",
        定制信息: "text",
        信息: "text",
        产品名称: "product_name"
      };
      return parseList(value).map(field => reverseNames[field] || field);
    }

    function inferColor(text) {
      if (/金色|Gold/i.test(text)) return "Gold";
      if (/黑色|Black/i.test(text)) return "Black";
      if (/白色|White/i.test(text)) return "White";
      if (/玫瑰金|Rose/i.test(text)) return "Rose gold";
      return "";
    }

    function inferDesign(text) {
      const match = text.match(/Design\\s*([0-9]+)/i) || text.match(/设计\\s*([0-9]+)/);
      return match ? `Design${match[1]}` : "";
    }

    function inferRotation(text) {
      const match = text.match(/(-?\\d+)\\s*度/) || text.match(/(-?\\d+)\\s*°/);
      return match ? `${match[1]}°` : "";
    }

    function fileName(path) {
      return String(path || "").split(/[\\\\/]/).pop() || "-";
    }

    function formatDate(value) {
      if (!value) return "-";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString("zh-CN", { hour12: false });
    }

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function setMessage(id, text, stateName) {
      const target = document.getElementById(id);
      target.className = `message ${stateName || ""}`.trim();
      target.textContent = text;
    }

    init().catch(error => {
      setMessage("taskMessage", String(error.message || error), "error");
    });
  </script>
</body>
</html>
"""
