# DrawFlow 方案二交付与客户端部署说明

需要执行完整安装、校验、启动和验收时，请先阅读 [`DEPLOY-SCHEME2-OPERATIONS.md`](./DEPLOY-SCHEME2-OPERATIONS.md)。本文保留方案二架构和客户端职责说明。

方案二把 DrawFlow 拆成中央服务和用户电脑本地客户端。浏览器入口推荐为用户双击 `DrawFlowClient.exe`，由本地网关打开 `http://127.0.0.1:8766/`，代理中央最新页面和 API，同时在本地截获扫描、渲染和输出下载接口。这样不需要公网中央页面直接访问 `localhost`，避免 Chrome Local Network Access 和 CORS 限制。

## 1. 架构

中央服务：

- Web/API、模板与规则中心。
- DeepSeek 中转和规则草稿编译。
- 不可变模板版本、manifest、SHA256、bundle 下载和备份。
- 不安装 Illustrator，不做真实渲染。

用户电脑 DrawFlowClient：

- 只监听 `127.0.0.1:8766`。
- 代理中央页面和普通 API。
- 本地截获 `/local/render`、`/api/render`、`/local/templates/scan`。
- 调用本机 Illustrator 扫描模板和执行订单渲染。
- 检查本机字体，按需缓存所选模板版本。
- 不保存 DeepSeek API Key。

## 2. 构建两个交付物

中央服务包：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package-release.ps1
```

产物：

- `release\drawflow-central-YYYYMMDD-HHMM\`
- `release\drawflow-central-YYYYMMDD-HHMM.zip`

本地客户端包：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package-client.ps1
```

产物：

- `release\drawflow-client-YYYYMMDD-HHMM\`
- `release\drawflow-client-YYYYMMDD-HHMM.zip`

本地客户端包使用 PyInstaller onedir，包含 `DrawFlowClient.exe`、运行依赖、JSX 脚本、配置示例和说明。用户电脑不需要单独安装 Python，但必须安装并激活 Adobe Illustrator 和模板字体。

## 3. 中央服务部署

按 `deploy/DEPLOY-WINDOWS.md` 部署中央服务。关键点：

- 设置 `DRAWFLOW_DATA_DIR`，建议为 `C:\DrawFlowData`。
- 配置 DeepSeek 只在中央服务完成。
- 启动时使用 `--role central`。
- `/api/health` 应返回 `role=central`、`illustrator=not_required`。

中央模板数据建议：

```text
C:\DrawFlowData\templates\<id>\versions\vNNNN\
├── manifest.json
├── template.ai
├── rules.json
└── assets\

C:\DrawFlowData\templates\<id>\active.json
```

## 4. 客户端部署

把 `drawflow-client-*.zip` 解压到用户电脑，例如：

```text
C:\DrawFlowClient
```

正式客户端包已经在 exe 同级包含 `drawflow-client.json`，默认连接当前 Linux 中央服务：

```json
{
  "central_url": "http://162.14.120.240:8765"
}
```

解压后直接双击：

```text
DrawFlowClient.exe
```

客户端会打开：

```text
http://127.0.0.1:8766/
```

不要把 `8766` 绑定到公网或局域网地址。程序启动时会拒绝非 loopback host。中央地址变化时只编辑 exe 同级 `drawflow-client.json`，不需要重打 exe，也不要在该文件中保存 API Key 或密码。

本地数据默认位置：

```text
%LOCALAPPDATA%\DrawFlow
├── templates\<id>\<version>\
├── jobs\
├── output\
├── uploads\
└── logs\
```

也可用 `DRAWFLOW_LOCAL_DATA_DIR` 覆盖。

## 5. 普通渲染流程

1. 用户在 `http://127.0.0.1:8766/` 选择模板和订单。
2. 本地网关查询中央 manifest。
3. 本地仅在缺失或版本变化时下载所选模板 bundle。
4. 本地校验 bundle 内文件 SHA256。
5. 本地检查模板必需字体。
6. 本地调用本机 Illustrator 渲染。
7. 浏览器从 `/local/jobs/{id}/output` 下载本机生成的 AI8 文件。

正式渲染不调用 LLM。

## 6. 新增模板流程

1. 用户在本机选择 `.ai` 和素材。
2. 本地网关调用本机 Illustrator 扫描模板。
3. 本地上传文件和扫描 JSON 到中央 `/api/templates/import-scan`。
4. 中央调用 DeepSeek 编译规则草稿。
5. 用户确认规则。
6. 中央发布不可变版本。
7. 其他客户端按需同步活动版本。

## 7. 接口清单

中央建议接口：

- `GET /api/runtime/templates/{id}/manifest`
- `GET /api/runtime/templates/{id}/bundle/{version}`
- `POST /api/runtime/templates/{id}/publish`
- `POST /api/templates/import-scan`
- 模板发布接口

`GET /api/runtime/templates/{id}/manifest` 不会隐式发布模板；只有确认后的发布动作会生成不可变版本并更新 `active.json`。

本地建议接口：

- `GET /health`
- `POST /local/render`
- `POST /local/templates/scan`
- `GET /local/jobs/{id}`
- `GET /local/jobs/{id}/output`

## 8. 两天内部 MVP 范围

已纳入：

- 中央/本地入口分离。
- 本机扫描与渲染。
- DeepSeek 留在中央。
- 选中模板按需同步、版本校验和 SHA256 校验。
- 字体缺失可读提示。
- 中央 zip 包和 DrawFlowClient zip 包。
- 单机单渲染锁。

暂不做：

- 登录鉴权。
- 数据库。
- 自动更新。
- 应用商店分发。
- 字体文件分发。
- 多人编辑冲突。
- 高可用。
- 统一云端输出文件存储。

## 9. 验收

中央：

- `/api/health` 返回 `role=central`。
- 未安装 Illustrator 也能启动。
- manifest 和 bundle 可下载，manifest 含 SHA256。
- `/api/render` 返回“通过 DrawFlowClient 本地网关生成效果图”的错误。

客户端：

- `/health` 返回 `role=local-client`。
- 服务只监听 `127.0.0.1:8766`。
- 首次渲染下载模板，缓存命中不重复下载。
- 版本变化时重新下载。
- hash 失败时不切换缓存。
- 缺字体时在调用 Illustrator 前给出可读错误。
- 新模板扫描可上传到中央并生成规则草稿。

真实 Illustrator 冒烟：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\test-illustrator.ps1
```

这个检查必须在用户自己的 Windows 登录会话中运行。不要把 Illustrator 放入 Session 0 服务。
