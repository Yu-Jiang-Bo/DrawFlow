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
