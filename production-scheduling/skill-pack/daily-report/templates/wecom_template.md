# 企微经营晨报模板（daily-report 技能）

> 发送渠道：企微对话（openclaw CLI，账号/目标见 `scripts/config.py` 的 WECOM_ACCOUNT / WECOM_TARGET）
> 发送脚本：`scripts/daily_morning_report_wecom.py`
> 文本为纯文本，无 Markdown 表格；每行含义与数据来源见下方标注。

## 模板原文

```
📅 某陶瓷企业 · 经营晨报（{date_str}）

数据来源：金蝶ERP 销售出库/即时库存/收款单 · 统计日：{MM-DD} · 口径：优等+优AA / 某陶瓷企业+B 基地 / 成品一仓+三仓 / 排除内部单

🏭 昨日产销率：{overall_rate:.1f}%｜{产销平衡|库存累积|消化库存|快照不足}
产量 {total_prod:,.0f}箱 / 销量 {y_total_qty:,.0f}箱

📊 昨日经营概况
▫ 昨日出库：{y_total_qty:,.0f}箱 / {y_total_amt}万元（赠品{y_total_free:,.0f}箱）
▫ 环比前日：{qty_chg:+.1f}%（金额{amt_chg:+.1f}%）
▫ 发货客户：{len(y_customers)}家
▫ 成品仓优等品库存：{stock_total/10000:.1f}万箱 / {sku_count:,}个SKU / 可撑{days_total:.0f}天

📈 昨日 TOP{TOP_N} 畅销产品（库存天数=当前库存÷近30天日均出库）
1️⃣ {产品} — {qty:,.0f}箱 / {amt}万 / 可撑{days:.1f}天 {🔴|✅}
2️⃣ ...

💰 回款率（{YYYY-MM}月累计）：{rate_overall:.1f}%
本月收款 {total_receipt}万 / 本月销售额 {month_sales_amt}万

⚠ 预警
🔴 断货预警：{产品}（库存0箱）...——今日在销但成品仓库存不足500箱，建议优先排产补货
🟠 积压预警：{产品}（9,664箱）...——≥3,000箱且近30天零出库，合计{total}箱，建议促销去化
```

## 每行参数说明

| 行 | 参数 | 计算规则 | 数据来源 |
|----|------|----------|----------|
| 标题 | `date_str` | 统计日 = 昨天（运行日−1天） | — |
| 口径行 | — | 固定文案 | — |
| 产销率 | `overall_rate` | 产量÷销量×100；产量 = 昨日末快照−前日末快照+昨日出库；销量 = 昨日出库量（日报口径） | 快照CSV + SAL_OUTSTOCK |
| 产量/销量 | `total_prod` / `y_total_qty` | 产量=Σ各产品反推产量(>0)；销量=昨日出库箱数合计 | 同上 |
| 昨日出库 | `y_total_qty` / `y_total_amt` | SAL_OUTSTOCK 按 FDate=统计日 聚合 FRealQty / FAllAmount | SAL_OUTSTOCK |
| 赠品 | `y_total_free` | FIsFree=True 的行数量合计（金额恒为0，不计入销售额） | SAL_OUTSTOCK |
| 环比前日 | `qty_chg` / `amt_chg` | (昨日−前日)÷前日×100 | SAL_OUTSTOCK |
| 发货客户 | `len(y_customers)` | 昨日出库单去重客户数（排除内部客户） | SAL_OUTSTOCK |
| 库存总量 | `stock_total` / `sku_count` | 统计日快照全量合计（两仓合并，仅优等品） | 快照CSV |
| 可撑天数 | `days_total` | 总库存÷近30天日均出库（30天出库÷30） | 快照CSV + SAL_OUTSTOCK |
| TOP5 每行 | `qty` / `amt` / `days` | 按昨日出库量降序取前5；可撑天数=当前库存÷该产品近30天日均出库；🔴=可撑<3天或库存<500箱 | SAL_OUTSTOCK + 快照CSV |
| 回款率 | `rate_overall` | 当月1日~统计日收款额(AR_RECEIVEBILL.FRECTOTALAMOUNTFOR) ÷ 当月1日~统计日已审核销售额(SAL_OUTSTOCK.FAllAmount, FDOCUMENTSTATUS='C')×100 | AR_RECEIVEBILL + SAL_OUTSTOCK |
| 本月收款 | `total_receipt` | AR_RECEIVEBILL.FRECAMOUNTFOR 按 FDate∈[当月1日,统计日] 汇总（排除内部客户） | AR_RECEIVEBILL |
| 本月销售额 | `month_sales_amt` | SAL_OUTSTOCK.FAllAmount 按 FDate∈[当月1日,统计日] 汇总（日报口径） | SAL_OUTSTOCK |
| 断货预警 | — | 统计日在销（出库>0）但库存<500箱，按昨日销量降序，最多列4个 | 快照CSV + SAL_OUTSTOCK |
| 积压预警 | — | 库存≥3000箱 且 近30天零出库，按库存降序，最多列2个 | 快照CSV + SAL_OUTSTOCK |

## 降级规则

- 快照缺失（缺统计日或前一日任一）：产销率/库存/预警部分显示"快照不足"提示，其余部分照常输出。
- 出库窗口任一分段触及 API Limit=10000：向 stderr 打印警告（结果可能不完整，需人工复核）。

## 发送方式

```bash
openclaw message send --channel wecom --account {WECOM_ACCOUNT} --target {WECOM_TARGET} --message "{文本}"
```
