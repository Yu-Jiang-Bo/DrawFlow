# DrawFlowClient 更新载荷（非同事安装包）

此目录由发布流程生成，是 `DrawFlow.exe` 自动下载的版本化 PyInstaller 载荷，**不得直接发给同事，也不得手工解压后运行 `DrawFlowClient.exe`**。同事只接收并安装 `DrawFlow-Setup-<version>.exe`，之后只从开始菜单或桌面快捷方式启动 `DrawFlow.exe`。

运行时，启动器把候选载荷放入用户应用目录的唯一候选目录 `versions\<version>-<sha>-<uuid>`，健康检查通过后再由 `active.json` 记录该版本的实际目录，并通过 `DRAWFLOW_CENTRAL_URL` 向子进程传递中央服务地址。用户的模板缓存、任务记录和出图文件仍位于 `%LOCALAPPDATA%\DrawFlow`，不在本载荷中。

本地客户端继续代理中央 DrawFlow 页面和 API，拦截本机渲染/扫描接口，按需校验和缓存模板 bundle，并调用本机 Illustrator。若页面提示生成失败，先保留页面上的完整错误文字；同时可查看 `%LOCALAPPDATA%\DrawFlow\logs\drawflow-client.log` 和安装目录 `logs\launcher.log` 的最后几行，二者一起用于定位问题。
