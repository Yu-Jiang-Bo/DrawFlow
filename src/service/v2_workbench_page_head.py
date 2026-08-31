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
  <header class="v2-header">
    <div class="v2-header-inner">
      <div class="v2-brand">
        <h1>DrawFlow</h1>
        <p>订单效果图与 V2 模板工作台</p>
      </div>
      <nav class="v2-nav" aria-label="主导航">
      <a href="/" data-nav-target="render-tasks">出图任务</a>
      <a href="/v2/templates/workbench" data-nav-target="v2-workbench" aria-current="page">V2 工作台</a>
      <a href="/jobs" data-nav-target="jobs">任务记录</a>
      </nav>
      <span class="v2-service-status">服务就绪</span>
    </div>
  </header>
"""
