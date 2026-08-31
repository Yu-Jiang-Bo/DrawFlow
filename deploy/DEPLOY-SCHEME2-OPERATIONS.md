# DrawFlow 方案二部署与验收手册

本文对应当前正式架构：Linux 测试机运行中央服务，安装了 Adobe Illustrator 的 Windows 电脑运行 DrawFlow 客户端。旧的 Windows 集中渲染包和 2026-07-16/17 客户端包均不再作为当前交付物。

## 1. 当前交付包

| 部署位置 | 文件 | SHA256 |
|---|---|---|
| Linux 中央服务器 | `drawflow-central-linux-20260720-scheme2-r10.zip` | `7E9E3A7239E15E94971D68C715E55FD82C079EF48AAF5D9D952B43916701EBEC` |
| Windows 出图电脑 | `drawflow-client-20260720-scheme2-r8.zip` | `A8CDEC621B2EF9800E9BC9F339DD6AFFA77B1D88EEE7D16C5383CDF289198BBA` |

开发机上的完整路径：

```text
C:\Users\Administrator\Desktop\image\custom-renderer\release\drawflow-central-linux-20260720-scheme2-r10.zip
C:\Users\Administrator\Desktop\image\custom-renderer\release\drawflow-client-20260720-scheme2-r8.zip
```

SHA256 用于确认 zip 没有传输损坏且没有拿错版本。它是校验摘要，不是密码或加密。Windows 校验命令：

```powershell
Get-FileHash .\drawflow-central-linux-20260720-scheme2-r10.zip -Algorithm SHA256
Get-FileHash .\drawflow-client-20260720-scheme2-r8.zip -Algorithm SHA256
```

Linux 校验命令：

```bash
sha256sum drawflow-central-linux-20260720-scheme2-r10.zip
```

输出必须与表中对应值完全一致，字母大小写不影响比较。校验失败时不要解压或运行，应重新传输文件。

## 2. 架构边界

- Linux 中央服务监听 `8765`，提供 Web/API、模板、规则、不可变版本和 bundle 下载，不安装或调用 Illustrator。
- Windows 客户端只监听 `127.0.0.1:8766`，下载所选模板、校验 SHA256、检查字体并调用本机 Illustrator。
- 浏览器始终访问 `http://127.0.0.1:8766/`。不要把公网中央网页当成正式渲染入口。
- 正式渲染不调用 LLM。DeepSeek 配置只留在中央服务器。

## 3. Linux 中央服务首次部署

### 3.1 上传并校验

在开发机 Git Bash 或 PowerShell 中上传：

```bash
scp "C:\Users\Administrator\Desktop\image\custom-renderer\release\drawflow-central-linux-20260720-scheme2-r10.zip" root@162.14.120.240:/tmp/
```

登录 Linux 后执行：

```bash
sha256sum /tmp/drawflow-central-linux-20260720-scheme2-r10.zip
```

预期摘要：

```text
7e9e3a7239e15e94971d68c715e55fd82c079ef48aaf5d9d952b43916701ebec
```

### 3.2 解压和配置

使用独立代码目录，运行数据继续放在 `/opt/drawflow-data`：

```bash
mkdir -p /opt/drawflow-central-r10
unzip -q -o /tmp/drawflow-central-linux-20260720-scheme2-r10.zip -d /opt/drawflow-central-r10
cd /opt/drawflow-central-r10
chmod +x deploy/linux/*.sh
cp deploy/linux/drawflow.env.example drawflow.env
chmod 600 drawflow.env
```

编辑 `drawflow.env`，至少确认：

```dotenv
DRAWFLOW_HOST=0.0.0.0
DRAWFLOW_PORT=8765
DRAWFLOW_DATA_DIR=/opt/drawflow-data
DRAWFLOW_LOG_DIR=/opt/drawflow-central-r10/output/logs
```

只有需要中央 DeepSeek 编译规则时，才在服务器自己的 `drawflow.env` 中填写 LLM 地址、模型和 Key。不要把 `drawflow.env` 放回 zip 或发送给客户端。

启用 V2 真实样例预览时，还必须为中央服务和可信 Windows 预览工作端配置相同的 `DRAWFLOW_PREVIEW_WORKER_SECRET`。自动识别 OpenType/PUA 尾巴字形时，中央服务和可信 Windows Illustrator 扫描工作端还必须配置另一把独立的 `DRAWFLOW_SCAN_WORKER_SECRET`。两把值都至少包含 32 字节随机内容，只能通过受控环境配置分发，不能互相复用；不要放入浏览器页面、客户端示例 JSON、日志、截图或发布 ZIP。中央端缺少预览密钥时会拒绝签发试渲染凭证；缺少扫描密钥时会拒绝保存自动尾巴字形扫描，不接受浏览器自行构造的扫描证据。

### 3.3 安装和启动

逐行执行：

```bash
./deploy/linux/install.sh
./deploy/linux/start-background.sh
./deploy/linux/status.sh
./deploy/linux/health-check.sh
```

健康检查预期包含：

```json
{
  "ok": true,
  "role": "central",
  "illustrator": "not_required",
  "runtime_templates": "/opt/drawflow-data/templates"
}
```

中央服务会在监听端口前自动检查所有活动模板：

- 第一次部署或没有活动版本时自动发布新版本；
- 模板、规则、结构配置或素材未变化时复用现有版本；
- 源文件变化或运行版本文件损坏时发布下一不可变版本；
- 只有 bundle 丢失或损坏时原版本重建 bundle；
- 任一活动模板无法形成完整运行包时，中央服务直接启动失败并显示模板 ID。

检查日志：

```bash
grep "DrawFlow runtime templates ready" /opt/drawflow-central-r10/output/logs/drawflow.log
tail -n 100 /opt/drawflow-central-r10/output/logs/drawflow.error.log
```

### 3.4 验证模板和下载接口

```bash
curl -sS http://127.0.0.1:8765/api/health
curl -sS http://127.0.0.1:8765/api/templates
curl -sS http://127.0.0.1:8765/api/runtime/templates/JJMB202603281027102517/manifest
```

manifest 应包含 `template_id`、`version`、`source_sha256`、`files` 和各文件的 `sha256`。不要手工修改 `/opt/drawflow-data/templates/*/active.json` 或已发布的 `versions/vNNNN`。

## 4. 已有 Linux 服务升级

旧 DrawFlow 服务已经在 `/opt/drawflow-central` 运行时，先备份环境配置和运行数据：

```bash
cp /opt/drawflow-central/drawflow.env /root/drawflow.env.backup
tar -czf /root/drawflow-data-backup-$(date +%Y%m%d-%H%M%S).tar.gz /opt/drawflow-data
```

停止旧 DrawFlow 进程，只使用它自己的停止脚本：

```bash
cd /opt/drawflow-central
./deploy/linux/stop-service.sh
```

按第 3 节把新包解压到 `/opt/drawflow-central-r10`，然后复制原环境配置：

```bash
cp /root/drawflow.env.backup /opt/drawflow-central-r10/drawflow.env
chmod 600 /opt/drawflow-central-r10/drawflow.env
cd /opt/drawflow-central-r10
./deploy/linux/install.sh
./deploy/linux/start-background.sh
./deploy/linux/status.sh
./deploy/linux/health-check.sh
```

确认新进程健康、模板 manifest 可读后再清理旧代码目录。不要删除 `/opt/drawflow-data`，也不要停止或修改原来监听 `8000` 的项目。

## 5. Windows 客户端部署

### 5.1 校验和解压

把 `drawflow-client-20260720-scheme2-r8.zip` 发送到出图电脑，在 PowerShell 中执行：

```powershell
Get-FileHash .\drawflow-client-20260720-scheme2-r8.zip -Algorithm SHA256
```

预期：

```text
A8CDEC621B2EF9800E9BC9F339DD6AFFA77B1D88EEE7D16C5383CDF289198BBA
```

把整个 zip 解压到独立目录，例如 `E:\DrawFlow`：

```powershell
New-Item -ItemType Directory -Force E:\DrawFlow | Out-Null
Expand-Archive -LiteralPath .\drawflow-client-20260720-scheme2-r8.zip -DestinationPath E:\DrawFlow -Force
Get-ChildItem E:\DrawFlow
```

至少应看到：

```text
DrawFlowClient.exe
_internal
drawflow-client.json
drawflow-client.example.json
README-CLIENT.md
start-client.bat
```

不要只复制 exe；`_internal` 和 `drawflow-client.json` 必须与 exe 保持同级。

### 5.2 启动前检查

客户端已预置中央地址，不需要手工改配置：

```powershell
Get-Content E:\DrawFlow\drawflow-client.json
Test-NetConnection 162.14.120.240 -Port 8765
Invoke-RestMethod http://162.14.120.240:8765/api/health
```

配置文件预期为：

```json
{
  "central_url": "http://162.14.120.240:8765"
}
```

电脑还必须安装并激活 Adobe Illustrator，并安装模板需要的字体。客户端不需要安装 Python，也不需要 DeepSeek API Key。

### 5.3 启动和验收

双击：

```text
E:\DrawFlow\DrawFlowClient.exe
```

程序应自动打开：

```text
http://127.0.0.1:8766/
```

PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8766/api/templates | ConvertTo-Json -Depth 5
```

`/health` 中必须包含：

```json
{
  "ok": true,
  "role": "local-client",
  "central": "http://162.14.120.240:8765"
}
```

选择模板并渲染时，客户端会按 manifest 下载当前活动 bundle，校验所有 SHA256 后缓存到 `%LOCALAPPDATA%\DrawFlow\templates`。同一版本再次使用时直接命中缓存；版本变化时才下载新版本。

## 6. 在开发机做干净客户端测试

可以先在当前开发机测试正式客户端 zip。开发机存在 `C:\Users\Administrator\Desktop\image` 不会影响正式包，因为 exe 使用包内 `_internal` 资源，并优先读取 exe 同目录的 `drawflow-client.json`，不会读取项目目录脚本。

为了排除旧缓存和旧进程干扰，建议这样测试：

```powershell
Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
$env:DRAWFLOW_LOCAL_DATA_DIR = "$env:LOCALAPPDATA\DrawFlow-Package-Test"
New-Item -ItemType Directory -Force C:\DrawFlowClient-Package-Test | Out-Null
Expand-Archive -LiteralPath "C:\Users\Administrator\Desktop\image\custom-renderer\release\drawflow-client-20260720-scheme2-r8.zip" -DestinationPath C:\DrawFlowClient-Package-Test -Force
Set-Location C:\DrawFlowClient-Package-Test
.\DrawFlowClient.exe
```

如果第一条命令显示已有 `8766` 监听进程，先正常关闭旧 DrawFlowClient 窗口，再启动新包。测试后关闭客户端；`DRAWFLOW_LOCAL_DATA_DIR` 只对当前 PowerShell 会话有效。

干净测试的判断标准：

- 浏览器打开 `http://127.0.0.1:8766/`；
- `/health` 的 `central` 是 `http://162.14.120.240:8765`；
- 页面能列出中央模板；
- 首次渲染在 `DrawFlow-Package-Test\templates` 生成模板缓存；
- Illustrator 生成 AI8 输出，第二次渲染同版本不重复下载。

## 7. 后续模板更新

以后在开发机新增模板或优化规则时：

1. 在源码项目中完成模板、规则、结构配置和素材调试。
2. 跑完整测试并重建 Linux 中央包。
3. 把新中央包部署到新的 Linux 代码目录，继续使用同一个 `/opt/drawflow-data`。
4. 重启中央服务。启动门禁会比较源指纹，变化的模板自动生成下一版本，未变化模板继续复用。
5. 客户端下次选择该模板时读取新 manifest，只下载这个模板的新 bundle。

仅更新模板、规则和 Web 页面时不需要重新发送客户端。只有本地网关协议、Illustrator 渲染脚本或客户端运行时代码变化时才需要新客户端包。

## 8. 常见错误

### `Template has no published active version`

新中央包会在监听前自动准备活动版本。出现此错误通常表示：

- Linux 仍运行旧中央进程；
- 新进程启动协调失败，旧进程仍占用 `8765`；
- 客户端仍指向旧地址。

检查 `status.sh`、两个日志文件、`DrawFlow runtime templates ready:` 和客户端 `/health` 的 `central` 字段。不要手工修改 `active.json`。

### `Style config not found`

当前 bundle 会把需要的 `template.config.json` 一起发布和缓存。若仍出现该错误，先确认中央已经升级到 r10、客户端 manifest 已切到新版本，再清理该模板的旧本地缓存后重试，不要删除整个 `%LOCALAPPDATA%\DrawFlow`。

### 客户端能打开 8766，但没有模板

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
Invoke-RestMethod http://162.14.120.240:8765/api/health
Get-Content E:\DrawFlow\drawflow-client.json
```

`central` 不能是 `http://127.0.0.1:8765`。若是，说明启动的是旧客户端目录或旧进程。

## 9. 安全边界

- 客户端端口固定绑定 loopback，不要把 `8766` 开放到外网。
- 中央 `8765` 当前 MVP 尚无完整登录鉴权，云安全组应尽量限制来源；长期公网使用应增加 HTTPS 和鉴权。
- 不要把 API Key、密码、服务器环境文件或本机敏感绝对路径放进任何交付 zip。
- 发布前后都校验 SHA256，模板 bundle 内部还会再次逐文件校验 SHA256。
