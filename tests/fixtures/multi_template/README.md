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

- 结果：160 passed，2 failed。

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

## MT6.1 自动化矩阵（2026-08-26）

| 场景 | 覆盖入口 |
| --- | --- |
| 解析与分组 | `test_multi_template_order.py`：固定 `模板` 表头、行号、空值、公式、一次扫描、1000 行/30 模板和分组工作簿 |
| 模板解析 | `test_multi_template_resolver.py`：legacy/V2、精确大小写、停用、未发布、配置/资产/SHA 失败与版本固定 |
| 静态预检 | `test_multi_template_preflight.py`：全错误聚合、零渲染调用、订单/分组文件校验和恢复选择 |
| 代表订单试渲染 | `test_multi_template_canary.py`、`test_per_template_canary.py`：确定性代表行、模板失败继续、系统失败停止、试渲染隔离 |
| 错误边界 | `test_multi_template_failures.py`、`test_multi_template_dispatcher.py`：模板/系统失败、可恢复与不可恢复 COM |
| 调度与检查点 | `test_multi_template_dispatcher.py`：稳定串行、B 失败 C 继续、系统中断、原子检查点写入失败与进程重启恢复 |
| 部门输出隔离 | `test_multi_template_dispatcher.py`：每模板子 ZIP 中独立 `templates/<template_id>/department/...` 路径，父调度不重跑生产管线 |
| 交付 ZIP | `test_multi_template_output.py`：正式/部分包互斥、子 ZIP 安全展开、成员/符号链接/哈希校验和原子发布 |
| retry / resume | `test_multi_template_checkpoint_selection.py`、`test_multi_template_render.py`、`test_multi_template_dispatcher.py`：仅失败或 pending 模板重跑，成功模板跳过，订单/快照变更拒绝 |
| API / UI | `test_multi_template_gateway.py`、`test_multi_template_gateway_contract.py`、`test_multi_template_web_page.py`：旧单模板兼容、忙碌锁、错误脱敏、部分包提示、retry/resume、陈旧 GET/POST 响应失效 |

复现多模板矩阵：

```powershell
pytest -q --basetemp .pytest-mt52-multi `
  tests/test_multi_template_canary.py `
  tests/test_per_template_canary.py `
  tests/test_multi_template_checkpoint_selection.py `
  tests/test_multi_template_dispatcher.py `
  tests/test_multi_template_failures.py `
  tests/test_multi_template_gateway.py `
  tests/test_multi_template_gateway_contract.py `
  tests/test_multi_template_order.py `
  tests/test_multi_template_output.py `
  tests/test_multi_template_parent_canary_persistence.py `
  tests/test_multi_template_preflight.py `
  tests/test_multi_template_render.py `
  tests/test_multi_template_resolver.py `
  tests/test_multi_template_web_page.py
```

本次结果：`144 passed in 20.28s`。冻结单模板基线为 `160 passed, 2 failed`；两条失败均记录在本文件上方，且不在多模板调用链内。

## MT6.2 真实 Illustrator 冒烟前置条件

真实冒烟必须使用脱敏 Excel 和可用的 `.ai` 模板/资产副本，并在独立输出目录中执行。当前工作树未包含 active 模板所需的 `template.ai` 与登记 `.ai` 资产，因而不得以占位文件或合成 mock 冒充真实 Illustrator 验收。
