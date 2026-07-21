# DrawFlowClient 本地客户端

## 用法

1. 解压整个 zip，保留同级的 `DrawFlowClient.exe`、`_internal` 和 `drawflow-client.json`。
2. 确认本机已安装并激活 Adobe Illustrator，模板需要的字体也已安装。
3. 双击 `DrawFlowClient.exe`。程序直接使用包内正式中央地址，只监听 `127.0.0.1:8766`，并自动打开 `http://127.0.0.1:8766/`。
4. 仅在中央服务器地址变化时编辑同级 `drawflow-client.json`，不需要重新打包 exe。
5. 若页面提示生成失败，先保留页面上的完整错误文字；同时可查看 `%LOCALAPPDATA%\\DrawFlow\\logs\\drawflow-client.log` 的最后几行，二者一起用于定位问题。

## 本地职责

- 代理中央 DrawFlow 页面和 API。
- 拦截 `/local/render`、`/api/render`、`/local/templates/scan`。
- 按需下载所选模板 bundle，校验 SHA256 后缓存到 `%LOCALAPPDATA%\DrawFlow\templates`。
- 检查本机字体，调用本机 Illustrator 渲染，输出文件保存在 `%LOCALAPPDATA%\DrawFlow\output`。

当前正式中央地址为 `http://162.14.120.240:8765`。客户端不保存 DeepSeek API Key，也不读取开发项目目录中的脚本或配置；DeepSeek 只在中央服务中配置。
