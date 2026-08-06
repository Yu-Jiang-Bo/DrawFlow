"""Static HTML for the V2 template configuration workbench."""

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DrawFlow · V2 模板配置工作台</title>
  <link rel="stylesheet" href="/static/v2-workbench/workbench.css" />
  <script src="/static/v2-workbench/workbench.js" defer></script>
  <script src="/static/v2-workbench/workbench-dom.js" defer></script>
  <script src="/static/v2-workbench/workbench-api.js" defer></script>
  <script src="/static/v2-workbench/workbench-scan-model.js" defer></script>
  <script src="/static/v2-workbench/workbench-form-model.js" defer></script>
  <script src="/static/v2-workbench/workbench-config.js" defer></script>
  <script src="/static/v2-workbench/workbench-content.js" defer></script>
  <script src="/static/v2-workbench/workbench-view.js" defer></script>
  <script src="/static/v2-workbench/workbench-draft-actions.js" defer></script>
  <script src="/static/v2-workbench/workbench-scan-actions.js" defer></script>
</head>
<body>
  <header class="v2-header">
    <div class="v2-header-inner">
      <div class="v2-brand">
        <h1>DrawFlow</h1>
        <p>订单效果图与模板管理</p>
      </div>
      <nav class="v2-nav" aria-label="主导航">
      <a href="/" data-nav-target="render-tasks">出图任务</a>
      <a href="/templates" data-nav-target="templates">模板管理</a>
      <a href="/v2/templates/workbench" data-nav-target="v2-workbench" aria-current="page">V2 工作台</a>
      <a href="/rules" data-nav-target="rules">规则配置</a>
      <a href="/jobs" data-nav-target="jobs">任务记录</a>
      </nav>
      <span class="v2-service-status">服务就绪</span>
    </div>
  </header>

  <main class="v2-shell" id="v2WorkbenchApp">
    <section class="v2-title-row" aria-labelledby="v2PageTitle">
      <div>
        <p class="v2-section-kicker">模板管理 / 独立入口</p>
        <h2 id="v2PageTitle">V2 模板配置工作台</h2>
      </div>
      <div class="v2-title-status" aria-label="当前模板状态">
        <span id="currentTemplateContext" class="v2-title-context">未选择模板</span>
        <span id="draftStatusBadge" class="v2-badge">草稿</span>
        <span id="draftVersion" class="v2-badge v2-badge-muted">v0</span>
      </div>
    </section>

    <section class="check-rail" id="v2CheckRail" aria-label="八项待确认">
      <button class="check-item" type="button" data-check-key="output">
        <span>Output 结构确认</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="fields">
        <span>订单字段绑定</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="options">
        <span>订单原值映射</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="slots">
        <span>槽位必填状态</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="content">
        <span>内容处理预设</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="dimensions">
        <span>尺寸/边界</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="colors">
        <span>颜色/字体</span>
        <strong>待确认</strong>
      </button>
      <button class="check-item" type="button" data-check-key="preview">
        <span>样例预览</span>
        <strong>待确认</strong>
      </button>
    </section>

    <div class="workspace-grid">
      <aside class="left-pane" aria-label="模板与扫描结构">
        <section class="pane">
          <div class="pane-header">
            <h3>模板列表</h3>
          </div>
          <div class="pane-body">
            <label for="templateSearch">搜索模板</label>
            <input id="templateSearch" type="search" placeholder="输入模板 ID 或名称" autocomplete="off" />
            <div class="v2-list" id="templateList" aria-live="polite"></div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>上传与扫描</h3>
          </div>
          <div class="pane-body">
            <div class="upload-zone" id="aiDropzone">
              <input id="aiFile" type="file" accept=".ai" />
              <p>拖放或选择 .ai 模板文件</p>
              <small>扫描后生成结构摘要，可重新扫描并恢复未发布草稿。</small>
            </div>
            <div class="v2-action-row">
              <button id="scanTemplateBtn" type="button">开始扫描</button>
              <button id="rescanTemplateBtn" type="button">重新扫描</button>
              <button id="cancelScanBtn" type="button">取消</button>
            </div>
            <div class="v2-progress" id="scanProgress" aria-live="polite" aria-label="扫描进度"></div>
            <div class="v2-summary" id="scanSummary" aria-live="polite"></div>
            <div class="v2-empty" id="scanEmptyState">尚未扫描模板，请先上传 .ai 文件。</div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>扫描结构</h3>
          </div>
          <div class="pane-body">
            <label for="structureSearch">搜索结构</label>
            <input id="structureSearch" type="search" placeholder="Output、Style、Design、Font、slot..." autocomplete="off" />
            <div class="v2-filter-row">
              <button id="toggleDesignsBtn" type="button">展开 Design</button>
              <button id="toggleFontsBtn" type="button">展开 Font</button>
            </div>
            <div class="structure-tree" id="structureTree" aria-live="polite">
              <section data-node-group="Output">
                <h4>Output</h4>
                <p>单 Output_main 显示为“主效果图”；多 Output 需确认中文部件名、用途和连续 Side 顺序。</p>
              </section>
              <section data-node-group="Style"><h4>Style</h4></section>
              <section data-node-group="Design"><h4>Design</h4></section>
              <section data-node-group="Font"><h4>Font</h4></section>
              <section data-node-group="slot"><h4>slot</h4></section>
              <section data-node-group="anchor"><h4>anchor</h4></section>
              <section data-node-group="tail"><h4>tail</h4></section>
              <section data-node-group="Assets"><h4>Assets</h4></section>
              <section data-node-group="Colors"><h4>Colors</h4></section>
            </div>
          </div>
        </section>
      </aside>

      <section class="center-pane" aria-label="当前配置">
        <section class="pane">
          <div class="pane-header">
            <h3>模板草稿</h3>
          </div>
          <div class="pane-body field-grid draft-field-grid">
            <label>
              <span>模板 ID</span>
              <input id="templateId" name="template_id" type="text" placeholder="例如 JJMB202608060001" autocomplete="off" />
            </label>
            <label>
              <span>模板名称</span>
              <input id="templateName" name="template_name" type="text" placeholder="输入中文模板名称" autocomplete="off" />
            </label>
            <label>
              <span>店铺</span>
              <input id="shopName" name="shop_name" type="text" placeholder="选填" autocomplete="off" />
            </label>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>Output 配置</h3>
          </div>
          <div class="pane-body">
            <div class="config-table" id="outputConfigRows" aria-live="polite"></div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>订单字段绑定</h3>
          </div>
          <div class="pane-body">
            <p class="v2-help">使用输入框或下拉框绑定英文订单表头到 Design、Font、Style、Color 和 slot。</p>
            <div class="config-table" id="fieldBindingRows" aria-live="polite"></div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>订单原值映射</h3>
          </div>
          <div class="pane-body">
            <p class="v2-help">支持将订单原值 03 映射为 Design03，将 F10 映射为 F10。</p>
            <div class="config-table" id="optionMappingRows" aria-live="polite"></div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>逐选项内容处理</h3>
          </div>
          <div class="pane-body">
            <p class="v2-help">每个具体 Design/F 单独选择内容处理方式；每个 slot 单独设置内容来源、业务渲染类型和必填状态。</p>
            <div class="content-option-list" id="contentOptionRows" aria-live="polite"></div>
          </div>
        </section>
      </section>

      <aside class="right-pane" aria-label="核验状态与上下文摘要">
        <section class="pane">
          <div class="pane-header">
            <h3>发布阻断</h3>
          </div>
          <div class="pane-body">
            <ul class="v2-blockers" id="blockerList" aria-live="polite"></ul>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>草稿摘要</h3>
          </div>
          <div class="pane-body">
            <div class="v2-summary" id="draftSummary">暂无草稿变更。</div>
          </div>
        </section>

        <section class="pane">
          <div class="pane-header">
            <h3>扫描事实</h3>
          </div>
          <div class="pane-body">
            <div class="v2-summary" id="selectedNodeSummary">请选择左侧结构节点查看上下文。</div>
          </div>
        </section>
      </aside>
    </div>

    <footer class="bottom-action-bar" aria-label="底部操作栏">
      <div class="v2-publish-state">
        <strong>发布状态</strong>
        <span id="publishBlockerText">完成八项确认后可发布新版本。</span>
      </div>
      <div class="v2-bottom-actions">
        <button id="saveDraftBtn" type="button">保存草稿</button>
        <button id="trialRenderBtn" type="button">使用样例试渲染</button>
        <button id="publishVersionBtn" type="button" disabled>发布新版本</button>
      </div>
    </footer>
  </main>

  <div class="modal-overlay" id="scanFailedOverlay" role="alertdialog" aria-modal="true" aria-labelledby="scanFailedTitle" aria-describedby="scanFailedMessage" hidden>
    <section class="modal-dialog">
      <header>
        <h2 id="scanFailedTitle">扫描失败</h2>
      </header>
      <section class="modal-body">
        <p id="scanFailedMessage">扫描没有完成，请检查模板文件后重试。</p>
      </section>
      <footer>
        <button id="retryScanBtn" type="button">重试扫描</button>
        <button id="closeScanFailedBtn" type="button">关闭</button>
      </footer>
    </section>
  </div>
</body>
</html>
"""
