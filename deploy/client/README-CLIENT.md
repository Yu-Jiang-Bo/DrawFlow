# DrawFlowClient 本地客户端

## 用法

1. 解压整个 zip，保留同级的 `DrawFlowClient.exe`、`_internal` 和 `drawflow-client.json`。
2. 确认本机已安装并激活 Adobe Illustrator，模板需要的字体也已安装。
3. 双击 `DrawFlowClient.exe`。程序直接使用包内正式中央地址，只监听 `127.0.0.1:8766`，并自动打开 `http://127.0.0.1:8766/`。
4. 仅在中央服务器地址变化时编辑同级 `drawflow-client.json`，不需要重新打包 exe。
5. V2 工作台的真实样例预览需要可信 Windows 工作端与中央服务配置同一 `DRAWFLOW_PREVIEW_WORKER_SECRET`。该密钥不在压缩包内：由演示管理员在受控环境中为本机进程设置后，再启动客户端；不要把它填到 `drawflow-client.json`、页面、日志或截图中。设置完成后，可在工作台对已发布模板执行一次真实样例预览确认。
6. 若页面提示生成失败，保留页面中的用户可读提示；同时可查看 `%LOCALAPPDATA%\\DrawFlow\\logs\\drawflow-client.log` 的最后几行，用于定位问题。

## 本地职责

- 代理中央 DrawFlow 页面和 API。
- 拦截 `/local/render`、`/api/render`、`/local/templates/scan`。
- 按需下载所选模板 bundle，校验 SHA256 后缓存到 `%LOCALAPPDATA%\DrawFlow\templates`。
- 检查本机字体，调用本机 Illustrator 渲染，输出文件保存在 `%LOCALAPPDATA%\DrawFlow\output`。

当前正式中央地址为 `http://162.14.120.240:8765`。客户端不保存 DeepSeek API Key，也不读取开发项目目录中的脚本或配置；DeepSeek 只在中央服务中配置。
