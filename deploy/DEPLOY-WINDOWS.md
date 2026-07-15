# Custom Renderer Windows 测试机部署流程

本服务的正式渲染依赖 Adobe Illustrator COM 自动化，因此测试机必须是 Windows，并且已安装 Adobe Illustrator。Linux 服务器不能执行 `.ai` 渲染；旧的 `uvicorn app:app` 部署说明属于另一个 FastAPI 解析服务，不适用于本项目。

## 1. 本机打包

在本机 PowerShell 里执行：

```powershell
cd <本机项目目录>\custom-renderer
powershell -ExecutionPolicy Bypass -File .\deploy\package-release.ps1
```

生成结果在：

```text
custom-renderer\release\custom-renderer-windows-YYYYMMDD-HHMM\
custom-renderer\release\custom-renderer-windows-YYYYMMDD-HHMM.zip
```

部署包只包含运行所需代码、模板、规则和必要模板配置，不包含 `.git`、本地任务历史、上传过的订单表格、测试缓存或虚拟环境。

## 2. 拷贝到 Windows 测试机

把生成的 zip 复制到测试机，例如解压到：

```text
D:\custom-renderer
```

建议保持目录不要带中文和空格，减少 Illustrator/PowerShell 路径兼容问题。

## 3. 安装依赖

测试机需要先安装 Python 3，并确保 PowerShell 里能执行：

```powershell
python --version
```

在测试机 PowerShell 里执行：

```powershell
cd D:\custom-renderer
powershell -ExecutionPolicy Bypass -File .\deploy\windows\install.ps1
```

依赖包括：

```text
pywin32
openpyxl
pytest
```

如果测试机不能联网，需要先准备离线 wheel 包，或临时开放 pip 安装所需网络。

## 4. 启动服务

前台启动，适合首次验证：

```powershell
cd D:\custom-renderer
.\deploy\windows\start-service.bat
```

后台启动，适合测试机常驻：

```powershell
cd D:\custom-renderer
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-background.ps1
```

默认监听：

```text
http://0.0.0.0:8765
```

局域网访问地址是：

```text
http://测试机IP:8765/
```

如果要改端口，启动前设置环境变量：

```powershell
$env:CUSTOM_RENDERER_PORT="8000"
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-background.ps1
```

## 5. 开放防火墙

如果其他电脑访问不了，在测试机用管理员 PowerShell 执行：

```powershell
New-NetFirewallRule -DisplayName "Custom Renderer 8765" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
```

如果改成 8000，就把命令里的 `8765` 改成 `8000`。

## 6. 验证

在测试机执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\health-check.ps1
```

浏览器打开：

```text
http://127.0.0.1:8765/
```

确认能看到模板列表，并用一个小订单表格跑一次渲染。首次启动 Illustrator 可能会弹许可、字体或文件安全提示；测试机需要先人工打开 Illustrator 处理这些弹窗。

## 7. 停止与日志

停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\stop-service.ps1
```

后台启动不会显示控制台日志。需要看启动错误时，先停止后台进程，再使用前台启动：

```powershell
.\deploy\windows\start-service.bat
```

渲染任务和上传文件会生成到：

```text
output\service-jobs\
output\service-uploads\
```

这些是运行时数据，更新代码时不要覆盖或删除，除非确认不需要历史任务。

## 8. 更新部署

本机重新生成 zip 后，在测试机：

1. 先停止服务。
2. 备份测试机当前 `output\` 和按需备份 `config\templates.json`、`templates\`。
3. 用新包覆盖代码目录。
4. 重新执行 `install.ps1`。
5. 启动服务并跑 `health-check.ps1`。

更新时尽量避开正在渲染的任务，因为停止服务会中断内存中的当前请求。
