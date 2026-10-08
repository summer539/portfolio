# 关键规则与自我进化（Key Rules & Maintenance）

## Key Rules

- 批量检查时自动两库联查：先查 flk，查不到的再查规章库
- flk API 无需认证，稳定可靠
- 规章库 API 需要动态 athenaappkey，过期后会自动通过 playwright-cli 刷新并验证，通常无需手动干预；如自动刷新失败，按 `config/README.md` 手动获取
- **查询和下载间隔建议 0.5–1 秒**
- 国家规章库只收录现行有效规章，已废止的不在库中
- 部分规范性文件（通知、意见、指引等）两库都不收录，需人工确认
- `--content` 按正文内容搜索，两个库都支持
- `--all-pages` 自动翻页获取全部结果，适用于结果较多的场景
- 全文搜索建议用短关键词（2–4 个词），长句可能无结果
- 规章库下载通过抓取详情页 HTML 用 pandoc 转 docx，需要安装 pandoc
- Excel 输出使用 openpyxl，需要安装（`pip install openpyxl`）
- **不要自己写法规匹配逻辑**，直接用 `unified_batch_check()`，它内部已处理好精确匹配、多版本选择、None 值等边界情况
- **不要自己写下载逻辑**，用 `batch_download_from_check()` 组合 `unified_batch_check()` 的结果，它自动区分 flk/规章库并支持断点续下
- 批量下载如有超时，重跑即可（自动跳过已完成的，断点续下）

## 自我进化规则

当使用本 skill 完成任务后，如果发现以下情况，应自动更新 skill 代码和文档：

1. **新的 API 变化**：如果 flk 或规章库的 API 接口发生变化（返回格式、URL、认证方式等），更新对应的 `scripts/lib/flk_api.py` 或 `scripts/lib/gov_api.py`
2. **新的使用模式**：如果用户的使用方式产生了新的有用函数或工作流，将其集成到 `scripts/law_search.py` 并更新 SKILL.md
3. **Bug 修复**：如果在使用中发现并修复了 bug，确保修复被持久化到 skill 文件中
4. **经验积累**：如果遇到新的已知问题或解决方案，更新 `assets/known-issues.md`
5. **依赖变化**：如果发现新的依赖需求或依赖版本问题，更新 `config/requirements.txt`

更新时遵循以下原则：

- 保持向后兼容，不破坏已有的 API
- 新增函数同时提供 Python API 和 CLI 接口
- 所有批量操作都支持断点续做（通过进度文件）
- 更新 SKILL.md 的函数一览表和使用示例

## 本地 law.db 维护（institution-audit 技能 lawdb 目录）

数据库位置：`skills/institution-audit/lawdb/law.db`（唯一权威副本；工作区 `lawdb/` 仅保留备份与缓存）
表结构：`laws`（元数据+题注 preamble+全文）、`articles`（条文）、`articles_fts`（FTS5 trigram 虚拟表）

### 预览服务（serve_lawdb.py）

```bash
# 启动（沙箱重启后需重新启动）
cd skills/institution-audit/lawdb && \
nohup python3 serve_lawdb.py --host 0.0.0.0 --port 8317 > serve_lawdb.log 2>&1 &

# 访问：http://<本机IP>:8317/   （API: /api/meta 返回版本号+法规/条文数）
```

- 服务动态读取 law.db：数据库 mtime/size 变化 → 自动重新生成 preview.html 并缓存
- 前端每 8 秒轮询 /api/meta，版本变化自动整页刷新，无需手动操作
- **改 preview_lawdb.py 模板后必须 `touch law.db`（或重启服务）**，否则 ensure_fresh 按 db_key 判断不会重新生成

### 删除法规的正确顺序（重要）

```sql
-- 1. 先取该法规的 article ids
SELECT id FROM articles WHERE law_id = <id>;
-- 2. 删 FTS 索引（否则留孤儿索引）
DELETE FROM articles_fts WHERE article_ref IN (SELECT id FROM articles WHERE law_id = <id>);
-- 3. 删条文
DELETE FROM articles WHERE law_id = <id>;
-- 4. 删法规
DELETE FROM laws WHERE id = <id>;
```

### 常用查询

```bash
sqlite3 law.db "SELECT COUNT(*) FROM laws;"          # 法规数
sqlite3 law.db "SELECT COUNT(*) FROM articles;"      # 条文数
sqlite3 law.db "SELECT id,name,status,level FROM laws ORDER BY id;"  # 清单
```

### 校验

```bash
python3 lawdb/verify_lawdb.py    # 逐字核对官方源（无官方源的自动跳过）
```

## 目录维护约定

- `assets/`：规范和规则（数据源、入库、已知问题、本文件）
- `references/`：输出模板（JSON 清单、进度文件、格式说明）
- `config/`：对接系统环境的配置文件（playwright-config、requirements、配置说明）
- `scripts/`：可执行脚本与 API 模块（`scripts/lib/` 为 Python 包）
- 运行时产物（`.playwright-cli/`、`__pycache__/`、`.athena_key_cache.json`）不提交、不入库
