# DrawFlow 中央服务更新流程

本文档记录更新已有中央服务的标准流程。不是从 0 部署；只用于替换 `/opt/drawflow-central` 代码目录，并保留线上 `drawflow.env` 与 `/opt/drawflow-data` 运行数据。

## 固定环境

- 服务器：`root@162.14.120.240`
- 中央服务地址：`http://162.14.120.240:8765`
- 线上代码目录：`/opt/drawflow-central`
- 线上数据目录：`/opt/drawflow-data`
- 上传目录：`/tmp`

## 出包前硬性检查

中央服务 ZIP 生成前必须通过 `deploy/package-linux-central.ps1` 的门禁：

- `config/templates.json` 中所有 `status=active` 模板的 `template_ai` 必须在包内存在，且必须是 `.ai` 文件。
- `assets[].stored_path` 中所有 `.ai` 资产必须在包内存在。
- `deploy/linux/*.sh` 必须在包内转为 LF 换行，避免 Linux 上出现 `bash\r`。
- 缺任一项不得上传、解压、停服或替换线上目录。

## 1. 本机上传包

执行位置：Windows Git Bash。

把下面命令中的包名替换为本次实际包名。示例使用 `drawflow-central-linux-20260723-1316.zip`：

```bash
scp -- "/c/Users/Administrator/Desktop/image/custom-renderer-master-jjmb-202603-merge/release/drawflow-central-linux-20260723-1316.zip" "root@162.14.120.240:/tmp/drawflow-central-linux-20260723-1316.zip"
```

预期输出：上传进度到 `100%`。

## 2. 登录服务器

执行位置：Windows Git Bash。

```bash
ssh root@162.14.120.240
```

预期进入服务器提示符，例如：

```text
[root@VM-16-136-opencloudos ~]#
```

后续 `/tmp` 和 `/opt` 命令必须在服务器提示符下执行。

## 3. 校验上传包

执行位置：服务器。

```bash
sha256sum /tmp/drawflow-central-linux-20260723-1316.zip
```

预期输出必须与本机出包时记录的 SHA256 一致。示例：

```text
dfbaaba6754ef2d83fe0133624ec600c9547a85ea9bdd6d801c746d2e75a09d8  /tmp/drawflow-central-linux-20260723-1316.zip
```

不一致就停止，重新上传。

## 4. 设置更新变量

执行位置：服务器。

```bash
RELEASE_ID=drawflow-central-linux-20260723-1316
PROJECT_DIR=/opt/drawflow-central
STAGE_DIR=/opt/drawflow-central-stage-$RELEASE_ID
FAILED_DIR=/opt/drawflow-central-failed-before-$RELEASE_ID-$(date +%Y%m%d-%H%M%S)
```

预期输出：无输出。

## 5. 解压到临时目录

执行位置：服务器。

```bash
unzip -q -o /tmp/drawflow-central-linux-20260723-1316.zip -d "$STAGE_DIR"
```

如果只出现下面警告，可以继续：

```text
appears to use backslashes as path separators
```

只要没有中断报错即可。

## 6. 给新包脚本执行权限

执行位置：服务器。

```bash
chmod +x "$STAGE_DIR"/deploy/linux/*.sh
```

预期输出：无输出。

## 7. 复制线上配置

执行位置：服务器。

```bash
cp -p "$PROJECT_DIR/drawflow.env" "$STAGE_DIR/drawflow.env"
chmod 600 "$STAGE_DIR/drawflow.env"
```

预期输出：无输出。

不得用 ZIP 中的示例配置覆盖线上 `drawflow.env`。

## 8. 停止当前服务

执行位置：服务器。

```bash
cd "$PROJECT_DIR"
```

```bash
./deploy/linux/stop-service.sh
```

如果旧目录脚本没有执行权限，先执行：

```bash
chmod +x deploy/linux/*.sh
./deploy/linux/stop-service.sh
```

可接受输出：

```text
Stopped DrawFlow PID <PID>.
```

或：

```text
DrawFlow PID file not found: /opt/drawflow-central/output/logs/drawflow.pid
```

或：

```text
DrawFlow process is not running.
```

## 9. 切换目录

执行位置：服务器。

```bash
mv "$PROJECT_DIR" "$FAILED_DIR"
```

```bash
mv "$STAGE_DIR" "$PROJECT_DIR"
```

预期输出：无输出。

不要删除旧目录；`FAILED_DIR` 是本次切换前的备份/问题目录。

## 10. 安装依赖

执行位置：服务器。

```bash
cd "$PROJECT_DIR"
```

```bash
chmod +x deploy/linux/*.sh
```

```bash
./deploy/linux/install.sh
```

预期末尾包含：

```text
DrawFlow Linux install complete.
Project: /opt/drawflow-central
Data: /opt/drawflow-data
```

## 11. 启动服务

执行位置：服务器。

```bash
./deploy/linux/start-background.sh
```

预期输出：

```text
Started DrawFlow central service with PID <PID> on http://0.0.0.0:8765
Logs: /opt/drawflow-central/output/logs/drawflow.log and /opt/drawflow-central/output/logs/drawflow.error.log
```

失败时立即查看：

```bash
tail -n 160 /opt/drawflow-central/output/logs/drawflow.error.log
```

## 12. 服务健康检查

执行位置：服务器。

```bash
./deploy/linux/status.sh
```

预期输出：

```text
DrawFlow running: PID=<PID> URL=http://0.0.0.0:8765
```

```bash
./deploy/linux/health-check.sh
```

预期返回 JSON：

```json
{
  "ok": true,
  "role": "central",
  "illustrator": "not_required",
  "runtime_templates": "/opt/drawflow-data/templates"
}
```

## 13. 模板列表检查

执行位置：服务器。

```bash
curl -fsS "http://127.0.0.1:8765/api/templates" | python3 -m json.tool
```

预期：返回有效 JSON；所有 active 模板 `rule_check.renderable` 应为 `true`。允许 legacy pipeline 出现 warning，但不允许 active 模板缺 `.ai`。

## 14. 关键模板 manifest 检查

执行位置：服务器。

```bash
curl -fsS "http://127.0.0.1:8765/api/runtime/templates/JJMB202509231236046265/manifest" | python3 -m json.tool
```

预期：

- `template_id` 为 `JJMB202509231236046265`
- `files` 中包含 `template.ai`
- `files` 中包含 `template.config.json`
- `assets` 中包含 title design `.ai`

继续检查：

```bash
curl -fsS "http://127.0.0.1:8765/api/runtime/templates/JJMB202603281027102517/manifest" | python3 -m json.tool
```

预期：

- `template_id` 为 `JJMB202603281027102517`
- `files` 中包含 `template.ai`
- `files` 中包含 `template.config.json`
- `assets` 中包含对应 `.ai` 资产

## 15. 外网健康检查

执行位置：本机 Git Bash 或 PowerShell。

```bash
curl -fsS "http://162.14.120.240:8765/api/health"
```

预期返回 JSON，且 `ok` 为 `true`。

## 16. 回滚流程

仅在启动失败、健康检查失败或 manifest 检查失败时执行。

执行位置：服务器。

```bash
echo "$FAILED_DIR"
```

确认有输出后执行：

```bash
cd /opt/drawflow-central
./deploy/linux/stop-service.sh
```

```bash
ROLLBACK_BAD_DIR=/opt/drawflow-central-failed-after-$RELEASE_ID-$(date +%Y%m%d-%H%M%S)
mv /opt/drawflow-central "$ROLLBACK_BAD_DIR"
mv "$FAILED_DIR" /opt/drawflow-central
cd /opt/drawflow-central
chmod +x deploy/linux/*.sh
./deploy/linux/start-background.sh
./deploy/linux/health-check.sh
```

预期：旧版本恢复，健康检查返回 `ok: true`。

## 本次 2026-07-23 更新验收记录

- 包名：`drawflow-central-linux-20260723-1316.zip`
- SHA256：`dfbaaba6754ef2d83fe0133624ec600c9547a85ea9bdd6d801c746d2e75a09d8`
- 启动 PID：`3932241`
- 健康检查：`ok: true`
- `JJMB202509231236046265` manifest：通过，版本 `v0003`
- `JJMB202603281027102517` manifest：通过，版本 `v0004`
