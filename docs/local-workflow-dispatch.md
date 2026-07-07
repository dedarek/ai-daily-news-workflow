# Local Workflow Dispatch

Use a local machine or Linux server as the reliable scheduler. The local
scheduler checks GitHub Pages first, then calls `workflow_dispatch` only when it
is useful.

## Token

Create a GitHub fine-grained token with access to this repository and
`Actions: Read and write`.

Set it on the scheduler machine:

```bash
export GH_TOKEN=github_pat_xxx
```

Windows PowerShell:

```powershell
setx GH_TOKEN "github_pat_xxx"
```

## Manual Test

```bash
python scripts/dispatch_daily_workflow.py morning --dry-run
python scripts/dispatch_daily_workflow.py afternoon --dry-run
```

Real dispatch:

```bash
python scripts/dispatch_daily_workflow.py morning
python scripts/dispatch_daily_workflow.py afternoon
```

## Linux Cron

Use Asia/Shanghai timezone on the host, or keep `CRON_TZ=Asia/Shanghai`.

```cron
CRON_TZ=Asia/Shanghai
25 11 * * * cd /path/to/ai-daily-news-workflow && mkdir -p logs && /usr/bin/python3 scripts/dispatch_daily_workflow.py morning >> logs/local-dispatch.log 2>&1
30 14 * * * cd /path/to/ai-daily-news-workflow && mkdir -p logs && /usr/bin/python3 scripts/dispatch_daily_workflow.py afternoon >> logs/local-dispatch.log 2>&1
```

Recommended fallback checks:

```cron
CRON_TZ=Asia/Shanghai
55 11 * * * cd /path/to/ai-daily-news-workflow && mkdir -p logs && /usr/bin/python3 scripts/dispatch_daily_workflow.py morning >> logs/local-dispatch.log 2>&1
00 15 * * * cd /path/to/ai-daily-news-workflow && mkdir -p logs && /usr/bin/python3 scripts/dispatch_daily_workflow.py afternoon >> logs/local-dispatch.log 2>&1
```

The script is idempotent:

- Morning dispatch is skipped when today's public manifest is already ready.
- Afternoon dispatch is skipped when the afternoon delivery marker exists.
- Afternoon dispatch is skipped when morning output is not ready.
- Existing active workflow_dispatch runs are not duplicated.

## Windows Task Scheduler

Create two daily tasks.

Program:

```text
python
```

Morning arguments:

```text
scripts\dispatch_daily_workflow.py morning
```

Afternoon arguments:

```text
scripts\dispatch_daily_workflow.py afternoon
```

Start in:

```text
D:\codes\projects\ai-daily-news-workflow
```
