"""Primary upload and structure markup for the V2 template workbench."""

PAGE_MAIN = """
  <main class="v2-shell" id="v2WorkbenchApp" data-workbench-stage="upload">
    <section class="v2-title-row" aria-labelledby="v2PageTitle">
      <div>
        <p class="v2-section-kicker">模板管理 / 独立入口</p>
        <h2 id="v2PageTitle">V2 模板配置工作台</h2>
        <p class="v2-title-copy">上传已按规范标注的 Illustrator 模板，完成扫描、核验、试渲染和版本发布。</p>
      </div>
      <div class="v2-title-status" aria-label="当前模板状态">
        <button id="backToUploadBtn" class="stage-back-btn" type="button" hidden>上一步</button>
        <span id="currentTemplateContext" class="v2-title-context">未选择模板</span>
        <span id="draftStatusBadge" class="v2-badge">草稿</span>
        <span id="draftVersion" class="v2-badge v2-badge-muted">v0</span>
      </div>
    </section>

    <section class="check-rail" id="v2CheckRail" aria-label="八项待确认">
      <button class="check-item" type="button" data-check-key="output"><span>Output 结构确认</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="fields"><span>订单字段绑定</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="options"><span>订单原值映射</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="slots"><span>槽位必填状态</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="content"><span>内容处理预设</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="dimensions"><span>尺寸/边界</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="colors"><span>颜色/字体</span><strong>待确认</strong></button>
      <button class="check-item" type="button" data-check-key="preview"><span>样例预览</span><strong>待确认</strong></button>
    </section>

    <div class="workspace-grid">
      <aside class="left-pane template-list-pane" data-stage-panel="upload" aria-label="当前模板列表">
        <section class="pane">
          <div class="pane-header"><h3>模板列表</h3><button id="newTemplateBtn" class="primary compact-btn" type="button">新增模板</button></div>
          <div class="pane-body">
            <label for="templateSearch">搜索模板</label>
            <input id="templateSearch" type="search" placeholder="输入模板 ID 或名称" autocomplete="off" />
            <div class="v2-list" id="templateList" aria-live="polite"></div>
            <div class="template-list-stats" id="templateListStats" aria-live="polite"></div>
          </div>
        </section>
      </aside>

      <section class="upload-pane" data-stage-panel="upload" aria-label="上传与扫描">
        <section class="pane">
          <div class="pane-header"><h3>模板草稿</h3></div>
          <div class="pane-body field-grid draft-field-grid">
            <label><span>模板 ID（创建后固定）</span><input id="templateId" name="template_id" type="text" placeholder="例如 JJMB202608060001" autocomplete="off" /></label>
            <label><span>模板名称</span><input id="templateName" name="template_name" type="text" placeholder="输入中文模板名称" autocomplete="off" /></label>
            <label><span>店铺</span><input id="shopName" name="shop_name" type="text" placeholder="选填" autocomplete="off" /></label>
          </div>
        </section>
        <section class="pane upload-scan-pane">
          <div class="pane-header"><h3>上传并扫描模板</h3><span class="v2-badge v2-badge-muted" id="uploadScanBadge">等待文件</span></div>
          <div class="pane-body upload-scan-grid">
            <div class="upload-zone" id="aiDropzone">
              <input id="aiFile" type="file" accept=".ai" />
              <p>拖入已标注的 .ai 模板</p><small>或点击选择文件，系统调用本机 Illustrator 扫描</small>
              <button class="dropzone-file-button" type="button" tabindex="-1">重新选择文件</button>
            </div>
            <div class="scan-flow-panel">
              <h4>扫描流程</h4><div class="v2-progress" id="scanProgress" aria-live="polite" aria-label="扫描进度"></div>
              <div class="v2-action-row"><button id="scanTemplateBtn" class="primary" type="button">上传并扫描</button><button id="rescanTemplateBtn" type="button">重新扫描已保存文件</button></div>
            </div>
          </div>
        </section>
        <section class="pane scan-summary-pane">
          <div class="pane-header"><h3>扫描摘要</h3><span class="muted">只展示 Template 下规范结构</span></div>
          <div class="pane-body">
            <div class="scan-metric-grid" id="scanSummaryMetrics" aria-live="polite"></div>
            <div class="v2-warning-note" id="scanSummaryWarning">等待扫描结果。完成扫描后先核对规范标注字段，再进入结构与字段核验。</div>
            <div class="scan-summary-footer"><div class="v2-summary" id="scanSummary" aria-live="polite"></div><button id="enterStructureBtn" class="primary" type="button">进入结构与字段核验</button></div>
            <div class="v2-empty" id="scanEmptyState">尚未扫描模板，请先上传 .ai 文件。</div>
          </div>
        </section>
      </section>

      <aside class="left-pane structure-pane" data-stage-panel="structure" aria-label="扫描结构">
        <section class="pane">
          <div class="pane-header"><h3>扫描结构</h3></div>
          <div class="pane-body">
            <label for="structureSearch">搜索结构</label><input id="structureSearch" type="search" placeholder="筛选 Output、选项或槽位" autocomplete="off" />
            <div class="v2-filter-row"><button id="toggleDesignsBtn" type="button">展开全部设计</button><button id="toggleFontsBtn" type="button">展开全部字体</button></div>
            <div class="structure-tree" id="structureTree" aria-live="polite">
              <section data-node-group="Output"><h4>Output</h4><p>单 Output_main 显示为“主效果图”；多 Output 需确认中文部件名、用途和连续 Side 顺序。</p></section>
              <section data-node-group="Style"><h4>Style</h4></section><section data-node-group="Design"><h4>Design</h4></section>
              <section data-node-group="Font"><h4>Font</h4></section><section data-node-group="slot"><h4>slot</h4></section>
              <section data-node-group="anchor"><h4>anchor</h4></section><section data-node-group="tail"><h4>tail</h4></section>
              <section data-node-group="Assets"><h4>Assets</h4></section><section data-node-group="Colors"><h4>Colors</h4></section>
            </div>
          </div>
        </section>
      </aside>

      <section class="center-pane" data-stage-panel="structure" aria-label="结构与字段配置">
        <section class="pane"><div class="pane-header"><h3>Output 配置</h3></div><div class="pane-body"><div class="config-table" id="outputConfigRows" aria-live="polite"></div></div></section>
        <section class="pane output-policy-panel"><div class="pane-header"><h3>输出处理</h3><span class="v2-badge output-policy-badge">模板输出设置</span></div><div class="pane-body output-policy-body">
          <p class="output-policy-description">对定制内容和生产标注生效</p>
          <label class="output-policy-row">
            <span class="output-policy-copy"><span class="output-policy-title">文字转曲</span><span class="output-policy-note">保存前将成品画布中的文字转换为轮廓</span></span>
            <input id="outlineTextToggle" class="output-policy-toggle" type="checkbox" checked role="switch" aria-label="文字转曲" />
            <span class="output-policy-switch" aria-hidden="true"></span>
          </label>
          <label class="output-policy-row">
            <span class="output-policy-copy"><span class="output-policy-title">文字去重</span><span class="output-policy-note">转曲后合并重叠轮廓</span></span>
            <input id="pathfinderMergeToggle" class="output-policy-toggle" type="checkbox" checked role="switch" aria-label="文字去重" />
            <span class="output-policy-switch" aria-hidden="true"></span>
          </label>
          <p class="output-policy-fallback">未设置时，按生产部门默认规则处理</p>
        </div></section>
        <section class="pane"><div class="pane-header"><h3>订单字段绑定</h3></div><div class="pane-body"><p class="v2-help">将扫描到的模板对象绑定到订单表头；多个槽位可以共用同一个订单字段。</p><div class="config-table" id="fieldBindingRows" aria-live="polite"></div></div></section>
        <section class="pane"><div class="pane-header"><h3>订单原值映射</h3></div><div class="pane-body"><p class="v2-help">将订单中的设计、字体或颜色值映射到扫描到的模板选项；单 Output 默认使用 Output_main。</p><div class="config-table" id="optionMappingRows" aria-live="polite"></div></div></section>
        <section class="pane"><div class="pane-header"><h3>Style 与尺寸验收</h3><span class="muted">误差上限 0.007mm，禁止超出</span></div><div class="pane-body"><div class="config-table" id="styleDimensionRows" aria-live="polite"></div></div></section>
      </section>

      <aside class="right-pane" data-stage-panel="structure" aria-label="核验状态与上下文摘要">
        <section class="pane"><div class="pane-header"><h3>发布阻断</h3></div><div class="pane-body"><ul class="v2-blockers" id="blockerList" aria-live="polite"></ul></div></section>
        <section class="pane"><div class="pane-header"><h3>草稿摘要</h3></div><div class="pane-body"><div class="v2-summary" id="draftSummary">暂无草稿变更。</div></div></section>
        <section class="pane"><div class="pane-header"><h3>扫描事实</h3></div><div class="pane-body"><div class="v2-summary" id="selectedNodeSummary">请选择左侧结构节点查看上下文。</div></div></section>
      </aside>
"""
