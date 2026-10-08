---
name: daily-report
description: 每日产销率&回款率日报（某陶瓷企业）。基于金蝶ERP（销售出库SAL_OUTSTOCK/收款单AR_RECEIVEBILL/即时库存STK_Inventory）+ 每日库存快照，生成①企微经营晨报（文本，9:00）②邮箱HTML日报+CSV附件（8:30）③库存快照（23:59）。指标：昨日产销率（快照反推产量）、月累计回款率、断货/积压预警、TOP5畅销。触发词：日报、晨报、产销率、回款率、经营日报、快照。
---

# 每日产销率 & 回款率日报（daily-report）

## 职责

某陶瓷企业每日经营日报的**唯一标准实现**：3个脚本 + 固定模板 + 固定口径，每天自动产出企微晨报与邮箱日报。与排产技能（prod-schedule）完全独立，不共享代码。

## 触发条件

- **定时**（主路径）：每天 23:59 快照 → 次日 08:30 邮箱日报 → 09:00 企微晨报（cron 配置见 `references/deployment.md`）
- **手动**：用户要求"生成/重发某日日报"、"预览日报"、"查产销率/回款率"时，按 `运行方式` 执行

## 数据流总览

```
金蝶ERP                         本地技能目录
─────────                       ─────────────
STK_Inventory ──23:59──▶ daily_stock_snapshot.py ──▶ data/snapshots/{date}.csv（全量，含0库存）
SAL_OUTSTOCK  ─┐
AR_RECEIVEBILL ┴─08:30──▶ daily_production_sales_report.py ──▶ 邮件HTML + 产销率CSV + 回款流水CSV
SAL_OUTSTOCK  ─┐
AR_RECEIVEBILL ┴─09:00──▶ daily_morning_report_wecom.py ──▶ 企微文本晨报
快照CSV(昨日+前日) ──────┘
```

## 运行方式

```bash
cd skills/daily-report/scripts

# ① 库存快照（每天23:59，产销率的前提）
python3 daily_stock_snapshot.py

# ② 邮箱日报（每天08:30，计算"昨天"并发送）
python3 daily_production_sales_report.py
python3 daily_production_sales_report.py --preview --date 2026-08-13   # 预览不发送

# ③ 企微晨报（每天09:00）
python3 daily_morning_report_wecom.py
python3 daily_morning_report_wecom.py --preview --date 2026-08-13     # 预览不发送
```

**人工重发某日**：`--date YYYY-MM-DD` 指定统计日（= 用户说的"昨天"），不加 --date 默认算昨天。

## 口径速查（详细规则见 references/calculation_rules.md）

| 项 | 口径 |
|----|------|
| 等级 | 优等品 = 优等(100001) + 优AA(100009) |
| 组织 | 某陶瓷企业(100080) + B 基地(100082) |
| 仓库 | 成品一仓(119400) + 成品三仓(177653) |
| 排除客户 | 某销售中心、某陶瓷有限公司（销量+回款都排除） |
| 赠品 | FIsFree=True，计入出库量不计金额 |
| 产销率 | 产量÷销量；产量=昨日末快照−前日末快照+昨日出库 |
| 回款率 | 月累计口径（销售出库回款率·业务指标）：当月1日~昨日收款(FRECTOTALAMOUNTFOR) ÷ 当月1日~昨日已审核销售额 |
| 收款字段 | AR_RECEIVEBILL：FDATE / FCONTACTUNIT.FName / FRECAMOUNTFOR |
| 预警 | 断货=在销且库存<500箱；积压=库存≥3000箱且30天零出库 |

## 模板文件（固定，勿随意改结构）

| 文件 | 内容 |
|------|------|
| `templates/wecom_template.md` | 企微晨报文本模板 + 每行参数来源 |
| `templates/email_template.md` | 邮箱HTML模板 + 各区块参数规则 |
| `templates/attachments_spec.md` | 3种CSV的列定义与编码规范 |

## 关键文件索引

| 文件 | 作用 |
|------|------|
| `scripts/config.py` | ⚙️ 所有环境配置（金蝶/邮件/企微/阈值/路径），分享迁移只改这里 |
| `scripts/query_kingdee.py` | 金蝶查询封装 + 业务口径常量（AUXPROP_FILTER等） |
| `references/erp_config.md` | 对接系统清单（账套/字段/常量值） |
| `references/calculation_rules.md` | 每个参数的计算规则（口径规范，改动需人工确认） |
| `references/deployment.md` | 部署步骤、cron配置、分享注意事项、FAQ |
| `data/snapshots/` | 库存快照历史（产销率反推前提） |

## 边界与注意事项

1. **快照缺失时降级**：产销率/库存/预警显示"快照不足"，销量+回款部分照常——属正常现象，不是故障。
2. **单据状态已过滤**：分母（销售出库）只统计已审核 FDOCUMENTSTATUS='C'（2026-08-14 用户确认，销售出库回款率口径）；分子（收款）暂未过滤状态，本月收款单均已完成审核、无实际影响。
3. **产量为反推值**：产量=快照差+出库，忽略杂项出入库，仅供经营参考，不是财务口径。
4. **敏感信息**：config.py / erp_config.md 含密钥与密码，分享技能前必须处理（见 deployment.md）。
5. **口径变更**：任何口径/阈值调整必须先在 references/calculation_rules.md 记录并经用户确认，再改代码。
