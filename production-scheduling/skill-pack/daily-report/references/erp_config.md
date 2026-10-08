# 对接系统配置（daily-report 技能）

## 1. 金蝶云星空 ERP

| 项 | 值 |
|----|-----|
| 系统 | 金蝶云星空（K3Cloud） |
| 服务器地址 | https://<ERP 主机>/k3cloud/ |
| 账套ID | <账套ID> |
| 用户名 | 龙工平台 |
| 应用ID | <应用ID> |
| 应用密钥 | <应用密钥>（敏感，勿外泄） |
| 语系 | 2052（中文） |
| SDK | kingdee.cdp.webapi.sdk==8.2.0（pip 安装） |

> 配置集中在 `scripts/config.py`。分享技能时替换为接收方自己的账套/应用密钥。

## 2. 用到的 ERP 单据/表

| 表单ID | 用途 | 关键字段 |
|--------|------|----------|
| SAL_OUTSTOCK | 销售出库（销量/销售额） | FDate、FMaterialId.FName、FRealQty（实际出库数量，**非FQty**）、FAllAmount、FCustomerID.FName、FIsFree（赠品标识）、FStockOrgID、FStockId |
| AR_RECEIVEBILL | 收款单（回款） | FBillNo（单据号，带它查询才按分录行返回）、FDATE（收款日期）、FCONTACTUNIT.FName（客户）、FRECTOTALAMOUNTFOR（分录行金额·本位币，行级汇总=单据总额）；FRECAMOUNTFOR=单据头金额（多行单据每行重复整单金额，仅限不带FBillNo查询时使用） |
| STK_Inventory | 即时库存（库存快照） | FStockId、FMaterialId.FName/FNumber/FSpecification、FBaseQty、FAuxPropID（等级） |

**不可用/已废弃：** 生产订单(PRD_MO)、BOM、质检模块、调拨单、STK_MisDelivery（数据不完整）。

## 3. 核心业务常量（口径，来自客户确认，改动需人工确认）

定义位置：`scripts/query_kingdee.py`

| 常量 | 值 | 含义 |
|------|-----|------|
| AUXPROP_FILTER | `FAuxPropID IN (100001,100009)` | 等级口径：优等品=优等(100001)+优AA(100009)，2026-08-12客户确认 |
| ORGANIZATIONS | 某陶瓷企业=100080，B 基地=100082 | 仅这两个生产基地 |
| FINISHED_WAREHOUSE_FILTER | `FStockId IN (119400,177653)` | 仅成品一仓(某陶瓷企业)+成品三仓(B 基地) |
| INTERNAL_CUSTOMERS | 某销售中心、某陶瓷有限公司 | 内部/关联单，整单排除（销量+收款都排除） |
| WAREHOUSES | 某陶瓷企业=119400，B 基地=177653 | 快照拉取范围 |

## 4. 邮件（腾讯企业邮）

| 项 | 值 |
|----|-----|
| 账号 | <发件邮箱> |
| 客户端密码 | <邮箱授权码>（敏感，勿外泄） |
| SMTP | smtp.exmail.qq.com:465（SSL） |
| 用途 | 日报/快照发送（自收自发，收件人=发件人） |

## 5. 企微通道

| 项 | 值 |
|----|-----|
| 通道 | wecom |
| 账号ID | <企微账号ID> |
| 目标 | user:woaf8bCAAAjdrxzJhJIm4beSi2ux9hvg（用户企微对话） |

> 发送通过 `openclaw message send --channel wecom --account ... --target ...`，依赖 OpenClaw Gateway 已配置 wecom 通道。
