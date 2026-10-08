from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from docx.oxml.ns import qn

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_ORG_STRUCTURE_PATH = SKILL_ROOT / "references" / "organization_structure.json"
ORG_STRUCTURE_PATH = Path(os.environ.get("POLICY_AUDIT_ORG_STRUCTURE", DEFAULT_ORG_STRUCTURE_PATH))

CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+章")
SECTION_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+节")
ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+条")
CN_DIGITS = "零一二三四五六七八九"
CN_FMTS = {"chineseCounting", "chineseCountingThousand", "chineseCountingFullwide", "japaneseCounting", "ideographTraditional", "ideographDigital", "ideographEnclosedCircle"}

QUICK_AUDIT_PROFILE = {
    "name": "fast",
    "normative_rules": ["N1-N11", "F1-F7", "F9-F12"],
    "completeness_rules": "按制度类型仅执行对应必备条款和章节主题",
    "excluded_by_default": [
        "正文对齐方式", "正文首行缩进", "法规有效性或时点检索", "跨制度冲突", "逐页视觉渲染", "低价值格式统计"
    ],
    "render_on": ["格式属性无法读取", "疑似版式异常", "用户明确要求"]
}


@lru_cache(maxsize=1)
def load_org_structure() -> dict:
    return json.loads(ORG_STRUCTURE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def organization_index() -> dict[str, dict]:
    data = load_org_structure()
    index: dict[str, dict] = {}

    def register(name: str, aliases: list[str], category: str, parent: str | None = None) -> None:
        entry = {"canonical_name": name, "category": category, "parent": parent, "aliases": aliases}
        for label in [name, *aliases]:
            index[label] = entry

    register(data["organization"], ["某集团"], "company")
    for item in data["headquarters_departments"]:
        register(item["name"], item.get("aliases", []), "headquarters_department")
        for child in item.get("children", []):
            register(child, [], "subordinate_unit", item["name"])
    for item in data["direct_units"]:
        register(item["name"], item.get("aliases", []), "direct_unit")
        for child in item.get("children", []):
            register(child, [], "subordinate_unit", item["name"])
    for item in data["branches"]:
        register(item["name"], item.get("aliases", []), "branch")
        for child in item.get("children", []):
            register(child, [], "branch", item["name"])
    for ownership, items in data["subsidiaries"].items():
        for item in items:
            register(item["name"], item.get("aliases", []), f"subsidiary_{ownership}")
    for body in data.get("generic_governance_bodies", []):
        register(body, [], "governance_body")
    return index


def match_organizations(*texts: str) -> list[dict]:
    combined = "\n".join(text or "" for text in texts)
    index = organization_index()
    matched: dict[str, dict] = {}
    for label in sorted(index, key=len, reverse=True):
        if label not in combined:
            continue
        entry = index[label]
        canonical = entry["canonical_name"]
        result = matched.setdefault(canonical, {
            "canonical_name": canonical,
            "category": entry["category"],
            "parent": entry["parent"],
            "matched_labels": [],
        })
        if label not in result["matched_labels"]:
            result["matched_labels"].append(label)
    return list(matched.values())


def infer_organization_scope(title: str, text: str) -> dict:
    combined = f"{title}\n{text}"
    matches = match_organizations(title, text)
    has_china_tower_context = any(label in combined for label in ["某集团有限公司", "某集团", "某智联子公司", "某能源子公司", "某服务子公司", "某海外子公司"])
    if not has_china_tower_context:
        matches = [item for item in matches if item["category"] not in {"company", "headquarters_department", "governance_body"}]
    categories = {item["category"] for item in matches}
    has_subsidiary = any(category.startswith("subsidiary_") for category in categories)
    has_branch = "branch" in categories or any(word in text for word in ["各省", "省分公司", "地市级分公司"])
    has_headquarters = bool(categories & {"headquarters_department", "direct_unit", "subordinate_unit", "governance_body"})
    active_scopes = sum([has_subsidiary, has_branch, has_headquarters])
    if active_scopes > 1:
        scope = "cross_organization"
    elif has_subsidiary:
        scope = "subsidiary"
    elif has_branch:
        scope = "branch"
    elif has_headquarters:
        scope = "headquarters_or_direct_unit"
    elif "company" in categories:
        scope = "company_wide"
    else:
        scope = "unresolved"
    return {"scope": scope, "matched_organizations": matches}


def canonical_organization_name(label: str) -> str | None:
    entry = organization_index().get(label)
    return entry["canonical_name"] if entry else None


# ---------------------------------------------------------------------------
# 自动编号与章/节/条坐标（所有审核脚本共享）
# 规则：任何"编号缺失/无编号"结论必须先经 numbering.xml 模板核实（见 SKILL.md 固定审核口径）；
#       位置输出一律使用"第X章第X条"式坐标，不使用"第几段/para:N"。
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def paragraph_numbering(paragraph) -> tuple[int, int] | None:
    """段落生效的自动编号引用 (numId, ilvl)：先查段落直接 numPr，再沿样式基链查样式级 numPr。"""
    candidates = []
    direct = paragraph._p.pPr.numPr if paragraph._p.pPr is not None else None
    if direct is not None:
        candidates.append(direct)
    style = paragraph.style
    seen = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        style_num = style.element.pPr.numPr if style.element.pPr is not None else None
        if style_num is not None:
            candidates.append(style_num)
        style = style.base_style
    for num_pr in candidates:
        num_id = int(num_pr.numId.val) if num_pr.numId is not None else -1
        ilvl = int(num_pr.ilvl.val) if num_pr.ilvl is not None else 0
        if num_id > 0 and ilvl >= 0:
            return num_id, ilvl
    return None


def numbering_index(doc) -> dict[tuple[int, int], dict]:
    """(numId, ilvl) -> {template, fmt, start}；合并 abstractNum 定义与 num 级 lvlOverride/startOverride。"""
    numbering_rel = next((rel for rel in doc.part.rels.values() if rel.reltype.endswith("/numbering")), None)
    if numbering_rel is None:
        return {}
    root = numbering_rel.target_part.element
    abstracts = {}
    for abstract in root.findall(qn("w:abstractNum")):
        aid = int(abstract.get(qn("w:abstractNumId")))
        abstracts[aid] = {}
        for level in abstract.findall(qn("w:lvl")):
            ilvl = int(level.get(qn("w:ilvl")))
            level_text = level.find(qn("w:lvlText"))
            num_fmt = level.find(qn("w:numFmt"))
            start_el = level.find(qn("w:start"))
            abstracts[aid][ilvl] = {
                "template": clean(level_text.get(qn("w:val"))) if level_text is not None else "",
                "fmt": num_fmt.get(qn("w:val")) if num_fmt is not None else "decimal",
                "start": int(start_el.get(qn("w:val"))) if start_el is not None else 1,
            }
    index = {}
    for num in root.findall(qn("w:num")):
        num_id = int(num.get(qn("w:numId")))
        abstract_id = num.find(qn("w:abstractNumId"))
        if abstract_id is None:
            continue
        aid = int(abstract_id.get(qn("w:val")))
        for ilvl, meta in abstracts.get(aid, {}).items():
            entry = dict(meta)
            for ov in num.findall(qn("w:lvlOverride")):
                if int(ov.get(qn("w:ilvl"))) != ilvl:
                    continue
                start_override = ov.find(qn("w:startOverride"))
                if start_override is not None:
                    entry["start"] = int(start_override.get(qn("w:val")))
            index[(num_id, ilvl)] = entry
    return index


def cn_number(n: int) -> str:
    if n < 10:
        return CN_DIGITS[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + (CN_DIGITS[n % 10] if n % 10 else "")
    tens, ones = divmod(n, 10)
    return CN_DIGITS[tens] + "十" + (CN_DIGITS[ones] if ones else "")


def render_auto_label(meta: dict, count: int) -> str:
    """按模板与 numFmt 渲染自动编号前缀，如 {template:'第%1章', fmt:'chineseCountingThousand'} + count=1 -> '第一章'。"""
    if "%1" not in meta["template"]:
        return meta["template"]
    value = cn_number(count) if meta["fmt"] in CN_FMTS else str(count)
    return meta["template"].replace("%1", value).strip()


def build_doc_structure(doc) -> list[dict]:
    """把 Word 段落流映射为章/节/条坐标，返回与 doc.paragraphs 一一对应的列表（含空段落）。
    每项：{"chapter": 章标签或None, "section": 节标签或None, "article": 条标签或None}。
    编号载体识别：可见文本（'第X章/节/条'）优先；否则读取 OOXML 自动编号，按 numbering.xml
    模板渲染并计数（计数器按 (numId, ilvl) 独立，起始值含 lvlOverride/startOverride）。
    文本型编号不消耗自动编号计数器，两者混排时与 Word 渲染行为一致。"""
    meta_index = numbering_index(doc)
    counters: dict[tuple[int, int], int] = {}
    current = {"chapter": None, "section": None, "article": None}
    entries = []
    for paragraph in doc.paragraphs:
        text = clean(paragraph.text)
        match = CHAPTER_RE.match(text)
        if match:
            current = {"chapter": match.group(0), "section": None, "article": None}
        else:
            match = SECTION_RE.match(text)
            if match:
                current["section"] = match.group(0)
                current["article"] = None
            else:
                match = ARTICLE_RE.match(text)
                if match:
                    current["article"] = match.group(0)
                else:
                    numbering = paragraph_numbering(paragraph)
                    if numbering is not None and numbering in meta_index:
                        meta = meta_index[numbering]
                        template = meta["template"]
                        if "章" in template and numbering[1] == 0:
                            counters[numbering] = counters.get(numbering, meta["start"] - 1) + 1
                            current = {"chapter": render_auto_label(meta, counters[numbering]), "section": None, "article": None}
                        elif "节" in template:
                            counters[numbering] = counters.get(numbering, meta["start"] - 1) + 1
                            current["section"] = render_auto_label(meta, counters[numbering])
                            current["article"] = None
                        elif "条" in template:
                            counters[numbering] = counters.get(numbering, meta["start"] - 1) + 1
                            current["article"] = render_auto_label(meta, counters[numbering])
        entries.append(dict(current))
    return entries


def structure_label(entry: dict | None) -> str:
    """章条坐标显示文本，如 '第一章第三条' / '第一章' / '第三条'；无坐标返回空串。"""
    if not entry:
        return ""
    return "".join(part for part in (entry.get("chapter"), entry.get("section"), entry.get("article")) if part)


def concern_sort_key(item: dict):
    """关注项/偏差行排序：无证据的缺失项置前（保持规则相对顺序），有证据的按首个证据的文档顺序升序。"""
    evidence = item.get("evidence") or []
    orders = [entry.get("order") for entry in evidence if isinstance(entry.get("order"), int)]
    return (0 if orders else 1, min(orders) if orders else 0)
