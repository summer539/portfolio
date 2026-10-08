# 已知问题与经验（Known Issues & Lessons）

实战踩坑记录，按主题组织。新增问题持续追加。

## 一、flk 下载超时与重试

- flk.npc.gov.cn 的下载 API 有 JS 反爬保护，直接 HTTP 请求会返回 HTML 而非 JSON
- 解决方案：`flk_api.download_file()` 内部通过 playwright-cli 获取签名下载 URL
- 如果 playwright-cli 不可用，下载会失败
- 批量下载时可能出现间歇性超时（`The read operation timed out`），这是 flk 的反爬触发
- `batch_download_from_check()` 支持断点续下，超时条目重跑即可自动跳过已完成
- **建议批量下载 delay 保持 0.5–1 秒**，如有超时直接重跑

### flk IP 级反爬限流（2026-08-27 批量下载实测）

- **触发条件**：连续请求约 50 次后触发（download/pc 与 detail API 都会触发）
- **现象**：返回 HTML 而非 JSON（`JSONDecodeError`）；触发后**所有 flk API（含 detail）都被限流**，属 IP 级
- **恢复**：冷却约 2–3 分钟后自动恢复
- **解决方案**：大批量下载用 cron 分批调度，每 30 分钟 30 条（`*/30 * * * *`），脚本必须支持断点续做（进度文件记录已完成条目，重跑自动跳过）
- **提速技巧**：入库/解析阶段无网络请求不受反爬影响，下载完成后可一次性跑完入库

## 二、规章库 API 返回格式变化（2026-04 发现）

- 规章库搜索 API 的返回结构可能有两种格式：
  - 旧格式：`result.data` 是 dict，包含 `pager` 和 `list`
  - 新格式：`result.data` 是 list（直接是结果列表），`result.totalCount` 和 `result.pageSize` 在上层
- `gov_api.py` 的 `search()` 和 `search_with_content()` 已兼容两种格式
- 当 athenaappkey 无效时，API 不会返回 HTTP 错误，而是返回 `data: []` + `resultCode` 包含错误信息（如 `athena_01503 解密失败`）
- **如果规章库返回 0 条结果但实际应该有数据，先检查 athenaappkey 是否有效**

## 三、规章库 athenaappkey 过期与刷新

- athenaappkey 约 1 小时过期
- `gov_api.py` 已实现自动刷新 + 验证：key 过期或无效时自动通过 playwright-cli 拦截请求获取新 key
- 自动刷新依赖 playwright-cli（`@playwright/cli`），未安装时脚本自动 `npm install -g @playwright/cli`
- 自动刷新流程：open 规章库页面 → 拦截 `athena/forward` 请求提取 `athenaappkey` header → 发测试请求验证（`resultCode.code == 200`）→ 缓存到 `scripts/lib/.athena_key_cache.json`
- 手动刷新 3 步流程见 `config/README.md`（Step 2 的拦截代码可直接复制）

## 四、root 环境下 playwright-cli 启动 Chromium 失败（2026-08 发现）

- 现象：以 root 运行时 `playwright-cli open` 报 `Chromium sandboxing failed!` / `Running as root without --no-sandbox is not supported`
- 原因：Chromium 在 root 下默认要求 `--no-sandbox`，而 playwright-cli 默认不传
- 解决方案：`config/playwright-config.json` 内容为 `{"browser": {"launchOptions": {"chromiumSandbox": false}}}`
- `gov_api.py` 的 `_pw_cmd()` 会在 `open` 命令时自动附加 `--config=<config/playwright-config.json>`（仅 open 有效；run-code/close 走已启动的 daemon socket，不接受 --config，会报 `Unknown option: --config`）
- 手动刷新时也需在 `open` 步骤加 `--config`

## 五、部分法规两库都查不到

- 通知、意见、指引等规范性文件两库都不收录
- 中央企业相关内部管理办法通常不在公开法规库中
- 国资委发布的"指引""意见""通知""工作规则""工作规定"通常查不到
- **党内法规（党章/准则/条例等）两库全部不收录**（属党的制度体系）——直接走官方网抓取
- 这类文件标记"未找到"，需从官方渠道获取（见 data-source-rules.md）

## 六、官方网抓取入库的坑（2026-08 实战总结，已固化进 lawdb_import.py）

1. **BeautifulSoup get_text(sep) 不插块级换行**：同一父节点下多个 `<p>` 之间不会插入分隔符，多条条文会连成一行（曾导致纪律处分条例 101–109 条被并进第 100 条）。
   解决：`lawdb_import.extract_text()` 先 deepcopy 候选节点，把所有块级标签（p/div/br/li/tr/h1-h6）替换为 `\n` 再取文本。
2. **中文数字编号两个大坑**：
   - 编号含"零"：正则必须带"零"（`第一百零一条` 匹配不了 `[一二三四五六七八九十百]+`）
   - "X百Y十"：`第一百一十条` = 110（不是 120）；用逐字符累加算法（build_lawdb 的 `cn2num` 是对的，别自己另写）
3. **章节格式**：`import_law` 的 chapters 参数必须传 `[(序号, 章节名)]` 元组列表，articles 的 chapter 字段传序号；传字符串列表会导致 chapter_no 存成"第一章xxx"、chapter_name 全空。
4. **尾部噪音混入末条**：页面 footer（`来源：新华社` / `编辑：xxx` / `版权所有` / `学习专栏` / `（责编：xxx）【纠错】`）会被合并进最后一条条文，需关键词截断（只在全文后 25% 匹配，防误伤正文）。
5. **清理 UI 噪音绝不删正文标点**：曾用 `\s*[。；，、]*\s*$` 清理导致 544 条末尾句号被删，全量重导才恢复。只删 UI 字符串，不动标点。
6. **FTS 表结构**：`articles_fts` 本身是 FTS5 虚拟表（`CREATE VIRTUAL TABLE articles_fts USING fts5(content, article_ref UNINDEXED, tokenize='trigram')`），不是普通表 + 索引表；结构照抄 `lawdb/build_lawdb.py::init_db`。
7. **数据源时效性**：入库前确认现行版本——如《党政机关厉行节约反对浪费条例》2025-05-02 已修订（11 章 63 条），旧版题注已过时；《中央八项规定及其实施细则》= 八项规定正文 8 条 + 2017 修订版实施细则 5 部分，需两页合并。
8. **幂等**：重复导入同名同 level 法规前先删旧（`import_law_from_html` 已内置），避免重复条文。
9. **12371.cn 专题页是列表**：`special/xxx` 页只是目录，正文在 `ARTI...` 子页面，别把列表页当正文抓。
10. **解析为空时检查**：页面可能不是法规正文页（登录墙/JS 渲染/跳转 404），先 `parse_html` 调试确认再入库。

## 七、香港法规与港交所规则网（2026-08 实战）

- **cn-rules.hkex.com.hk 沙箱直连失败**，需走 `https://sc.hkex.com.hk/TuniS/<原URL>` 代理
- 规则网部分页面（如附录 C1 企业管治守则）正文是 **JS 动态加载**，`main` 容器只有目录；
  解决：页面提供官方 PDF 下载链接（`/sites/default/files/net_file_store/HKEXCN_*.pdf`），用 PDF + PyMuPDF 提取更可靠
- **pdftotext 对港交所 PDF 的文本顺序会乱**（双栏/块排序问题，如 A 章节标题跑到 B 后面）；
  改用 PyMuPDF（fitz）`page.get_text("blocks")` 按 y/x 坐标排序，顺序正确
- 守则类文件章节识别：字母章节（A./B./C./D.）+"第十四A章"等正文引用会误判为章节——
  用**预定义章节词表**（基本原则/释义/绝对禁止/通知/特殊情况/披露）解决
- 章节切换时必须先 flush 当前条文，否则条文会挂错章节
- e-legislation.gov.hk（香港法例）对 requests/curl 有客户端检测（返回 7.5KB 壳页），需 playwright-cli 渲染
- 港交所 PDF URL 是繁体编码路径，用简体编码请求会 404

## 八、党内法规源（2026-08 实战）

- 党内法规两库（flk/规章库）均不收录，直接走官方网
- 共产党员网 12371.cn 是首选（章程/条例全文都在），专题页 `special/xxx` 是列表需进子页
- 国企基层组织条例：人民网 dangjian 连接超时，备用源上观新闻 shobserver.com 可用
- 数据源须权威（12371.cn、gov.cn、ccps.gov.cn、mof.gov.cn、miit.gov.cn 等），地方政协转载站已弃用

## 九、通信标准类（2026-08 评估）

- YD 系列（通信行业标准）：工信部官网可查发布通知，但正文 PDF 多为扫描版，OCR 质量差（文字顺序错乱、0→O 误识别）时不强行入库
- GB 系列（工程建设国标）：openstd 国标公开系统不收录，无官方免费全文
- 强制性条文汇编：出版社书籍，无官方免费全文
- 结论：技术标准类无官方免费全文渠道时，如实向用户汇报，不降质入库

## 四、废止批量导入的数据质量坑（2026-08-27 全量入库实战）

- **docx 标题跨行**：flk 下载的废止决定 docx 标题常被拆成 2-3 段（如"××市人民代表大会\n关于废止《××条例》\n的决定"），`parse_docx` 的主正则/兜底会提取到残缺标题（"的决定"、"最高人民法院"、"管理条例》的决定"等），入库 name 残缺。
  - 修复：入库后全量比对 flk 清单 `title` 与 `laws.name`，不一致一律以清单为准 UPDATE（本次 463 条）。
  - 注意 flk 清单个别 title 本身也是残缺值（如"废止决定"），此时需从 docx 段落手动拼完整标题。
- **FTS 索引脏数据**：`import_law` 幂等删除 laws/articles 时**不清理 articles_fts**，反复重导后 FTS 产生孤儿行（article_ref 已删除）和重复行（同 article_ref 多行）。本次重建前 23976 行（应 15030），孤儿 2477、重复 4369。
  - 修复：`DELETE FROM articles_fts; INSERT INTO articles_fts(content, article_ref) SELECT content, id FROM articles;`
  - 建议：每次批量导入后跑此重建。
- **刑法"第X条之一/之二"**：`parse_docx` 的 `cn2num` 只取数字，"第一百二十条之一"解析为 article_no=120，7 条并列（内容完整、序号丢失）。article_no 为 INTEGER 无法存"120之一"，如需精确展示需改 content 前缀或改列类型。
- **flk 清单 title 可能含零宽空格（\u200b）**：入库比对时注意 strip。
