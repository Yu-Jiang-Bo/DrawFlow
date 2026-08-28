# DrawFlow 中央服务部署说明

需要按顺序部署中央服务和客户端时，请先阅读 [`DEPLOY-SCHEME2-OPERATIONS.md`](./DEPLOY-SCHEME2-OPERATIONS.md)。本文保留中央服务的专项说明。

本文档只描述方案二的中央服务。中央服务负责 Web/API、模板与规则中心、DeepSeek 中转、不可变模板版本、SHA256 manifest、bundle 下载和备份；中央服务不安装 Adobe Illustrator，也不做真实 `.ai` 渲染。

真实扫描和渲染由用户电脑上的 DrawFlow 桌面客户端完成，见 `deploy/DEPLOY-DESKTOP-AGENT.md`。

## 1. 构建中央发布包

在开发机仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package-release.ps1
```

产物：

- `release\drawflow-central-YYYYMMDD-HHMM\`
- `release\drawflow-central-YYYYMMDD-HHMM.zip`

发布包不应包含 DeepSeek API Key、测试机密码或开发机个人路径。

## 2. 解压目录

建议解压到：

```text
C:\DrawFlowCentral
```

模板运行数据建议使用：

```text
C:\DrawFlowData
```

目录结构：

```text
C:\DrawFlowCentral
├── src\
├── config\
├── templates\
├── deploy\
├── output\
└── requirements.txt

C:\DrawFlowData
└── templates\<template_id>\versions\vNNNN\
    ├── manifest.json
    ├── template.ai
    ├── rules.json
    └── assets\
```

`active.json` 指向当前活动版本。客户端只按需下载所选模板的活动版本 bundle。

## 3. 安装依赖

```powershell
cd C:\DrawFlowCentral
powershell -ExecutionPolicy Bypass -File .\deploy\windows\install.ps1
```

测试机需要 Python 3。中央服务不需要 Illustrator，也不需要模板字体。

## 4. 配置 DeepSeek

中央服务是唯一保存 DeepSeek 访问配置的位置：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\configure-llm.ps1
```

脚本把以下变量写入当前 Windows 用户环境：

- `DRAWFLOW_LLM_BASE_URL`
- `DRAWFLOW_LLM_API_KEY`
- `DRAWFLOW_LLM_MODEL`

不要把 API Key 写入文档、发布包或脚本。

## 5. 启动中央服务

前台启动：

```powershell
setx DRAWFLOW_DATA_DIR C:\DrawFlowData
setx DRAWFLOW_HOST 0.0.0.0
setx DRAWFLOW_PORT 8765
.\deploy\windows\start-service.bat
```

后台启动：

```powershell
$env:DRAWFLOW_DATA_DIR = "C:\DrawFlowData"
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-background.ps1
```

服务命令会显式使用：

```text
python -m src.service.http_server --role central
```

## 6. 健康检查

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\health-check.ps1
```

也可以直接访问：

```text
http://<central-host>:8765/api/health
```

期望响应：

```json
{
  "ok": true,
  "role": "central",
  "illustrator": "not_required"
}
```

中央服务的 `/api/render` 会拒绝真实渲染，并提示必须通过 DrawFlowClient 本地网关出图。

## 7. 中央接口

- `GET /api/health`
- `GET /api/runtime/templates/{id}/manifest`
- `GET /api/runtime/templates/{id}/bundle/{version}`
- `POST /api/runtime/templates/{id}/publish`
- `POST /api/templates/import-scan`
- 模板管理、规则解析和发布接口

`manifest` 是只读接口。模板必须先由发布接口生成不可变版本并写入 `active.json`，客户端才能按活动版本同步。

## 8. 防火墙

如果需要让局域网客户端访问中央服务，只开放 `8765` 给可信网络。不要开放客户端本地端口 `8766`，该端口只允许用户电脑 loopback 使用。

## 9. 验收

中央服务验收项：

- `/api/health` 返回 `role=central`。
- 打开 `http://<central-host>:8765/` 能看到 DrawFlow 页面。
- 不安装 Illustrator 时中央服务仍可启动。
- `/api/runtime/templates/{id}/manifest` 返回活动版本和文件 SHA256。
- `/api/runtime/templates/{id}/bundle/{version}` 能下载 zip。
- 日志和发布包不包含 DeepSeek API Key、密码或个人绝对路径。

真实 `.ai` 渲染验收必须在安装 Illustrator 的用户电脑上通过 DrawFlow 桌面客户端完成。
