# 进度文件模板（Progress Files）

批量操作（查询/下载）的断点续做进度文件结构。

## 一、check_progress.json（批量检查进度）

`batch_check_to_excel()` 的 `progress_file` 参数生成的进度文件，结构为 `{法规名: 结果dict}`：

```json
{
  "中华人民共和国安全生产法": {
    "found": true,
    "title": "中华人民共和国安全生产法",
    "status": "有效",
    "bbbs": "xxx",
    "url": "https://flk.npc.gov.cn/...",
    "flxz": "法律",
    "source": "国家法律法规数据库"
  },
  "某内部指引": {
    "found": false,
    "status": "未找到（搜索结果不匹配）"
  }
}
```

断点续查：重新运行会跳过已存在的 key，只查缺失的法规。

## 二、download_progress.json（批量下载进度）

`batch_download_from_check()` 的 `dl_progress_file` 参数生成的进度文件，结构为 `{法规名: {状态, 路径}}`：

```json
{
  "中华人民共和国安全生产法": {
    "status": "ok",
    "path": "./下载/法律_中华人民共和国安全生产法_2021-06-10_有效.docx",
    "source": "国家法律法规数据库"
  },
  "某指引": {
    "status": "not_found",
    "error": "两库均未找到"
  }
}
```

- `status: "ok"` → 已下载完成，重跑自动跳过
- `status: "not_found"` / `"failed"` → 重跑会重试

## 三、batch 入库清单模板

批量入库（`lawdb_import.import_batch`）的 entries 清单见 `batch-entries.example.json`。
