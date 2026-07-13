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
    .render-layout {
      max-width: 860px;
      margin: 0 auto;
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
    .render-task-panel .panel-body {
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    .render-task-panel .form-grid {
      flex: none;
      align-content: start;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 15px 16px;
    }
    .field-full { grid-column: 1 / -1; }
    .task-upload {
      min-height: 118px;
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
    .render-task-panel .actions {
      margin-top: 14px;
      padding-top: 14px;
    }
    .render-task-panel .btn-primary {
      min-width: 142px;
      min-height: 40px;
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
    .template-list-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
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
      grid-template-columns: minmax(0, 1fr);
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
    .asset-panel-grid {
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(300px, 1.1fr);
      gap: 16px;
      align-items: stretch;
    }
    .upload-box {
      min-height: 276px;
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
      grid-template-columns: minmax(0, 1.4fr) 122px 76px 122px;
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
    .asset-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .asset-actions button {
      min-height: 30px;
      padding: 5px 9px;
      font-size: 12px;
    }
    .asset-note {
      color: var(--muted);
      font-size: 12px;
    }
    .rule-section {
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }
    .rule-section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .rule-section-title {
      margin: 0;
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .rule-section-note {
      margin: -6px 0 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .structured-table {
      display: grid;
      gap: 8px;
    }
    .structured-row {
      display: grid;
      grid-template-columns: minmax(130px, 1fr) minmax(120px, 0.8fr) minmax(120px, 0.8fr) minmax(90px, 0.5fr);
      gap: 8px;
      align-items: end;
    }
    .structured-row.dynamic {
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfe;
    }
    .structured-row.two {
      grid-template-columns: minmax(160px, 1fr) minmax(160px, 1fr);
    }
    .structured-row.three {
      grid-template-columns: minmax(150px, 1fr) minmax(130px, 0.8fr) minmax(130px, 0.8fr);
    }
    .structured-row.dimension {
      grid-template-columns: minmax(150px, 1.1fr) minmax(100px, 0.7fr) minmax(100px, 0.7fr) minmax(90px, 0.5fr) 42px;
    }
    .structured-row.sequence {
      grid-template-columns: minmax(120px, 0.9fr) minmax(110px, 0.8fr) minmax(70px, 0.45fr) minmax(120px, 0.9fr) minmax(80px, 0.5fr) minmax(80px, 0.5fr) 42px;
    }
    .structured-row label {
      margin-bottom: 4px;
    }
    .rule-add-btn {
      min-height: 32px;
      padding: 6px 10px;
      white-space: nowrap;
    }
    .row-remove-btn {
      width: 36px;
      min-height: 36px;
      padding: 0;
      border: 1px solid #d6dfe9;
      border-radius: 7px;
      background: #fff;
      color: var(--muted);
      font-size: 18px;
      line-height: 1;
    }
    .row-remove-btn:hover {
      border-color: #efb0aa;
      color: var(--danger);
      background: #fff7f6;
    }
    .advanced-rule-box {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      overflow: hidden;
    }
    .advanced-rule-box summary {
      padding: 12px 14px;
      cursor: pointer;
      color: #394756;
      font-weight: 700;
      background: var(--soft);
    }
    .advanced-rule-body {
      padding: 14px;
    }
    .advanced-rule-body textarea {
      min-height: 92px;
      resize: vertical;
    }
    .preview-box {
      min-height: 154px;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fbfcfe;
    }
    .readonly-summary {
      min-height: 100px;
      white-space: pre-wrap;
      color: var(--ink);
      line-height: 1.65;
    }
    .scan-evidence-details {
      margin-top: 10px;
    }
    .scan-evidence-details textarea {
      min-height: 280px;
      color: #435366;
      font-family: Consolas, "Microsoft YaHei", monospace;
      font-size: 12px;
      line-height: 1.55;
    }
    .extract-panel {
      display: grid;
      gap: 10px;
    }
    .extract-panel textarea {
      min-height: 132px;
    }
    .extract-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .extract-status {
      color: var(--muted);
      font-size: 12px;
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
    .progress-overlay,
    .error-overlay {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(23, 33, 43, 0.42);
    }
    .progress-overlay { z-index: 60; }
    .error-overlay { z-index: 70; }
    .progress-overlay.active,
    .error-overlay.active {
      display: flex;
    }
    .progress-dialog,
    .error-dialog {
      width: min(520px, 100%);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 22px 60px rgba(23, 33, 43, 0.24);
      overflow: hidden;
    }
    .error-dialog {
      width: min(460px, 100%);
    }
    .progress-head {
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .error-head {
      padding: 18px 20px 10px;
    }
    .progress-title {
      margin: 0;
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .error-title {
      margin: 0;
      color: var(--danger);
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .progress-subtitle {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    .progress-body {
      padding: 20px;
      display: grid;
      gap: 14px;
    }
    .error-body {
      padding: 0 20px 20px;
      display: grid;
      gap: 16px;
    }
    .error-text {
      margin: 0;
      color: var(--ink);
      line-height: 1.6;
      overflow-wrap: anywhere;
    }
    .error-actions {
      display: flex;
      justify-content: flex-end;
    }
    .progress-track {
      height: 10px;
      border-radius: 999px;
      background: #e9eef5;
      overflow: hidden;
    }
    .progress-bar {
      width: 0%;
      height: 100%;
      border-radius: 999px;
      background: var(--primary);
      transition: width 240ms ease;
    }
    .progress-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .progress-stage {
      color: var(--ink);
      font-weight: 700;
    }
    .progress-steps {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .progress-steps li {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .progress-steps li::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #c9d4e2;
    }
    .progress-steps li.active {
      color: var(--ink);
      font-weight: 700;
    }
    .progress-steps li.active::before {
      background: var(--primary);
    }
    .progress-steps li.done::before {
      background: var(--success);
    }
    @media (max-width: 960px) {
      .header-inner, .shell { width: min(100vw - 24px, 1320px); }
      .tabs { overflow-x: auto; }
      .grid.two,
      .grid.template-layout,
      .grid.rule-layout,
      .form-grid,
      .asset-panel-grid,
      .preview-grid,
      .structured-row,
      .structured-row.two,
      .structured-row.three,
      .structured-row.sequence,
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
      <div class="render-layout">
        <section class="panel render-task-panel">
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
              <div class="field-full">
                <label for="sheetName">工作表名称</label>
                <input id="sheetName" placeholder="默认第一个工作表，例如 Sheet2" />
              </div>
            </div>
            <div class="actions">
              <button class="btn-primary" id="renderBtn" title="解析订单并调用 Illustrator 生成 AI 效果图">生成效果图</button>
            </div>
          </div>
        </section>
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
            <div class="template-list-head">
              <button class="btn-primary" id="newTemplateBtn">新增模板</button>
            </div>
            <div class="template-list" id="templateList"></div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2 class="panel-title">新增或编辑模板</h2>
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
              <div class="field-full">
                <label>上传并扫描 .ai 模板</label>
                <p class="rule-section-note">选择文件后点击“上传并扫描 .ai 模板”。系统会先保存全部文件和角色，再自动扫描；扫描失败也会保留草稿和已保存文件。</p>
                <div class="asset-panel-grid">
                  <div class="upload-box">
                    <div>
                      <label for="referenceAiFile">原始参考模板（简单模板可只传这一项）</label>
                      <input id="referenceAiFile" type="file" accept=".ai" />
                    </div>
                    <div>
                      <label for="primaryAiFile">尺寸/作图区模板（可选，复杂模板用）</label>
                      <input id="primaryAiFile" type="file" accept=".ai" />
                    </div>
                    <div>
                      <label for="designFontAiFiles">独立设计字体资源（可选，可多选）</label>
                      <input id="designFontAiFiles" type="file" accept=".ai" multiple />
                    </div>
                    <div>
                      <label for="assetAiFiles">独立设计资源（可选，可多选）</label>
                      <input id="assetAiFiles" type="file" accept=".ai" multiple />
                    </div>
                  </div>
                  <div class="asset-list">
                    <div class="asset-list-head"><span>文件</span><span>类型</span><span>状态</span><span>操作</span></div>
                    <div id="assetRows"></div>
                  </div>
                </div>
                <div class="actions">
                  <button class="btn-primary" id="uploadScanTemplateBtn" type="button">上传并扫描 .ai 模板</button>
                  <span class="extract-status" id="uploadScanStatus">选择文件后从这里开始</span>
                </div>
              </div>
              <div class="field-full">
                <div class="rule-section">
                  <div class="rule-section-head">
                    <h3 class="rule-section-title">选项组角色</h3>
                    <button class="btn-subtle rule-add-btn" id="addOptionGroupBtn" type="button">+ 添加选项组</button>
                  </div>
                  <p class="rule-section-note">填写模板中出现的编号组，例如 F1-F10、D1-D12、Design1-Design12、Style1-Style5，并指定它在渲染中扮演什么角色。</p>
                  <div class="structured-table" id="optionGroupRows">
                    <div class="structured-row two">
                      <div>
                        <label for="optionGroup1Name">编号组 1</label>
                        <input id="optionGroup1Name" data-option-group-name placeholder="例如 F1-F10" />
                      </div>
                      <div>
                        <label for="optionGroup1Role">角色</label>
                        <select id="optionGroup1Role" data-option-group-role>
                          <option value="font_options">字体组</option>
                          <option value="design_font_options">独立设计字体</option>
                          <option value="design_options">设计组</option>
                          <option value="style_options">尺寸/版式组</option>
                          <option value="">请选择角色</option>
                        </select>
                      </div>
                    </div>
                    <div class="structured-row two">
                      <div>
                        <label for="optionGroup2Name">编号组 2</label>
                        <input id="optionGroup2Name" data-option-group-name placeholder="例如 Design1-Design12" />
                      </div>
                      <div>
                        <label for="optionGroup2Role">角色</label>
                        <select id="optionGroup2Role" data-option-group-role>
                          <option value="">请选择角色</option>
                          <option value="font_options">字体组</option>
                          <option value="design_font_options">独立设计字体</option>
                          <option value="design_options">设计组</option>
                          <option value="style_options">尺寸/版式组</option>
                        </select>
                      </div>
                    </div>
                    <div class="structured-row two">
                      <div>
                        <label for="optionGroup3Name">编号组 3</label>
                        <input id="optionGroup3Name" data-option-group-name placeholder="例如 Style1-Style5" />
                      </div>
                      <div>
                        <label for="optionGroup3Role">角色</label>
                        <select id="optionGroup3Role" data-option-group-role>
                          <option value="">请选择角色</option>
                          <option value="font_options">字体组</option>
                          <option value="design_font_options">独立设计字体</option>
                          <option value="design_options">设计组</option>
                          <option value="style_options">尺寸/版式组</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="rule-section">
                  <div class="rule-section-head">
                    <h3 class="rule-section-title">独立资源映射</h3>
                    <button class="btn-subtle rule-add-btn" id="addDesignAssetMappingBtn" type="button">+ 添加映射</button>
                  </div>
                  <p class="rule-section-note">填写订单选项、资源文件和 AI 编组的对应关系。独立设计字体和独立设计资源均可映射；扫描只提供候选，最终以这里确认的映射为准。</p>
                  <div class="structured-table" id="designAssetMappingRows"></div>
                </div>

                <div class="rule-section">
                  <h3 class="rule-section-title">扫描证据与模板类型</h3>
                  <div class="form-grid">
                    <div>
                      <label for="templateProfile">Profile</label>
                      <select id="templateProfile">
                        <option value="unclassified">待人工分类</option>
                        <option value="pure_text">纯文字</option>
                        <option value="fixed_font_design">设计加固定字体</option>
                        <option value="composite">尺寸/设计/字体/颜色复合</option>
                        <option value="bundle">套装</option>
                      </select>
                    </div>
                    <div><label for="scanVersion">扫描版本</label><input id="scanVersion" readonly /></div>
                    <div class="field-full">
                      <label id="scanEvidenceLabel">扫描结果摘要（只读）</label>
                      <div class="preview-box readonly-summary" id="scanEvidence">暂无扫描事实</div>
                      <details class="advanced-rule-box scan-evidence-details">
                        <summary>查看原始扫描明细</summary>
                        <div class="advanced-rule-body"><textarea id="scanEvidenceRaw" readonly></textarea></div>
                      </details>
                    </div>
                    <div class="field-full">
                      <details class="advanced-rule-box">
                        <summary>查看系统审计明细（可选）</summary>
                        <div class="advanced-rule-body">
                          <p class="rule-section-note">仅用于核对扫描建议与当前配置是否一致，不需要填写。</p>
                          <label for="fieldSources">系统建议与当前配置差异（只读）</label>
                          <textarea id="fieldSources" readonly></textarea>
                        </div>
                      </details>
                    </div>
                    <div class="field-full">
                      <button class="btn-subtle" id="restoreSuggestionsBtn" type="button">恢复系统建议</button>
                      <button class="btn-subtle" id="rescanTemplateBtn" type="button" hidden>重新扫描已保存文件</button>
                    </div>
                  </div>
                </div>

                <div class="rule-section">
                  <h3 class="rule-section-title">映射、文字策略与验证样例</h3>
                  <p class="rule-section-note">以下规则均可编辑；JSON 格式错误会阻止检查与确认。</p>
                  <div class="form-grid">
                    <div><label for="orderBindingsJson">订单字段绑定</label><textarea id="orderBindingsJson" placeholder='{"text":"定制信息"}'></textarea></div>
                    <div><label for="assetMappingsJson">设计/资产映射</label><textarea id="assetMappingsJson" placeholder='[{"option":"Design1","asset":"design-1.ai"}]'></textarea></div>
                    <div><label for="textPoliciesJson">文字适配/拆分策略</label><textarea id="textPoliciesJson" placeholder='{"fit":"scale_to_box"}'></textarea></div>
                    <div><label for="outputTransformsJson">输出处理</label><textarea id="outputTransformsJson" placeholder='{"color_mode":"CMYK"}'></textarea></div>
                    <div class="field-full"><label for="validationSampleJson">验证样例</label><textarea id="validationSampleJson" placeholder='{"input":{},"expected":{}}'></textarea></div>
                    <div class="field-full"><label for="templateChangeSummary">本次确认说明</label><input id="templateChangeSummary" placeholder="例如：核对对象命名并补齐 Design 映射" /></div>
                  </div>
                  <div class="preview-box" id="templateVersionHistory">尚无已确认版本</div>
                </div>

                <div class="rule-section">
                  <div class="rule-section-head">
                    <h3 class="rule-section-title">尺寸规则</h3>
                    <button class="btn-subtle rule-add-btn" id="addDimensionRowBtn" type="button">+ 添加尺寸</button>
                  </div>
                  <div class="structured-row three"><div><label for="dimensionMode">尺寸模式</label><select id="dimensionMode"><option value="object">按尺寸/版式选项</option><option value="fixed">固定制图尺寸</option></select></div><div><label for="fixedWidth">固定宽度</label><input id="fixedWidth" type="number" min="0" step="0.1" placeholder="mm" /></div><div><label for="fixedHeight">固定高度</label><input id="fixedHeight" type="number" min="0" step="0.1" placeholder="mm" /></div></div>
                  <p class="rule-section-note">固定尺寸模板选择“固定制图尺寸”，只填写一次宽高；不需要填写尺寸对象或订单 Style Option。</p>
                  <div class="structured-table" id="dimensionRows"></div>
                </div>

                <div class="rule-section">
                  <div class="rule-section-head">
                    <h3 class="rule-section-title">字段拆分与变量序列</h3>
                    <button class="btn-subtle rule-add-btn" id="addTextSequenceRowBtn" type="button">+ 添加字段规则</button>
                  </div>
                  <p class="rule-section-note">订单字段可按分隔符拆分，并按顺序写入 AI 模板中的变量序列，例如 Name 字段写入 Name1、Name2、Name3。</p>
                  <div class="structured-table" id="textSequenceRows"></div>
                </div>

                <div class="rule-section">
                  <h3 class="rule-section-title">默认值</h3>
                  <div class="form-grid">
                    <div>
                      <label for="defaultFont">默认字体</label>
                      <input id="defaultFont" placeholder="例如 F1" />
                    </div>
                    <div>
                      <label for="defaultDesign">默认设计</label>
                      <input id="defaultDesign" placeholder="例如 Design1" />
                    </div>
                    <div>
                      <label for="defaultStyle">默认尺寸/版式</label>
                      <input id="defaultStyle" placeholder="例如 Style1" />
                    </div>
                    <div>
                      <label for="defaultColor">默认颜色</label>
                      <input id="defaultColor" placeholder="例如 Gold" />
                    </div>
                    <div class="field-full">
                      <label for="outputColorMode">输出色彩</label>
                      <select id="outputColorMode">
                        <option value="CMYK">CMYK</option>
                        <option value="RGB">RGB</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div class="rule-section">
                  <h3 class="rule-section-title">特殊处理</h3>
                  <div class="structured-table" id="overrideRows">
                    <div class="structured-row three">
                      <div><label>对象/选项</label><input data-override-target placeholder="例如 F3" /></div>
                      <div>
                        <label>处理方式</label>
                        <select data-override-action>
                          <option value="">无</option>
                          <option value="bold">加粗</option>
                          <option value="uppercase">转大写</option>
                          <option value="no_width_compress">禁止压缩字宽</option>
                          <option value="fixed_color">固定颜色</option>
                        </select>
                      </div>
                      <div><label>补充值</label><input data-override-value placeholder="可选" /></div>
                    </div>
                    <div class="structured-row three">
                      <div><input data-override-target placeholder="例如 F7" /></div>
                      <div>
                        <select data-override-action>
                          <option value="">无</option>
                          <option value="bold">加粗</option>
                          <option value="uppercase">转大写</option>
                          <option value="no_width_compress">禁止压缩字宽</option>
                          <option value="fixed_color">固定颜色</option>
                        </select>
                      </div>
                      <div><input data-override-value placeholder="可选" /></div>
                    </div>
                  </div>
                  <details class="advanced-rule-box">
                    <summary>高级例外规则（可选）</summary>
                    <div class="advanced-rule-body">
                      <label for="templateAdvancedRules">例外说明</label>
                      <textarea id="templateAdvancedRules" placeholder="例如：Design5 的第二行文字需要向上偏移 2mm。这里仅作为待确认说明保存，不会直接自动参与出图。"></textarea>
                      <label for="templateExceptionStatus">例外状态</label>
                      <select id="templateExceptionStatus"><option value="none">无例外</option><option value="resolved">已解决</option><option value="manual_review">待人工处理（阻止启用）</option></select>
                    </div>
                  </details>
                </div>

                <div class="rule-section">
                  <h3 class="rule-section-title">规则检查结果</h3>
                  <div class="preview-box" id="templateRulePreview"></div>
                </div>
              </div>
            </div>
            <div class="actions">
              <button class="btn-subtle" id="checkTemplateRuleBtn">检查规则</button>
              <button class="btn-primary" id="saveTemplateBtn">检查并保存规则</button>
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

  <div class="progress-overlay" id="renderProgressOverlay" aria-hidden="true">
    <div class="progress-dialog" role="status" aria-live="polite">
      <div class="progress-head">
        <h2 class="progress-title" id="progressTitle">正在处理</h2>
        <div class="progress-subtitle" id="progressSubtitle">请保持 Illustrator 可用</div>
      </div>
      <div class="progress-body">
        <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
        <div class="progress-row">
          <span class="progress-stage" id="progressStage">准备任务</span>
          <span id="progressPercent">0%</span>
        </div>
        <ul class="progress-steps" id="progressSteps"></ul>
      </div>
    </div>
  </div>

  <div class="error-overlay" id="renderErrorOverlay" aria-hidden="true">
    <div class="error-dialog" role="alertdialog" aria-labelledby="renderErrorTitle" aria-describedby="renderErrorText">
      <div class="error-head">
        <h2 class="error-title" id="renderErrorTitle">生成失败</h2>
      </div>
      <div class="error-body">
        <p class="error-text" id="renderErrorText">请检查模板和订单表格后重试。</p>
        <div class="error-actions">
          <button class="btn-primary" id="closeRenderErrorBtn">我知道了</button>
        </div>
      </div>
    </div>
  </div>

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
      templateRuleBaseConfig: null,
      templateOnboarding: null,
      optionGroupsTouched: false,
      assetMappingsTouched: false,
      dimensionRowsTouched: false,
      textSequenceRowsTouched: false,
      templateRulesDescriptionDirty: false
    };
    let progressTimer = null;
    let progressValue = 0;
    let progressMode = "render";

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
      prepareBusinessRuleEditor();
      bindEvents();
      await checkHealth();
      await Promise.all([loadTemplates(), loadRules(), loadJobs()]);
      resetTaskResult();
    }

    function prepareBusinessRuleEditor() {
      const profile = document.getElementById("templateProfile");
      if (profile) profile.disabled = true;
      const profileWrapper = profile && profile.closest(".form-grid > div");
      if (profileWrapper) profileWrapper.hidden = true;
      const jsonIds = ["orderBindingsJson", "assetMappingsJson", "textPoliciesJson", "outputTransformsJson", "validationSampleJson"];
      jsonIds.forEach(id => {
        const input = document.getElementById(id);
        const wrapper = input && input.closest(".form-grid > div");
        if (wrapper) wrapper.hidden = true;
      });
      const orderInput = document.getElementById("orderBindingsJson");
      const ruleSection = orderInput && orderInput.closest(".rule-section");
      if (!ruleSection || document.getElementById("templateRuleDescription")) return;
      const specialRules = document.getElementById("templateAdvancedRules");
      const specialSection = specialRules && specialRules.closest(".rule-section");
      if (specialSection) specialSection.insertAdjacentElement("afterend", ruleSection);
      const title = ruleSection.querySelector(".rule-section-title");
      if (title) title.textContent = "补充说明（可选）";
      const note = ruleSection.querySelector(".rule-section-note");
      if (note) note.textContent = "先完成上方固定项。这里只补充固定项无法表达的特殊业务条件；生成草稿不会覆盖已填写内容，仍需检查并确认保存。";
      const formGrid = ruleSection.querySelector(".form-grid");
      const panel = document.createElement("div");
      panel.className = "extract-panel";
      panel.innerHTML = `
        <label for="templateRuleDescription">补充规则说明</label>
        <textarea id="templateRuleDescription" placeholder="例如：名字位置 1、3、5、7 使用红色，2、4、6 使用白色；或某个固定项无法表达的特殊处理。"></textarea>
        <div class="extract-actions">
          <button class="btn-subtle" id="extractTemplateRulesBtn" type="button">将补充说明生成草稿</button>
          <span class="extract-status" id="templateExtractionStatus">未填写补充说明</span>
        </div>
        <div class="preview-box readonly-summary" id="templateExtractionSummary">填写补充说明后，系统会在这里显示可补充的规则和仍需确认的内容。</div>`;
      if (formGrid) ruleSection.insertBefore(panel, formGrid);
      const scanSection = profile && profile.closest(".rule-section");
      if (scanSection) {
        const scanTitle = scanSection.querySelector(".rule-section-title");
        if (scanTitle) scanTitle.textContent = "系统扫描结果";
        const profileLabel = scanSection.querySelector('label[for="templateProfile"]');
        if (profileLabel) profileLabel.textContent = "系统推断类型";
        const scanNote = document.createElement("p");
        scanNote.className = "rule-section-note";
        scanNote.textContent = "以下内容由系统从 AI 模板中读取，只用于核对，不需要用户分类或填写。";
        const scanGrid = scanSection.querySelector(".form-grid");
        if (scanGrid) scanSection.insertBefore(scanNote, scanGrid);
        const evidenceLabel = document.getElementById("scanEvidenceLabel");
        if (evidenceLabel) evidenceLabel.textContent = "扫描结果摘要（只读）";
        const sourceLabel = scanSection.querySelector('label[for="fieldSources"]');
        if (sourceLabel) sourceLabel.textContent = "系统建议与当前配置差异（只读）";
      }
    }

    function bindEvents() {
      document.querySelectorAll("[data-page-tab]").forEach(button => {
        button.addEventListener("click", () => switchPage(button.dataset.pageTab));
      });
      document.getElementById("renderTemplate").addEventListener("change", event => {
        state.selectedTemplateId = event.target.value;
        syncSelectedTemplate();
      });
      document.getElementById("renderBtn").addEventListener("click", () => submitRender(false));
      document.getElementById("refreshJobsPageBtn").addEventListener("click", loadJobs);
      document.getElementById("closeRenderErrorBtn").addEventListener("click", hideRenderError);
      document.getElementById("newTemplateBtn").addEventListener("click", newTemplate);
      document.getElementById("extractTemplateRulesBtn").addEventListener("click", extractTemplateRules);
      document.getElementById("templateRuleDescription").addEventListener("input", () => {
        state.templateRulesDescriptionDirty = true;
        document.getElementById("templateExtractionStatus").textContent = "补充说明已修改，如需采用建议请重新生成草稿";
      });
      document.getElementById("checkTemplateRuleBtn").addEventListener("click", checkTemplateRule);
      document.getElementById("saveTemplateBtn").addEventListener("click", saveTemplate);
      document.getElementById("uploadScanTemplateBtn").addEventListener("click", uploadAndScanTemplate);
      document.getElementById("addOptionGroupBtn").addEventListener("click", () => {
        state.optionGroupsTouched = true;
        addOptionGroupRow();
      });
      document.getElementById("addDesignAssetMappingBtn").addEventListener("click", () => {
        state.assetMappingsTouched = true;
        addDesignAssetMappingRow();
      });
      document.getElementById("restoreSuggestionsBtn").addEventListener("click", restoreRuleSuggestions);
      document.getElementById("rescanTemplateBtn").addEventListener("click", rescanTemplate);
      document.getElementById("addDimensionRowBtn").addEventListener("click", addDimensionRow);
      document.getElementById("dimensionMode").addEventListener("change", () => {
        state.dimensionRowsTouched = true;
        syncDimensionMode();
        renderTemplateRulePreview();
      });
      ["fixedWidth", "fixedHeight"].forEach(id => {
        document.getElementById(id).addEventListener("input", () => {
          state.dimensionRowsTouched = true;
          renderTemplateRulePreview();
        });
      });
      document.getElementById("addTextSequenceRowBtn").addEventListener("click", addTextSequenceRow);
      document.getElementById("referenceAiFile").addEventListener("change", renderAssetRows);
      document.getElementById("designFontAiFiles").addEventListener("change", renderAssetRows);
      document.getElementById("assetAiFiles").addEventListener("change", renderAssetRows);
      document.getElementById("primaryAiFile").addEventListener("change", renderAssetRows);
      bindTemplateRuleInputs();
      document.getElementById("previewRuleBtn").addEventListener("click", renderRulePreviewFromServer);
      document.getElementById("saveRuleDraftBtn").addEventListener("click", saveRuleDraft);
      document.getElementById("publishRuleBtn").addEventListener("click", publishRule);
      document.getElementById("newRuleBtn").addEventListener("click", newRuleDraft);
      ["ruleName", "ruleDisplayName", "ruleDepartments", "ruleMatch", "ruleLabelFields", "ruleShowFrame", "ruleColorMode", "ruleNaturalText"].forEach(id => {
        document.getElementById(id).addEventListener("input", renderRulePreview);
        document.getElementById(id).addEventListener("change", renderRulePreview);
      });
    }

    function bindTemplateRuleInputs() {
      const selectors = [
        "#optionGroupRows input",
        "#optionGroupRows select",
        "#defaultFont",
        "#defaultDesign",
        "#defaultStyle",
        "#defaultColor",
        "#outputColorMode",
        "#templateProfile",
        "#orderBindingsJson",
        "#assetMappingsJson",
        "#textPoliciesJson",
        "#outputTransformsJson",
        "#validationSampleJson",
        "#templateRuleDescription",
        "#overrideRows input",
        "#overrideRows select",
        "#templateAdvancedRules",
        "#templateExceptionStatus"
      ];
      document.querySelectorAll(selectors.join(",")).forEach(element => {
        element.addEventListener("input", renderTemplateRulePreview);
        element.addEventListener("change", renderTemplateRulePreview);
      });
      document.getElementById("optionGroupRows").addEventListener("click", event => {
        const button = event.target.closest("[data-remove-option-group]");
        if (!button) return;
        button.closest(".structured-row").remove();
        state.optionGroupsTouched = true;
        renderTemplateRulePreview();
      });
      ["input", "change"].forEach(eventName => {
        document.getElementById("optionGroupRows").addEventListener(eventName, () => {
          state.optionGroupsTouched = true;
          renderTemplateRulePreview();
        });
      });
      const mappingRows = document.getElementById("designAssetMappingRows");
      mappingRows.addEventListener("input", () => {
        state.assetMappingsTouched = true;
        renderTemplateRulePreview();
      });
      mappingRows.addEventListener("click", event => {
        const button = event.target.closest("[data-remove-design-asset-mapping]");
        if (!button) return;
        button.closest(".structured-row").remove();
        state.assetMappingsTouched = true;
        renderTemplateRulePreview();
      });
      ["dimensionRows", "textSequenceRows"].forEach(id => {
        const container = document.getElementById(id);
        container.addEventListener("input", () => {
          markDynamicRowsTouched(id);
          renderTemplateRulePreview();
        });
        container.addEventListener("change", () => {
          markDynamicRowsTouched(id);
          renderTemplateRulePreview();
        });
        container.addEventListener("click", event => {
          const dimensionButton = event.target.closest("[data-remove-dimension-row]");
          if (dimensionButton) {
            removeDynamicRuleRow(dimensionButton, "dimensionRows");
            return;
          }
          const sequenceButton = event.target.closest("[data-remove-text-sequence-row]");
          if (sequenceButton) {
            removeDynamicRuleRow(sequenceButton, "textSequenceRows");
          }
        });
      });
    }

    function addDimensionRow() {
      state.dimensionRowsTouched = true;
      const rows = collectDimensionRows({ includeEmpty: true });
      rows.push(blankDimensionRow());
      setDimensionRows(rows);
      renderTemplateRulePreview();
    }

    function addTextSequenceRow() {
      state.textSequenceRowsTouched = true;
      const rows = collectTextSequenceRows({ includeEmpty: true });
      rows.push(blankTextSequenceRow());
      setTextSequenceRows(rows);
      renderTemplateRulePreview();
    }

    function removeDynamicRuleRow(button, rowType) {
      markDynamicRowsTouched(rowType);
      const row = button.closest(".structured-row");
      if (row) row.remove();
      renderTemplateRulePreview();
    }

    function markDynamicRowsTouched(rowType) {
      if (rowType === "dimensionRows") {
        state.dimensionRowsTouched = true;
      } else if (rowType === "textSequenceRows") {
        state.textSequenceRowsTouched = true;
      }
    }

    function setDimensionRows(rows) {
      const items = rows && rows.length ? rows : defaultDimensionRows();
      document.getElementById("dimensionRows").innerHTML = items
        .map((row, index) => renderDimensionRow(row, index))
        .join("");
      syncDimensionMode();
    }

    function syncDimensionMode() {
      const fixed = document.getElementById("dimensionMode").value === "fixed";
      document.getElementById("dimensionRows").hidden = fixed;
      document.getElementById("addDimensionRowBtn").hidden = fixed;
    }

    function setTextSequenceRows(rows) {
      const items = rows && rows.length ? rows : defaultTextSequenceRows();
      document.getElementById("textSequenceRows").innerHTML = items
        .map((row, index) => renderTextSequenceRow(row, index))
        .join("");
    }

    function renderDimensionRow(row, index) {
      const placeholders = [
        { target: "例如 Style1", width: "5", height: "5" },
        { target: "例如 Name", width: "6", height: "7" },
        { target: "例如 Title 或 Design1", width: "", height: "" }
      ];
      const hint = placeholders[index] || placeholders[0];
      const unit = row.unit || "cm";
      return `
        <div class="structured-row dynamic dimension" data-dimension-row>
          <div><label>尺寸对象</label><input data-dimension-target placeholder="${hint.target}" value="${escapeHtml(row.target || "")}" /></div>
          <div><label>宽</label><input data-dimension-width placeholder="${hint.width}" value="${escapeHtml(row.width || "")}" /></div>
          <div><label>高</label><input data-dimension-height placeholder="${hint.height}" value="${escapeHtml(row.height || "")}" /></div>
          <div>
            <label>单位</label>
            <select data-dimension-unit>
              <option value="cm" ${selectedAttr(unit, "cm")}>cm</option>
              <option value="mm" ${selectedAttr(unit, "mm")}>mm</option>
            </select>
          </div>
          <div><button class="row-remove-btn" type="button" data-remove-dimension-row aria-label="删除尺寸规则">×</button></div>
        </div>
      `;
    }

    function renderTextSequenceRow(row, index) {
      const hints = [
        { scope: "例如 Design1", field: "例如 Name", delimiter: "|", prefix: "例如 Name", start: "1", count: "3" },
        { scope: "例如 Design2", field: "例如 Name", delimiter: "|", prefix: "例如 Name", start: "1", count: "2" },
        { scope: "可留空", field: "例如 Title", delimiter: "可留空", prefix: "例如 Title", start: "1", count: "1" }
      ];
      const hint = hints[index] || hints[0];
      return `
        <div class="structured-row dynamic sequence" data-text-sequence-row>
          <div><label>适用设计/选项</label><input data-text-sequence-scope placeholder="${hint.scope}" value="${escapeHtml(row.scope || "")}" /></div>
          <div><label>订单字段</label><input data-text-sequence-field placeholder="${hint.field}" value="${escapeHtml(row.field || "")}" /></div>
          <div><label>分隔符</label><input data-text-sequence-delimiter placeholder="${hint.delimiter}" value="${escapeHtml(row.delimiter || "")}" /></div>
          <div><label>变量前缀</label><input data-text-sequence-prefix placeholder="${hint.prefix}" value="${escapeHtml(row.variable_prefix || "")}" /></div>
          <div><label>起始编号</label><input data-text-sequence-start placeholder="${hint.start}" value="${escapeHtml(row.start_index || "")}" /></div>
          <div><label>数量</label><input data-text-sequence-count placeholder="${hint.count}" value="${escapeHtml(row.count || "")}" /></div>
          <div><button class="row-remove-btn" type="button" data-remove-text-sequence-row aria-label="删除字段拆分规则">×</button></div>
        </div>
      `;
    }

    function selectedAttr(current, expected) {
      return current === expected ? "selected" : "";
    }

    function blankDimensionRow() {
      return { target: "", width: "", height: "", unit: "cm" };
    }

    function blankTextSequenceRow() {
      return { scope: "", field: "", delimiter: "", variable_prefix: "", start_index: "", count: "" };
    }

    function defaultDimensionRows() {
      return [blankDimensionRow()];
    }

    function defaultTextSequenceRows() {
      return [blankTextSequenceRow()];
    }

    function switchPage(name) {
      document.querySelectorAll("[data-page-tab]").forEach(button => {
        button.classList.toggle("active", button.dataset.pageTab === name);
      });
      document.querySelectorAll(".page").forEach(page => {
        page.classList.toggle("active", page.id === `page-${name}`);
      });
    }

    function newTemplate() {
      state.selectedTemplateId = "";
      state.templateRuleDraft = null;
      state.templateRuleBaseConfig = null;
      state.optionGroupsTouched = false;
      state.dimensionRowsTouched = false;
      state.textSequenceRowsTouched = false;
      clearTemplateForm();
      renderTemplateOptions();
      renderTemplateList();
      switchPage("templates");
      setMessage("templateSaveMessage", "正在新增模板，填写基础信息和规则后保存", "");
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
      renderJobsTable();
    }

    function renderTemplateOptions() {
      const select = document.getElementById("renderTemplate");
      select.innerHTML = "";
      state.templates.filter(template => template.status === "active").forEach(template => {
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
          <button class="btn-subtle" data-template-disable="${escapeHtml(template.template_id)}">停用</button>
          <button class="btn-secondary" data-template-remove="${escapeHtml(template.template_id)}">移除</button>
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
      target.querySelectorAll("[data-template-disable]").forEach(button => {
        button.addEventListener("click", () => disableTemplate(button.dataset.templateDisable));
      });
      target.querySelectorAll("[data-template-remove]").forEach(button => {
        button.addEventListener("click", () => removeTemplate(button.dataset.templateRemove));
      });
    }

    async function disableTemplate(templateId) {
      const confirmation = window.prompt(`输入模板 ID ${templateId} 确认停用。文件不会被删除。`);
      if (confirmation !== templateId) return;
      try {
        await postJson(`/api/templates/${encodeURIComponent(templateId)}/disable`, { confirmation });
        await loadTemplates(templateId);
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    async function removeTemplate(templateId) {
      const confirmation = window.prompt(`输入模板 ID ${templateId} 确认移除登记。所有本地文件都会保留，可用于恢复。`);
      if (confirmation !== templateId) return;
      try {
        await deleteJson(`/api/templates/${encodeURIComponent(templateId)}`, { confirmation });
        state.selectedTemplateId = "";
        await loadTemplates();
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function syncSelectedTemplate() {
      const template = selectedTemplate();
      if (!template) {
        document.getElementById("renderTemplateBadge").textContent = "未选择模板";
        clearTemplateForm();
        return;
      }
      document.getElementById("renderTemplate").value = template.template_id;
      document.getElementById("renderTemplateBadge").textContent = displayType(template.template_type);
      fillTemplateForm(template);
      renderTemplateList();
    }

    function fillTemplateForm(template) {
      document.getElementById("templateId").value = template.template_id || "";
      document.getElementById("templateName").value = template.name || "";
      document.getElementById("referenceAiFile").value = "";
      document.getElementById("primaryAiFile").value = "";
      document.getElementById("designFontAiFiles").value = "";
      document.getElementById("assetAiFiles").value = "";
      loadTemplateRuleText(template);
      renderAssetRows();
    }

    function updateTemplateWorkflowState(hasDraft) {
      const saveButton = document.getElementById("saveTemplateBtn");
      if (saveButton) saveButton.textContent = "检查并保存规则";
      const uploadButton = document.getElementById("uploadScanTemplateBtn");
      if (uploadButton) uploadButton.disabled = Boolean(selectedTemplate() && selectedTemplate().status === "active");
      const uploadStatus = document.getElementById("uploadScanStatus");
      if (uploadStatus && !hasDraft) uploadStatus.textContent = "选择文件后从这里开始";
      const rescanButton = document.getElementById("rescanTemplateBtn");
      if (rescanButton) {
        const savedTemplate = Boolean(selectedTemplate());
        rescanButton.hidden = !savedTemplate;
        rescanButton.disabled = !savedTemplate;
      }
    }

    async function loadTemplateRuleText(template) {
      state.templateRuleDraft = null;
      state.templateRuleBaseConfig = null;
      state.templateOnboarding = null;
      state.optionGroupsTouched = false;
      state.dimensionRowsTouched = false;
      state.textSequenceRowsTouched = false;
      resetTemplateRuleFields();
      updateTemplateWorkflowState(false);
      if (template) {
        try {
          const onboarding = await getJson(`/api/templates/${encodeURIComponent(template.template_id)}/onboarding`);
          state.templateOnboarding = onboarding;
          if (onboarding.draft) {
            const pack = onboarding.draft;
            state.templateRuleDraft = pack;
            state.templateRuleBaseConfig = pack.rules || {};
            fillOnboardingFields(pack, onboarding.versions || [], onboarding.scan_evidence || {});
            renderTemplateRulePreview();
            updateTemplateWorkflowState(true);
            return;
          }
          fillOnboardingFields(null, onboarding.versions || [], onboarding.scan_evidence || {});
        } catch (error) {
          state.templateOnboarding = null;
        }
      }
      if (!template || !(template.template_rules_config || template.template_config)) {
        renderTemplateRulePreview();
        updateTemplateWorkflowState(false);
        return;
      }
      try {
        const payload = await getJson(`/api/templates/${encodeURIComponent(template.template_id)}/config`);
        const config = payload.config || {};
        state.templateRuleDraft = payload.config || null;
        state.templateRuleBaseConfig = config;
        fillTemplateRuleFields(config);
      } catch (error) {
        state.templateRuleDraft = null;
        state.templateRuleBaseConfig = null;
        resetTemplateRuleFields();
      }
      renderTemplateRulePreview();
      updateTemplateWorkflowState(false);
    }

    function renderAssetRows() {
      const template = formTemplate();
      const rows = [];
      if (template && template.template_ai) {
        const templateAiRole = displayTemplateAiRole(template);
        rows.push({
          name: fileName(template.template_ai),
          type: templateAiRole,
          status: "已保存",
          action: "primary",
          key: "primary"
        });
      }
      (template && template.assets ? template.assets : []).forEach((asset, index) => {
        rows.push({
          name: asset.file_name || fileName(asset.stored_path),
          type: asset.role || "独立设计模板",
          status: displayAssetStatus(asset.status),
          action: "asset",
          key: String(index)
        });
      });
      const reference = document.getElementById("referenceAiFile").files[0];
      if (reference) rows.push({ name: reference.name, type: "原始参考模板", status: "本次选择，待上传并扫描", action: "pending" });
      const primary = document.getElementById("primaryAiFile").files[0];
      if (primary) rows.push({ name: primary.name, type: "尺寸/作图区模板", status: "本次选择，待上传并扫描", action: "pending" });
      Array.from(document.getElementById("designFontAiFiles").files || []).forEach(file => {
        rows.push({ name: file.name, type: "独立设计字体资源", status: "本次选择，待上传并扫描", action: "pending" });
      });
      Array.from(document.getElementById("assetAiFiles").files || []).forEach(file => {
        rows.push({ name: file.name, type: "独立设计资源", status: "本次选择，待上传并扫描", action: "pending" });
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
          <span>${renderAssetActions(row)}</span>
        </div>
      `).join("");
      target.querySelectorAll("[data-asset-download]").forEach(button => {
        button.addEventListener("click", () => downloadTemplateAsset(button.dataset.assetDownload));
      });
      target.querySelectorAll("[data-asset-delete]").forEach(button => {
        button.addEventListener("click", () => deleteTemplateAsset(button.dataset.assetDelete));
      });
    }

    function renderAssetActions(row) {
      if (row.action === "primary") {
        return `
          <span class="asset-actions">
            <button class="btn-subtle" data-asset-download="primary">下载</button>
            <button class="btn-secondary" data-asset-delete="primary">删除</button>
          </span>
        `;
      }
      if (row.action === "asset") {
        return `
          <span class="asset-actions">
            <button class="btn-subtle" data-asset-download="${escapeHtml(row.key)}">下载</button>
            <button class="btn-secondary" data-asset-delete="${escapeHtml(row.key)}">删除</button>
          </span>
        `;
      }
      return '<span class="asset-note">保存后可操作</span>';
    }

    async function rescanTemplate() {
      const templateId = document.getElementById("templateId").value.trim();
      if (!templateId || !selectedTemplate()) {
        setMessage("templateSaveMessage", "请先保存模板文件，再重新扫描", "error");
        return;
      }
      setMessage("templateSaveMessage", "正在扫描已保存的模板文件，请稍候", "");
      try {
        const result = await postJson("/api/templates/" + encodeURIComponent(templateId) + "/scan", {});
        await loadTemplates(templateId);
        if (result.scan_ok) {
          const uploadStatus = document.getElementById("uploadScanStatus");
          if (uploadStatus) uploadStatus.textContent = "扫描完成，请核对规则";
          setMessage("templateSaveMessage", "扫描完成，已生成规则草稿，请核对后确认保存", "ok");
        } else {
          setMessage(
            "templateSaveMessage",
            "扫描未完全成功，文件和草稿已保留：" +
              (result.scan_error || "请检查 Illustrator 和模板文件后重试") +
              "。可点击“重新扫描已保存文件”继续",
            "error"
          );
          const uploadStatus = document.getElementById("uploadScanStatus");
          if (uploadStatus) uploadStatus.textContent = "文件已保存，扫描失败，可重新扫描";
        }
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function displayAssetStatus(status) {
      const names = {
        uploaded: "已保存",
        active: "已保存",
        draft: "草稿",
        pending: "待上传"
      };
      return names[status] || status || "已保存";
    }

    function uploadedAssetCount() {
      const template = formTemplate();
      const existingDesignCount = template && template.assets
        ? template.assets.filter(asset => String(asset.role || "").includes("独立设计")).length
        : 0;
      const designCount = (document.getElementById("designFontAiFiles").files || []).length + (document.getElementById("assetAiFiles").files || []).length;
      return existingDesignCount + designCount;
    }

    function renderTemplateRulePreview() {
      const target = document.getElementById("templateRulePreview");
      const draft = buildTemplateRulePayload();
      state.templateRuleDraft = draft;
      target.innerHTML = renderTemplateRuleCheck(draft);
    }

    async function extractTemplateRules() {
      const templateId = document.getElementById("templateId").value.trim();
      const description = document.getElementById("templateRuleDescription").value.trim();
      if (!templateId || !description) {
        setMessage("templateSaveMessage", "请先填写模板 ID 和补充说明", "error");
        return;
      }
      const status = document.getElementById("templateExtractionStatus");
      status.textContent = "正在生成补充草稿";
      try {
        const result = await postJson("/api/templates/rules/draft", {
          template_id: templateId,
          template_type: inferTemplateTypeFromForm(),
          natural_text: description,
          asset_count: uploadedAssetCount()
        });
        const current = buildTemplateRulePayload();
        const draft = result.draft || {};
        const merged = { ...current };
        Object.entries(draft).forEach(([key, value]) => {
          if (key !== "natural_text" && key !== "raw_text" && !hasConfiguredRuleValue(merged[key]) && hasConfiguredRuleValue(value)) {
            merged[key] = value;
          }
        });
        merged.natural_text = description;
        state.templateRuleBaseConfig = merged;
        state.optionGroupsTouched = false;
        state.dimensionRowsTouched = false;
        state.textSequenceRowsTouched = false;
        fillTemplateRuleFields(merged);
        setHiddenRuleJson("orderBindingsJson", merged.order_bindings || {});
        setHiddenRuleJson("assetMappingsJson", merged.asset_mappings || []);
        setHiddenRuleJson("textPoliciesJson", merged.text_policies || {});
        setHiddenRuleJson("outputTransformsJson", merged.transforms || {});
        setHiddenRuleJson("validationSampleJson", draft.validation_sample || parseJsonField("validationSampleJson", {}));
        state.templateRulesDescriptionDirty = false;
        renderTemplateExtractionFeedback(result);
        renderTemplateRulePreview();
        status.textContent = "已生成补充草稿，未覆盖固定项";
        setMessage("templateSaveMessage", "补充规则草稿已生成，请核对后再检查", "ok");
      } catch (error) {
        status.textContent = "补充草稿生成失败";
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function hasConfiguredRuleValue(value) {
      if (Array.isArray(value)) return value.length > 0;
      if (value && typeof value === "object") return Object.keys(value).length > 0;
      return String(value == null ? "" : value).trim().length > 0;
    }

    function setHiddenRuleJson(id, value) {
      const input = document.getElementById(id);
      if (input) input.value = JSON.stringify(value == null ? {} : value);
    }

    function renderTemplateExtractionFeedback(result) {
      const summary = Array.isArray(result.summary) ? result.summary : [];
      const unresolved = Array.isArray(result.unresolved) ? result.unresolved : [];
      const lines = [];
      lines.push(summary.length ? "已识别：" : "暂未识别到可直接使用的规则：");
      summary.forEach(item => lines.push(`- ${item}`));
      if (unresolved.length) {
        lines.push("待补充：");
        unresolved.forEach(item => lines.push(`- ${item}`));
      }
      document.getElementById("templateExtractionSummary").textContent = lines.join("\\n");
    }

    async function checkTemplateRule() {
      renderTemplateRulePreview();
      const templateId = document.getElementById("templateId").value.trim();
      if (!templateId || !state.templateOnboarding || !state.templateOnboarding.draft) {
        setMessage("templateSaveMessage", "请先保存模板并完成 AI 扫描，再检查规则", "error");
        return false;
      }
      try {
        const result = await postJson(`/api/templates/${encodeURIComponent(templateId)}/rules/check`, {
          pack: buildCanonicalRulePack()
        });
        state.templateRuleDraft = result.pack;
        document.getElementById("fieldSources").value = formatFieldSources(
          (result.pack.audit && result.pack.audit.field_sources) || {},
          result.pack.rules || {}
        );
        const issues = [...(result.errors || []), ...(result.warnings || [])];
        document.getElementById("templateRulePreview").innerHTML = renderOnboardingIssues(result, issues);
        const blockers = (result.errors || []).map(formatRuleBlocker).filter(Boolean);
        const blockerText = blockers.length ? blockers.slice(0, 3).join("；") : "请查看下方规则检查结果";
        setMessage("templateSaveMessage", result.ok ? "后端检查通过，等待你最终确认" : `不能启用：${blockerText}${blockers.length > 3 ? "；请查看下方规则检查结果" : ""}`, result.ok ? "ok" : "error");
        return Boolean(result.ok);
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
        return false;
      }
    }

    function buildCanonicalRulePack() {
      const source = state.templateOnboarding && state.templateOnboarding.draft;
      if (!source) throw new Error("缺少扫描草稿，不能确认模板");
      const rules = buildTemplateRulePayload();
      rules.order_bindings = parseJsonField("orderBindingsJson", {});
      rules.asset_mappings = collectDesignAssetMappings();
      rules.text_policies = parseJsonField("textPoliciesJson", {});
      rules.transforms = parseJsonField("outputTransformsJson", {});
      const unresolved = ((source.validation && source.validation.unresolved_items) || []).filter(item => {
        if (item.code === "profile") return document.getElementById("templateProfile").value === "unclassified";
        if (item.code === "text_targets") return !hasSlotsOrMappings(rules);
        if (item.code === "option_group_names") return !rules.option_groups.length;
        return item.code !== "confirmation_required";
      });
      return {
        ...source,
        template: { ...source.template, template_id: document.getElementById("templateId").value.trim(), profile: document.getElementById("templateProfile").value },
        structure: source.structure,
        rules,
        validation: { ...source.validation, status: "draft", unresolved_items: unresolved, sample: parseJsonField("validationSampleJson", {}) },
        audit: source.audit
      };
    }

    function parseJsonField(id, fallback) {
      const text = document.getElementById(id).value.trim();
      if (!text) return fallback;
      try { return JSON.parse(text); }
      catch (error) { throw new Error(`${document.querySelector(`label[for="${id}"]`).textContent} JSON 格式错误`); }
    }

    function renderOnboardingIssues(result, issues) {
      const rows = issues.length ? issues.map(item => `<li>${escapeHtml(item.code)}：${escapeHtml(item.message)}</li>`).join("") : "<li>无阻断项</li>";
      return `<div class="preview-chip"><span>后端检查</span><strong>${result.ok ? "通过" : "未通过"}</strong></div><ul>${rows}</ul>`;
    }

    function formatRuleBlocker(item) {
      const code = String((item && item.code) || "");
      const names = { profile: "请选择模板规则类型", text_targets: "补充文字目标", option_group_names: "补充选项组角色", order_bindings: "补充订单字段绑定", text_policies: "补充文字适配/拆分规则", validation_sample: "补充验证样例", exceptions: "处理高级例外", scan_failed: "重新扫描模板" };
      return names[code] || String((item && item.message) || "规则配置不完整");
    }

    function buildTemplateRulePayload() {
      const baseConfig = isPlainObject(state.templateRuleBaseConfig) ? state.templateRuleBaseConfig : {};
      const optionGroups = collectOptionGroups();
      const dimensionMode = document.getElementById("dimensionMode").value;
      const collectedDimensions = dimensionMode === "fixed" ? collectFixedDimensions() : collectDimensions();
      const dimensions = dimensionMode === "fixed"
        ? collectedDimensions
        : (state.dimensionRowsTouched
          ? collectedDimensions
          : mergeDimensions(baseConfig.dimensions, collectedDimensions));
      const baseTextSequences = Array.isArray(baseConfig.text_sequences) && baseConfig.text_sequences.length
        ? baseConfig.text_sequences
        : legacyTextSequences(baseConfig);
      const collectedTextSequences = collectTextSequences();
      const textSequences = state.textSequenceRowsTouched
        ? mergeTextSequences([], collectedTextSequences)
        : mergeTextSequences(baseTextSequences, collectedTextSequences);
      const sequenceSlotMappings = slotMappingsFromTextSequences(textSequences);
      const legacySlotMappingRows = !state.textSequenceRowsTouched && Array.isArray(baseConfig.slot_mappings) && baseConfig.slot_mappings.length
        ? baseConfig.slot_mappings
        : (!state.textSequenceRowsTouched ? legacySlotMappings(baseConfig.slots || []) : []);
      const slotMappings = sequenceSlotMappings.length ? sequenceSlotMappings : legacySlotMappingRows;
      const slots = buildSlotsFromMappings(
        slotMappings,
        state.textSequenceRowsTouched && !slotMappings.length ? [] : baseConfig.slots
      );
      const overrides = collectOverrides();
      const fontOptions = optionsByRole(optionGroups, "font_options");
      const designFontOptions = optionsByRole(optionGroups, "design_font_options");
      const designOptions = optionsByRole(optionGroups, "design_options");
      const styleOptions = optionsByRole(optionGroups, "style_options");
      const collectedAssetMappings = collectDesignAssetMappings();
      const baseAssetMappings = Array.isArray(baseConfig.asset_mappings) ? baseConfig.asset_mappings : [];
      const baseDefaults = isPlainObject(baseConfig.defaults) ? baseConfig.defaults : {};
      const defaults = {
        ...baseDefaults,
        font: document.getElementById("defaultFont").value.trim(),
        design: document.getElementById("defaultDesign").value.trim(),
        style: document.getElementById("defaultStyle").value.trim(),
        color: document.getElementById("defaultColor").value.trim()
      };
      const advancedText = document.getElementById("templateAdvancedRules").value.trim();
      return {
        ...baseConfig,
        version: 2,
        template_id: document.getElementById("templateId").value.trim(),
        mode: inferTemplateTypeFromForm(),
        template_type: inferTemplateTypeFromForm(),
        status: "draft",
        rule_source: "structured_form",
        natural_text: document.getElementById("templateRuleDescription").value.trim(),
        raw_text: state.dimensionRowsTouched ? "" : (baseConfig.raw_text || ""),
        option_groups: optionGroups,
        font_options: state.optionGroupsTouched ? fontOptions : (fontOptions.length ? fontOptions : normalizeOptions(baseConfig.font_options)),
        design_font_options: state.optionGroupsTouched
          ? designFontOptions
          : (designFontOptions.length ? designFontOptions : normalizeOptions(baseConfig.design_font_options)),
        design_options: state.optionGroupsTouched ? designOptions : mergeDesignOptions(baseConfig.design_options, designOptions),
        style_options: state.optionGroupsTouched ? styleOptions : (styleOptions.length ? styleOptions : normalizeOptions(baseConfig.style_options)),
        asset_mappings: state.assetMappingsTouched
          ? collectedAssetMappings
          : (collectedAssetMappings.length ? collectedAssetMappings : baseAssetMappings),
        dimension_mode: dimensionMode,
        dimensions,
        slots,
        text_sequences: textSequences,
        slot_mappings: slotMappings,
        defaults,
        option_overrides: {
          ...(isPlainObject(baseConfig.option_overrides) ? baseConfig.option_overrides : {}),
          ...overrides
        },
        output: {
          ...(isPlainObject(baseConfig.output) ? baseConfig.output : {}),
          color_mode: document.getElementById("outputColorMode").value
        },
        exceptions: {
          ...(isPlainObject(baseConfig.exceptions) ? baseConfig.exceptions : {}),
          note: advancedText,
          status: document.getElementById("templateExceptionStatus").value || (advancedText ? "manual_review" : "none")
        },
        assets: buildAssetsRulePayload(baseConfig),
        parser: {
          ...(isPlainObject(baseConfig.parser) ? baseConfig.parser : {}),
          source: "structured_form"
        }
      };
    }

    function isPlainObject(value) {
      return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    }

    function mergeDesignOptions(existing, optionValues) {
      const options = optionValues.length ? optionValues : normalizeOptions(existing);
      if (isPlainObject(existing)) {
        const merged = { ...existing };
        if (optionValues.length) {
          if (Array.isArray(merged.design_font_options)) {
            merged.design_font_options = optionValues;
          } else {
            merged.options = optionValues;
          }
        }
        return merged;
      }
      return options;
    }

    function buildSlotsFromMappings(slotMappings, existingSlots) {
      const slots = Array.isArray(existingSlots) ? existingSlots : [];
      if (!slotMappings.length) return slots.slice();
      return slotMappings.map(item => {
        const match = slots.find(slot => (
          slot.name === item.slot ||
          slot.source === item.field ||
          slot.field === item.field
        )) || {};
        return {
          ...match,
          name: item.slot,
          type: match.type || "text_fit_box",
          source: item.field,
          field: item.field,
          scope: item.scope || match.scope || "",
          delimiter: item.delimiter || match.delimiter || "",
          sequence_index: item.sequence_index || match.sequence_index || null
        };
      });
    }

    function buildAssetsRulePayload(baseConfig) {
      if (Array.isArray(baseConfig.assets)) return baseConfig.assets;
      const count = uploadedAssetCount();
      const baseAssets = isPlainObject(baseConfig.assets) ? baseConfig.assets : {};
      return {
        ...baseAssets,
        mode: count > 0 ? "split_ai" : (baseAssets.mode || "inline"),
        count
      };
    }

    function mergeDimensions(existing, visibleDimensions) {
      const base = isPlainObject(existing) ? { ...existing } : {};
      return Object.keys(visibleDimensions || {}).length ? visibleDimensions : base;
    }

    function mergeTextSequences(existing, visibleSequences) {
      const base = (Array.isArray(existing) ? existing : []).map(item => ({ ...item }));
      const visible = Array.isArray(visibleSequences) ? visibleSequences : [];
      if (!visible.length) return base;
      return visible.map(sequence => {
        const normalized = { ...sequence };
        delete normalized.row_index;
        return normalized;
      }).filter(item => item.field && Array.isArray(item.variables) && item.variables.length);
    }

    function templateRuleJsonText() {
      return JSON.stringify(buildTemplateRulePayload());
    }

    function collectOptionGroups() {
      const names = Array.from(document.querySelectorAll("[data-option-group-name]"));
      const roles = Array.from(document.querySelectorAll("[data-option-group-role]"));
      return names.map((input, index) => ({
        name: input.value.trim(),
        role: roles[index] ? roles[index].value : "",
        options: expandOptionRange(input.value.trim())
      })).filter(item => item.name && item.role);
    }

    function setDesignAssetMappingRows(mappings) {
      const target = document.getElementById("designAssetMappingRows");
      target.innerHTML = "";
      (Array.isArray(mappings) ? mappings : []).forEach(mapping => addDesignAssetMappingRow(mapping));
    }

    function addDesignAssetMappingRow(mapping = {}) {
      const row = document.createElement("div");
      row.className = "structured-row";
      row.innerHTML = `
        <div><label>订单选项</label><input data-design-asset-option placeholder="例如 F10 或 D1" value="${escapeHtml(mapping.option || "")}" /></div>
        <div><label>独立资源文件</label><input data-design-asset-file placeholder="例如 font-f10.ai 或 design-d1.ai" value="${escapeHtml(mapping.asset || "")}" /></div>
        <div><label>AI 编组</label><input data-design-asset-group placeholder="例如 F10" value="${escapeHtml(mapping.group || mapping.ai_group || "")}" /></div>
        <div><label>操作</label><button class="btn-subtle" type="button" data-remove-design-asset-mapping>移除</button></div>`;
      document.getElementById("designAssetMappingRows").appendChild(row);
    }

    function collectDesignAssetMappings() {
      return Array.from(document.querySelectorAll("#designAssetMappingRows .structured-row")).map(row => ({
        option: row.querySelector("[data-design-asset-option]").value.trim(),
        asset: row.querySelector("[data-design-asset-file]").value.trim(),
        group: row.querySelector("[data-design-asset-group]").value.trim()
      })).filter(mapping => mapping.option || mapping.asset || mapping.group);
    }

    function expandOptionRange(value) {
      const text = String(value || "").trim();
      const range = text.match(/^([A-Za-z]+)\\s*(\\d+)\\s*-\\s*(?:[A-Za-z]+)?\\s*(\\d+)$/);
      if (!range) {
        return splitList(text);
      }
      const prefix = range[1];
      const start = Number(range[2]);
      const end = Number(range[3]);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || end - start > 100) {
        return [text];
      }
      const result = [];
      for (let index = start; index <= end; index += 1) {
        result.push(`${prefix}${index}`);
      }
      return result;
    }

    function splitList(value) {
      return String(value || "")
        .split(/[,，/、\\s]+/)
        .map(item => item.trim())
        .filter(Boolean);
    }

    function optionsByRole(optionGroups, role) {
      const result = [];
      optionGroups.filter(group => group.role === role).forEach(group => {
        group.options.forEach(option => {
          if (!result.includes(option)) result.push(option);
        });
      });
      return result;
    }

    function collectDimensions() {
      const result = {};
      collectDimensionRows().forEach(row => {
        const target = row.target;
        const width = Number(row.width);
        const height = Number(row.height);
        const unit = row.unit || "cm";
        if (!target || !width || !height) return;
        const scale = unit === "cm" ? 10 : 1;
        result[target] = {
          width_mm: Number((width * scale).toFixed(3)),
          height_mm: Number((height * scale).toFixed(3)),
          unit
        };
      });
      return result;
    }

    function collectFixedDimensions() {
      const width = Number(document.getElementById("fixedWidth").value);
      const height = Number(document.getElementById("fixedHeight").value);
      if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return {};
      }
      return {
        Fixed: {
          width_mm: Number(width.toFixed(3)),
          height_mm: Number(height.toFixed(3)),
          unit: "mm"
        }
      };
    }

    function collectDimensionRows(options = {}) {
      return Array.from(document.querySelectorAll("[data-dimension-row]")).map(row => {
        const target = row.querySelector("[data-dimension-target]")?.value.trim() || "";
        const width = row.querySelector("[data-dimension-width]")?.value.trim() || "";
        const height = row.querySelector("[data-dimension-height]")?.value.trim() || "";
        const unit = row.querySelector("[data-dimension-unit]")?.value || "cm";
        return { target, width, height, unit };
      }).filter(row => options.includeEmpty || row.target || row.width || row.height);
    }

    function collectTextSequences() {
      return collectTextSequenceRows().map((row, index) => {
        const field = row.field;
        const variablePrefix = row.variable_prefix;
        const countValue = Number(row.count);
        const count = Number.isFinite(countValue) && countValue > 0 ? Math.floor(countValue) : 1;
        const startText = row.start_index;
        const startValue = Number(startText);
        const startIndex = startText && Number.isFinite(startValue) ? Math.floor(startValue) : null;
        const delimiter = row.delimiter;
        const variables = buildSequenceVariables(variablePrefix, startIndex, count);
        return {
          row_index: index,
          scope: row.scope,
          field,
          delimiter: delimiter || (count > 1 ? "|" : ""),
          variable_prefix: variablePrefix,
          start_index: startIndex,
          count,
          variables
        };
      }).filter(item => item.field && item.variable_prefix && item.variables.length);
    }

    function collectTextSequenceRows(options = {}) {
      return Array.from(document.querySelectorAll("[data-text-sequence-row]")).map(row => ({
        scope: row.querySelector("[data-text-sequence-scope]")?.value.trim() || "",
        field: row.querySelector("[data-text-sequence-field]")?.value.trim() || "",
        delimiter: row.querySelector("[data-text-sequence-delimiter]")?.value.trim() || "",
        variable_prefix: row.querySelector("[data-text-sequence-prefix]")?.value.trim() || "",
        start_index: row.querySelector("[data-text-sequence-start]")?.value.trim() || "",
        count: row.querySelector("[data-text-sequence-count]")?.value.trim() || ""
      })).filter(row => (
        options.includeEmpty ||
        row.scope ||
        row.field ||
        row.delimiter ||
        row.variable_prefix ||
        row.start_index ||
        row.count
      ));
    }

    function buildSequenceVariables(prefix, startIndex, count) {
      if (!prefix) return [];
      if (count <= 1 && startIndex === null) return [prefix];
      const firstIndex = startIndex === null ? 1 : startIndex;
      return Array.from({ length: count }, (_, offset) => `${prefix}${firstIndex + offset}`);
    }

    function slotMappingsFromTextSequences(sequences) {
      const rows = [];
      (Array.isArray(sequences) ? sequences : []).forEach(sequence => {
        (sequence.variables || []).forEach((variable, index) => {
          rows.push({
            field: sequence.field,
            slot: variable,
            scope: sequence.scope || "",
            delimiter: sequence.delimiter || "",
            sequence_index: index + 1
          });
        });
      });
      return rows;
    }

    function collectOverrides() {
      const targets = Array.from(document.querySelectorAll("[data-override-target]"));
      const actions = Array.from(document.querySelectorAll("[data-override-action]"));
      const values = Array.from(document.querySelectorAll("[data-override-value]"));
      const result = {};
      targets.forEach((input, index) => {
        const target = input.value.trim();
        const action = actions[index] ? actions[index].value : "";
        const value = values[index] ? values[index].value.trim() : "";
        if (!target || !action) return;
        result[target] = { action };
        if (action === "bold") result[target].bold = true;
        if (action === "uppercase") result[target].uppercase = true;
        if (action === "no_width_compress") result[target].no_width_compress = true;
        if (action === "fixed_color" && value) result[target].color = value;
        if (value) result[target].value = value;
      });
      return result;
    }

    function inferTemplateTypeFromForm() {
      const existingTemplate = formTemplate();
      if (existingTemplate && existingTemplate.template_type) return existingTemplate.template_type;
      if (state.templateRuleBaseConfig && (state.templateRuleBaseConfig.template_type || state.templateRuleBaseConfig.mode)) {
        return state.templateRuleBaseConfig.template_type || state.templateRuleBaseConfig.mode;
      }
      const optionGroups = collectOptionGroups();
      const hasDesignAssets = uploadedAssetCount() > 0;
      const hasDesignGroup = optionGroups.some(group => group.role === "design_options");
      const hasStyleGroup = optionGroups.some(group => group.role === "style_options");
      if (hasDesignAssets) return "asset_split";
      if (hasDesignGroup) return "annotated_ai";
      if (hasStyleGroup) return "pure_text_style";
      return "pure_text_color_design";
    }

    function templateRuleMissingItems(draft) {
      const missing = [];
      const strict = !isEditingExistingTemplate();
      if (!draft.template_id) missing.push("模板 ID");
      if (strict && (!draft.font_options || !draft.font_options.length)) missing.push("字体组");
      if (strict && !hasSlotsOrMappings(draft)) missing.push("字段拆分与变量序列");
      if (strict && (!draft.defaults || !draft.defaults.font)) missing.push("默认字体");
      if (draft.dimension_mode === "fixed" && !hasFixedDimensions(draft.dimensions)) missing.push("固定宽度和固定高度");
      if (strict && draft.dimension_mode !== "fixed" && draft.dimension_mode && !hasMeaningfulDimensions(draft.dimensions)) missing.push("至少一个尺寸规则");
      return missing;
    }

    function isEditingExistingTemplate() {
      return Boolean(formTemplate() || state.templateRuleBaseConfig);
    }

    function hasSlotsOrMappings(draft) {
      return Boolean(
        (Array.isArray(draft.slot_mappings) && draft.slot_mappings.length) ||
        (Array.isArray(draft.slots) && draft.slots.length) ||
        (Array.isArray(draft.text_sequences) && draft.text_sequences.length)
      );
    }

    function hasMeaningfulDimensions(dimensions) {
      if (!isPlainObject(dimensions)) return false;
      return Object.values(dimensions).some(value => {
        if (!isPlainObject(value)) return false;
        return Number(value.width_mm || 0) > 0 || Number(value.height_mm || 0) > 0 || Boolean(value.source);
      });
    }

    function hasFixedDimensions(dimensions) {
      const fixed = isPlainObject(dimensions) ? dimensions.Fixed : null;
      return isPlainObject(fixed) && Number(fixed.width_mm || 0) > 0 && Number(fixed.height_mm || 0) > 0;
    }

    function renderTemplateRuleCheck(draft) {
      const missing = templateRuleMissingItems(draft);
      const optionGroups = draft.option_groups || [];
      const advancedNote = draft.exceptions && draft.exceptions.note ? "有高级例外，需要人工确认" : "无";
      return `
        <div class="preview-grid">
          <div class="preview-chip"><span>规则状态</span><strong>${escapeHtml(missing.length ? "待补充" : "完整")}</strong></div>
          <div class="preview-chip"><span>字体组</span><strong>${escapeHtml(displayOptions(draft.font_options))}</strong></div>
          <div class="preview-chip"><span>独立设计字体</span><strong>${escapeHtml(displayOptions(draft.design_font_options))}</strong></div>
          <div class="preview-chip"><span>设计组</span><strong>${escapeHtml(displayOptions(draft.design_options))}</strong></div>
          <div class="preview-chip"><span>尺寸/版式组</span><strong>${escapeHtml(displayOptions(draft.style_options))}</strong></div>
          <div class="preview-chip"><span>尺寸对象</span><strong>${escapeHtml(displayDimensionTargets(draft.dimensions || {}, draft.dimension_mode))}</strong></div>
          <div class="preview-chip"><span>字段拆分</span><strong>${escapeHtml(displayTextSequences(draft.text_sequences || []))}</strong></div>
          <div class="preview-chip"><span>默认值</span><strong>${escapeHtml(describeDefaults(draft.defaults || {}))}</strong></div>
          <div class="preview-chip"><span>特殊处理</span><strong>${escapeHtml(displayOverrides(draft.option_overrides || {}))}</strong></div>
          <div class="preview-chip"><span>高级例外</span><strong>${escapeHtml(advancedNote)}</strong></div>
          <div class="preview-chip"><span>已填写选项组</span><strong>${escapeHtml(optionGroups.map(group => `${group.name}=${displayOptionGroupRole(group.role)}`).join("；") || "未填写")}</strong></div>
          <div class="preview-chip"><span>缺失项</span><strong>${escapeHtml(missing.join("；") || "无")}</strong></div>
        </div>
      `;
    }

    function displayDimensionTargets(dimensions, mode = "") {
      if (mode === "fixed" && hasFixedDimensions(dimensions)) {
        const fixed = dimensions.Fixed;
        return `固定尺寸 ${trimNumber(Number(fixed.width_mm))}mm x ${trimNumber(Number(fixed.height_mm))}mm`;
      }
      const keys = Object.keys(dimensions || {});
      return keys.length ? keys.join(" / ") : "未填写";
    }

    function displayTextSequences(items) {
      if (!Array.isArray(items) || !items.length) return "未填写";
      return items.map(item => {
        const scope = item.scope ? `${item.scope}: ` : "";
        const variables = Array.isArray(item.variables) ? item.variables.join("/") : "";
        const delimiter = item.delimiter ? ` 按 ${item.delimiter} 拆分` : "";
        return `${scope}${item.field}${delimiter} -> ${variables}`;
      }).join("；");
    }

    function displayOptionGroupRole(value) {
      const names = {
        font_options: "字体组",
        design_font_options: "独立设计字体",
        design_options: "设计组",
        style_options: "尺寸/版式组"
      };
      return names[value] || "未选择";
    }

    function displayOverrides(items) {
      const keys = Object.keys(items || {});
      if (!keys.length) return "无";
      return keys.map(key => `${key}: ${displayOverrideAction(items[key].action)}`).join("；");
    }

    function displayOverrideAction(value) {
      const names = {
        bold: "加粗",
        uppercase: "转大写",
        no_width_compress: "禁止压缩字宽",
        fixed_color: "固定颜色"
      };
      return names[value] || value || "-";
    }

    function resetTemplateRuleFields() {
      setOptionGroupRows([{ name: "", role: "font_options" }]);
      setDesignAssetMappingRows([]);
      state.assetMappingsTouched = false;
      document.getElementById("dimensionMode").value = "object";
      document.getElementById("fixedWidth").value = "";
      document.getElementById("fixedHeight").value = "";
      setDimensionRows(defaultDimensionRows());
      setTextSequenceRows(defaultTextSequenceRows());
      document.getElementById("defaultFont").value = "";
      document.getElementById("defaultDesign").value = "";
      document.getElementById("defaultStyle").value = "";
      document.getElementById("defaultColor").value = "";
      document.getElementById("outputColorMode").value = "CMYK";
      document.querySelectorAll("[data-override-target], [data-override-value]").forEach(input => { input.value = ""; });
      document.querySelectorAll("[data-override-action]").forEach(select => { select.value = ""; });
      document.getElementById("templateAdvancedRules").value = "";
      document.getElementById("templateExceptionStatus").value = "none";
      document.getElementById("templateProfile").value = "unclassified";
      document.getElementById("scanVersion").value = "";
      document.getElementById("scanEvidence").textContent = "暂无扫描事实";
      document.getElementById("scanEvidenceRaw").value = "";
      document.getElementById("fieldSources").value = "";
      document.getElementById("templateRuleDescription").value = "";
      document.getElementById("templateExtractionStatus").textContent = "未填写补充说明";
      document.getElementById("templateExtractionSummary").textContent = "填写补充说明后，系统会在这里显示可补充的规则和仍需确认的内容。";
      state.templateRulesDescriptionDirty = false;
      document.getElementById("orderBindingsJson").value = "{}";
      document.getElementById("assetMappingsJson").value = "[]";
      document.getElementById("textPoliciesJson").value = "{}";
      document.getElementById("outputTransformsJson").value = "{}";
      document.getElementById("validationSampleJson").value = "{}";
      document.getElementById("templateChangeSummary").value = "";
      document.getElementById("templateVersionHistory").textContent = "尚无已确认版本";
    }

    function setOptionGroupRows(groups) {
      const target = document.getElementById("optionGroupRows");
      target.innerHTML = "";
      (groups.length ? groups : [{ name: "", role: "" }]).forEach(group => addOptionGroupRow(group));
    }

    function addOptionGroupRow(group = {}) {
      const row = document.createElement("div");
      row.className = "structured-row three";
      row.innerHTML = `
        <div><label>编号组</label><input data-option-group-name placeholder="例如 F1-F10" value="${escapeHtml(group.name || "")}" /></div>
        <div><label>角色</label><select data-option-group-role>
          <option value="">请选择角色</option><option value="font_options">字体组</option>
          <option value="design_font_options">独立设计字体</option>
          <option value="design_options">设计组</option><option value="style_options">尺寸/版式组</option>
        </select></div>
        <div><label>操作</label><button class="btn-subtle" type="button" data-remove-option-group>移除</button></div>`;
      row.querySelector("[data-option-group-role]").value = group.role || "";
      document.getElementById("optionGroupRows").appendChild(row);
    }

    function fillOnboardingFields(pack, versions, rawScan = {}) {
      const structure = pack && pack.structure ? pack.structure : {};
      const audit = pack && pack.audit ? pack.audit : {};
      const rules = pack && pack.rules ? pack.rules : {};
      const editableRules = prefillScannedOptionSuggestions(rules, audit.field_sources || {});
      state.templateRuleBaseConfig = editableRules;
      fillTemplateRuleFields(editableRules);
      document.getElementById("templateProfile").value = (pack && pack.template && pack.template.profile) || "unclassified";
      document.getElementById("scanVersion").value = structure.scan_version || "";
      const evidence = Object.keys(rawScan).length ? rawScan : (structure.evidence || {});
      document.getElementById("scanEvidence").textContent = formatScanEvidence(evidence);
      document.getElementById("scanEvidenceRaw").value = formatRawScanEvidence(evidence);
      document.getElementById("fieldSources").value = formatFieldSources(audit.field_sources || {}, editableRules);
      document.getElementById("templateRuleDescription").value = editableRules.natural_text || editableRules.raw_text || "";
      document.getElementById("templateExtractionStatus").textContent = editableRules.natural_text ? "已保存补充说明" : "未填写补充说明";
      state.templateRulesDescriptionDirty = false;
      setHiddenRuleJson("orderBindingsJson", editableRules.order_bindings || {});
      setHiddenRuleJson("assetMappingsJson", editableRules.asset_mappings || []);
      setHiddenRuleJson("textPoliciesJson", editableRules.text_policies || {});
      setHiddenRuleJson("outputTransformsJson", editableRules.transforms || {});
      setHiddenRuleJson("validationSampleJson", (pack && pack.validation && pack.validation.sample) || {});
      const history = document.getElementById("templateVersionHistory");
      history.innerHTML = versions.length
        ? versions.map(item => `<div>v${item.version} ${escapeHtml(item.event)} ${escapeHtml(item.created_at || "")} <button class="btn-subtle" type="button" data-rule-rollback="${item.version}">回滚到此版本</button></div>`).join("")
        : "尚无已确认版本";
      history.querySelectorAll("[data-rule-rollback]").forEach(button => {
        button.addEventListener("click", () => rollbackRuleVersion(Number(button.dataset.ruleRollback)));
      });
    }

    function prefillScannedOptionSuggestions(rules, fieldSources) {
      const next = { ...(rules || {}) };
      ["font_options", "design_font_options", "design_options", "style_options"].forEach(key => {
        if (normalizeOptions(next[key]).length) return;
        const source = fieldSources && fieldSources[`rules.${key}`];
        const suggestion = source && typeof source === "object" ? normalizeOptions(source.suggestion) : [];
        if (suggestion.length) next[key] = suggestion;
      });
      return next;
    }

    function prettyJson(value) {
      return JSON.stringify(value == null ? {} : value, null, 2);
    }

    function formatScanEvidence(value) {
      if (!value || typeof value !== "object") return "暂无扫描事实";
      const documentInfo = value.document && typeof value.document === "object" ? value.document : {};
      const sourceFiles = Array.isArray(value.source_files) ? value.source_files : [];
      const items = Array.isArray(value.items) ? value.items : [];
      const typeCounts = value.type_counts && typeof value.type_counts === "object"
        ? value.type_counts
        : items.reduce((counts, item) => {
          const type = item && item.type ? String(item.type) : "Unknown";
          counts[type] = (counts[type] || 0) + 1;
          return counts;
        }, {});
      const namedItems = Array.isArray(value.named_items)
        ? value.named_items
        : items.filter(item => item && item.name).map(item => ({
          path: item.path,
          type: item.type,
          name: item.name
        }));
      const groupNames = Array.from(new Set(namedItems
        .filter(item => item && item.type === "GroupItem" && item.name)
        .map(item => String(item.name))));
      const fontMappings = items
        .filter(item => item && /^F\\d+$/i.test(String(item.name || "")) && (item.font_family || item.font_name))
        .map(item => ({
          option: String(item.name),
          font: String(item.font_family || item.font_name)
        }))
        .sort((left, right) => compareTemplateOptionNames(left.option, right.option));
      const namedOptions = namedItems
        .filter(item => item && /^F\\d+$/i.test(String(item.name || "")))
        .map(item => String(item.name))
        .sort(compareTemplateOptionNames);
      const typeLabels = {
        TextFrame: "文字对象",
        GroupItem: "编组",
        PathItem: "路径",
        RasterItem: "图片"
      };
      const lines = [];
      const primaryFile = documentInfo.name || (sourceFiles[0] && sourceFiles[0].file_name) || "未命名模板";
      const colorSpace = String(documentInfo.color_space || "").replace("DocumentColorSpace.", "");
      const fileCount = sourceFiles.length || (documentInfo.name ? 1 : 0);
      lines.push(fileCount ? `已扫描 ${fileCount} 个模板文件` : "已生成扫描摘要");
      lines.push(`- 主模板：${primaryFile}${documentInfo.source_role ? `（${documentInfo.source_role}）` : ""}`);
      const layerCount = value.layer_count || (Array.isArray(value.layers) ? value.layers.length : 0);
      const itemCount = value.item_count || items.length;
      if (colorSpace || layerCount || itemCount) {
        lines.push(`- ${colorSpace ? `色彩模式：${colorSpace}` : "色彩模式：未识别"}；图层：${layerCount}；对象：${itemCount}`);
      }

      const typeSummary = Object.entries(typeCounts)
        .filter(([, count]) => Number(count) > 0)
        .map(([type, count]) => `${typeLabels[type] || type} ${count}`)
        .join("、");
      if (typeSummary || groupNames.length) {
        lines.push("\\n识别到的结构");
        if (typeSummary) lines.push(`- 对象组成：${typeSummary}`);
        if (groupNames.length) lines.push(`- 命名编组：${groupNames.join("、")}`);
      }

      if (fontMappings.length) {
        lines.push(`\\n可选字体（${fontMappings.length}）`);
        fontMappings.forEach(item => lines.push(`- ${item.option}：${item.font}`));
      } else if (namedOptions.length) {
        lines.push(`\\n识别到的字体编号：${namedOptions.join("、")}`);
      }

      const scanErrors = [
        ...(Array.isArray(value.scan_errors) ? value.scan_errors : []),
        ...sourceFiles.filter(item => item && (!item.scan_ok || item.error)).map(item => item.error || `${item.file_name || "模板文件"} 扫描失败`),
        ...(value.fatal_error ? [value.fatal_error] : [])
      ].filter(Boolean);
      if (scanErrors.length) {
        lines.push("\\n扫描提醒");
        scanErrors.forEach(item => lines.push(`- ${formatReadableValue(item)}`));
      }
      const unresolved = Array.isArray(value.unresolved_items) ? value.unresolved_items : [];
      if (unresolved.length) {
        lines.push("\\n待确认事项");
        unresolved.forEach(item => lines.push(`- ${formatReadableValue(item)}`));
      }
      lines.push("\\n完整对象路径、坐标和颜色信息已收起，可在下方原始明细中查看。");
      return lines.join("\\n");
    }

    function compareTemplateOptionNames(left, right) {
      const leftMatch = String(left).match(/^(.*?)(\\d+)$/i);
      const rightMatch = String(right).match(/^(.*?)(\\d+)$/i);
      if (leftMatch && rightMatch && leftMatch[1].toLowerCase() === rightMatch[1].toLowerCase()) {
        return Number(leftMatch[2]) - Number(rightMatch[2]);
      }
      return String(left).localeCompare(String(right));
    }

    function formatRawScanEvidence(value) {
      if (!value || typeof value !== "object") return "暂无原始扫描明细";
      const labels = {
        profile: "系统推断类型",
        capabilities: "支持能力",
        groups: "识别到的编组",
        layers: "识别到的图层",
        text_frames: "识别到的文字对象",
        text_objects: "识别到的文字对象",
        fonts: "识别到的字体",
        dimensions: "识别到的尺寸对象",
        assets: "识别到的资产",
        warnings: "扫描提醒",
        unresolved_items: "待确认事项"
      };
      return Object.entries(value).map(([key, item]) => {
        const label = labels[key] || key.replace(/_/g, " ");
        return `${label}：${formatReadableValue(item)}`;
      }).join("\\n");
    }

    function formatFieldSources(value, rules = null) {
      if (!value || typeof value !== "object") return "暂无规则来源记录";
      const labels = {
        "rules.font_options": "字体选项",
        "rules.design_font_options": "独立设计字体",
        "rules.design_options": "设计选项",
        "rules.style_options": "尺寸/版式选项",
        "rules.dimensions": "尺寸规则",
        "rules.text_targets": "文字目标"
      };
      return Object.entries(value).map(([field, details]) => {
        const source = details && typeof details === "object" ? details : {};
        const configured = rules && field.startsWith("rules.") ? rules[field.slice("rules.".length)] : undefined;
        const differs = configured === undefined ? Boolean(source.modified) : !ruleValuesMatch(configured, source.suggestion);
        const status = differs ? "当前配置与系统建议不同" : "当前配置与系统建议一致";
        const suggestion = source.suggestion == null ? "" : `；系统建议：${formatReadableValue(source.suggestion)}`;
        return `${labels[field] || field}：${status}${suggestion}`;
      }).join("\\n");
    }

    function ruleValuesMatch(left, right) {
      return JSON.stringify(left == null ? null : left) === JSON.stringify(right == null ? null : right);
    }

    function formatReadableValue(value) {
      if (Array.isArray(value)) return value.map(item => formatReadableValue(item)).join("、");
      if (value && typeof value === "object") {
        return Object.entries(value).map(([key, item]) => `${key}=${formatReadableValue(item)}`).join("；");
      }
      return String(value == null ? "暂无" : value);
    }

    async function rollbackRuleVersion(version) {
      const templateId = document.getElementById("templateId").value.trim();
      if (!templateId || !window.confirm(`确认回滚到规则版本 v${version}？回滚操作本身也会生成新版本。`)) return;
      try {
        await postJson(`/api/templates/${encodeURIComponent(templateId)}/rules/rollback`, {
          version,
          change_summary: `User rollback to version ${version}`
        });
        await loadTemplateRuleText(formTemplate());
        setMessage("templateSaveMessage", `已回滚到 v${version}，并保留完整版本历史`, "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function restoreRuleSuggestions() {
      const pack = state.templateOnboarding && state.templateOnboarding.draft;
      if (!pack) return;
      const rules = { ...(pack.rules || {}) };
      const sources = (pack.audit && pack.audit.field_sources) || {};
      Object.entries(sources).forEach(([field, details]) => {
        if (!field.startsWith("rules.") || !details || !("suggestion" in details)) return;
        rules[field.slice("rules.".length)] = details.suggestion;
      });
      state.templateRuleBaseConfig = rules;
      fillTemplateRuleFields(rules);
      renderTemplateRulePreview();
      setMessage("templateSaveMessage", "已恢复扫描建议，仍需检查并确认", "");
    }

    function fillTemplateRuleFields(config) {
      state.optionGroupsTouched = false;
      state.assetMappingsTouched = false;
      const savedGroups = Array.isArray(config.option_groups) && config.option_groups.length
        ? config.option_groups
        : legacyOptionGroups(config);
      const groups = mergeScannedOptionGroups(savedGroups, config);
      setOptionGroupRows(groups.map(group => ({
        name: group.name || compactOptionRange(group.options || group.values || []),
        role: group.role || ""
      })));
      setDesignAssetMappingRows(config.asset_mappings || []);

      const fixed = config.dimension_mode === "fixed" && (config.dimensions || {}).Fixed;
      const dimensionRows = Object.entries(config.dimensions || {}).filter(([key]) => !(fixed && key === "Fixed")).map(([key, value]) => {
        const unit = value.unit || "cm";
        const scale = unit === "cm" ? 10 : 1;
        return {
          target: key,
          width: value.width_mm ? trimNumber(Number(value.width_mm) / scale) : "",
          height: value.height_mm ? trimNumber(Number(value.height_mm) / scale) : "",
          unit
        };
      });
      document.getElementById("dimensionMode").value = fixed ? "fixed" : "object";
      document.getElementById("fixedWidth").value = fixed ? trimNumber(Number(fixed.width_mm || 0)) : "";
      document.getElementById("fixedHeight").value = fixed ? trimNumber(Number(fixed.height_mm || 0)) : "";
      setDimensionRows(dimensionRows.length ? dimensionRows : defaultDimensionRows());
      syncDimensionMode();

      fillTextSequenceFields(
        Array.isArray(config.text_sequences) && config.text_sequences.length
          ? config.text_sequences
          : legacyTextSequences(config)
      );

      const defaults = config.defaults || {};
      document.getElementById("defaultFont").value = defaults.font || "";
      document.getElementById("defaultDesign").value = defaults.design || "";
      document.getElementById("defaultStyle").value = defaults.style || "";
      document.getElementById("defaultColor").value = defaults.color || "";
      document.getElementById("outputColorMode").value = (config.output && config.output.color_mode) || "CMYK";

      const overrideEntries = Object.entries(config.option_overrides || {});
      const overrideTargets = Array.from(document.querySelectorAll("[data-override-target]"));
      const overrideActions = Array.from(document.querySelectorAll("[data-override-action]"));
      const overrideValues = Array.from(document.querySelectorAll("[data-override-value]"));
      overrideEntries.slice(0, overrideTargets.length).forEach(([key, value], index) => {
        overrideTargets[index].value = key;
        overrideActions[index].value = value.action || inferOverrideAction(value);
        overrideValues[index].value = value.value || value.color || "";
      });

      document.getElementById("templateAdvancedRules").value = (config.exceptions && config.exceptions.note) || config.raw_text || "";
      document.getElementById("templateExceptionStatus").value = (config.exceptions && config.exceptions.status) || "none";
    }

    function legacyOptionGroups(config) {
      const groups = [];
      if (config.font_options && config.font_options.length) {
        groups.push({ name: compactOptionRange(config.font_options), role: "font_options", options: config.font_options });
      }
      if (config.design_font_options && config.design_font_options.length) {
        groups.push({ name: compactOptionRange(config.design_font_options), role: "design_font_options", options: config.design_font_options });
      }
      if (config.design_options && config.design_options.length) {
        groups.push({ name: compactOptionRange(normalizeOptions(config.design_options)), role: "design_options", options: normalizeOptions(config.design_options) });
      }
      if (config.style_options && config.style_options.length) {
        groups.push({ name: compactOptionRange(config.style_options), role: "style_options", options: config.style_options });
      }
      return groups;
    }

    function mergeScannedOptionGroups(groups, config) {
      const merged = (Array.isArray(groups) ? groups : []).map(group => ({ ...group }));
      const scannedByRole = {
        font_options: normalizeOptions(config.font_options),
        design_font_options: normalizeOptions(config.design_font_options),
        design_options: normalizeOptions(config.design_options),
        style_options: normalizeOptions(config.style_options)
      };
      Object.entries(scannedByRole).forEach(([role, scanned]) => {
        if (!scanned.length) return;
        const index = merged.findIndex(group => group && group.role === role);
        if (index < 0) {
          merged.push({ name: compactOptionRange(scanned), role, options: scanned });
          return;
        }
        const group = merged[index];
        const existing = normalizeOptions(group.options || group.values || expandOptionRange(group.name || ""));
        const options = normalizeOptions([...existing, ...scanned]);
        merged[index] = { ...group, name: compactOptionRange(options), options };
      });
      return merged;
    }

    function fillTextSequenceFields(sequences) {
      const rows = (Array.isArray(sequences) ? sequences : []).map(sequence => ({
        scope: sequence.scope || "",
        field: sequence.field || sequence.source || "",
        delimiter: sequence.delimiter || "",
        variable_prefix: sequence.variable_prefix || inferSequencePrefix(sequence.variables || [sequence.slot || sequence.name || ""]),
        start_index: sequence.start_index || inferSequenceStart(sequence.variables || []) || "",
        count: sequence.count || (Array.isArray(sequence.variables) ? sequence.variables.length : 1)
      }));
      setTextSequenceRows(rows.length ? rows : defaultTextSequenceRows());
    }

    function legacyTextSequences(config) {
      if (Array.isArray(config.text_sequences) && config.text_sequences.length) return config.text_sequences;
      const mappings = Array.isArray(config.slot_mappings) && config.slot_mappings.length
        ? config.slot_mappings
        : legacySlotMappings(config.slots || []);
      return mappings.map(mapping => {
        const slot = mapping.slot || mapping.name || "";
        return {
          scope: mapping.scope || "",
          field: mapping.field || mapping.source || "",
          delimiter: mapping.delimiter || "",
          variable_prefix: inferSequencePrefix([slot]) || slot,
          start_index: inferSequenceStart([slot]),
          count: 1,
          variables: slot ? [slot] : []
        };
      }).filter(item => item.field && item.variables.length);
    }

    function inferSequencePrefix(variables) {
      const first = Array.isArray(variables) && variables.length ? String(variables[0] || "") : "";
      const match = first.match(/^(.+?)(\\d+)$/);
      return match ? match[1] : first;
    }

    function inferSequenceStart(variables) {
      const first = Array.isArray(variables) && variables.length ? String(variables[0] || "") : "";
      const match = first.match(/^.+?(\\d+)$/);
      return match ? Number(match[1]) : null;
    }

    function legacySlotMappings(slots) {
      return (Array.isArray(slots) ? slots : []).map(slot => ({
        field: slot.source || "",
        slot: slot.name || ""
      })).filter(item => item.field && item.slot);
    }

    function compactOptionRange(options) {
      const optionValues = normalizeOptions(options);
      if (!optionValues.length) return "";
      const matches = optionValues.map(value => String(value).match(/^([A-Za-z]+)(\\d+)$/));
      if (matches.every(Boolean)) {
        const prefix = matches[0][1];
        const numbers = matches.map(match => Number(match[2])).sort((left, right) => left - right);
        const contiguous = numbers.every((value, index) => index === 0 || value === numbers[index - 1] + 1);
        if (contiguous && matches.every(match => match[1] === prefix)) {
          return numbers.length === 1 ? `${prefix}${numbers[0]}` : `${prefix}${numbers[0]}-${prefix}${numbers[numbers.length - 1]}`;
        }
      }
      return optionValues.join(" / ");
    }

    function inferOverrideAction(value) {
      if (!value || typeof value !== "object") return "";
      if (value.bold) return "bold";
      if (value.uppercase) return "uppercase";
      if (value.no_width_compress) return "no_width_compress";
      if (value.color) return "fixed_color";
      return value.action || "";
    }

    async function uploadAndScanTemplate() {
      const templateId = document.getElementById("templateId").value.trim();
      const name = document.getElementById("templateName").value.trim();
      const existingTemplate = formTemplate();
      const reference = document.getElementById("referenceAiFile").files[0];
      const primary = document.getElementById("primaryAiFile").files[0];
      const designFontFiles = Array.from(document.getElementById("designFontAiFiles").files || []);
      const assetFiles = Array.from(document.getElementById("assetAiFiles").files || []);
      const hasPendingFiles = Boolean(reference || primary || designFontFiles.length || assetFiles.length);

      if (!templateId || !name) {
        setMessage("templateSaveMessage", "请填写模板 ID 和模板名称", "error");
        return;
      }
      if (!hasPendingFiles) {
        if (existingTemplate) {
          await rescanTemplate();
        } else {
          setMessage("templateSaveMessage", "请至少选择一个 .ai 模板文件", "error");
        }
        return;
      }
      if (existingTemplate && existingTemplate.status === "active") {
        setMessage("templateSaveMessage", "请先停用模板，再上传替换文件", "error");
        return;
      }

      const form = new FormData();
      form.append("template_id", templateId);
      form.append("name", name);
      form.append("template_type", buildTemplateRulePayload().template_type);
      form.append("status", "draft");
      if (reference) form.append("reference_ai", reference);
      if (primary) form.append("template_ai", primary);
      designFontFiles.forEach(file => form.append("design_font_assets", file));
      assetFiles.forEach(file => form.append("template_assets", file));

      let registeredTemplateId = "";
      const uploadStatus = document.getElementById("uploadScanStatus");
      setMessage("templateSaveMessage", "正在保存文件并扫描，请稍候", "");
      if (uploadStatus) uploadStatus.textContent = "正在上传并扫描";
      try {
        const result = await postForm("/api/templates", form);
        registeredTemplateId = result.template.template_id;
        state.selectedTemplateId = registeredTemplateId;
        const scan = await postJson("/api/templates/" + encodeURIComponent(registeredTemplateId) + "/scan", {});
        document.getElementById("referenceAiFile").value = "";
        document.getElementById("primaryAiFile").value = "";
        document.getElementById("designFontAiFiles").value = "";
        document.getElementById("assetAiFiles").value = "";
        await loadTemplates(registeredTemplateId);
        if (!scan.scan_ok) {
          throw new Error("AI 扫描失败，模板保持草稿：" + (scan.scan_error || "未知错误"));
        }
        if (uploadStatus) uploadStatus.textContent = "扫描完成，请核对规则";
        setMessage("templateSaveMessage", "扫描草稿已生成，请核对并修改规则后点击“检查并保存规则”", "ok");
      } catch (error) {
        if (registeredTemplateId) {
          document.getElementById("referenceAiFile").value = "";
          document.getElementById("primaryAiFile").value = "";
          document.getElementById("designFontAiFiles").value = "";
          document.getElementById("assetAiFiles").value = "";
          try {
            await loadTemplates(registeredTemplateId);
          } catch (refreshError) {
            setMessage("templateSaveMessage", String(refreshError.message || refreshError), "error");
            return;
          }
          if (uploadStatus) uploadStatus.textContent = "文件已保存，扫描失败，可重新扫描";
          setMessage(
            "templateSaveMessage",
            "文件已保存为草稿，但扫描未完成：" +
              String(error.message || error) +
              "。可点击“重新扫描已保存文件”继续",
            "error"
          );
        } else {
          if (uploadStatus) uploadStatus.textContent = "上传失败，请检查文件后重试";
          setMessage("templateSaveMessage", String(error.message || error), "error");
        }
      }
    }

    async function saveTemplate() {
      setMessage("templateSaveMessage", "处理中", "");
      const templateId = document.getElementById("templateId").value.trim();
      const name = document.getElementById("templateName").value.trim();
      if (!templateId || !name) {
        setMessage("templateSaveMessage", "请填写模板 ID 和模板名称", "error");
        return;
      }
      if (state.templateRulesDescriptionDirty) {
        setMessage("templateSaveMessage", "补充说明已修改，请先点击“将补充说明生成草稿”", "error");
        return;
      }
      if (!state.templateOnboarding || !state.templateOnboarding.draft) {
        setMessage("templateSaveMessage", "请先点击“上传并扫描 .ai 模板”，扫描完成后再保存规则", "error");
        return;
      }
      const hasPendingFiles = Boolean(
        document.getElementById("referenceAiFile").files[0] ||
        document.getElementById("primaryAiFile").files[0] ||
        document.getElementById("designFontAiFiles").files.length ||
        document.getElementById("assetAiFiles").files.length
      );
      if (hasPendingFiles) {
        setMessage("templateSaveMessage", "检测到尚未上传的 .ai 文件，请先点击“上传并扫描 .ai 模板”", "error");
        return;
      }
      const draft = buildTemplateRulePayload();
      const hasScanDraft = Boolean(state.templateOnboarding && state.templateOnboarding.draft);
      const missing = templateRuleMissingItems(draft);
      if (hasScanDraft && missing.length) {
        state.templateRuleDraft = draft;
        renderTemplateRulePreview();
        setMessage("templateSaveMessage", `规则还不完整：${missing.join("、")}`, "error");
        return;
      }
      let canonicalPack = null;
      if (hasScanDraft) {
        try {
          canonicalPack = buildCanonicalRulePack();
        } catch (error) {
          setMessage("templateSaveMessage", String(error.message || error), "error");
          return;
        }
        if (!(await checkTemplateRule())) return;
      }
      const existingTemplate = formTemplate();
      if (hasScanDraft && existingTemplate && existingTemplate.status === "active") {
        if (name !== existingTemplate.name) {
          setMessage("templateSaveMessage", "请先停用模板，再修改文件或基础信息；规则修改可直接确认", "error");
          return;
        }
        try {
          await postJson(`/api/templates/${encodeURIComponent(templateId)}/rules/confirm`, {
            pack: canonicalPack,
            change_summary: document.getElementById("templateChangeSummary").value.trim()
          });
          await loadTemplates(templateId);
          setMessage("templateSaveMessage", `已发布新规则版本：${templateId}`, "ok");
        } catch (error) {
          setMessage("templateSaveMessage", String(error.message || error), "error");
        }
        return;
      }
      try {
        await postJson(`/api/templates/${encodeURIComponent(templateId)}/rules/confirm`, {
          pack: canonicalPack,
          change_summary: document.getElementById("templateChangeSummary").value.trim()
        });
        await loadTemplates(templateId);
        setMessage("templateSaveMessage", `已确认并启用模板：${templateId}`, "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    function clearTemplateForm() {
      document.getElementById("templateId").value = "";
      document.getElementById("templateName").value = "";
      document.getElementById("referenceAiFile").value = "";
      document.getElementById("primaryAiFile").value = "";
      document.getElementById("designFontAiFiles").value = "";
      document.getElementById("assetAiFiles").value = "";
      state.templateRuleDraft = null;
      state.templateRuleBaseConfig = null;
      state.optionGroupsTouched = false;
      state.dimensionRowsTouched = false;
      state.textSequenceRowsTouched = false;
      document.getElementById("assetRows").innerHTML = '<div class="empty">暂无 .ai 模板资产</div>';
      updateTemplateWorkflowState(false);
      resetTemplateRuleFields();
      renderTemplateRulePreview();
      setMessage("templateSaveMessage", "等待编辑", "");
    }

    function downloadTemplateAsset(assetKey) {
      const template = formTemplate();
      if (!template) {
        setMessage("templateSaveMessage", "请先选择模板", "error");
        return;
      }
      if (assetKey === "primary") {
        window.location.href = `/api/templates/${encodeURIComponent(template.template_id)}/download/template_ai`;
        return;
      }
      window.location.href = `/api/templates/${encodeURIComponent(template.template_id)}/assets/${encodeURIComponent(assetKey)}/download`;
    }

    async function deleteTemplateAsset(assetKey) {
      const template = formTemplate();
      if (!template) return;
      if (assetKey === "primary") {
        const assetName = fileName(template.template_ai) || "尺寸/作图区模板";
        const confirmed = window.confirm(`确认删除文件资产 ${assetName}？\n\n只会移除当前模板中的渲染基准 .ai 登记，不会删除本地 .ai 文件。删除后该模板需要重新上传原始参考模板或尺寸/作图区模板才能渲染。`);
        if (!confirmed) return;
        try {
          await deleteJson(`/api/templates/${encodeURIComponent(template.template_id)}/download/template_ai`);
          await loadTemplates(template.template_id);
          setMessage("templateSaveMessage", `已移除文件资产：${assetName}`, "ok");
        } catch (error) {
          setMessage("templateSaveMessage", String(error.message || error), "error");
        }
        return;
      }
      const asset = (template.assets || [])[Number(assetKey)];
      if (!asset) return;
      const assetName = asset.file_name || fileName(asset.stored_path);
      const confirmed = window.confirm(`确认删除文件资产 ${assetName}？\n\n只会移除当前模板中的资产登记，不会删除本地 .ai 文件。`);
      if (!confirmed) return;
      try {
        await deleteJson(`/api/templates/${encodeURIComponent(template.template_id)}/assets/${encodeURIComponent(assetKey)}`);
        await loadTemplates(template.template_id);
        setMessage("templateSaveMessage", `已移除文件资产：${assetName}`, "ok");
      } catch (error) {
        setMessage("templateSaveMessage", String(error.message || error), "error");
      }
    }

    async function submitRender(dryRun) {
      hideRenderError();
      const file = document.getElementById("orderFile").files[0];
      const templateId = document.getElementById("renderTemplate").value;
      if (!templateId) {
        showRenderError("请先选择要使用的模板。");
        return;
      }
      if (!file) {
        showRenderError("请先上传订单表格。");
        return;
      }
      const payload = new FormData();
      payload.append("template_id", templateId);
      payload.append("order_file", file);
      const sheetName = document.getElementById("sheetName").value.trim();
      if (sheetName) payload.append("sheet_name", sheetName);
      if (dryRun) payload.append("dry_run", "true");
      setTaskRunning(dryRun);
      showProgress(dryRun ? "dryRun" : "render");
      try {
        const result = await postForm("/api/render", payload);
        completeProgress(result.status === "completed");
        renderTaskResult(result);
        await loadJobs();
      } catch (error) {
        failProgress();
        showRenderError(error);
      } finally {
        setRenderButtonsDisabled(false);
      }
    }

    function setTaskRunning(dryRun) {
      setRenderButtonsDisabled(true);
    }

    function setRenderButtonsDisabled(disabled) {
      ["renderBtn"].forEach(id => {
        document.getElementById(id).disabled = disabled;
      });
    }

    function showProgress(mode) {
      progressMode = mode;
      progressValue = 0;
      const overlay = document.getElementById("renderProgressOverlay");
      overlay.classList.add("active");
      overlay.setAttribute("aria-hidden", "false");
      document.getElementById("progressTitle").textContent = progressTitle(mode);
      document.getElementById("progressSubtitle").textContent = progressSubtitle(mode);
      renderProgressSteps(0);
      updateRenderProgress(6, progressStages()[0]);
      clearInterval(progressTimer);
      progressTimer = setInterval(tickProgress, 900);
    }

    function tickProgress() {
      const cap = progressCap();
      const next = Math.min(cap, progressValue + progressIncrement(progressValue));
      updateRenderProgress(next, stageForProgress(next));
    }

    function progressTitle(mode) {
      if (mode === "dryRun") return "正在解析订单";
      return "正在生成效果图";
    }

    function progressSubtitle(mode) {
      if (mode === "dryRun") return "正在检查字段、分组和渲染任务";
      return "Illustrator 正在生成 AI 文件，请不要关闭软件";
    }

    function progressCap() {
      if (progressMode === "dryRun") return 88;
      return 96;
    }

    function progressIncrement(value) {
      if (progressMode === "render") {
        if (value < 24) return 8;
        if (value < 46) return 5;
        if (value < 68) return 3;
        return 1;
      }
      if (value < 28) return 9;
      if (value < 58) return 6;
      if (value < 78) return 3;
      return 1;
    }

    function progressStages() {
      if (progressMode === "dryRun") {
        return ["上传订单表格", "解析订单字段", "生成 render task", "等待返回结果"];
      }
      return ["上传订单表格", "解析订单字段", "调用 Illustrator", "生成 AI 文件", "完成收尾"];
    }

    function stageForProgress(value) {
      const stages = progressStages();
      if (progressMode === "dryRun") {
        if (value < 28) return stages[0];
        if (value < 58) return stages[1];
        if (value < 82) return stages[2];
        return stages[3];
      }
      if (value < 18) return stages[0];
      if (value < 36) return stages[1];
      if (value < 52) return stages[2];
      if (value < 98) return stages[3];
      return stages[4];
    }

    function updateRenderProgress(value, stage) {
      progressValue = Math.max(0, Math.min(100, Math.round(value)));
      document.getElementById("progressBar").style.width = `${progressValue}%`;
      document.getElementById("progressPercent").textContent = `${progressValue}%`;
      document.getElementById("progressStage").textContent = stage;
      renderProgressSteps(progressValue);
    }

    function renderProgressSteps(value) {
      const current = stageForProgress(value);
      const stages = progressStages();
      const target = document.getElementById("progressSteps");
      target.innerHTML = stages.map(stage => {
        const done = stages.indexOf(stage) < stages.indexOf(current);
        const active = stage === current;
        return `<li class="${done ? "done" : ""} ${active ? "active" : ""}">${escapeHtml(stage)}</li>`;
      }).join("");
    }

    function completeProgress(success) {
      clearInterval(progressTimer);
      progressTimer = null;
      updateRenderProgress(success ? 100 : progressValue, success ? "处理完成" : "处理失败");
      if (success) {
        setTimeout(hideRenderProgress, 550);
      } else {
        setTimeout(hideRenderProgress, 900);
      }
    }

    function failProgress() {
      clearInterval(progressTimer);
      progressTimer = null;
      updateRenderProgress(progressValue || 100, "处理失败");
      setTimeout(hideRenderProgress, 900);
    }

    function hideRenderProgress() {
      const overlay = document.getElementById("renderProgressOverlay");
      overlay.classList.remove("active");
      overlay.setAttribute("aria-hidden", "true");
    }

    function showRenderError(error) {
      const message = explainRenderError(error);
      document.getElementById("renderErrorText").textContent = message;
      const overlay = document.getElementById("renderErrorOverlay");
      overlay.classList.add("active");
      overlay.setAttribute("aria-hidden", "false");
    }

    function hideRenderError() {
      const overlay = document.getElementById("renderErrorOverlay");
      overlay.classList.remove("active");
      overlay.setAttribute("aria-hidden", "true");
    }

    function explainRenderError(error) {
      const raw = String(error && error.message ? error.message : error || "").trim();
      const text = raw.toLowerCase();
      if (!raw) {
        return "生成效果图失败。请检查模板、订单表格和规则配置后再试一次。";
      }
      if (/^(请|系统|当前|模板|订单|Illustrator|生成)/.test(raw)) {
        return raw;
      }
      if (/font config not found|missing font|字体|font/.test(text)) {
        return "模板缺少本次订单需要的字体样本或字体规则。请在模板管理中检查字体组是否完整，再重新生成。";
      }
      if (/template|模板|rule|规则|config|配置/.test(text)) {
        return "当前模板的文件或规则还没有配置完整。请先到模板管理中检查模板文件、尺寸框和规则配置。";
      }
      if (/order|excel|csv|sheet|表格|工作表|字段/.test(text)) {
        return "订单表格无法正确读取。请确认文件格式、工作表名称和表格字段是否正确。";
      }
      if (/illustrator|com|ai file|ai 文件|render|渲染/.test(text)) {
        return "Illustrator 没有成功生成效果图。请确认 Illustrator 可以正常打开，模板文件没有被占用，然后再试一次。";
      }
      return `生成效果图失败。${cleanErrorText(raw)}`;
    }

    function cleanErrorText(value) {
      return String(value || "")
        .replace(/^Error:\\s*/i, "")
        .replace(/\\s+/g, " ")
        .slice(0, 180);
    }

    function renderTaskResult(result) {
      if (result.status === "completed" && result.outputs && result.outputs.output_ai) {
        window.location.href = `/api/jobs/${encodeURIComponent(result.job_id)}/download/output_ai`;
      } else if (result.status === "completed" && result.outputs && result.outputs.render_task) {
        window.location.href = `/api/jobs/${encodeURIComponent(result.job_id)}/download/render_task`;
      } else if (result.status === "failed") {
        showRenderError(result.error || "渲染失败");
      } else {
        showRenderError("系统没有返回可下载的效果图，请检查模板和订单表格后重试。");
      }
    }

    function resetTaskResult() {
      document.getElementById("orderFile").value = "";
      document.getElementById("sheetName").value = "";
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
          <div class="preview-chip"><span>默认色彩模式</span><strong>${escapeHtml(requirements.default_output_color_mode || "CMYK")}</strong></div>
          <div class="preview-chip"><span>转曲要求</span><strong>${escapeHtml(requirements.must_outline_text ? "需要" : "未声明")}</strong></div>
          <div class="preview-chip"><span>合并去重</span><strong>${escapeHtml(requirements.must_pathfinder_merge ? "需要" : "未声明")}</strong></div>
          <div class="preview-chip"><span>部门输出规则</span><strong>${escapeHtml(`${outputs.length} 条`)}</strong></div>
        </div>
      `;
    }

    function describeDefaults(defaults) {
      const parts = [];
      if (defaults.color) parts.push(`颜色 ${defaults.color}`);
      if (defaults.design) parts.push(`设计 ${defaults.design}`);
      if (defaults.font) parts.push(`字体 ${defaults.font}`);
      if (defaults.title) parts.push(`标题 ${defaults.title}`);
      return parts.join("；") || "无默认值";
    }

    function trimNumber(value) {
      return Number(value.toFixed(3)).toString();
    }

    function displayOptions(values) {
      const options = normalizeOptions(values);
      return options.length ? options.join(" / ") : "未识别";
    }

    function normalizeOptions(values) {
      const result = [];
      const add = value => {
        const text = optionText(value);
        if (text && !result.includes(text)) result.push(text);
      };
      if (Array.isArray(values)) {
        values.forEach(add);
      } else if (values && typeof values === "object") {
        ["design_font_options", "font_options", "style_options", "options"].forEach(key => {
          if (Array.isArray(values[key])) values[key].forEach(add);
        });
        if (!result.length) {
          Object.keys(values).forEach(key => add(key));
        }
      } else {
        add(values);
      }
      return result;
    }

    function optionText(value) {
      if (value === undefined || value === null || value === "") return "";
      if (typeof value !== "object") return String(value).trim();
      const keys = [
        "id",
        "value",
        "name",
        "code",
        "key",
        "option",
        "font_option",
        "fontOption",
        "style_option",
        "styleOption",
        "design_option",
        "designOption",
        "font",
        "label",
        "display_name"
      ];
      for (const key of keys) {
        if (value[key] !== undefined && value[key] !== null && value[key] !== "") {
          return String(value[key]).trim();
        }
      }
      const objectKeys = Object.keys(value);
      return objectKeys.length === 1 ? objectKeys[0] : "";
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

    async function deleteJson(url, body = null) {
      const options = { method: "DELETE" };
      if (body) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
      }
      const response = await fetch(url, options);
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

    function displayTemplateAiRole(template) {
      const role = template && template.template_ai_role ? template.template_ai_role : "尺寸/作图区模板";
      return role === "原始参考模板" ? "原始参考模板（渲染基准）" : role;
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
      if (!target) return;
      target.className = `message ${stateName || ""}`.trim();
      target.textContent = text;
    }

    init().catch(error => {
      showRenderError(error);
    });
  </script>
</body>
</html>
"""
