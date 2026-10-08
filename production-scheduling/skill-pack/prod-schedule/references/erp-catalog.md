# 某陶瓷企业 · 金蝶ERP数据资产清单

**最后修正：** 2026-08-12（等级过滤修正：优等品 = 优等100001 + 优AA 100009；内部客户排除）
**对接方式：** 金蝶云星空 WebAPI （Python SDK V8.2.0）

---

## ⚠️ 核心修正记录

| 日期 | 修正内容 |
|------|---------|
| 2026-07-28 初版 | FName vs FNumber：排产表编码对应BD_MATERIAL的FName字段 |
| 2026-07-28 v2 | **库存**：仅查成品一仓(某陶瓷企业)+成品三仓(B 基地)，不查全仓库 |
| 2026-07-28 v2 | **销量**：用 SAL_OUTSTOCK 替代 STK_MisDelivery，1,013条完整记录 |
| 2026-07-31 | **🔑 等级过滤**：库存和销量均过滤 FAuxPropID=100001（优等品），排除一等品/合格品 |
| 2026-08-12 | **🔑 等级过滤修正**：优等品 = 优等(100001) + **优AA(100009)**（客户确认）；排除内部客户（某销售中心、某陶瓷有限公司） |

---

## 一、ERP对接配置

```
账套ID:     <账套ID>
用户名:     龙工平台
应用ID:     <应用ID>
应用密钥:    <应用密钥>
服务器地址:  https://<ERP 主机>/k3cloud/
语言:       2052（中文）
```

```python
from k3cloud_webapi_sdk.main import K3CloudApiSdk
api_sdk = K3CloudApiSdk("https://<ERP 主机>/k3cloud/")
api_sdk.InitConfig(
    acct_id='<账套ID>', user_name='龙工平台',
    app_id='<应用ID>',
    app_secret='<应用密钥>',
    server_url='https://<ERP 主机>/k3cloud/', lcid=2052
)
```

---

## 二、组织架构

| OrgId | 编码 | 名称 | 排产数据范围 |
|-------|------|------|------------|
| 1 | 100 | 某陶瓷企业集团 | — |
| **100080** | 100.01 | **某陶瓷企业生产基地** | ✅ 库存+销量 |
| **100082** | 100.02 | **B 基地生产基地** | ✅ 库存+销量 |
| 100083 | 100.03 | D 基地 | ❌ 不在范围 |
| 100084 | 100.04 | 品牌中心 | ❌ 不在范围 |
| 101830 | 100.05 | 某分公司 | ❌ 不在范围 |
| 101831 | 100.06 | 西北分公司 | ❌ 不在范围 |
| 350714 | 100.0301 | D2 基地 | ❌ 不在范围 |

---

## 三、关键仓库（仅某陶瓷企业+B 基地下的成品仓）

| StockId | 名称 | 编号 | 所属组织 | 是否计入排产 |
|---------|------|------|---------|------------|
| **119400** | **成品一仓** | A01 | 某陶瓷企业(100080) | ✅ 计入 |
| **177653** | **成品三仓** | CK001 | B 基地(100082) | ✅ 计入 |
| 119401 | D 基地仓(某陶瓷企业) | A05 | 某陶瓷企业(100080) | ❌ 外厂仓 |
| 119402 | 某陶瓷企业(KR) | A06 | 某陶瓷企业(100080) | ❌ 外厂仓 |
| 119403 | 样品仓 | A13 | 某陶瓷企业(100080) | ❌ 样品 |
| 119404 | 待处理仓 | A14 | 某陶瓷企业(100080) | ❌ |
| 289430 | 样品仓 | CK003 | B 基地(100082) | ❌ 样品 |

> **库存数据 = 成品一仓(119400) + 成品三仓(177653) 的库存之和**
> 
> 后续如需增加仓库（如D 基地仓等），客户会说明。

---

## 四、可用数据表清单

### 1️⃣ 物料主数据 — BD_MATERIAL ✅

| 字段 | 含义 | 示例 | 用途 |
|------|------|------|------|
| **FName** ⭐ | 物料名称 | `MSA6Z006-HB`、`HL7K010-HB` | **排产表编码匹配此字段** |
| FNumber | 系统编码 | `MAT.010301120021` | 内部编码，不用于匹配 |
| FMasterId | 内部ID | `110293` | 关联库存和出库查询 |
| FSpecification | 规格 | `750*1500` | 规格验证 |

**查询方式：**
```python
# ✅ 按 FName 匹配排产表编码
api_sdk.ExecuteBillQuery({
    "FormId": "BD_MATERIAL",
    "FieldKeys": "FMasterId,FName,FNumber,FSpecification",
    "FilterString": "FName = 'HL7K010-HB'",
})

# -HB编码查不到时，去掉后缀重试
# 如 'RM15T20-HB' 查不到 → 查 'RM15T20'
```

**实测匹配率：** 89%（31/35，750×1500规格例）

---

### 2️⃣ 即时库存 — STK_Inventory ✅

| 字段 | 说明 | 用途 |
|------|------|------|
| FMaterialId | 物料ID | 从 BD_MATERIAL.FMasterId 获取 |
| FBaseQty | 库存数量（箱） | 汇总为总库存 |
| FStockId | 仓库ID | **必须过滤**，仅保留成品仓 |
| FStockName | 仓库名称 | 展示用 |
| FStockOrgId | 所属组织 | 可用但非必须（StockId已限定组织） |
| **FAuxPropID** ⭐ | **辅助属性(产品等级)** | **必须过滤 IN (100001,100009)：优等品+优AA** |

> **🔑 优等品过滤规则（2026-07-31新增，2026-08-12修正）：**
> 所有库存查询必须加 `AND FAuxPropID IN (100001,100009)`。
> FAuxPropID值分布：100001=优等品(95%+), **100009=优AA（客户2026-08-12确认也算优等品）**, 100008/100012/100013=其他等级, 0=无等级。
> 此规则同时适用于 STK_Inventory 和 SAL_OUTSTOCK。代码中用常量 AUXPROP_FILTER。

**查询示例（修正后）：**
```python
# ✅ 仅查成品一仓(某陶瓷企业) + 成品三仓(B 基地)，且仅优等品（优等+优AA）
api_sdk.ExecuteBillQuery({
    "FormId": "STK_Inventory",
    "FieldKeys": "FMaterialId,FBaseQty,FStockId,FStockName,FAuxPropID",
    "FilterString": "FMaterialId = '110293' and FStockId in ('119400','177653') and FAuxPropID in (100001,100009)",
})
# 汇总所有返回行的 FBaseQty = 该物料在成品仓的实时库存
```

---

### 3️⃣ 销售出库单 — SAL_OUTSTOCK ✅（主力销量数据源）

| 字段 | 说明 | 用途 |
|------|------|------|
| FBillNo | 单据编号 | XSCKD26072840513 |
| FDate | 日期 | 2026-07-28T00:00:00 |
| FMaterialId | 物料ID | 关联库存和物料 |
| **FRealQty** ⭐ | 实际出库数量（箱） | **销量统计字段，注意不是FQty！** |
| FStockOrgId | 出库组织 | 用于按基地过滤 |
| **FIsFree** ⭐ | **是否赠品（官方标识）** | **True=赠品（金额恒为0），统计时单独标注 free_qty** |
| **FAuxPropID** ⭐ | **辅助属性(产品等级)** | **必须过滤 IN (100001,100009)：优等品+优AA** |

**查询示例（修正后）：**
```python
# ✅ 仅查某陶瓷企业+B 基地的成品仓出库（排除样品仓等），且仅优等品（优等+优AA），排除内部客户
api_sdk.ExecuteBillQuery({
    "FormId": "SAL_OUTSTOCK",
    "FieldKeys": "FDate,FMaterialId,FRealQty,FStockOrgId,FAuxPropID,FStockId",
    "FilterString": "FMaterialId = '110293' and FStockOrgId in ('100080','100082') and FStockId in ('119400','177653') and FAuxPropID in (100001,100009) and FDate >= '2026-06-01'",
    "Limit": 500,
})
# 按 FDate 月份分组汇总 FRealQty = 该月实际出库量
# 注意1：某销售中心、某陶瓷有限公司为内部客户，统计时整单排除
# 注意2：必须限定成品仓（成品一仓119400+成品三仓177653），否则样品仓/格莱斯仓出库会混入
```

**实测数据量：** 6月+7月共约 **1,013条**记录，涵盖30/31个物料
**与Excel差异：** 两份数据统计口径不同，存在合理差异，排产以 ERP SAL_OUTSTOCK 为准

---

### 4️⃣ 销售订单 — SAL_SaleOrder ✅

| 字段 | 说明 |
|------|------|
| FBillNo | 单据编号 |
| FDate | 日期 |
| FCustId | 客户 |
| FSalerId | 业务员 |
| FSaleOrgId | 销售组织 |
| SaleOrderEntry | 明细行（物料、数量、单价） |

---

### 5️⃣ 组织架构 — ORG_Organizations ✅

见第二节。

---

### 6️⃣ 仓库主数据 — BD_Stock ✅

52个仓库（某陶瓷企业42个+B 基地10个），仅成品一仓和成品三仓用于排产。

---

### 7️⃣ 其他验证可用的表

| 表名 | 状态 |
|------|------|
| BD_Customer（客户） | ✅ |
| BD_Supplier（供应商） | ✅ |
| BD_Department（部门） | ✅ |
| AR_Receivable（应收） | ✅ |
| AP_Payable（应付） | ✅ |
| PUR_PurchaseOrder（采购订单） | ✅ |

---

## 五、不可用/废弃的数据

| 数据表 | 原因 |
|--------|------|
| **STK_MisDelivery（出库单）** | ~~曾用~~ → 数据仅~1,044条不完整，已被SAL_OUTSTOCK替代 |
| PRD_MO（生产订单） | 无数据 |
| ENG_BOM（BOM表） | 表结构不同 |
| QM_InspResult（质检） | 未启用 |
| STK_TransferBill（调拨单） | 未启用 |

---

## 六、数据关联关系图

```
BD_MATERIAL（物料）- FName 匹配排产表编码
     │
     ├──→ STK_Inventory（库存）─ FStockId IN (119400,177653) = 仅成品仓
     │         └── 某陶瓷企业成品一仓 + B 基地成品三仓
     │
     └──→ SAL_OUTSTOCK（销售出库）─ FStockOrgId IN (100080,100082) = 仅某陶瓷企业+B 基地
               └── FRealQty = 实际出库量
```

---

## 七、排产场景数据使用优先级（最终版）

| 数据 | 第一来源 | 回退来源 | 过滤条件 |
|------|---------|---------|---------|
| 物料匹配 | BD_MATERIAL.FName | 去-HB后缀重试 | — |
| 库存 | STK_Inventory | Excel计划表 | FStockId IN (119400,177653) |
| 销量 | SAL_OUTSTOCK | Excel计划表 | FStockOrgId IN (100080,100082) |
| 营销排产 | Excel计划表 col7 | — | — |
| 产品属性(定制/新品) | Excel计划表 col8+col9 | — | — |
