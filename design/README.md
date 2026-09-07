# DrawFlow 页面原型

本目录保存 DrawFlow 页面设计审核稿，不是前端实现。V2 工作台是当前唯一模板与规则配置入口；旧 Web 模板管理和规则配置原型只作历史参考。

## 当前 V2 原型

- `desktop-v2-workbench-v1.svg`：V2 工作台（新建模板与扫描）
- `desktop-v2-structure-config-v1.svg`：V2 工作台（扫描后的字段配置）
- `desktop-v2-option-rules-v1.svg`：V2 工作台（扫描后的预设处理）
- `desktop-v2-preview-publish-v1.svg`：V2 工作台（样例预览与发布）

## 历史 Web 原型

- `web-prototype-render-task-v1.svg`：出图任务页
- `web-prototype-template-management-v1.svg`：已关闭的模板管理页
- `web-prototype-render-task-v2.svg`：出图任务页 V2
- `web-prototype-template-management-v2.svg`：已关闭的模板管理页 V2
- `web-prototype-rule-config-v1.svg`：已关闭的规则配置页 V1

## 本版设计取向

- 用户上传订单表格，不填写本机路径。
- 用户上传 `.ai` 模板，不填写服务端已有路径。
- 页面不展示内部技术字段、调试参数和任务文件路径。
- 部门规则以中文业务说明展示。
- 渲染完成后自动下载 `.ai` 文件。
- 用户主导航只保留“出图任务 / V2 工作台 / 任务记录”，旧模板管理和规则配置入口不再展示。
- V2 配置流程使用扫描结构、受控表单、核验状态和底部操作区组织上传扫描、字段配置、预设处理、样例预览与发布。
- V2 工作台支持多 `.ai` 资产和结构化规则预览，配置必须人工确认后保存或发布。
- 出图任务首页不展示“当前模板状态”和“最近任务”辅助卡片。
