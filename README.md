# Custom Renderer

定制效果图自动生成服务的初版实现。

## MVP

当前版本只实现最简单的纯文字模板：

```text
CSV/JSON 输入
→ 生成纯文字 render task
→ Illustrator 执行 scripts/illustrator/render_text.jsx
→ 输出 Illustrator 8 兼容 .ai
```

## 干跑验证

不启动 Illustrator，只生成 render task：

```powershell
python -m src.main --csv samples/orders_text.csv --output output --dry-run
```

## 实际渲染

需要 Windows + Adobe Illustrator + pywin32：

```powershell
python -m src.main --csv samples/orders_text.csv --output output
```

## JJMB202603281027102517 模板纯文字渲染

当前只处理字体选项 `F1-F9` 的纯文字订单，`F10-F12` 设计字体先跳过。

```powershell
python -m src.jjmb_template_main `
  --xlsx "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\C-208.xlsx" `
  --template-ai "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\JJMB202603281027102517.ai" `
  --output output\jjmb202603281027102517-text `
  --dry-run
```

实际渲染会调用 Illustrator，并从模板里读取 `字体区/F1-F9` 的字体属性和 `作图区/Style1-Style5` 的方框尺寸：

```powershell
python -m src.jjmb_template_main `
  --xlsx "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\C-208.xlsx" `
  --template-ai "C:\Users\Administrator\Desktop\image\test\ai测试\JJMB202603281027102517--文本+颜色\JJMB202603281027102517\JJMB202603281027102517.ai" `
  --output output\jjmb202603281027102517-text `
  --limit 1
```

如果 Illustrator COM 启动失败，可以先 dry-run 生成 `render-tasks/*.json`，再在 Illustrator 中运行：

```text
scripts/illustrator/run_render_template_text_task.jsx
```

运行后选择对应的 render task JSON 即可手动渲染。
