# DrawFlow 部署检查点（2026-07-15）

## 当前结论

DrawFlow 代码、Windows 发布包和无需 Illustrator 的本地验收已经完成。Windows 测试机已成功通过远程桌面登录，但最终发布包尚未传入测试机，因此测试机上的 Python 安装、服务启动、端口开放和外部访问验证还没有执行。

Illustrator 安装及真实 `.ai` 渲染按约定暂停，待咨询同事后继续。测试机凭据和 DeepSeek API Key 均未写入仓库、文档或发布包。

## 已完成

- 对外项目名称改为 `DrawFlow`，Web 标题、服务日志、README、部署脚本和发布包名称已同步。
- `DRAWFLOW_LLM_*` 环境变量优先，并兼容原 `CUSTOM_RENDERER_*` 变量。
- `/api/render` 增加单任务锁；并发任务返回 HTTP 409，异常后释放锁。
- Windows 安装、前后台启动、停止、健康检查、DeepSeek 配置、登录启动和 Illustrator 检查脚本已补齐。
- 发布包隐私门禁已覆盖本机路径、服务器地址、私钥、API Key、密码、token 和敏感文件名。
- 全量测试通过：`247 passed`。
- PowerShell 脚本语法检查通过。
- 两阶段代码审查复审通过，无遗留 HIGH/MEDIUM 问题。
- 从最终发布目录独立启动验证通过：`/api/health` 为 `ok`、模板数量为 `4`、DeepSeek 规则解析成功。

## 最终交付物

- 发布包：`release/drawflow-windows-20260715-2111.zip`
- SHA256：`F343687FDC224765D687D0EAA9CA7977DF80D189EFF02F6334915ED11C5FAE2A`
- 部署流程：`deploy/DEPLOY-WINDOWS.md`

不要使用较早的 `drawflow-windows-20260715-2100.zip` 或旧 `custom-renderer-*` 发布包。

## 当前卡点

- 远程桌面文件剪贴板没有把 63.15 MB 的 zip 粘贴到测试机桌面。
- 测试机文件管理器已经打开，但本机磁盘映射 `\\tsclient\C` 尚未确认可用。
- 用户按下 Escape 停止了远程操作；应从传包步骤恢复，不需要重做代码、测试或打包。

## 明天恢复顺序

1. 重新进入现有 Windows 测试机远程桌面。
2. 优先使用启用“本地资源 > 本地设备和资源 > 驱动器”的 RDP 连接，把最终 zip 从本机映射盘复制到测试机；若仍不可用，由用户手动粘贴最终 zip。
3. 将 zip 解压到 `C:\DrawFlow`，不要套多一层发布包目录。
4. 检查测试机是否已有 Python 3；没有则先安装官方 64 位 Python 并加入 PATH。
5. 按 `deploy/DEPLOY-WINDOWS.md` 依次执行安装依赖、配置 DeepSeek、后台启动、健康检查和登录启动注册。
6. 放行 Windows 防火墙 TCP `8765`，并确认腾讯云安全组已放行同一端口。
7. 在测试机本地验证健康接口、4 个模板和 DeepSeek 解析；再从同事电脑访问 `http://<测试机公网IP>:8765`。
8. Illustrator 到位后，执行 `deploy/windows/test-illustrator.ps1`，最后补一笔真实订单效果图渲染验收。

## 验收边界

当前可以验收 Web 页面、模板读取、任务记录、DeepSeek 规则解析和 dry-run。没有安装 Illustrator 前，不能把真实 `.ai` 渲染标记为通过。

工作区中原有模板、测试缓存等未提交改动均未清理或回退；继续工作时应保留这些用户改动。
