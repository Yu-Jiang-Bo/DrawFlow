"""Head and header markup for the V2 template workbench."""

PAGE_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DrawFlow · V2 模板配置工作台</title>
  <link rel="stylesheet" href="/static/v2-workbench/workbench.css" />
  <link rel="stylesheet" href="/static/v2-workbench/workbench-stages.css" />
  <script src="/static/v2-workbench/workbench.js" defer></script>
  <script src="/static/v2-workbench/workbench-dom.js" defer></script>
  <script src="/static/v2-workbench/workbench-api.js" defer></script>
  <script src="/static/v2-workbench/workbench-scan-model.js" defer></script>
  <script src="/static/v2-workbench/workbench-form-model.js" defer></script>
  <script src="/static/v2-workbench/workbench-config.js" defer></script>
  <script src="/static/v2-workbench/workbench-content.js" defer></script>
  <script src="/static/v2-workbench/workbench-style-dimensions.js" defer></script>
  <script src="/static/v2-workbench/workbench-option-rules.js" defer></script>
  <script src="/static/v2-workbench/workbench-rule-evidence.js" defer></script>
  <script src="/static/v2-workbench/workbench-stage-view.js" defer></script>
  <script src="/static/v2-workbench/workbench-preview-state.js" defer></script>
  <script src="/static/v2-workbench/workbench-preview-versions.js" defer></script>
  <script src="/static/v2-workbench/workbench-preview.js" defer></script>
  <script src="/static/v2-workbench/workbench-preview-actions.js" defer></script>
  <script src="/static/v2-workbench/workbench-view-tables.js" defer></script>
  <script src="/static/v2-workbench/workbench-validation-checks.js" defer></script>
  <script src="/static/v2-workbench/workbench-validation-targets.js" defer></script>
  <script src="/static/v2-workbench/workbench-validation-navigation.js" defer></script>
  <script src="/static/v2-workbench/workbench-validation-blockers.js" defer></script>
  <script src="/static/v2-workbench/workbench-view.js" defer></script>
  <script src="/static/v2-workbench/workbench-structure-tree.js" defer></script>
  <script src="/static/v2-workbench/workbench-draft-actions.js" defer></script>
  <script src="/static/v2-workbench/workbench-published-actions.js" defer></script>
  <script src="/static/v2-workbench/workbench-scan-actions.js" defer></script>
</head>
<body>
  <div class="v2-desktop-frame">
    <aside class="v2-desktop-sidebar" aria-label="DrawFlow 主导航">
      <a class="v2-sidebar-brand" href="/" aria-label="返回 DrawFlow 出图任务">
        <strong>DrawFlow</strong>
        <span>订单效果图与 V2 工作台</span>
      </a>
      <p class="v2-sidebar-label">工作台</p>
      <nav class="v2-nav v2-desktop-nav" aria-label="主导航">
        <a href="/" data-nav-target="render-tasks">出图任务</a>
        <a href="/v2/templates/workbench" data-nav-target="v2-workbench" aria-current="page">V2 工作台</a>
        <a href="/?page=jobs" data-nav-target="jobs">任务记录</a>
      </nav>
      <div class="v2-sidebar-note"><span></span>模板与渲染均受控处理</div>
    </aside>
    <div class="v2-desktop-main">
      <header class="v2-header">
        <div class="v2-header-inner">
          <div class="v2-brand">
            <h1>V2 工作台</h1>
            <p>模板配置与发布流程</p>
          </div>
          <div class="v2-health-group" aria-live="polite" aria-label="服务状态">
            <span id="v2LocalHealthText" class="v2-service-status is-busy">本机检查中</span>
            <span id="v2CentralHealthText" class="v2-service-status is-busy">中央服务连接中</span>
          </div>
        </div>
      </header>
"""
