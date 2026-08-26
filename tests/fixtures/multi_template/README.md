# 多模板渲染测试基线

本目录只存放脱敏、合成的多模板测试数据；不得提交客户订单、模板资产或生产输出。

## V2 单模板基线

- 基线提交：`1976bee`
- 执行日期：2026-08-26
- 命令：

  ```powershell
  python -m pytest `
    tests/test_local_client.py `
    tests/test_local_gateway.py `
    tests/test_service_integration.py `
    tests/test_v2_order_render.py `
    tests/test_production_output.py `
    tests/test_web_page.py -q `
    --basetemp .pytest-multi-template-baseline
  ```

- 结果：147 passed，2 failed。

已知历史失败（本次多模板改造不得通过修改业务逻辑将其“修绿”）：

1. `tests/test_local_client.py::test_local_render_downloads_template_and_runs_dry_run`：合成订单缺少当前公共生产输出要求的订单明细字段，`LocalDrawFlowClient.render()` 抛出 `LocalClientError(code="render_failed")`。
2. `tests/test_service_integration.py::test_service_routes_w_manufacturers_to_cs5_master_ai_pngs_and_standard_ai`：`OTHER-W` dry-run 的 `delivery_plan` 为空，原断言访问首项时发生 `IndexError`。

## 单模板任务结构快照

下列快照只记录稳定字段名和工作流边界，不记录本机绝对路径、真实订单、模板资产或成品内容。

| 场景 | 请求固定字段 | 成功任务关键字段 | 验证依据 |
| --- | --- | --- | --- |
| Legacy dry-run | `template_id`、`order_file`、`dry_run=true` | `status=completed`、`request`、`outputs.render_task`、`stats.dry_run=true` | `test_service_dry_run_creates_job_and_render_task` |
| Legacy 正式渲染 | `template_id`、`order_file`、`dry_run=false` | 同一 Job 合同；由模板自己的公共生产输出层补充交付输出，且仅在 Illustrator 成功后标记完成 | `RenderService.submit` 与各 pipeline 的正式分支 |
| V2 dry-run | `template_id`、已发布 `template_version`、`order_file`、`dry_run=true` | `status=completed`、`request`、`outputs.render_task`、`outputs.output_manifest`、`stats.dry_run=true` | `V2OrderRenderService._run` 的 dry-run 分支 |
| V2 正式渲染 | `template_id`、已发布 `template_version`、`order_file`、`dry_run=false` | `status=completed`、`outputs.primary_output`、`outputs.output_bundle`、模板内部生产部门成品列表、`stats.dry_run=false` | `test_v2_single_name_template_splits_newline_names_into_one_order_column` |

多模板父任务只能把这些单模板正式成品作为子任务结果收集；不得改写旧 `/local/render`、`/api/render` 或 `LocalDrawFlowClient.render()` 的请求合同。

测试必须使用工作树内的 `--basetemp`，避免访问用户级临时目录；完成后应删除该临时目录。
