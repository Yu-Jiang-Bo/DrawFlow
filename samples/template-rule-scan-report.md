# Template Rule Scan Baseline

Generated: 2026-07-13

Source: `test/ai测试/模板样本规则/模板类型`

Command:

```powershell
python -m src.inspect_template_rules `
  --input-root "..\test\ai测试\模板样本规则\模板类型" `
  --output "output\template-rule-scans" `
  --resume
```

## Summary

| Category | Total | Scanned | Failed | Draft profiles |
|---|---:|---:|---:|---|
| 套装 | 1 | 1 | 0 | `pure_text: 1` |
| 尺寸+设计或图案+字体组+字体颜色 | 9 | 9 | 0 | `pure_text: 2`, `composite: 1`, `unclassified: 5`, `fixed_font_design: 1` |
| 纯文本 | 2 | 2 | 0 | `pure_text: 1`, `unclassified: 1` |
| 设计+固定字体 | 5 | 0 | 5 | `unclassified: 5` |
| Total | 17 | 12 | 5 | `pure_text: 4`, `composite: 1`, `unclassified: 11`, `fixed_font_design: 1` |

Thirteen drafts require manual review. Every draft remains unconfirmed even when automatic scanning succeeds.

## Failed Illustrator Scans

The following files could not be opened through Illustrator COM and were saved as `scan_failed` drafts with failure evidence:

- `设计+固定字体/JJMB202511032233377652.ai`
- `设计+固定字体/JJMB202603092028315766.ai`
- `设计+固定字体/JJMB202606040948134106.ai`
- `设计+固定字体/JJMB202606232022116923.ai`
- `设计+固定字体/JJMB202607061603501856.ai`

Observed COM error: `-2147417851` (`服务器出现意外情况`). These drafts must be rescanned successfully or configured and validated manually before confirmation.

## Generated Artifacts

The full evidence and editable drafts are reproducible and intentionally excluded from Git:

```text
output/template-rule-scans/scan-index.json
output/template-rule-scans/comparison-report.json
output/template-rule-scans/<template-key>/scan.json
output/template-rule-scans/<template-key>/rule-draft.json
```
