#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import smtplib
import ssl
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TMP = Path('/tmp')
TEST_RECIPIENT = 'yyc54321@126.com'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Send the AI daily-news test email to the single approved recipient')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--dry-run', action='store_true', help='Build and validate messages without SMTP delivery')
    parser.add_argument('--subject-suffix', default='', help='Optional text appended to the email subject')
    return parser.parse_args()


def read_smtp_config() -> tuple[str, int, str, str]:
    text = (SKILL_DIR / 'references' / 'smtp-config.md').read_text(encoding='utf-8')

    def value(pattern: str, label: str) -> str:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            raise RuntimeError(f'Cannot read {label} from smtp-config.md')
        return match.group(1).strip()

    sender = os.environ.get('AI_DAILY_SMTP_USER') or value(r'\*\*邮箱\*\*[：:]\s*([^\s]+)', 'sender')
    password = os.environ.get('AI_DAILY_SMTP_PASSWORD') or value(r'\*\*授权码\*\*[：:]\s*([^\s]+)', 'password')
    host = os.environ.get('AI_DAILY_SMTP_HOST') or value(r'\*\*SMTP服务器\*\*[：:]\s*([^\s]+)', 'host')
    port = int(os.environ.get('AI_DAILY_SMTP_PORT', '465'))
    return host, port, sender, password


def read_recipients() -> list[str]:
    text = (SKILL_DIR / 'references' / 'recipients.md').read_text(encoding='utf-8')
    configured = list(dict.fromkeys(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)))
    if configured != [TEST_RECIPIENT]:
        raise RuntimeError(
            f'Test-mode recipient guard rejected configuration: expected only {TEST_RECIPIENT}, got {configured}'
        )
    return configured


def build_message(
    date_str: str,
    sender: str,
    recipient: str,
    html_content: str,
    mp3_path: Path,
    subject_suffix: str = '',
) -> MIMEMultipart:
    message = MIMEMultipart('mixed')
    message['Subject'] = f'每日AI热点新闻（试运营）— {date_str}{subject_suffix}'
    message['From'] = sender
    message['To'] = recipient

    alternative = MIMEMultipart('alternative')
    plain = re.sub(r'<[^>]+>', ' ', html_content)
    plain = re.sub(r'\s+', ' ', plain).strip()
    alternative.attach(MIMEText(plain, 'plain', 'utf-8'))
    alternative.attach(MIMEText(html_content, 'html', 'utf-8'))
    message.attach(alternative)

    with mp3_path.open('rb') as audio_file:
        audio = MIMEBase('audio', 'mpeg')
        audio.set_payload(audio_file.read())
    encoders.encode_base64(audio)
    audio.add_header('Content-Disposition', 'attachment', filename=f'ai-daily-news-{date_str}.mp3')
    message.attach(audio)
    return message


def send_one(host: str, port: int, sender: str, password: str, recipient: str, message: MIMEMultipart) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], message.as_string())


def main() -> int:
    args = parse_args()
    html_path = TMP / f'ai-daily-news-html-{args.date}.html'
    mp3_path = TMP / f'ai-daily-news-podcast-{args.date}.mp3'
    if not html_path.exists() or not mp3_path.exists():
        raise FileNotFoundError(f'Missing input: html={html_path.exists()} mp3={mp3_path.exists()}')

    html_content = html_path.read_text(encoding='utf-8')
    recipients = read_recipients()
    if recipients != [TEST_RECIPIENT]:
        raise RuntimeError('Recipient guard failed; refusing delivery')
    host, port, sender, password = read_smtp_config()
    delay = float(os.environ.get('AI_DAILY_SEND_DELAY', '8'))
    batch_pause = float(os.environ.get('AI_DAILY_BATCH_PAUSE', '30'))
    success = 0

    for index, recipient in enumerate(recipients, start=1):
        message = build_message(
            args.date,
            sender,
            recipient,
            html_content,
            mp3_path,
            args.subject_suffix,
        )
        if args.dry_run:
            print(f'✅ [{index}/{len(recipients)}] DRY-RUN {recipient}', flush=True)
            success += 1
            continue

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                send_one(host, port, sender, password, recipient, message)
                print(f'✅ [{index}/{len(recipients)}] {recipient}', flush=True)
                success += 1
                last_error = None
                break
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                print(f'⚠️ [{index}/{len(recipients)}] attempt={attempt} {recipient}: {exc}', flush=True)
                if attempt < 3:
                    time.sleep(60)
        if last_error is not None:
            print(f'❌ {recipient}: {last_error}', flush=True)

        if index < len(recipients):
            time.sleep(delay)
            if index % 10 == 0:
                time.sleep(batch_pause)

    print(f'成功: {success} / {len(recipients)}', flush=True)
    return 0 if success == len(recipients) else 1


if __name__ == '__main__':
    raise SystemExit(main())
