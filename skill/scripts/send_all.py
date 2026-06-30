#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
RECIPIENTS_FILE = SKILL_DIR / 'references' / 'recipients.json'
SEND_EMAIL_CONFIG_FILE = SKILL_DIR / 'references' / 'send-email-config.json'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Send the AI daily-news email to a configured recipient audience')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument(
        '--artifact-dir',
        help='Directory containing generated artifacts. Defaults to /tmp for legacy compatibility.',
    )
    parser.add_argument('--phase', help='Delivery phase from send-email-config.json, for example morning or afternoon')
    parser.add_argument(
        '--audience',
        help='Override recipient audience key from recipients.json, for example admins or all',
    )
    parser.add_argument(
        '--subject-suffix',
        default=None,
        help='Override text appended to the email subject. Defaults to the phase config.',
    )
    parser.add_argument('--dry-run', action='store_true', help='Build and validate messages without SMTP delivery')
    return parser.parse_args()


def resolve_artifact(artifact_dir: Path, date_str: str, names: list[str]) -> Path:
    for name in names:
        path = artifact_dir / name.format(date=date_str)
        if path.is_file():
            return path
    expected = ', '.join(str(artifact_dir / name.format(date=date_str)) for name in names)
    raise FileNotFoundError(f'Missing artifact. Tried: {expected}')


def read_send_email_config() -> dict:
    try:
        configured = json.loads(SEND_EMAIL_CONFIG_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'Missing send email config: {SEND_EMAIL_CONFIG_FILE}') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid send email config JSON in {SEND_EMAIL_CONFIG_FILE}: {exc}') from exc
    if not isinstance(configured, dict):
        raise RuntimeError(f'Send email config must be a JSON object: {SEND_EMAIL_CONFIG_FILE}')
    return configured


def resolve_delivery_options(args: argparse.Namespace, config: dict) -> tuple[str, str, float, float, int, float]:
    phase_config: dict = {}
    if args.phase:
        phases = config.get('phases')
        if not isinstance(phases, dict) or args.phase not in phases:
            available = ', '.join(sorted(str(key) for key in phases)) if isinstance(phases, dict) else ''
            raise RuntimeError(f'Unknown email phase "{args.phase}". Available phases: {available}')
        phase_config = phases[args.phase]
        if not isinstance(phase_config, dict):
            raise RuntimeError(f'Email phase "{args.phase}" must be an object')

    audience = args.audience or phase_config.get('audience')
    if not isinstance(audience, str) or not audience.strip():
        raise RuntimeError('Missing recipient audience. Pass --phase or --audience.')

    subject_suffix = args.subject_suffix
    if subject_suffix is None:
        subject_suffix = phase_config.get('subject_suffix', '')
    if not isinstance(subject_suffix, str):
        raise RuntimeError('subject_suffix must be a string')

    delay = float(os.environ.get('AI_DAILY_SEND_DELAY', config.get('send_delay_seconds', 8)))
    batch_pause = float(os.environ.get('AI_DAILY_BATCH_PAUSE', config.get('batch_pause_seconds', 30)))
    retry_attempts = int(os.environ.get('AI_DAILY_SEND_RETRY_ATTEMPTS', config.get('retry_attempts', 3)))
    retry_delay = float(os.environ.get('AI_DAILY_SEND_RETRY_DELAY', config.get('retry_delay_seconds', 60)))
    if retry_attempts < 1:
        raise RuntimeError('retry_attempts must be >= 1')
    return audience.strip(), subject_suffix, delay, batch_pause, retry_attempts, retry_delay


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


def read_recipients(audience: str) -> list[str]:
    try:
        configured = json.loads(RECIPIENTS_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'Missing recipient config: {RECIPIENTS_FILE}') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid recipient JSON in {RECIPIENTS_FILE}: {exc}') from exc

    if not isinstance(configured, dict) or not configured:
        raise RuntimeError(f'Recipient JSON must be a non-empty object of audience arrays: {RECIPIENTS_FILE}')
    if audience not in configured:
        available = ', '.join(sorted(str(key) for key in configured))
        raise RuntimeError(f'Unknown recipient audience "{audience}". Available audiences: {available}')

    recipients = configured[audience]
    if not isinstance(recipients, list) or not recipients:
        raise RuntimeError(f'Recipient audience "{audience}" must be a non-empty array: {RECIPIENTS_FILE}')

    validated: list[str] = []
    seen: set[str] = set()
    for item in recipients:
        if not isinstance(item, str):
            raise RuntimeError(f'Recipient audience "{audience}" must contain only strings: {RECIPIENTS_FILE}')
        recipient = item.strip()
        if not recipient:
            raise RuntimeError(f'Recipient audience "{audience}" contains blank entry: {RECIPIENTS_FILE}')
        if not re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', recipient):
            raise RuntimeError(f'Invalid recipient address in {RECIPIENTS_FILE}: {recipient}')
        if recipient in seen:
            raise RuntimeError(f'Duplicate recipient in audience "{audience}": {recipient}')
        seen.add(recipient)
        validated.append(recipient)
    return validated


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
    email_config = read_send_email_config()
    audience, subject_suffix, delay, batch_pause, retry_attempts, retry_delay = resolve_delivery_options(
        args,
        email_config,
    )
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else TMP
    html_path = resolve_artifact(
        artifact_dir,
        args.date,
        [
            'daily-news-{date}.html',
            'ai-daily-news-html-{date}.html',
        ],
    )
    mp3_path = resolve_artifact(
        artifact_dir,
        args.date,
        [
            'daily-news-podcast-{date}.mp3',
            'ai-daily-news-podcast-{date}.mp3',
        ],
    )

    html_content = html_path.read_text(encoding='utf-8')
    recipients = read_recipients(audience)
    host, port, sender, password = read_smtp_config()
    success = 0

    if args.phase:
        print(f'Phase: {args.phase}', flush=True)
    print(f'Audience: {audience}', flush=True)

    for index, recipient in enumerate(recipients, start=1):
        message = build_message(args.date, sender, recipient, html_content, mp3_path, subject_suffix)
        if args.dry_run:
            print(f'✅ [{index}/{len(recipients)}] DRY-RUN {recipient}', flush=True)
            success += 1
            continue

        last_error: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            try:
                send_one(host, port, sender, password, recipient, message)
                print(f'✅ [{index}/{len(recipients)}] {recipient}', flush=True)
                success += 1
                last_error = None
                break
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                print(f'⚠️ [{index}/{len(recipients)}] attempt={attempt} {recipient}: {exc}', flush=True)
                if attempt < retry_attempts:
                    time.sleep(retry_delay)
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
