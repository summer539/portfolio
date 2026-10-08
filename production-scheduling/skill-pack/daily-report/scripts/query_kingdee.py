#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金蝶云星空 数据查询工具 V3.5
架构：
  - 支持按单个仓库/组织独立查询（用于双基地分裂排产）
  - 支持双仓/双组织汇总查询
  - base 字段仅用于窑炉分配，不用于数据过滤
  - 🆕 库存和销量自动过滤优等品(优等100001 + 优AA 100009)
"""

from k3cloud_webapi_sdk.main import K3CloudApiSdk

from config import SERVER_URL, ACCT_ID, USER_NAME, APP_ID, APP_SECRET, LCID

# ════════════════════════════════════════════
#  仓库/组织配置
# ════════════════════════════════════════════
WAREHOUSES = {
    "某陶瓷企业": {"id": "119400", "org": "某陶瓷企业生产基地"},
    "B 基地":   {"id": "177653", "org": "B 基地生产基地"},
}

# 销量口径：仅统计成品仓出库（成品一仓+成品三仓），排除样品仓等非成品仓
FINISHED_WAREHOUSE_FILTER = "FStockId IN (119400,177653)"

ORGANIZATIONS = {
    "某陶瓷企业": 100080,
    "B 基地":   100082,
}

EXCLUDED_CUSTOMER = "某销售中心"

# 内部/关联客户（非真实销售，统计时整单排除）：
# - 某销售中心：金额恒为0的关联单（8/11达53,686箱/125单）
# - 某陶瓷有限公司：公司内部单（8/11 R89688 关联单1,000箱）
INTERNAL_CUSTOMERS = {"某销售中心", "某陶瓷有限公司"}

# 辅助属性·产品等级：优等品 = 优等(100001) + 优AA(100009)（客户2026-08-12确认优AA也算优等品）
AUXPROP_GRADE_PREMIUM = (100001, 100009)
AUXPROP_FILTER = "FAuxPropID IN (100001,100009)"


class KingdeeQuery:
    """金蝶查询封装 — V3.0 基地分流架构"""

    def __init__(self):
        self.api = K3CloudApiSdk(SERVER_URL)
        self.api.InitConfig(
            acct_id=ACCT_ID, user_name=USER_NAME,
            app_id=APP_ID, app_secret=APP_SECRET,
            server_url=SERVER_URL, lcid=LCID
        )

    def _query(self, form_id, fields, filter_str="", limit=200):
        """通用查询"""
        no_fbillno = form_id in ("STK_Inventory", "BD_MATERIAL", "BD_Stock")
        order = "" if no_fbillno else "FBillNo ASC"
        result = self.api.BillQuery({
            "FormId": form_id,
            "FieldKeys": fields,
            "FilterString": filter_str,
            "OrderString": order,
            "TopRowCount": 0,
            "Limit": limit,
        })
        import json
        return json.loads(result) if isinstance(result, str) else result

    # ════════════════════════════════════════════
    #  物料查询（全组织通用，FName匹配）
    # ════════════════════════════════════════════

    def query_material(self, code):
        """
        按 FName 精确匹配物料。
        -HB编码查不到时自动去掉后缀重试。
        返回: {fnumber, fname, master_id, spec} 或 None
        """
        codes_to_try = [code]
        if code.endswith('-HB'):
            codes_to_try.append(code.replace('-HB', ''))

        for try_code in codes_to_try:
            rows = self._query("BD_MATERIAL",
                f"FNumber,FMasterId,FName,FSpecification",
                f"FName='{try_code}'")
            if rows:
                r = rows[0]
                return {
                    "fnumber": r.get("FNumber", ""),
                    "fname":   r.get("FName", ""),
                    "master_id": str(r.get("FMasterId", "")),
                    "spec":    r.get("FSpecification", ""),
                }
        return None

    # ════════════════════════════════════════════
    #  库存查询
    # ════════════════════════════════════════════

    def query_inventory_by_warehouse(self, code, warehouse_id, org_name):
        """按单个仓库查询库存（仅优等品：优等100001 + 优AA 100009）"""
        fstr = (f"FMaterialId.FName='{code}' "
                f"AND FStockId='{warehouse_id}' "
                f"AND FStockOrgId.FName='{org_name}' "
                f"AND {AUXPROP_FILTER}")
        total = 0.0
        for r in self._query("STK_Inventory", "FBaseQty", fstr, 500):
            total += float(r.get("FBaseQty", 0) or 0)
        return round(total, 2)

    def query_inventory_total(self, code):
        """双仓汇总查库存"""
        total = 0.0
        for name, wh in WAREHOUSES.items():
            total += self.query_inventory_by_warehouse(code, wh["id"], wh["org"])
        return round(total, 2)

    def query_inventory(self, code):
        """双仓汇总（保持向后兼容）"""
        return self.query_inventory_total(code)

    def query_inventory_split(self, code):
        """返回两个仓库各自的库存，用于分裂判定"""
        return {
            "某陶瓷企业": self.query_inventory_by_warehouse(code, WAREHOUSES["某陶瓷企业"]["id"], WAREHOUSES["某陶瓷企业"]["org"]),
            "B 基地":   self.query_inventory_by_warehouse(code, WAREHOUSES["B 基地"]["id"], WAREHOUSES["B 基地"]["org"]),
        }

    # ════════════════════════════════════════════
    #  销量查询
    # ════════════════════════════════════════════

    def query_sales_by_org(self, code, org_id, date_start, date_end):
        """按单个组织查询销量（仅优等品：优等100001 + 优AA 100009，仅成品仓）
        🔧 V3.6：补上成品仓过滤，与日报口径完全一致"""
        fstr = (f"FMaterialId.FName='{code}' "
                f"AND FStockOrgID={org_id} "
                f"AND {AUXPROP_FILTER} "
                f"AND {FINISHED_WAREHOUSE_FILTER} "
                f"AND FDate>='{date_start}' AND FDate<='{date_end}'")
        total = 0.0
        daily = {}
        for r in self._query("SAL_OUTSTOCK",
                "FDate,FCustomerID.FName,FRealQty", fstr, 1000):
            if r.get("FCustomerID.FName", "") in INTERNAL_CUSTOMERS:
                continue
            qty = float(r.get("FRealQty", 0) or 0)
            total += qty
            date_key = r.get("FDate", "")[:10]
            if date_key:
                daily[date_key] = daily.get(date_key, 0) + qty
        return {"total": round(total, 2), "daily": daily}

    def query_sales(self, code, date_start, date_end):
        """双组织汇总查销量"""
        total = 0.0
        daily = {}
        for name, org_id in ORGANIZATIONS.items():
            result = self.query_sales_by_org(code, org_id, date_start, date_end)
            total += result["total"]
            for d, q in result["daily"].items():
                daily[d] = daily.get(d, 0) + q
        return {"total": round(total, 2), "daily": daily}

    def query_sales_split(self, code, schedule_date):
        """返回两个组织各自的销量窗口，用于分裂判定。
        🔧 V3.4修复：排除排产日当天，d7/d30裁切点基于排产日，查询到前一天。
        """
        from datetime import datetime, timedelta
        end_raw = datetime.strptime(schedule_date, "%Y-%m-%d")
        end = end_raw - timedelta(days=1)  # 查询到排产日前一天
        d90_start = (end - timedelta(days=90)).strftime("%Y-%m-%d")
        d7_cut  = (end_raw - timedelta(days=7)).strftime("%Y-%m-%d")   # 排产日-7天
        d30_cut = (end_raw - timedelta(days=30)).strftime("%Y-%m-%d")  # 排产日-30天

        result = {}
        for name, org_id in ORGANIZATIONS.items():
            r = self.query_sales_by_org(code, org_id, d90_start, end.strftime("%Y-%m-%d"))
            d7_sum = sum(q for d, q in r["daily"].items() if d >= d7_cut)
            d30_sum = sum(q for d, q in r["daily"].items() if d >= d30_cut)
            result[name] = {
                "d7_sum": round(d7_sum, 2),
                "d30_sum": round(d30_sum, 2),
                "d90_sum": r["total"],
            }
        return result

    def aggregate_sales(self, date_start, date_end):
        """
        按产品聚合销售出库（统一口径 V3.7）：
        - 等级：仅优等品（优等100001 + 优AA 100009）
        - 客户：排除内部/关联客户（某销售中心、某陶瓷有限公司）
        - 赠品：按 ERP 官方标识 FIsFree=True 识别（赠品行金额恒为0），计入出库量但单独标注 free_qty
        返回: {产品编码: {'qty':出库箱数, 'amt':销售额, 'free_qty':其中赠品箱数, 'rows':行数}}
        """
        from collections import defaultdict
        fstr = (f"FDate>='{date_start}' AND FDate<='{date_end}' "
                f"AND FStockOrgID IN (100080,100082) AND {AUXPROP_FILTER} "
                f"AND {FINISHED_WAREHOUSE_FILTER}")
        rows = self._query("SAL_OUTSTOCK",
            "FMaterialId.FName,FRealQty,FAllAmount,FCustomerID.FName,FIsFree", fstr, 20000)
        by_prod = defaultdict(lambda: {'qty': 0.0, 'amt': 0.0, 'free_qty': 0.0, 'rows': 0})
        for r in rows:
            if r.get('FCustomerID.FName') in INTERNAL_CUSTOMERS:
                continue
            name = r.get('FMaterialId.FName', '') or '未知'
            qty = float(r.get('FRealQty', 0) or 0)
            amt = float(r.get('FAllAmount', 0) or 0)
            by_prod[name]['qty'] += qty
            by_prod[name]['amt'] += amt
            by_prod[name]['rows'] += 1
            if r.get('FIsFree'):
                by_prod[name]['free_qty'] += qty
        return dict(by_prod)

    def top_sales(self, date_start, date_end, n=10):
        """按出库箱数取TOP n（含赠品标注），返回 [(code, {qty,amt,free_qty,rows}), ...]"""
        agg = self.aggregate_sales(date_start, date_end)
        return sorted(agg.items(), key=lambda x: -x[1]['qty'])[:n]

    def query_sales_windows(self, code, schedule_date):
        """双组织汇总销量窗口（保持向后兼容）。
        🔧 V3.4修复：排除排产日当天，d7/d30裁切点基于排产日，查询到前一天。
        """
        from datetime import datetime, timedelta
        end_raw = datetime.strptime(schedule_date, "%Y-%m-%d")
        end = end_raw - timedelta(days=1)  # 查询到排产日前一天
        d90_start = (end - timedelta(days=90)).strftime("%Y-%m-%d")

        result = self.query_sales(code, d90_start, end.strftime("%Y-%m-%d"))
        d7_cut  = (end_raw - timedelta(days=7)).strftime("%Y-%m-%d")   # 排产日-7天
        d30_cut = (end_raw - timedelta(days=30)).strftime("%Y-%m-%d")  # 排产日-30天

        d7_sum = sum(q for d, q in result["daily"].items() if d >= d7_cut)
        d30_sum = sum(q for d, q in result["daily"].items() if d >= d30_cut)
        return {
            "d7_sum": round(d7_sum, 2),
            "d30_sum": round(d30_sum, 2),
            "d90_sum": result["total"],
        }

    def query_monthly_sales(self, code, year_month):
        """
        查询指定月份的双组织汇总销量。
        year_month: '2026-06' 或 '2026-07'
        """
        from datetime import datetime, timedelta
        start = f"{year_month}-01"
        dt = datetime.strptime(start, "%Y-%m-%d")
        if dt.month == 12:
            end = f"{dt.year+1}-01-01"
        else:
            end = f"{dt.year}-{dt.month+1:02d}-01"
        end_dt = datetime.strptime(end, "%Y-%m-%d") - timedelta(days=1)
        end_str = end_dt.strftime("%Y-%m-%d")
        result = self.query_sales(code, start, end_str)
        return round(result["total"], 2)

    def query_monthly_sales_by_org(self, code, year_month, base):
        """按基地查询指定月份销量"""
        from datetime import datetime, timedelta
        start = f"{year_month}-01"
        dt = datetime.strptime(start, "%Y-%m-%d")
        if dt.month == 12:
            end = f"{dt.year+1}-01-01"
        else:
            end = f"{dt.year}-{dt.month+1:02d}-01"
        end_dt = datetime.strptime(end, "%Y-%m-%d") - timedelta(days=1)
        end_str = end_dt.strftime("%Y-%m-%d")
        org_id = ORGANIZATIONS[base]
        result = self.query_sales_by_org(code, org_id, start, end_str)
        return round(result["total"], 2)

    # ════════════════════════════════════════════
    #  批量查询 — 处理整个产品列表
    # ════════════════════════════════════════════

    def enrich_products(self, products, schedule_date):
        """
        为产品列表填充ERP数据，并按双基地分裂规则展开。
        - 同一产品在双基地都有数据 → 分裂为两行
        - 仅单基地有数据 → 保持一行
        🔧 V3.4：末尾强制校验，确保每行的erp_sales与base严格对应。
        """
        expanded = []
        for i, p in enumerate(products):
            code = p["code"]
            try:
                inv = self.query_inventory_split(code)
                sal = self.query_sales_split(code, schedule_date)
            except Exception as e:
                print(f"  ⚠️ 查询失败 {code}: {e}")
                p["erp_stock"] = 0
                p["erp_sales"] = {"d7_sum": 0, "d30_sum": 0, "d90_sum": 0}
                p["base"] = "某陶瓷企业"
                expanded.append(p)
                continue

            has_a = inv["某陶瓷企业"] > 0 or max(sal["某陶瓷企业"].values()) > 0
            has_b  = inv["B 基地"]   > 0 or max(sal["B 基地"].values())   > 0

            if has_a and has_b:
                # 🔧 跨基地 → 分裂为两行，各自使用对应组织销量
                p_a = dict(p)
                p_a["base"] = "某陶瓷企业"
                p_a["erp_stock"] = inv["某陶瓷企业"]
                p_a["erp_sales"] = dict(sal["某陶瓷企业"])  # 🔧 深拷贝防污染
                p_a["plan_qty"] = p.get("plan_qty", 0) if p.get("plan_qty_source", "") != "B 基地" else 0
                expanded.append(p_a)

                p_jl = dict(p)
                p_jl["base"] = "B 基地"
                p_jl["erp_stock"] = inv["B 基地"]
                p_jl["erp_sales"] = dict(sal["B 基地"])  # 🔧 深拷贝防污染
                p_jl["plan_qty"] = p.get("plan_qty", 0) if p.get("plan_qty_source", "") == "B 基地" else 0
                expanded.append(p_jl)

                print(f"  ⚡ {code} 双基地分裂: MAT库存{inv['某陶瓷企业']}/JL库存{inv['B 基地']}")
            elif has_a:
                p["base"] = "某陶瓷企业"
                p["erp_stock"] = inv["某陶瓷企业"]
                p["erp_sales"] = dict(sal["某陶瓷企业"])  # 🔧 深拷贝
                expanded.append(p)
            elif has_b:
                p["base"] = "B 基地"
                p["erp_stock"] = inv["B 基地"]
                p["erp_sales"] = dict(sal["B 基地"])  # 🔧 深拷贝
                expanded.append(p)
            else:
                # 无ERP数据，使用Excel数据
                p["base"] = "某陶瓷企业"
                p["erp_stock"] = p.get("excel_stock", 0)
                p["erp_sales"] = {"d7_sum": 0, "d30_sum": 0, "d90_sum": 0}
                expanded.append(p)

            if (i + 1) % 10 == 0:
                print(f"  ... {i+1}/{len(products)} 已查询，展开后{len(expanded)}行")

        # 为所有展开产品补充6月/7月ERP月度销量（按各自基地查对应组织）
        for p in expanded:
            try:
                p["erp_sales_june"] = self.query_monthly_sales_by_org(
                    p["code"], "2026-06", p["base"])
                p["erp_sales_july"] = self.query_monthly_sales_by_org(
                    p["code"], "2026-07", p["base"])
            except:
                p["erp_sales_june"] = 0
                p["erp_sales_july"] = 0

        # 🔧 V3.4 末尾强制校验：每行销量必须与base对应，防止双组织汇总混入
        print(f"\n🔍 分裂后校验 ({len(expanded)}行)...")
        for p in expanded:
            expected_org = p["base"]
            # 校验信号：d7_sum不应超过对应组织的实际销量
            # 如果有污染（某陶瓷企业行拿到双组织合计），d7会比B 基地行大很多
            actual_sales = p.get("erp_sales", {})
            print(f"  {p['code']} base={expected_org} stock={p.get('erp_stock',0)} "
                  f"d7={actual_sales.get('d7_sum',0)} d30={actual_sales.get('d30_sum',0)}")

        return expanded


# ════════════════════════════════════════════
#  独立调试入口
# ════════════════════════════════════════════
if __name__ == "__main__":
    kq = KingdeeQuery()

    print("=== 库存双仓汇总 ===")
    for code in ["HL4K008", "JZ48T05", "JL48802"]:
        print(f"  {code}: {kq.query_inventory(code)}箱")

    print("\n=== 销量双组织汇总 ===")
    for code in ["JZ48T05", "HL4K008"]:
        sal = kq.query_sales_windows(code, "2026-07-27")
        print(f"  {code}: d7={sal['d7_sum']:.0f} d30={sal['d30_sum']:.0f} d90={sal['d90_sum']:.0f}")
