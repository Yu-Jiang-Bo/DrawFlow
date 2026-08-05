# V2 template fixtures

本目录只存放 V2 首版真实模板验收所需的最小结构夹具。

- 不迁移现有四个生产模板；旧模板继续走 `config/templates.json` 中的旧管线。
- 不执行 `component_key` / `scope=local/shared` 传播；首版只允许保存这些字段作为不可执行审计信息。
- 后续新增真实 `.ai` 夹具时，应同时提供脱敏订单样本、扫描证据摘要和预期阻断/通过结果。
