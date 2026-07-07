# Custom Renderer

定制效果图自动生成服务的初版实现。

## MVP

当前版本只实现最简单的纯文字模板：

```text
CSV/JSON 输入
→ 生成纯文字 render task
→ Illustrator 执行 scripts/illustrator/render_text.jsx
→ 输出 Illustrator 8 兼容 .ai
```

## 干跑验证

不启动 Illustrator，只生成 render task：

```powershell
python -m src.main --csv samples/orders_text.csv --output output --dry-run
```

## 实际渲染

需要 Windows + Adobe Illustrator + pywin32：

```powershell
python -m src.main --csv samples/orders_text.csv --output output
```

## JJMB202603281027102517 模板纯文字渲染

当前只处理字体选项 `F1-F9` 的纯文字订单，`F10-F12` 设计字体先跳过。

```powershell
python -m src.jjmb_template_main `
  --xlsx "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\C-208.xlsx" `
  --template-ai "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\JJMB202603281027102517.ai" `
  --output output\jjmb202603281027102517-text `
  --dry-run
```

实际渲染会调用 Illustrator，并从模板里读取 `字体区/F1-F9` 的字体属性和 `作图区/Style1-Style5` 的方框尺寸：

```powershell
python -m src.jjmb_template_main `
  --xlsx "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\C-208.xlsx" `
  --template-ai "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\JJMB202603281027102517.ai" `
  --output output\jjmb202603281027102517-text `
  --limit 1
```

如果 Illustrator COM 启动失败，可以先 dry-run 生成 `render-tasks/*.json`，再在 Illustrator 中运行：

```text
scripts/illustrator/run_render_template_text_task.jsx
```

运行后选择对应的 render task JSON 即可手动渲染。

## 本地 Web/API 工作台

启动服务：

```powershell
python -m src.service.http_server --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

页面包含：

```text
出图任务   # 上传订单表格，渲染完成后自动下载 AI 文件
模板管理   # 登记模板信息，上传主 .ai 和多个附加 .ai 模板资产
规则配置   # 查看部门规则，新增或编辑自然语言规则草稿
任务记录   # 查看最近任务并下载历史输出
```

当前 API：

```text
GET  /api/health
GET  /api/templates
GET  /api/templates/{template_id}/config
GET  /api/templates/{template_id}/download/template_ai
POST /api/templates
DELETE /api/templates/{template_id}
POST /api/templates/rules/draft
GET  /api/rules/department
POST /api/rules/department/parse
POST /api/rules/department/draft
POST /api/rules/department/publish
POST /api/render
GET  /api/jobs
GET  /api/jobs/{job_id}
GET  /api/jobs/{job_id}/download/output_ai
GET  /api/jobs/{job_id}/download/render_task
```

当前模板注册仍是本地 MVP：

```text
config/templates.json                  # 模板元数据注册表
templates/<template_id>/template.ai    # 页面上传后的模板文件
templates/<template_id>/assets/*.ai    # 复杂设计拆分出的附加模板资产
templates/<template_id>/template.config.json # 自然语言规则转换后的结构化配置
config/department_rule_drafts.json     # 部门规则页面新增/编辑的草稿
```

正式部署时，这部分应迁移为数据库记录 + 共享文件存储。

LLM 规则解析是可选能力。未配置时服务会回退到本地启发式解析；正式渲染不会调用 LLM。需要接入真实接口时配置：

```powershell
$env:CUSTOM_RENDERER_LLM_API_KEY="your-api-key"
$env:CUSTOM_RENDERER_LLM_BASE_URL="https://your-llm-host/v1"
$env:CUSTOM_RENDERER_LLM_MODEL="your-model"
```

`POST /api/render` 使用 `multipart/form-data` 上传订单表格：

```text
template_id: JJMB202508261001394920
order_file: 订单 Excel/CSV 文件
dry_run: true  # 可选；只解析测试，不启动 Illustrator
```

页面渲染成功后会自动请求 `/api/jobs/{job_id}/download/output_ai` 下载 AI 文件。

任务记录会写入：

```text
output/service-jobs/{job_id}/job.json
```
