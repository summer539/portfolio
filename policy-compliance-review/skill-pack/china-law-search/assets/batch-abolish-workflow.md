# 批量废止法规导入流程（flk 标题含"废止"全量入库）

> 场景：把国家法律法规数据库（flk）+ 国家规章库中**标题含"废止"**的法规全量录入本地 law.db。
> 首次实战：2026-08-27，规模 574 条（flk 573 + 规章库 1）。
> 完整脚本：`lawdb/abolish/import_abolish.py`（工作区 lawdb 目录），可复制复用。

## 为什么需要专门流程

1. **flk 有 IP 级反爬**：连续约 50 次请求触发限流，返回 HTML 而非 JSON，冷却 2–3 分钟（详见 known-issues.md 第一节）
2. **规模大**：500+ 条不可能一次跑完，必须分批 + 断点续做
3. **多阶段**：下载（受反爬限制，慢）→ 入库（纯本地解析 docx，无网络，可提速）

## 标准流程

```text
1. 预检清单
   flk 搜索"废止"（标题），得到 bbbs 清单；规章库搜索"废止"（标题）
   → 合并去重，写入 flk_abolish_list.json

2. 分批下载（受反爬限制，cron 调度）
   */30 * * * *  →  每批 30 条
   进度文件：download_progress.json（断点续做，重跑自动跳过已完成）
   docx 存储：abolish/docx/{bbbs}.docx

3. 解析入库（无网络请求，可一次跑完）
   解析 docx（复用 build_lawdb.parse_docx 逻辑）→ import_law 入库
   进度文件：import_progress.json
   幂等：已入库的跳过

4. 校验
   verify 子命令逐字核对官方源；全部完成后更新 preview.html

5. 收尾
   全部完成 → 删除 cron 任务 → 向用户汇报收录统计
```

## 脚本结构（import_abolish.py）

五个子命令，全部断点续做：

| 子命令 | 作用 |
|---|---|
| `fetch-gov` | 从规章库抓取标题含"废止"的规章清单 |
| `download` | 分批下载 flk docx（每批条数可配，默认 30） |
| `import` | 解析 docx 入库（幂等，可反复跑） |
| `gov-import` | 规章库条目入库 |
| `verify` | 校验已入库条文与官方源一致性 |

`run_once.py`：自动判断当前阶段（下载未完成→继续下载；下载完→入库；入库完→校验报告），供 cron 直接调用，无需人工判断。

## cron 调度模板

```bash
openclaw cron add --agent <ID> --name "废止法规分批入库(flk30条/30分钟)" \
  --session isolated --timeout-seconds 0 \
  --schedule "*/30 * * * *" --tz Asia/Shanghai \
  --no-deliver \
  --message "运行 lawdb/abolish/run_once.py，按进度文件断点续做废止法规下载/入库"
```

## 关键经验

- 下载阶段必须克制：30 条/30 分钟是验证过的安全节奏，贪快会触发 IP 级限流
- 反爬触发后**所有** flk API 都被限流，不是单个接口，必须等冷却
- 入库阶段不受限流影响（纯本地解析），下载完成后可手动加速一次跑完
- 进度文件是唯一事实来源：cron 每次运行先读进度文件决定做什么，绝不从头开始
