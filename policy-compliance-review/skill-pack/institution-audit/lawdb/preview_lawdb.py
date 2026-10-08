# -*- coding: utf-8 -*-
"""法规库预览工具：导出 self-contained HTML（浏览器打开即可浏览/搜索）
用法:
  python3 preview_lawdb.py              # 生成 lawdb/preview.html
  python3 preview_lawdb.py <输出路径>
"""
import sqlite3, json, sys, html, os

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "law.db")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "preview.html")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
laws = [dict(r) for r in con.execute("SELECT * FROM laws ORDER BY id")]
for law in laws:
    law.pop("full_text", None)  # 全文太大，条文已足够
    arts = [dict(r) for r in con.execute(
        "SELECT article_no, chapter_no, chapter_name, content FROM articles WHERE law_id=? ORDER BY article_no",
        (law["id"],))]
    # 按章节分组
    chapters = {}
    for a in arts:
        key = a["chapter_name"] or (f"第{a['chapter_no']}章" if a["chapter_no"] else "全文")
        chapters.setdefault(key, []).append(a)
    law["chapters"] = [{"name": k, "articles": v} for k, v in chapters.items()]
con.close()

data_json = json.dumps(laws, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>法律法规数据库 · 预览</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6fa; color:#2c3e50; }
  header { background:#1e3a5f; color:#fff; padding:20px 32px; }
  header h1 { font-size:22px; }
  header p { font-size:13px; opacity:.8; margin-top:4px; }
  .wrap { max-width:1320px; margin:0 auto; padding:24px 16px; display:flex; gap:20px; align-items:flex-start; }
  .main { flex:1; min-width:0; }
  .filters { width:260px; flex-shrink:0; background:#fff; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.08); padding:18px 18px 8px; position:sticky; top:16px; max-height:calc(100vh - 32px); overflow-y:auto; }
  .filters h3 { font-size:15px; color:#1e3a5f; margin-bottom:14px; padding-bottom:10px; border-bottom:2px solid #eef0f3; }
  .filters .fg { margin-bottom:16px; }
  .filters .fg label { display:block; font-size:13px; color:#7f8c8d; margin-bottom:6px; font-weight:600; }
  .filters select { width:100%; padding:9px 10px; font-size:13px; border:2px solid #dce1e8; border-radius:8px; outline:none; background:#fff; color:#33445a; cursor:pointer; }
  .filters select:focus { border-color:#1e3a5f; }
  .filters .reset { width:100%; margin-bottom:12px; padding:8px; font-size:13px; background:#f0f2f5; color:#33445a; border:none; border-radius:8px; cursor:pointer; }
  .filters .reset:hover { background:#e3e7ec; }
  .filters .fcount { font-size:12px; color:#bdc3c7; margin-top:4px; }
  /* 制定机关分类树 */
  .org-tree { border:2px solid #dce1e8; border-radius:8px; background:#fff; }
  .og-group { border-bottom:1px solid #f0f2f5; }
  .og-group:last-child { border-bottom:none; }
  .og-head { display:flex; align-items:center; gap:6px; padding:9px 10px; cursor:pointer; user-select:none; font-size:13px; color:#33445a; background:#fafbfc; }
  .og-head:hover { background:#f0f4f9; }
  .og-head .arrow { margin-left:auto; font-size:11px; color:#bdc3c7; transition:transform .15s; }
  .og-group.open .og-head .arrow { transform:rotate(90deg); }
  .og-head .ogcnt { font-size:11px; color:#bdc3c7; }
  .og-body { display:none; padding:2px 6px 8px 26px; }
  .og-group.open .og-body { display:block; }
  .og-body label { display:flex; align-items:center; gap:5px; padding:3px 4px; font-size:12px; color:#44566c; cursor:pointer; border-radius:4px; }
  .og-body label:hover { background:#f5f8fc; }
  .og-body label input { margin:0; cursor:pointer; }
  .og-body .ocnt { margin-left:auto; font-size:11px; color:#bdc3c7; }
  .org-tree input[type=checkbox] { accent-color:#1e3a5f; }
  @media (max-width:900px){ .wrap{ flex-direction:column; } .filters{ width:100%; position:static; } }
  .stats { display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
  .stat { background:#fff; border-radius:10px; padding:14px 22px; box-shadow:0 1px 4px rgba(0,0,0,.08); flex:1; min-width:140px; text-align:center; }
  .stat b { display:block; font-size:26px; color:#1e3a5f; }
  .stat span { font-size:13px; color:#7f8c8d; }
  .searchbar { margin-bottom:20px; }
  .search-row { display:flex; gap:10px; }
  .search-row select { padding:0 12px; font-size:14px; border:2px solid #dce1e8; border-radius:10px; outline:none; background:#fff; color:#33445a; cursor:pointer; }
  .search-row select:focus { border-color:#1e3a5f; }
  .searchbar input { flex:1; padding:12px 16px; font-size:15px; border:2px solid #dce1e8; border-radius:10px; outline:none; }
  .searchbar input:focus { border-color:#1e3a5f; }
  .law-card { background:#fff; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:16px; overflow:hidden; }
  .law-head { display:flex; justify-content:space-between; align-items:center; padding:16px 22px; cursor:pointer; }
  .law-head:hover { background:#f8fafc; }
  .law-title { font-size:17px; font-weight:600; }
  .badge { display:inline-block; padding:2px 10px; border-radius:20px; font-size:12px; margin-left:8px; }
  .b-law { background:#e3f0ff; color:#1e5fb4; }
  .b-reg { background:#e8f7ee; color:#1e8e4e; }
  .b-valid { background:#e8f7ee; color:#1e8e4e; }
  .b-amended { background:#fff3e0; color:#c77700; }
  .law-meta { font-size:13px; color:#7f8c8d; margin-top:6px; }
  .law-body { padding:0 22px 18px; border-top:1px solid #f0f2f5; display:none; }
  .law-body.open { display:block; }
  .chapter { margin-top:14px; }
  .chapter h3 { font-size:14px; color:#1e3a5f; border-left:4px solid #1e3a5f; padding-left:8px; margin-bottom:8px; scroll-margin-top:12px; }
  .preamble { background:#f0f6ff; border:1px solid #d6e4f5; border-radius:6px; padding:10px 14px; font-size:13px; color:#33445a; line-height:1.9; margin-top:14px; }
  .toc { margin-top:12px; padding:10px 14px; background:#fafbfc; border:1px solid #eef0f3; border-radius:6px; }
  .toc b { color:#1e3a5f; margin-right:10px; font-size:13px; }
  .toc a { display:inline-block; color:#1e5fb4; font-size:13px; margin:2px 10px 2px 0; text-decoration:none; }
  .toc a:hover { text-decoration:underline; }
  .article { padding:8px 12px; background:#fafbfc; border-radius:6px; margin-bottom:6px; font-size:14px; line-height:1.7; }
  .article b.no { color:#1e3a5f; margin-right:6px; }
  mark { background:#ffe58f; padding:0 2px; border-radius:2px; }
  .diff-old { background:#fff1f0; color:#a8071a; padding:6px 10px; border-radius:6px; font-size:13px; margin:4px 0; }
  .diff-new { background:#f6ffed; color:#237804; padding:6px 10px; border-radius:6px; font-size:13px; margin:4px 0; }
  .diff-title { font-size:13px; color:#7f8c8d; margin:10px 0 4px; }
  .empty { text-align:center; color:#bdc3c7; padding:40px; }
  footer { text-align:center; color:#bdc3c7; font-size:12px; padding:20px; }
</style>
</head>
<body>
<header>
  <h1>📚 法律法规数据库 · 预览</h1>
  <p>数据来源：国家法律法规数据库（flk）+国家规章库+官方官网+香港交易所+用户提供</p>
</header>
<div class="wrap">
  <aside class="filters">
    <h3>🔎 检索筛选</h3>
    <button class="reset" onclick="resetFilters()">↺ 重置筛选</button>
    <div class="fg">
      <label>效力位阶</label>
      <select id="fLevel"><option value="">全部</option></select>
    </div>
    <div class="fg">
      <label>制定机关（分类树，可多选）</label>
      <div class="org-tree" id="orgTree"></div>
    </div>
    <div class="fg">
      <label>时效性</label>
      <select id="fStatus"><option value="">全部</option></select>
    </div>
    <div class="fcount" id="fcount"></div>
  </aside>
  <div class="main">
  <div class="stats" id="stats"></div>
  <div class="searchbar">
    <div class="search-row">
      <select id="mode">
        <option value="all">全部</option>
        <option value="title">按标题</option>
        <option value="content">按正文</option>
      </select>
      <input id="q" type="text" placeholder="🔍 搜索条文关键词（如：年休假、劳动合同、经济补偿）…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
    </div>
  </div>
  <div id="laws"></div>
  <footer>本地静态预览 · 由 preview_lawdb.py 生成</footer>
  </div>
</div>
<script>
const LAWS = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const hl = (text, kw) => {
  if (!kw) return esc(text);
  const t = esc(text), k = esc(kw);
  return t.split(k).join('<mark>'+k+'</mark>');
};
const badge = (l) => {
  const lv = l.level==='法律'?'b-law':(l.level==='部门规章'||l.level==='地方政府规章')?'b-reg':'b-law';
  const st = l.status==='现行有效'?'b-valid':'b-amended';
  return `<span class="badge ${lv}">${l.level}</span><span class="badge ${st}">${l.status}</span>`;
};
// 统计
$('#stats').innerHTML = [
  ['法规数量', LAWS.length+' 部'],
  ['条文总数', LAWS.reduce((s,l)=>s+l.chapters.reduce((a,c)=>a+c.articles.length,0),0)+' 条'],
  ['现行有效', LAWS.filter(l=>l.status==='现行有效').length+' 部'],
  ['数据源', '官方数据+用户提供']
].map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
// 筛选状态
let fLevel='', fStatus='';
const fOrgs = new Set();
const trunc = (s,n)=> s.length>n ? s.slice(0,n)+'…' : s;
// 机关名规范化：去括号注释 + 按分号/顿号/逗号拆分（联合发文）
const normOrgs = l => ((l.issuing_org||'（未知）')
  .replace(/[（(][^（）()]*[）)]/g,'')
  .split(/[;；、,，]/)
  .map(s=>s.trim()).filter(Boolean));
// 机关分类（7 类，规则见方案）
const classify = (org) => {
  if (!org) return '群团及其他';
  if (org.includes('全国人民代表大会')) return '国家权力机关';
  if (org.includes('人民代表大会') || org.includes('人大常委会') || org.includes('人大常务委员会') || (org.includes('人大') && !org.includes('全国'))) return '地方权力机关';
  if (org.includes('人民法院') || org.includes('人民检察院')) return '司法机关';
  if (org.includes('人民政府')) return '地方行政机关';
  if (org.includes('中共中央') || org.includes('中央纪律检查委员会') || org.includes('中央委员会')) return '党中央机构';
  // 地方政府部门（省厅/市局/自治区部门等）→ 地方行政机关
  if (/省|市|自治区|自治州|自治县|地区|盟/.test(org)) return '地方行政机关';
  if (org==='国务院' || org==='国务院办公厅' || /^(国家|中国证券|中国银行|国务院)/.test(org) || /(部|委员会|总局|局|署|行|院|办公室|委|办)$/.test(org)) return '国务院部门';
  return '群团及其他';
};
// 生成机关分类树
(function buildOrgTree(){
  const cnt = {};
  LAWS.forEach(l=>{ normOrgs(l).forEach(o=>{ cnt[o]=(cnt[o]||0)+1; }); });
  const groups = {};
  Object.entries(cnt).forEach(([o,n])=>{ const g=classify(o); (groups[g]=groups[g]||[]).push([o,n]); });
  const ORDER = ['国家权力机关','党中央机构','国务院部门','司法机关','地方权力机关','地方行政机关','群团及其他'];
  const tree = $('#orgTree');
  tree.innerHTML = ORDER.filter(g=>groups[g]).map(g=>{
    const items = groups[g].sort((a,b)=>b[1]-a[1]);
    const gsum = items.reduce((s,x)=>s+x[1],0);
    return `<div class="og-group" data-g="${g}">
      <div class="og-head" onclick="toggleGroup(this)">
        <input type="checkbox" class="og-all" data-g="${g}" onclick="event.stopPropagation();toggleAll(this)" title="全选/全不选本组">
        <span>${g}</span><span class="ogcnt">（${gsum} 部次）</span><span class="arrow">▸</span>
      </div>
      <div class="og-body">${items.map(([o,n])=>`<label title="${esc(o)}"><input type="checkbox" class="og-item" value="${esc(o)}" data-g="${g}" onchange="onOrgChange()">${esc(trunc(o,16))}<span class="ocnt">${n}</span></label>`).join('')}</div>
    </div>`;
  }).join('');
})();
const toggleGroup = (head)=>{ head.parentElement.classList.toggle('open'); };
const toggleAll = (cb)=>{
  const g = cb.dataset.g;
  document.querySelectorAll(`.og-item[data-g="${g}"]`).forEach(i=>{ i.checked = cb.checked; });
  onOrgChange();
};
const onOrgChange = ()=>{
  fOrgs.clear();
  document.querySelectorAll('.og-item:checked').forEach(i=>fOrgs.add(i.value));
  render(qInput.value, modeSel.value);
};
const clearOrgTree = ()=>{
  document.querySelectorAll('.og-item,.og-all').forEach(i=>i.checked=false);
  fOrgs.clear();
};
const fillSelect = (id, key) => {
  const cnt = {};
  LAWS.forEach(l=>{ const v = l[key]||'（未知）'; cnt[v]=(cnt[v]||0)+1; });
  const opts = Object.entries(cnt).sort((a,b)=>b[1]-a[1]);
  $(id).innerHTML = '<option value="">全部</option>' +
    opts.map(([v,n])=>`<option value="${esc(v)}">${esc(trunc(v,20))}（${n}）</option>`).join('');
};
fillSelect('#fLevel','level');
fillSelect('#fStatus','status');
const resetFilters = ()=>{ fLevel=''; fStatus=''; clearOrgTree(); ['#fLevel','#fStatus'].forEach(s=>$(s).value=''); render(qInput.value, modeSel.value); };
['#fLevel','#fStatus'].forEach(s=>$(s).addEventListener('change', e=>{
  if (s==='#fLevel') fLevel=e.target.value;
  if (s==='#fStatus') fStatus=e.target.value;
  render(qInput.value, modeSel.value);
}));
// 渲染法规
function render(kw, mode){
  kw = (kw||'').trim();
  mode = mode || 'all';
  const inTitle = l => (l.name||'').includes(kw) || (l.doc_no||'').includes(kw);
  const kwHit = a => kw && (a.content.includes(kw) || a.article_no==parseInt(kw));
  const inContent = l => l.chapters.some(c=>c.articles.some(kwHit));
  const match = l => !kw || (mode==='title' ? inTitle(l) : mode==='content' ? inContent(l) : inTitle(l)||inContent(l));
  // 筛选：效力位阶 / 制定机关 / 时效性（可叠加，对当前结果再筛选）
  const passFilter = l => (!fLevel || (l.level||'')===fLevel) && (fOrgs.size===0 || normOrgs(l).some(o=>fOrgs.has(o))) && (!fStatus || (l.status||'')===fStatus);
  // 正文过滤：正文命中时仅渲染命中章节+条文；标题命中或无关键词时渲染全文
  const onlyHits = l => kw && (mode==='content' || (mode==='all' && !inTitle(l)));
  const bodyChapters = l => (onlyHits(l)
    ? l.chapters.map((c,ci)=>({ci, name:c.name, articles:c.articles.filter(kwHit)})).filter(c=>c.articles.length>0)
    : l.chapters.map((c,ci)=>({ci, name:c.name, articles:c.articles})));
  const box = $('#laws');
  const filtered = LAWS.filter(passFilter);
  const shown = filtered.filter(match);
  $('#fcount').textContent = '当前筛选：' + filtered.length + ' 部' + (filtered.length!==LAWS.length ? '（共 '+LAWS.length+' 部）' : '');
  if (!shown.length) { box.innerHTML = '<div class="empty">没有匹配「'+esc(kw)+'」'+(mode==='title'?'的法规标题':mode==='content'?'的条文':'的内容')+(filtered.length!==LAWS.length?'（或当前筛选条件下无结果，试试重置筛选）':'')+'</div>'; return; }
  box.innerHTML = shown.map((l,i)=>{
    const arts = l.chapters.flatMap(c=>c.articles);
    const tHit = kw && inTitle(l);
    const hit = kw && mode!=='title' ? arts.filter(a=>a.content.includes(kw)).length : 0;
    const titleHtml = tHit ? hl(l.name, kw) : esc(l.name);
    const hitInfo = mode==='title' ? (tHit?' ｜ 命中 <b style="color:#c77700">标题</b>':'') : (kw && hit ? ' ｜ 命中 <b style="color:#c77700">'+hit+'</b> 条'+(onlyHits(l)?'（仅显示命中条文）':'') : '');
    const bc = bodyChapters(l);
    const chHit = ci => onlyHits(l) && !l.chapters[ci].articles.some(kwHit);
    return `<div class="law-card">
      <div class="law-head" onclick="document.getElementById('lb${i}').classList.toggle('open')">
        <div>
          <span class="law-title">${titleHtml}</span>${badge(l)}
          <div class="law-meta">${l.doc_no?('文号：'+esc(l.doc_no)+' ｜ '):''}公布：${l.publish_date||'—'} ｜ 修正：${l.amend_date||'—'} ｜ 制定机关：${esc(l.issuing_org||'—')} ｜ 条文：${arts.length} 条${hitInfo}</div>
        </div>
        <span style="color:#bdc3c7;font-size:20px">▾</span>
      </div>
      <div class="law-body" id="lb${i}">
        ${l.preamble?`<div class="preamble">📜 题注：${esc(l.preamble)}</div>`:''}
        ${l.chapters.length>1?`<div class="toc"><b>📑 目录</b>${l.chapters.map((c,ci)=> chHit(ci) ? `<span style="color:#bdc3c7">${esc(c.name)}</span>` : `<a href="#ch${i}_${ci}">${esc(c.name)}</a>`).join('')}${onlyHits(l)?` <span style="color:#c77700;font-size:12px">（灰显=未命中章节）</span>`:''}</div>`:''}
        ${bc.map(c=>`<div class="chapter"><h3 id="ch${i}_${c.ci}">${esc(c.name)}</h3>${
          c.articles.map(a=>`<div class="article"><b class="no">${a.article_no?`第${a.article_no}条`:'全文'}</b>${hl(a.content, mode==='title'?'':kw)}</div>`).join('')
        }</div>`).join('')}
        ${onlyHits(l)?`<div style="font-size:12px;color:#bdc3c7;margin-top:8px">🔍 命中 ${hit} 条，仅显示上述命中条文（切换「全部/按标题」可看全文）</div>`:''}
      </div>
    </div>`;
  }).join('');
  // 自动展开：仅正文命中时展开（内容模式/全部模式的正文命中）；按标题搜索保持折叠，由用户自行展开
  if (kw && mode!=='title') shown.forEach((l,i)=>{ if(inContent(l)) document.getElementById('lb'+i)?.classList.add('open'); });
}
const modeSel = $('#mode'), qInput = $('#q');
qInput.addEventListener('input', e=>render(e.target.value, modeSel.value));
modeSel.addEventListener('change', e=>{
  const m = e.target.value;
  qInput.placeholder = m==='title' ? '🔍 按法规标题搜索（如：公司法、劳动法、上市规则）…' : m==='content' ? '🔍 搜索条文关键词（如：年休假、劳动合同、经济补偿）…' : '🔍 标题或条文关键词搜索…';
  render(qInput.value, m);
});
render('', 'all');
</script>
</body>
</html>
"""

html_out = HTML.replace("__DATA__", data_json)
d = os.path.dirname(OUT)
if d:
    os.makedirs(d, exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html_out)
print(f"✅ 预览已生成: {OUT}")
print(f"   大小: {os.path.getsize(OUT)/1024:.0f} KB | 法规 {len(laws)} 部 | 条文 {sum(len(l['chapters'][c]['articles']) for l in laws for c in range(len(l['chapters'])))} 条")
