# DrawFlow 方案二交付与客户端部署说明

需要执行完整安装、校验、启动和验收时，请先阅读 [`DEPLOY-SCHEME2-OPERATIONS.md`](./DEPLOY-SCHEME2-OPERATIONS.md)。本文保留方案二架构和客户端职责说明。

方案二把 DrawFlow 拆成中央服务和用户电脑本地客户端。用户入口为安装后双击 `DrawFlow.exe`；启动器先安全检查客户端更新，再启动版本化 `DrawFlowClient.exe` 本地网关，打开 `http://127.0.0.1:8766/`，代理中央最新页面和 API，同时在本地截获扫描、渲染和输出下载接口。这样不需要公网中央页面直接访问 `localhost`，避免 Chrome Local Network Access 和 CORS 限制。

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
powershell -ExecutionPolicy Bypass -File .\deploy\package-client.ps1 -ClientVersion <x.y.z>
```

产物：

- `release\drawflow-client-<x.y.z>.payload.zip`（仅供发布到中央服务）
- `release\.client-payload-<x.y.z>\`（构建暂存目录，包含且仅包含 `DrawFlowClient.exe` 和 `_internal`）

版本化更新载荷使用 PyInstaller onedir，仅包含 `DrawFlowClient.exe` 与 `_internal`。它不是用户安装包，不能直接分发或解压运行；同事只使用 `DrawFlow-Setup-<version>.exe`。用户电脑不需要单独安装 Python，但必须安装并激活 Adobe Illustrator 和模板字体。

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

同事只接收一次 `DrawFlow-Setup-<version>.exe`。运行安装包后，从开始菜单或桌面快捷方式启动：

```text
DrawFlow.exe
```

客户端会打开：

```text
http://127.0.0.1:8766/
```

不要把 `8766` 绑定到公网或局域网地址。程序启动时会拒绝非 loopback host。管理员仅在中央地址变化时更新安装目录的 `drawflow-launcher.json`；该文件不保存 API Key、密码或私钥。用户不得手工替换或直接运行 `DrawFlowClient.exe`。

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
- 中央 zip 包、版本化客户端载荷、一次性安装包和启动时自动更新。
- 单机单渲染锁。

暂不做：

- 登录鉴权。
- 数据库。
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

## 10. 一次安装与客户端自动更新

自动更新在现有 `DrawFlowClient.exe` 外新增 `DrawFlow.exe` 启动器。第一次只向同事分发 `DrawFlow-Setup-<version>.exe`；安装到当前用户的 `%LOCALAPPDATA%\Programs\DrawFlow` 后，用户只启动 `DrawFlow.exe`。`%LOCALAPPDATA%\DrawFlow` 内的模板缓存、订单上传、任务记录、输出和日志仍由渲染客户端管理，安装、更新和卸载都不会清理它。

生产自动更新必须先为中央服务配置 HTTPS 反向代理，例如 `https://drawflow.example.com`。现有 `http://<central-host>:8765` 可继续提供页面、模板和渲染 API，但不能作为更新地址；启动器会拒绝公网 HTTP 更新源。中央服务升级到包含客户端发布接口后，需确认：

```text
GET https://drawflow.example.com/api/client/releases/stable/latest
GET https://drawflow.example.com/api/client/releases/stable/download/<version>
```

构建首次安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package-setup.ps1 `
  -ClientVersion 1.0.0 `
  -CentralUrl http://<central-host>:8765 `
  -UpdateBaseUrl https://drawflow.example.com
```

构建机必须安装 Inno Setup 6，且能找到 `ISCC.exe`；脚本找不到该工具会停止，不会伪造安装包。发布一个客户端更新时，先完成测试、审查和人工验收，再构建版本化载荷：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\package-client.ps1 -ClientVersion 1.0.1
```

把生成的 `release\drawflow-client-1.0.1.payload.zip` 传至已升级的中央服务，再在中央服务环境执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\publish-client-release.ps1 `
  -DataDir <DRAWFLOW_DATA_DIR> `
  -PayloadPath <已上传的 payload zip> `
  -ClientVersion 1.0.1 `
  -Notes "说明本次本地渲染改动"
```

该操作会先保存不可变 `1.0.1` 载荷，再原子更新 stable latest 清单。用户下一次启动 `DrawFlow.exe` 时自动下载、校验 SHA256，并仅在本机 `127.0.0.1:8766/health` 就绪后切换；下载、hash、解压或启动失败都会继续启动旧版。需要回退时，使用已保留的旧版 payload 重新发布其原版本号，latest 将回指旧版；不要手工编辑 `latest.json` 或删除版本目录。
