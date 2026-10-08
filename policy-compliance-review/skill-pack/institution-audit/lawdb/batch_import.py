# -*- coding: utf-8 -*-
"""批量导入法规：只从官方库录入（flk 国家法律法规数据库 + gov 国家规章库），查不到则跳过
用法: python3 batch_import.py
"""
import sys, os, re, sqlite3, urllib.request, tempfile, time

BASE = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(BASE)  # .../skills/
SKILL = os.path.join(SKILLS_DIR, "china-law-search")
sys.path.insert(0, SKILL)
sys.path.insert(0, f"{SKILL}/scripts")
sys.path.insert(0, BASE)

from lib import flk_api, gov_api
from build_lawdb import parse_docx, init_db, import_law

# 待导入清单（通信工程建设项目招标投标管理办法已入库，不再重复）
TARGETS = [
    "企业国有资产法",
    "企业国有资产监督管理暂行条例",
    "民法典",
    "某集团有限公司章程",
    "招标投标法",
    "招标投标法实施条例",
    "必须招标的工程项目规定",
    "必须招标的基础设施和公用事业项目范围规定",
    "工程建设项目招标代理机构管理暂行办法",
    "电子招标投标办法",
    "建筑法",
    "建设工程质量管理条例",
    "建设工程安全生产管理条例",
    "通信建设工程质量监督管理规定",
    "安全生产法",
    "网络安全法",
    "数据安全法",
    "个人信息保护法",
]

SXX_MAP = {3: "现行有效", 2: "已修改", 1: "已废止", 4: "尚未生效"}

def norm(s):
    return re.sub(r"[《》\s]", "", s)

def match_title(title, target):
    t, n = norm(title), norm(target)
    return t == n or t == "中华人民共和国" + n

def download_docx(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(3)

def extract_effective_date(rev_text, gbrq):
    m = re.search(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行", rev_text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if "自公布之日起施行" in rev_text:
        return gbrq
    return None

def extract_amend_date(rev_text):
    # 最后一个 修正/修订 日期（含"根据YYYY年...修正"和"YYYY年...修订"两种写法）
    pat = re.finditer(r"(?:根据)?(\d{4})年(\d{1,2})月(\d{1,2})日[^　\n]{0,30}?(?:修正|修订)", rev_text)
    dates = [(m.group(1), m.group(2), m.group(3)) for m in pat]
    if dates:
        y, mo, d = dates[-1]
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None

def extract_doc_num(doc_num_text):
    if not doc_num_text:
        return None
    # 排除日期尾字"日"，非贪婪匹配机关名（联合规章机关名可能很长）
    m = re.search(r"([^\d日]{2,60}?令第[零一二三四五六七八九十百\d]+号)", doc_num_text)
    return m.group(1).strip() if m else None

def import_flk_versions(con, target, rows):
    """从 flk 搜索结果的精确匹配行导入全部版本，返回 (导入数, 版本信息列表)"""
    versions = [r for r in rows if match_title(r.get("title", ""), target)]
    if not versions:
        return 0, []
    versions.sort(key=lambda r: r.get("gbrq", ""))
    imported, info = 0, []
    for v in versions:
        bbbs = v["bbbs"]
        try:
            dinfo = flk_api.download_info(bbbs, fmt="docx")
            data = download_docx(dinfo["url"])
            fd, path = tempfile.mkstemp(suffix=".docx")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            name, chapters, articles, meta = parse_docx(path)
            os.unlink(path)
            gbrq = v.get("gbrq", "")
            rev_text = meta.get("full_text", "")[:2000]
            meta["publish_date"] = gbrq
            meta["amend_date"] = extract_amend_date(rev_text)
            meta["issuing_org"] = meta.get("issuing_org") or v.get("zdjgName")
            eff = extract_effective_date(rev_text, gbrq)
            status = SXX_MAP.get(v.get("sxx"), "现行有效")
            n = import_law(con, law_id=next_id(con), name="中华人民共和国" + target if not name.startswith("中华人民共和国") else name,
                           chapters=chapters, articles=articles, meta=meta,
                           level="法律", status=status, doc_no=None, bbbs=bbbs,
                           effective_date=eff,
                           source="国家法律法规数据库",
                           official_url=f"https://flk.npc.gov.cn/detail2.html?bbbs={bbbs}")
            imported += 1
            info.append(f"{gbrq}版 {len(articles)}条 {status}")
        except Exception as e:
            info.append(f"{v.get('gbrq','?')}版 失败: {e}")
    return imported, info

def import_gov(con, target):
    """从规章库导入，返回 (是否成功, 信息)"""
    try:
        resp = gov_api.search_with_content(target, size=10)
        rows = resp.get("rows", [])
        matches = [r for r in rows if match_title(r.get("title", ""), target)]
        if not matches:
            return False, "规章库无精确匹配"
        # 同名多条时取公布日期最早的（避免取到"重新收录"记录）
        row = min(matches, key=lambda r: r.get("date", ""))
        out = gov_api.download_as_docx(target, output_dir=tempfile.mkdtemp())
        name, chapters, articles, meta = parse_docx(out)
        date = row.get("date", "")
        meta["publish_date"] = date
        meta["amend_date"] = None
        meta["issuing_org"] = row.get("org")
        doc_no = extract_doc_num(row.get("doc_num"))
        # 施行日期：从文号说明提取
        eff = None
        dn = row.get("doc_num") or ""
        m_eff = re.search(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行", dn)
        if m_eff:
            eff = f"{m_eff.group(1)}-{int(m_eff.group(2)):02d}-{int(m_eff.group(3)):02d}"
        elif "自公布之日起施行" in dn:
            eff = date
        n = import_law(con, law_id=next_id(con), name=name,
                       chapters=chapters, articles=articles, meta=meta,
                       level=row.get("type", "部门规章"), status="现行有效", doc_no=doc_no,
                       effective_date=eff,
                       source="国家规章库",
                       official_url=row.get("url"))
        return True, f"{len(articles)}条 文号:{doc_no or '无'} 施行:{eff or '?'}"
    except Exception as e:
        return False, f"失败: {e}"

def next_id(con):
    return con.execute("SELECT COALESCE(MAX(id),0)+1 FROM laws").fetchone()[0]

def main():
    con = init_db(os.path.join(BASE, "law.db"))
    report = []
    for target in TARGETS:
        print(f"\n▶ 处理: {target}")
        # 1. 先查 flk
        try:
            resp = flk_api.search(target, exact=False)
            rows = resp.get("rows", [])
        except Exception as e:
            rows = []
            print(f"  flk搜索异常: {e}")
        imported, info = import_flk_versions(con, target, rows)
        if imported:
            print(f"  ✅ 法规库导入 {imported} 个版本: {info}")
            report.append((target, "✅ 法规库", info))
            continue
        if rows and info and any("失败" in x for x in info):
            print(f"  ❌ 法规库有匹配但导入失败: {info}")
            report.append((target, "❌ 导入失败", info))
            continue
        # 2. flk 无 → 查 gov 规章库
        ok, msg = import_gov(con, target)
        if ok:
            print(f"  ✅ 规章库导入: {msg}")
            report.append((target, "✅ 规章库", [msg]))
        else:
            print(f"  ⏭️  未收录: {msg}")
            report.append((target, "⏭️ 未收录", [msg]))
    con.commit()
    # 汇总
    print("\n" + "=" * 70)
    print("批量导入汇总")
    print("=" * 70)
    for t, src, info in report:
        print(f"  {src} {t}: {', '.join(info)}")
    print(f"\n库内法规总数: {con.execute('SELECT count(*) FROM laws').fetchone()[0]}")
    print(f"条文总数: {con.execute('SELECT count(*) FROM articles').fetchone()[0]}")
    con.close()

if __name__ == "__main__":
    main()
