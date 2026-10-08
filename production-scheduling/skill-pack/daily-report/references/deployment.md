# 部署与分享说明（daily-report 技能）

## 目录结构

```
daily-report/
├── SKILL.md                        # 技能主文档（入口）
├── scripts/
│   ├── config.py                   # ⚙️ 统一配置（金蝶/邮箱/企微/阈值/路径）
│   ├── query_kingdee.py            # 金蝶查询封装 + 业务口径常量
│   ├── daily_stock_snapshot.py     # 每日23:59 库存快照 → data/snapshots/
│   ├── daily_production_sales_report.py  # 每日8:30 邮箱日报（HTML+CSV附件）
│   └── daily_morning_report_wecom.py    # 每日9:00 企微晨报（文本）
├── templates/
│   ├── wecom_template.md           # 企微晨报模板 + 每行参数说明
│   ├── email_template.md           # 邮箱HTML模板 + 区块参数说明
│   └── attachments_spec.md         # CSV附件规范
├── references/
│   ├── erp_config.md               # 对接系统配置（金蝶/邮件/企微）
│   ├── calculation_rules.md        # 每个参数的计算规则（口径规范）
│   └── deployment.md               # 本文件
├── data/snapshots/                 # 库存快照CSV（运行时生成，历史积累）
└── output/                         # 日报预览HTML等产出
```

## 环境依赖

```bash
pip install kingdee.cdp.webapi.sdk==8.2.0
# OpenClaw Gateway 需配置 wecom 通道（企微晨报发送依赖）
# 邮件用 Python 标准库 smtplib，无需额外安装
```

## 部署步骤（新环境）

1. 将 `daily-report/` 整个目录放到目标工作空间的 `skills/` 下
2. 修改 `scripts/config.py`：
   - 金蝶：SERVER_URL / ACCT_ID / APP_ID / APP_SECRET
   - 邮件：MAIL_USER / MAIL_PWD（自收自发，也可改为收件人列表）
   - 企微：WECOM_ACCOUNT / WECOM_TARGET
3. 首次运行前确认 `data/snapshots/` 至少有连续两日快照（否则产销率降级）
   - 手动补快照：`python3 scripts/daily_stock_snapshot.py`
4. 冒烟测试（不发送）：
   ```bash
   cd skills/daily-report/scripts
   python3 daily_production_sales_report.py --preview --date 2026-08-13
   python3 daily_morning_report_wecom.py --preview --date 2026-08-13
   ```
5. 配置定时任务（见下）

## 定时任务（OpenClaw cron，3个）

> 禁止使用 crontab，一律 `openclaw cron add`。以下为关键参数，实际执行时以对应agent的ID/渠道为准。

| 任务 | 时间 | 命令 | 说明 |
|------|------|------|------|
| 每日库存快照 | 每天 23:59 | `python3 {SKILL_DIR}/scripts/daily_stock_snapshot.py` | 快照必须在日报前生成 |
| 每日产销率回款率日报 | 每天 08:30 | `python3 {SKILL_DIR}/scripts/daily_production_sales_report.py` | 邮件日报 |
| 每日企微经营晨报 | 每天 09:00 | `python3 {SKILL_DIR}/scripts/daily_morning_report_wecom.py` | 企微文本晨报 |

顺序依赖：快照(23:59) → 邮箱日报(08:30) → 企微晨报(09:00)。若某日快照失败，次日两个日报会自动降级（只发销量/回款部分并提示"快照不足"）。

cron 模板（isolated session，agentTurn）：
```
openclaw cron add --agent <AGENT_ID> --name "每日库存快照" --session isolated --timeout-seconds 0 \
  --schedule "cron:59 23 * * *" \
  --message "执行每日库存快照任务：运行 python3 {SKILL_DIR}/scripts/daily_stock_snapshot.py ..." \
  --no-deliver
```

## 分享给别人时的注意事项

1. **敏感信息**：`scripts/config.py` 和 `references/erp_config.md` 含金蝶密钥、邮箱密码、企微目标。分享前确认接收方为授权人员，或替换为接收方自己的配置。
2. **数据目录**：`data/snapshots/` 是历史积累（产销率反推的前提），分享时可携带最近快照，或让接收方先跑几天快照再启用日报。
3. **业务口径**：references/calculation_rules.md 中的口径（优等品定义、排除客户、阈值）是某陶瓷企业客户确认的。分享给其他企业时需重新确认，不能照搬。
4. **渠道依赖**：企微发送依赖 OpenClaw Gateway 的 wecom 通道配置；邮件依赖 SMTP 可达性。

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 日报显示"快照不足" | data/snapshots 缺连续两日 | 跑 daily_stock_snapshot.py 补快照 |
| 回款率异常偏高/偏低 | 未过滤单据状态（暂存单混入） | 待用户确认后加 FDOCUMENTSTATUS='C' |
| 出库窗口"触及Limit"警告 | 分段查询超10000行 | 结果可能不完整，人工复核 |
| 企微发送失败 rc!=0 | wecom 通道未配置/账号目标失效 | 检查 config.py 的 WECOM_ACCOUNT/TARGET 与 Gateway 通道 |
