---
name: data-fetch
description: 某陶瓷企业排产-数据拉取子技能。接收Excel文件，执行ERP三路查询（物料→库存→销量），产出结构化产品数据JSON供后续排产子技能使用。父技能：prod-schedule。
---

# 数据拉取与预处理

**父技能：** prod-schedule（路由器调用）
**输出产物：** `/tmp/schedule-data.json`

## 输入契约

主技能通过 `sessions_spawn` 调用，附带消息体：
```
数据拉取 | 文件: {Excel绝对路径} | 排产日期: {YYYY-MM-DD}
```

## 核心原则

**库存和销量均以ERP为准，仅ERP未覆盖的物料退而使用Excel数据。**

**架构：双源汇总。同一产品可同时存在于两个仓库、从两个组织出库。**

| 数据 | 来源 | 汇总方式 |
|------|------|---------|
| **库存** | 成品一仓(119400) + 成品三仓(177653) | 双仓求和（仅优等100001+优AA 100009） |
| **销量** | 某陶瓷企业(100080) + B 基地(100082) 成品仓出库 | 双组织求和 + 仅成品仓(119400/177653)，等级同上 |

- 排除：内部客户（某销售中心、某陶瓷有限公司）
- `base` 字段仅用于窑炉分配，不用于ERP数据过滤
- 未匹配物料（ERP无此编码）：库存和销量退而使用Excel数据

## 操作步骤

### 1. 文件识别
- 用 xlrd 读取 Excel 文件
- 打印文件标题确认内容
- 从标题自动识别规格（如"600*1200"） → 匹配窑炉参数
- 规格→窑炉映射：750×1500→1号窑 / 600×1200→2号窑 / 400×800→3号窑 / 800×800→5号窑

### 2. Excel解析
- 品牌行：col0有品牌名且col1有编号 → **既是品牌声明也是首条产品数据**，必须同时提取
- 数据行：col0为空，col1有编号 → 归属当前品牌
- 小计行：col0='小计' → 品牌结束
- 总计行：col0='总计' → 全部结束
- 提取字段：品牌/生产编号/规格/工艺/6月销量/7月销量/库存/排产数量/备注
- 自动标记：`is_custom`（备注含"定制"或col9含"定制底标"）、`is_new`（备注含"新品"）、`is_hb`（编码含-HB）、`has_history`（6月或7月有销量）
- **基地识别**：按编码前缀自动归属 → `MAT%`=A 基地 / `b%`=B 基地。B 基地仅有400×800规格（B 基地窑，日产70000方/31250箱）

**🔴 base字段强制写入（每条产品必须设置，不可遗漏）：**
```python
for p in products:
    code = p['code']
    if code.startswith('MAT'):
        p['base'] = '某陶瓷企业'
    elif code.startswith('b'):
        p['base'] = 'B 基地'
    else:
        # 以其他字母开头 → 检查品牌，金博达=B 基地
        if p.get('brand') == '金博达':
            p['base'] = 'B 基地'
        else:
            p['base'] = '某陶瓷企业'
```

### 3. 金蝶ERP数据查询（必须执行，三个查询按顺序）

#### 🔑 关键：BD_MATERIAL 用 FName 查询，不是 FNumber！

排产计划表中的物料编码（如 `MSA6Z006-HB`、`HL4K008`）对应 ERP 物料主数据的 **FName（物料名称）** 字段，**不是** FNumber（系统编码如 `MAT.010201100022`）。

#### A. 物料ID查询 (BD_MATERIAL)

```python
# ✅ 正确方式：用 FName 匹配
sdk.ExecuteBillQuery({
    "FormId": "BD_MATERIAL",
    "FieldKeys": "FNumber,FMasterId,FName,FSpecification",
    "FilterString": f"FName = '{code}'",  # ← 用 FName！
})

# 对于排产表中的 -HB 编码：优先查带-HB的FName
# 如果查不到，再查不带-HB的FName（部分-HB产品在ERP中以非-HB名称存储）
```

- 建立 `编码 → {master_id, fnumber, fname, spec}` 映射
- 打印匹配率：找到X/总数Y（预期85%+，非100%）

#### B. 即时库存查询 (STK_Inventory) + C. 销售出库 (SAL_OUTSTOCK)

**🔴 强制：库存和销量统一由 `enrich_products` 完成，严禁在此之前单独设置 `erp_stock`/`erp_sales`。**

```python
from scripts.query_kingdee import KingdeeQuery
kq = KingdeeQuery()

# ⚠️ 禁止：不要在这里单独调用 query_inventory 或 query_sales_windows
# ✅ 正确：所有ERP数据填充统一走 enrich_products（含库存+销量+分裂）
products = kq.enrich_products(products, schedule_date)
```

- **enrich_products 内部自动完成**：库存查询（双仓）+ 销量查询（双组织分查）+ 基地分裂
- **分组织查询保障**：A 基地行 → 仅某陶瓷企业组织(100080)销量；B 基地行 → 仅B 基地组织(100082)销量
- **排除**：内部客户（某销售中心、某陶瓷有限公司）
- **V3.8**：销量仅统计成品仓出库（FStockId IN 119400,177653，排除样品仓）；等级=优等100001+优AA 100009
- **V3.4**：排除排产日当天，d7/d30为完整N天，末尾强制校验

### 4. 双基地分裂（由 enrich_products 自动完成）

`enrich_products` 已自动执行分裂逻辑，无需额外操作：

**分裂示例：**
```
Excel输入: JZ48T01 × 1行(plan_qty=5000)
     ↓
ERP查询: 某陶瓷企业仓库=1357, B 基地仓库=548 → 双基地都有
     ↓
分裂输出:
  JZ48T01-某陶瓷企业: plan_qty=5000 | stock=1357(119400) | sales=13687(100080)
  JZ48T01-B 基地:   plan_qty=0    | stock= 548(177653) | sales=18371(100082)
```

**plan_qty 分配：**
- 产品来自某陶瓷企业Excel → 某陶瓷企业行保留plan_qty，B 基地行plan_qty=0
- 产品来自B 基地Excel → B 基地行保留plan_qty，某陶瓷企业行plan_qty=0
- 无营销计划表 → 两行plan_qty均为0
- **Limit=1000**：避免大销量产品被截断

#### D. 未匹配物料回退 — Excel数据

ERP未匹配的物料（通常为新增编码未录入），库存和销量退而使用Excel数据。

#### 数据使用优先级

| 数据 | 优先级 | 原因 |
|------|--------|------|
| **库存** | **ERP > Excel** | ERP成品仓实时准确，Excel可能滞后 |
| **销量** | **ERP > Excel** | SAL_OUTSTOCK完整可用，未匹配物料用Excel补齐 |

### 5. 焕白(-HB)产品库存处理
- -HB产品库存 = 普通编码库存 + -HB编码库存（如两者均存在）
- 例如：MSA6Z006的库存 + MSA6Z006-HB的库存 = 总库存
- 在 data.json 中存储合并后的总库存

### 6. 输出 — 打印并写JSON

**必须打印：**
- 文件标题、规格、窑炉参数（日产箱数）
- 品牌数/产品数/定制/新品/营销总排产
- ERP FName匹配率、库存覆盖数、出库记录总数
- 每个品牌的品数和排产量
- **基地分布：某陶瓷企业X个产品 / B 基地Y个产品（必须打印，确认base字段已设置）**

### 7. 输出验证（写入JSON后必须执行）

```python
# 写入后立即验证
import json
with open('/tmp/schedule-data.json', 'r') as f:
    verify = json.load(f)

# 检查1：每个产品必须有 base 字段
missing_base = [p['code'] for p in verify['products'] if not p.get('base')]
if missing_base:
    raise ValueError(f"❌ 以下产品缺少base字段: {missing_base}")

# 检查2：base值分布在{某陶瓷企业, B 基地}内
invalid_base = [p['code'] for p in verify['products'] if p.get('base') not in ('某陶瓷企业', 'B 基地')]
if invalid_base:
    raise ValueError(f"❌ 以下产品base值异常: {invalid_base}")

# 检查3：打印基地分布确认
from collections import Counter
base_dist = Counter(p['base'] for p in verify['products'])
print(f"✅ base分布验证通过: {dict(base_dist)}")
```

**写入 `/tmp/schedule-data.json`**，格式见下。

## 输出契约

```json
{
  "meta": {
    "spec": "600*1200",
    "kiln": "2号窑",
    "total_products": 65,
    "brands": ["好运来", "梅赛德斯", "精钻", "马萨拉蒂"],
    "erp_match_rate": 0.89,
    "schedule_date": "2026-07-30",
    "start_date": "2026-04-30"
  },
  "products": [
    {
      "base": "某陶瓷企业",
      "brand": "好运来",
      "code": "HL7K010-HB",
      "spec": "600*1200",
      "craft": "通体大理石",
      "is_custom": false,
      "is_new": false,
      "is_hb": true,
      "has_history": true,
      "excel_stock": 1200,
      "plan_qty": 3000,
      "remark": "",
      "erp_stock": 1150,
      "erp_sales": {
        "d7_sum": 420,
        "d30_sum": 1800,
        "d90_sum": 5400
      },
      "erp_sales_june": 3200,
      "erp_sales_july": 2800
    }
  ]
}
```

## 🔴 铁律

1. **每次从头拉取**，不依赖缓存
2. **BD_MATERIAL 必须用 FName 查询**，不用 FNumber
3. **STK_Inventory 无 FBillNo**，OrderString 必须为 `""`
4. **库存精确仓库ID**：某陶瓷企业=119400，B 基地=177653
5. **销量精确组织名**：某陶瓷企业='某陶瓷企业生产基地'，B 基地='B 基地生产基地'
6. **排除某销售中心**
7. **完成后必须写 `/tmp/schedule-data.json`**
8. **每条产品必须有 `base` 字段**（仅用于窑炉分配，不用作ERP数据过滤）
9. **库存双仓汇总**：成品一仓(119400) + 成品三仓(177653)，不按 base 拆分
10. **销量双组织汇总**：某陶瓷企业(100080) + B 基地(100082)，排除某分公司(101830)和某销售中心
11. **首次写入 data.json 后立即验证字段完整性**（第6节），不通过则修复后重写
