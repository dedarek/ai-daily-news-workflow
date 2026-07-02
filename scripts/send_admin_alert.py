#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
RECIPIENTS_FILE = SKILL_DIR / 'references' / 'recipients.json'
SMTP_CONFIG_FILE = SKILL_DIR / 'references' / 'smtp-config.md'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Send a plain-text admin alert for AI daily-news workflow failures')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--phase', required=True, help='Workflow phase, for example afternoon')
    parser.add_argument('--reason', required=True, help='Failure reason to include in the alert')
    parser.add_argument('--issue-url', default='', help='Related content API URL')
    parser.add_argument('--dry-run', action='store_true', help='Print recipients and subject without SMTP delivery')
    return parser.parse_args()


def read_recipients(audience: str = 'admins') -> list[str]:
    configured = json.loads(RECIPIENTS_FILE.read_text(encoding='utf-8'))
    recipients = configured.get(audience)
    if not isinstance(recipients, list) or not recipients:
        raise RuntimeError(f'Missing non-empty recipient audience "{audience}" in {RECIPIENTS_FILE}')
    return [str(item).strip() for item in recipients if str(item).strip()]


def read_smtp_config() -> tuple[str, int, str, str]:
    text = SMTP_CONFIG_FILE.read_text(encoding='utf-8')

    def value(pattern: str, label: str) -> str:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            raise RuntimeError(f'Cannot read {label} from {SMTP_CONFIG_FILE}')
        return match.group(1).strip()

    sender = os.environ.get('AI_DAILY_SMTP_USER') or value(r'\*\*邮箱\*\*[：:]\s*([^\s]+)', 'sender')
    password = os.environ.get('AI_DAILY_SMTP_PASSWORD') or value(r'\*\*授权码\*\*[：:]\s*([^\s]+)', 'password')
    host = os.environ.get('AI_DAILY_SMTP_HOST') or value(r'\*\*SMTP服务器\*\*[：:]\s*([^\s]+)', 'host')
    port = int(os.environ.get('AI_DAILY_SMTP_PORT', '465'))
    return host, port, sender, password


def build_message(sender: str, recipient: str, subject: str, body: str) -> MIMEText:
    message = MIMEText(body, 'plain', 'utf-8')
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient
    return message


def main() -> int:
    args = parse_args()
    recipients = read_recipients('admins')
    subject = f'AI日报流程告警 - {args.date} - {args.phase}'
    body_lines = [
        'AI日报流程告警',
        '',
        f'日期: {args.date}',
        f'阶段: {args.phase}',
        f'原因: {args.reason}',
    ]
    if args.issue_url:
        body_lines.append(f'Manifest URL: {args.issue_url}')
    body = '\n'.join(body_lines)

    if args.dry_run:
        print(f'DRY-RUN subject={subject}', flush=True)
        print(f'DRY-RUN recipients={", ".join(recipients)}', flush=True)
        return 0

    host, port, sender, password = read_smtp_config()
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
        server.login(sender, password)
        for recipient in recipients:
            message = build_message(sender, recipient, subject, body)
            server.sendmail(sender, [recipient], message.as_string())
            print(f'Admin alert sent to {recipient}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
