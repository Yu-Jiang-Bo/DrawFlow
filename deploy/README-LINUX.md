# DrawFlow Linux 中央服务部署

本包只部署 DrawFlow 中央服务，不部署 Illustrator。真实模板扫描和 AI8 渲染继续在安装了 Illustrator 的 Windows 客户端完成。

## 端口边界

- 旧项目端口：`8000`，本包不会停止、覆盖或复用它。
- DrawFlow 默认端口：`8765`。
- 本包脚本发现端口被占用时会直接失败，不会杀掉未知进程。

## 包内容

```text
src/
config/
templates/
deploy/linux/
requirements.txt
```

运行时模板版本数据放在 `DRAWFLOW_DATA_DIR` 指定的外部目录，推荐为 `/opt/drawflow-data`。不要把真实 API Key、密码或 `.env` 文件放入发布 ZIP。

## 安装

在 Linux 测试机上解压到独立目录，例如 `/opt/drawflow-central`，不要覆盖旧项目目录：

```bash
mkdir -p /opt/drawflow-central
unzip -q drawflow-central-linux-*.zip -d /opt/drawflow-central
cd /opt/drawflow-central
chmod +x deploy/linux/*.sh
cp deploy/linux/drawflow.env.example drawflow.env
chmod 600 drawflow.env
```

编辑 `drawflow.env`，只在中央服务上填写 `DRAWFLOW_LLM_API_KEY`、`DRAWFLOW_LLM_BASE_URL` 和模型。客户端不需要这些变量。

安装 Python 依赖。项目要求 Python 3.10 或更高版本；脚本会在创建虚拟环境前检查版本：

```bash
./deploy/linux/install.sh
```

如果创建虚拟环境失败，按发行版安装 `python3-venv` 后重试。安装脚本不会自动安装操作系统软件包。

## 运行与检查

前台运行，适合首次查看日志：

```bash
./deploy/linux/start-service.sh
```

后台运行：

```bash
./deploy/linux/start-background.sh
./deploy/linux/status.sh
./deploy/linux/health-check.sh
```

预期健康检查包含：

```json
{"ok": true, "role": "central", "illustrator": "not_required"}
```

中央服务开始监听前会自动检查 `config/templates.json` 中所有已启用模板。没有活动版本、活动文件损坏、或随新中央包交付的模板/规则/结构配置/素材发生变化时，会生成下一不可变版本并更新 `active.json`；内容未变化时复用当前版本。任一已启用模板无法生成完整运行包时，服务会直接启动失败并在错误日志中指出模板 ID，不会出现健康检查成功但模板无法下载的状态。

停止 DrawFlow 自己的进程：

```bash
./deploy/linux/stop-service.sh
```

脚本只使用自己的 PID 文件并校验进程命令，不会停止旧项目的 `uvicorn`。

## 模板运行数据

如果已有 Windows 中央服务的运行数据，把完整的 `C:\DrawFlow\Data` 内容迁移到 Linux 的 `/opt/drawflow-data`，保留以下结构：

```text
/opt/drawflow-data/templates/<template_id>/active.json
/opt/drawflow-data/templates/<template_id>/versions/v0001/manifest.json
/opt/drawflow-data/templates/<template_id>/versions/v0001/template.ai
/opt/drawflow-data/templates/<template_id>/versions/v0001/rules.json
/opt/drawflow-data/templates/<template_id>/versions/v0001/template.config.json  # 需要结构配置的模板
/opt/drawflow-data/templates/<template_id>/versions/v0001/assets/
/opt/drawflow-data/templates/<template_id>/versions/v0001/template-bundle.zip
```

迁移后检查：

```bash
./deploy/linux/health-check.sh
curl http://127.0.0.1:8765/api/runtime/templates/<template_id>/manifest
manifest_version="$(curl -sS http://127.0.0.1:8765/api/runtime/templates/<template_id>/manifest | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')"
curl -o /tmp/drawflow-bundle.zip "http://127.0.0.1:8765/api/runtime/templates/<template_id>/bundle/$manifest_version"
```

### 从 Windows 中央服务迁移已有运行数据

如果模板已经发布在 Windows 的 `C:\DrawFlow\Data`，可以先在 Windows 测试机导出，再传到 Linux。不要把 API Key 或其他环境配置放进压缩包：

Windows PowerShell：

```powershell
Compress-Archive -Path "C:\DrawFlow\Data\*" -DestinationPath "C:\DrawFlow\drawflow-data.zip" -Force
scp "C:\DrawFlow\drawflow-data.zip" "<linux-user>@<linux-public-host>:/tmp/drawflow-data.zip"
```

Linux 测试机：

```bash
mkdir -p /opt/drawflow-data
unzip -q /tmp/drawflow-data.zip -d /opt/drawflow-data
chmod -R u+rwX /opt/drawflow-data
```

如果 Linux 服务使用 systemd 的 `drawflow` 用户运行，还需要把 `/opt/drawflow-data` 的所有者改为该用户，再启动服务。迁移完成后，`drawflow.env` 中的 `DRAWFLOW_DATA_DIR` 必须与此目录一致。

## 外部访问

先在 Linux 本机确认 `health-check.sh` 成功，再在云平台安全组只允许受控来源访问 TCP `8765`。不要把 `192.168.*` 这类客户端局域网地址填入云安全组；云平台看到的是客户端公网出口 IP。

客户端电脑验证：

```powershell
Test-NetConnection <linux-public-host> -Port 8765
Invoke-RestMethod "http://<linux-public-host>:8765/api/health"
```

客户端配置 `drawflow-client.json`：

```json
{
  "central_url": "http://<linux-public-host>:8765"
}
```

当前 MVP 未提供完整登录鉴权，不要把 `8765` 对全网开放。长期公网使用应增加 HTTPS、鉴权和更细的访问控制。

## 旧项目保护

旧项目位于其他目录并使用 `8000`。DrawFlow 部署时不要执行旧项目的 `pkill`、不要覆盖旧项目目录、不要直接复用 `8000`。如需 systemd，可复制 `deploy/linux/drawflow-central.service.example`，确认 `drawflow` 用户和路径后再启用。
