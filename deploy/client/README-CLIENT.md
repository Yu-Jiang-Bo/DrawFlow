# DrawFlow 桌面客户端

## 用法

1. 安装管理员提供的 `DrawFlow-Setup-<version>.exe`；不要单独复制 `DrawFlowClient.exe` 或 `_internal`。
2. 确认本机已安装并激活 Adobe Illustrator，模板需要的字体也已安装。
3. 从开始菜单或桌面快捷方式启动 `DrawFlow`。程序在独立窗口中运行，后台本地网关只监听 `127.0.0.1:8766`，不打开系统浏览器。
4. 程序更新时安装管理员提供的新 Setup 安装包；覆盖安装不会删除 `%LOCALAPPDATA%\\DrawFlow` 下的任务、输出、日志和模板缓存。
5. V2 工作台的真实样例预览需要可信 Windows 工作端与中央服务配置同一 `DRAWFLOW_PREVIEW_WORKER_SECRET`。该密钥不在安装包内：由演示管理员在受控环境中为本机进程设置后，再启动客户端；不要把它填到配置、页面、日志或截图中。
6. 若页面提示生成失败，保留页面中的用户可读提示；同时可查看 `%LOCALAPPDATA%\\DrawFlow\\logs\\drawflow-client.log` 的最后几行，用于定位问题。

## 本地职责

- 代理中央 DrawFlow 页面和 API。
- 拦截 `/local/render`、`/api/render`、`/local/templates/scan`。
- 按需下载所选模板 bundle，校验 SHA256 后缓存到 `%LOCALAPPDATA%\DrawFlow\templates`。
- 检查本机字体，调用本机 Illustrator 渲染，输出文件保存在 `%LOCALAPPDATA%\DrawFlow\output`。

当前正式中央地址由安装包构建时写入。客户端不保存 DeepSeek API Key，也不读取开发项目目录中的脚本或配置；DeepSeek 只在中央服务中配置。
