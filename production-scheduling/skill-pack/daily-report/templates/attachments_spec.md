# CSV 附件规范（daily-report 技能）

> 所有 CSV 均用 `utf-8-sig` 编码（带BOM），Excel 直接打开不乱码；换行符 `\n`。

## 1. 库存快照 CSV（daily_stock_snapshot.py 生成）

- 位置：`data/snapshots/{YYYY-MM-DD}.csv`
- 同时追加写入 `data/snapshots/all_snapshots.csv`（累计，用于趋势分析）

| 列 | 说明 |
|----|------|
| 日期 | 快照日期 YYYY-MM-DD |
| 仓库 | 某陶瓷企业 / B 基地 |
| 物料编码 | 产品名（ERP FName，排产表编码口径） |
| 系统编码 | ERP FNumber（MAT.xxx 系统编码） |
| 规格 | FMaterialId.FSpecification |
| 库存(箱) | FBaseQty 合计，仅优等品（优等100001+优AA 100009） |

**要点：库存为0的行也保留**（产销率反推依赖，漏掉会导致产量虚增）。

## 2. 产销率 CSV（daily_production_sales_report.py 附件）

- 文件名：`产销率-{YYYY-MM-DD}.csv`

| 列 | 说明 |
|----|------|
| 产品 | 产品名（FName） |
| 产量(箱) | 昨日末快照−前日末快照+昨日出库（>0才列出） |
| 销量(箱) | 昨日出库量（日报口径） |
| 产销率(%) | 产量÷销量×100；无销量标"无销量" |

## 3. 回款流水 CSV（daily_production_sales_report.py 附件）

- 文件名：`回款流水-{YYYY-MM}.csv`
- **每笔收款一行**（不聚合），含收款日期

| 列 | 说明 |
|----|------|
| 收款日期 | AR_RECEIVEBILL.FDATE（YYYY-MM-DD） |
| 客户 | FCONTACTUNIT.FName（排除内部客户后） |
| 收款金额(元) | FRECAMOUNTFOR（本位币） |

- 排序：先按日期、再按客户名
