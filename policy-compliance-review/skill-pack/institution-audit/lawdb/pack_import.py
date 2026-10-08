# -*- coding: utf-8 -*-
"""18 个包清单导入：52 部待导入（flk 34 + gov 18），查不到的跳过并报告
用法: python3 pack_import.py
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

# 52 部待导入（flk 优先，gov 兜底）
TARGETS = [
    # flk（34）
    "中华人民共和国劳动合同法", "中华人民共和国社会保险法", "工伤保险条例", "职工带薪年休假条例",
    "女职工劳动保护特别规定", "失业保险条例", "住房公积金管理条例", "中华人民共和国会计法",
    "中华人民共和国预算法", "中华人民共和国企业所得税法", "中华人民共和国企业所得税法实施条例",
    "中华人民共和国增值税法", "中华人民共和国税收征收管理法", "中华人民共和国税收征收管理法实施细则",
    "中华人民共和国印花税法", "中华人民共和国契税法", "中华人民共和国反不正当竞争法",
    "中华人民共和国反垄断法", "中华人民共和国刑法", "中华人民共和国监察法", "国有企业管理人员处分条例",
    "中华人民共和国民事诉讼法", "中华人民共和国仲裁法", "中华人民共和国电子签名法",
    "中华人民共和国审计法", "中华人民共和国审计法实施条例", "国有资产评估管理办法",
    "中华人民共和国证券法", "网络数据安全管理条例", "关键信息基础设施安全保护条例",
    "中华人民共和国消防法", "生产安全事故应急条例", "生产安全事故报告和调查处理条例", "中华人民共和国电信条例",
    # gov（18）
    "劳务派遣暂行规定", "工资支付暂行规定", "最低工资规定", "中央企业工资总额管理办法", "企业年金办法",
    "企业财务通则", "企业会计准则——基本准则", "会计档案管理办法", "中央企业合规管理办法",
    "中央企业投资监督管理办法", "中央企业境外投资监督管理办法", "企业国有资产交易监督管理办法",
    "企业国有资产评估管理暂行办法", "中央企业违规经营投资责任追究实施办法", "数据出境安全评估办法",
    "个人信息出境标准合同办法", "促进和规范数据跨境流动规定", "电信建设管理办法",
    # 再确认（工贸企业重大事故隐患判定标准，应急管理部令）
    "工贸企业重大事故隐患判定标准",
]

SXX_MAP = {3: "现行有效", 2: "已修改", 1: "已废止", 4: "尚未生效"}

def norm(s):
    return re.sub(r"[《》\s——-]", "", s).replace("（试行）", "").replace("(试行)", "")

def match_title(title, target):
    t, n = norm(title), norm(target)
    return t == n or t == "中华人民共和国" + n

def download_docx(url, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(5)

def extract_effective_date(rev_text, gbrq):
    m = re.search(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行", rev_text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if "自公布之日起施行" in rev_text:
        return gbrq
    return None

def extract_amend_date(rev_text):
    pat = re.finditer(r"(?:根据)?(\d{4})年(\d{1,2})月(\d{1,2})日[^　\n]{0,30}?(?:修正|修订)", rev_text)
    dates = [(m.group(1), m.group(2), m.group(3)) for m in pat]
    if dates:
        y, mo, d = dates[-1]
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None

def extract_doc_num(doc_num_text):
    if not doc_num_text:
        return None
    m = re.search(r"([^\d日]{2,60}?令第[零一二三四五六七八九十百\d]+号)", doc_num_text)
    return m.group(1).strip() if m else None

def import_flk_versions(con, target, rows):
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
            n = import_law(con, law_id=next_id(con), name=name,
                           chapters=chapters, articles=articles, meta=meta,
                           level="法律" if "条例" not in name else "行政法规",
                           status=status, doc_no=None, bbbs=bbbs,
                           effective_date=eff,
                           source="国家法律法规数据库",
                           official_url=f"https://flk.npc.gov.cn/detail2.html?bbbs={bbbs}")
            imported += 1
            info.append(f"{gbrq}版 {len(articles)}条 {status}")
        except Exception as e:
            info.append(f"{v.get('gbrq','?')}版 失败: {str(e)[:80]}")
    return imported, info

def import_gov(con, target):
    try:
        resp = gov_api.search_with_content(target, size=10)
        rows = resp.get("rows", [])
        matches = [r for r in rows if match_title(r.get("title", ""), target)]
        if not matches:
            return False, "规章库无精确匹配"
        row = min(matches, key=lambda r: r.get("date", ""))
        out = gov_api.download_as_docx(target, output_dir=tempfile.mkdtemp())
        name, chapters, articles, meta = parse_docx(out)
        date = row.get("date", "")
        meta["publish_date"] = date
        meta["amend_date"] = None
        meta["issuing_org"] = row.get("org")
        doc_no = extract_doc_num(row.get("doc_num"))
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
        return False, f"失败: {str(e)[:100]}"

def next_id(con):
    return con.execute("SELECT COALESCE(MAX(id),0)+1 FROM laws").fetchone()[0]

def main():
    con = init_db(os.path.join(BASE, "law.db"))
    report = []
    for i, target in enumerate(TARGETS, 1):
        print(f"\n[{i}/{len(TARGETS)}] ▶ {target}", flush=True)
        try:
            resp = flk_api.search(target, exact=False)
            rows = resp.get("rows", []) if isinstance(resp, dict) else (resp or [])
        except Exception as e:
            rows = []
            print(f"  flk搜索异常: {str(e)[:60]}", flush=True)
        imported, info = import_flk_versions(con, target, rows)
        if imported:
            print(f"  ✅ 法规库 {info}", flush=True)
            report.append((target, "✅ 法规库", info))
            continue
        if info and any("失败" in x for x in info):
            print(f"  ❌ 法规库匹配但导入失败: {info}", flush=True)
            report.append((target, "❌ 导入失败", info))
            continue
        ok, msg = import_gov(con, target)
        if ok:
            print(f"  ✅ 规章库 {msg}", flush=True)
            report.append((target, "✅ 规章库", [msg]))
        else:
            print(f"  ⏭️  {msg}", flush=True)
            report.append((target, "⏭️ 未收录", [msg]))
        con.commit()
    con.commit()
    print("\n" + "=" * 70)
    print("导入汇总")
    print("=" * 70)
    for t, src, info in report:
        print(f"  {src} {t}: {', '.join(info)}")
    print(f"\n库内法规总数: {con.execute('SELECT count(*) FROM laws').fetchone()[0]}")
    print(f"条文总数: {con.execute('SELECT count(*) FROM articles').fetchone()[0]}")
    con.close()

if __name__ == "__main__":
    main()
