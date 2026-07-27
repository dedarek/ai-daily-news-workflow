#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import smtplib
import ssl
from pathlib import Path

from send_admin_alert import build_message, read_recipients, read_smtp_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Alert admins when one or more AI daily-news sources fail"
    )
    parser.add_argument("--date", required=True, help="Issue date in YYYY-MM-DD")
    parser.add_argument("--health-report", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def failed_sources(report: dict) -> list[dict]:
    sources = report.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("Source health report has no sources list")
    return [
        item
        for item in sources
        if isinstance(item, dict) and item.get("status") != "ok"
    ]


def build_alert_text(issue_date: str, report: dict, failures: list[dict]) -> str:
    lines = [
        "AI 日报数据源告警",
        "",
        f"日报日期: {issue_date}",
        f"总体状态: {report.get('overall_status', 'unknown')}",
        f"仍可继续生成: {'是' if report.get('pipeline_can_continue') else '否'}",
        f"候选新闻: {report.get('candidate_count_after_dedup', 0)} 条（去重后）",
        f"异常源数量: {len(failures)}",
        "",
    ]
    for index, source in enumerate(failures, 1):
        lines.extend(
            [
                f"{index}. {source.get('source_name') or source.get('source_id')}",
                f"   适配器: {source.get('adapter', '')}",
                f"   地址: {source.get('source_url', '')}",
                f"   状态: {source.get('status', 'unknown')}",
                f"   原因: {source.get('error') or 'unknown error'}",
                f"   耗时: {source.get('duration_ms', 0)} ms",
                "",
            ]
        )
    lines.append("其他正常数据源会继续参与聚合；请单独检查上述站点或适配器。")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = json.loads(args.health_report.read_text(encoding="utf-8"))
    failures = failed_sources(report)
    if not failures:
        print("All enabled news sources are healthy; no alert sent.", flush=True)
        return 0

    recipients = read_recipients("admins")
    subject = (
        f"AI日报数据源告警 - {args.date} - "
        f"{len(failures)}/{len(report.get('sources', []))} 异常"
    )
    body = build_alert_text(args.date, report, failures)
    if args.dry_run:
        print(f"DRY-RUN subject={subject}", flush=True)
        print(f"DRY-RUN recipients={', '.join(recipients)}", flush=True)
        print(body, flush=True)
        return 0

    host, port, sender, password = read_smtp_config()
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
        server.login(sender, password)
        for recipient in recipients:
            message = build_message(sender, recipient, subject, body)
            server.sendmail(sender, [recipient], message.as_string())
            print(f"Source health alert sent to {recipient}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
