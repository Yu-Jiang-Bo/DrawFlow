"""Rules, preview, actions, and dialogs for the V2 template workbench."""

PAGE_FINISH = """
      <aside class="left-pane option-rules-list-pane" data-stage-panel="rules" aria-label="选项列表">
        <section class="pane"><div class="pane-header"><h3>选项列表</h3><span class="muted" id="optionRuleCount">0 项</span></div>
          <div class="pane-body"><label for="optionRuleSearch">搜索 Design 或 F</label><input id="optionRuleSearch" type="search" placeholder="Design08 或 F2" autocomplete="off" />
            <div class="option-rule-list" id="optionRuleList" aria-live="polite"></div><div class="option-rule-stats" id="optionRuleStats"></div><button id="pendingOnlyBtn" type="button">仅显示待处理选项</button></div>
        </section>
      </aside>
      <section class="center-pane option-rules-editor-pane" data-stage-panel="rules" aria-label="选项渲染规则">
        <section class="pane"><div class="pane-header"><h3 id="selectedOptionTitle">Design08 · 双素材组合设计</h3><span class="v2-badge v2-badge-muted" id="selectedOptionPendingBadge">待确认</span></div>
          <div class="pane-body option-rule-editor"><div class="option-rule-controls"><label><span>内容处理预设</span><select id="optionContentPreset"></select></label></div>
            <p class="v2-help" id="optionProcessingHelp">系统会按当前处理方式推荐槽位处理。</p><h4>槽位要求</h4><p class="v2-help">每个槽位的内容来源、处理方式和必填状态都可以分别确认。</p>
            <div class="content-option-list" id="contentOptionRows" aria-live="polite"></div><h4>素材库绑定</h4><div class="asset-binding-list" id="assetBindingRows" aria-live="polite"></div></div>
        </section>
      </section>
      <aside class="right-pane option-capability-pane" data-stage-panel="rules" aria-label="模板能力与依赖">
        <section class="pane"><div class="pane-header"><h3>模板能力与依赖</h3></div><div class="pane-body" id="templateCapabilityPanel">
          <div class="capability-tags"><span>双素材库</span><span>可替换文本</span><span>尺寸边界</span></div><div class="capability-evidence" id="capabilityEvidenceRows"></div>
          <h4 id="colorRuleTitle">颜色规则</h4><div class="capability-evidence" id="colorRuleRows"></div><h4>尺寸边界</h4><div class="capability-evidence" id="dimensionRuleRows"></div>
          <h4>字体依赖</h4><div class="capability-evidence" id="fontDependencyRows"></div></div></section>
      </aside>

      <section class="preview-stage-pane" data-stage-panel="preview" aria-label="样例预览与发布">
        <section class="pane preview-main-pane"><div class="pane-header"><h3>样例订单与真实效果图</h3><span class="v2-badge v2-badge-muted" id="previewRuntimeBadge">未试渲染</span></div>
          <div class="pane-body"><p class="v2-help">样例字段来自当前模板实际使用的订单字段。修改后请重新试渲染，系统会先保存草稿，再调用正式渲染链路。</p>
            <div class="preview-sample-grid" id="previewSampleRows"></div><div class="preview-side-tabs" id="previewSideTabs" hidden></div>
            <div class="preview-artwork-layout"><div class="preview-artwork-pane" id="previewArtworkPane"><div class="empty-state">尚未执行样例试渲染。</div></div>
              <div class="preview-side-summary"><div class="preview-trial-status" id="previewTrialStatus">填写样例订单数据后开始试渲染。</div><div class="preview-warning-list" id="previewWarningList"></div>
                <button id="rerunTrialRenderBtn" class="primary" type="button" disabled>使用当前数据试渲染</button></div></div></div>
        </section>
        <section class="pane preview-validation-pane"><div class="pane-header"><h3>核验结果</h3><span class="stage-status-pill warn" id="previewValidationStatus">未试渲染</span></div>
          <div class="pane-body"><div class="preview-validation-callout">与正式订单共用 Illustrator 渲染链路</div><div id="previewValidationRows" class="preview-validation-list"></div></div></section>
        <section class="pane version-publish-panel" id="versionPublishPanel"><div class="pane-header"><h3>版本与发布</h3><span class="stage-status-pill warn" id="versionPublishStatus">等待发布核验</span></div>
          <div class="pane-body version-publish-grid"><div><span class="muted">当前草稿</span><strong id="draftVersionSummary">尚未选择草稿</strong><small id="draftTrialSummary">未试渲染</small></div>
            <div><span class="muted">当前正式版</span><strong id="currentVersionSummary">尚未发布正式版本</strong><small id="currentVersionMeta"></small></div>
            <div><span class="muted">上一回滚版</span><strong id="rollbackVersionSummary">暂无可回滚版本</strong><small id="rollbackVersionMeta"></small></div>
            <label><span>发布说明</span><input id="publishNotes" type="text" placeholder="说明本次模板变更" autocomplete="off" /></label></div></section>
      </section>
    </div>

    <footer class="bottom-action-bar" aria-label="底部操作栏"><div class="v2-publish-state" data-role="summary">
      <div><strong>草稿状态</strong><span id="draftSaveStatusText">尚未保存本次修改。</span></div><div><strong>发布状态</strong><span id="publishBlockerText">完成八项确认后可发布新版本。</span></div></div>
      <div class="v2-bottom-actions"><button id="confirmStageBtn" type="button">确认本页核验</button><button id="saveAndNextOptionBtn" type="button">保存并配置下一个选项</button>
        <button id="saveDraftBtn" type="button">保存草稿</button><button id="trialRenderBtn" type="button">使用样例试渲染</button><button id="publishVersionBtn" type="button" disabled>发布新版本</button></div></footer>
  </main>
    </div>
  </div>

  <div class="modal-overlay scan-running-overlay" id="scanRunningOverlay" role="status" aria-live="polite" aria-modal="true" aria-labelledby="scanRunningTitle" aria-describedby="scanRunningMessage" hidden>
    <section class="modal-dialog scan-running-dialog"><header><h2 id="scanRunningTitle">正在扫描模板</h2></header><section class="modal-body">
      <p id="scanRunningMessage">正在调用本机 Illustrator 扫描 .ai 模板中的规范标注字段。</p><div class="scan-running-progress" aria-hidden="true"><span></span></div>
      <p class="modal-note">请勿刷新或关闭页面；刷新只会中断当前页面等待，不能保证停止已经开始的 Illustrator 扫描。</p></section></section>
  </div>
  <div class="modal-overlay" id="scanFailedOverlay" role="alertdialog" aria-modal="true" aria-labelledby="scanFailedTitle" aria-describedby="scanFailedMessage" hidden>
    <section class="modal-dialog"><header><h2 id="scanFailedTitle">扫描失败</h2></header><section class="modal-body"><p id="scanFailedMessage">扫描没有完成，请检查模板文件后重试。</p></section>
      <footer><button id="retryScanBtn" type="button">重试扫描</button><button id="closeScanFailedBtn" type="button">关闭</button></footer></section>
  </div>
  <div class="modal-overlay" id="preflightFailedOverlay" role="alertdialog" aria-modal="true" aria-labelledby="preflightFailedTitle" aria-describedby="preflightFailedMessage" hidden>
    <section class="modal-dialog preflight-dialog"><header><h2 id="preflightFailedTitle">订单数据预检未通过</h2><span class="stage-status-pill blocked">整批阻断</span></header>
      <section class="modal-body"><p id="preflightFailedMessage">样例订单未通过预检，请按下列提示修改后重新试渲染。</p><div class="preflight-issue-list" id="preflightIssueList"></div>
        <div class="preflight-pass-note">预检通过后才会开始 Illustrator 试渲染。</div></section><footer><button id="closePreflightFailedBtn" type="button">关闭</button>
        <button id="returnToSampleDataBtn" class="primary" type="button">返回修改测试数据</button></footer></section>
  </div>
</body>
</html>
"""
