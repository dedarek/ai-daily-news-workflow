#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.policy import SMTP
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TMP = Path('/tmp')
RECIPIENTS_FILE = SKILL_DIR / 'references' / 'recipients.json'
SEND_EMAIL_CONFIG_FILE = SKILL_DIR / 'references' / 'send-email-config.json'
DEFAULT_PUBLIC_BASE_URL = 'https://dedarek.github.io/ai-daily-news-workflow'
DEFAULT_DAILY_SITE_URL = 'https://tokenless.top/daily'


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
    parser.add_argument('--dry-run', action='store_true', help='Build and validate messages without SMTP delivery')
    return parser.parse_args()


def resolve_artifact(artifact_dir: Path, date_str: str, names: list[str]) -> Path:
    for name in names:
        path = artifact_dir / name.format(date=date_str)
        if path.is_file():
            return path
    expected = ', '.join(str(artifact_dir / name.format(date=date_str)) for name in names)
    raise FileNotFoundError(f'Missing artifact. Tried: {expected}')


def resolve_optional_artifact(artifact_dir: Path, date_str: str, names: list[str]) -> Path | None:
    for name in names:
        path = artifact_dir / name.format(date=date_str)
        if path.is_file():
            return path
    return None


def env_truthy(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def email_video_attachment_limit_bytes() -> int:
    raw = (
        os.environ.get('AI_DAILY_EMAIL_VIDEO_ATTACHMENT_LIMIT_BYTES')
        or os.environ.get('AI_DAILY_EMAIL_MP4_ATTACHMENT_LIMIT_BYTES')
        or str(20 * 1024 * 1024)
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return 20 * 1024 * 1024


def flow_limit_cooldown_seconds() -> float:
    raw = os.environ.get('AI_DAILY_FLOW_LIMIT_COOLDOWN_SECONDS', '900')
    try:
        return max(60.0, float(raw))
    except ValueError:
        return 900.0


def recipient_batch_size(media_kind: str) -> int:
    raw = os.environ.get('AI_DAILY_RECIPIENT_BATCH_SIZE')
    if raw is None and media_kind == 'video':
        raw = os.environ.get('AI_DAILY_VIDEO_RECIPIENT_BATCH_SIZE', '10')
    if raw is None:
        raw = '1'
    try:
        return max(1, int(raw))
    except ValueError:
        return 10 if media_kind == 'video' else 1


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def delivery_status_path(artifact_dir: Path, date_str: str, phase: str | None) -> Path:
    phase_name = phase or 'manual'
    return artifact_dir / f'delivery-status-{phase_name}-{date_str}.json'


def load_delivery_status(path: Path, date_str: str, phase: str | None, audience: str) -> dict:
    default = {
        'date': date_str,
        'phase': phase or 'manual',
        'audience': audience,
        'sent': {},
        'failed': {},
    }
    if not path.is_file() or env_truthy('AI_DAILY_IGNORE_DELIVERY_STATUS', False):
        return default
    try:
        loaded = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid delivery status JSON in {path}: {exc}') from exc
    if not isinstance(loaded, dict):
        raise RuntimeError(f'Delivery status must be a JSON object: {path}')
    if loaded.get('date') != date_str or loaded.get('phase') != (phase or 'manual'):
        raise RuntimeError(f'Delivery status does not match this run: {path}')
    loaded.setdefault('audience', audience)
    loaded.setdefault('sent', {})
    loaded.setdefault('failed', {})
    if not isinstance(loaded['sent'], dict) or not isinstance(loaded['failed'], dict):
        raise RuntimeError(f'Delivery status sent/failed must be objects: {path}')
    return loaded


def write_delivery_status(path: Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def mark_delivery_status(status: dict, recipients: list[str], state: str, error: Exception | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    target = status['sent'] if state == 'sent' else status['failed']
    for recipient in recipients:
        key = recipient.lower()
        target[key] = {
            'recipient': recipient,
            f'{state}_at': now,
        }
        if error is not None:
            target[key]['error'] = str(error)
        if state == 'sent':
            status['failed'].pop(key, None)


def is_flow_limit_error(exc: Exception) -> bool:
    return 'flow over limit' in str(exc).lower()


def public_video_url(date_str: str) -> str:
    base_url = (
        os.environ.get('AI_DAILY_PUBLIC_BASE_URL')
        or os.environ.get('CONTENT_BASE_URL')
        or DEFAULT_PUBLIC_BASE_URL
    ).rstrip('/')
    return f'{base_url}/video/{date_str}.mp4'


def public_daily_site_url() -> str:
    return (
        os.environ.get('AI_DAILY_NEW_SITE_PUBLIC_URL')
        or DEFAULT_DAILY_SITE_URL
    ).rstrip('/')


def insert_after_summary(html_content: str, block: str) -> str:
    if 'data-role="daily-site-entry"' in html_content:
        return html_content
    marker = 'padding:22px 36px 18px;'
    start = html_content.find(marker)
    if start >= 0:
        end = html_content.find('</td></tr>', start)
        if end >= 0:
            return html_content[:end] + block + html_content[end:]
    if '</body>' in html_content:
        return html_content.replace('</body>', block + '</body>')
    return html_content + block


def append_daily_site_link(html_content: str) -> str:
    site_url = public_daily_site_url()
    block = (
        '<table data-role="daily-site-entry" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:18px 0 0;background-color:#eff6ff;border:1px solid #bfdbfe;'
        'border-radius:6px;">'
        '<tr><td style="padding:18px 20px;">'
        '<p style="margin:0 0 7px;color:#1e3a8a;font-size:16px;font-weight:700;line-height:1.5;">'
        '<span style="display:inline-block;margin-right:7px;padding:2px 7px;background-color:#2563eb;'
        'color:#ffffff;font-size:10px;font-weight:700;line-height:1.5;border-radius:3px;'
        'vertical-align:2px;">NEW</span>AI 日报网页版正式上线</p>'
        '<p style="margin:0 0 14px;color:#475569;font-size:13px;line-height:1.7;">'
        '图文、音频与视频内容现已同步更新，阅读更流畅，内容更完整。</p>'
        f'<a href="{site_url}" style="display:inline-block;padding:9px 16px;background-color:#2563eb;'
        'color:#ffffff;text-decoration:none;font-size:13px;font-weight:700;line-height:1.5;'
        'border-radius:5px;">立即体验网页版&nbsp;→</a>'
        '</td></tr></table>'
    )
    return insert_after_summary(html_content, block)


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


def resolve_delivery_options(args: argparse.Namespace, config: dict) -> tuple[str, float, float, int, float]:
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

    delay = float(os.environ.get('AI_DAILY_SEND_DELAY', config.get('send_delay_seconds', 8)))
    batch_pause = float(os.environ.get('AI_DAILY_BATCH_PAUSE', config.get('batch_pause_seconds', 30)))
    retry_attempts = int(os.environ.get('AI_DAILY_SEND_RETRY_ATTEMPTS', config.get('retry_attempts', 3)))
    retry_delay = float(os.environ.get('AI_DAILY_SEND_RETRY_DELAY', config.get('retry_delay_seconds', 60)))
    if retry_attempts < 1:
        raise RuntimeError('retry_attempts must be >= 1')
    return audience.strip(), delay, batch_pause, retry_attempts, retry_delay


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
        dedupe_key = recipient.lower()
        if dedupe_key in seen:
            print(f'WARN duplicate_recipient_skipped audience={audience} recipient={recipient}', flush=True)
            continue
        seen.add(dedupe_key)
        validated.append(recipient)
    return validated


def build_message(
    date_str: str,
    sender: str,
    to_header: str,
    html_content: str,
    media_path: Path,
    media_kind: str,
) -> MIMEMultipart:
    message = MIMEMultipart('mixed', policy=SMTP)
    message['Subject'] = f'每日AI热点新闻（博客试运营）— {date_str}'
    message['From'] = sender
    message['To'] = to_header

    alternative = MIMEMultipart('alternative', policy=SMTP)
    plain = re.sub(r'<[^>]+>', ' ', html_content)
    plain = re.sub(r'\s+', ' ', plain).strip()
    alternative.attach(MIMEText(plain, 'plain', 'utf-8'))
    alternative.attach(MIMEText(html_content, 'html', 'utf-8'))
    message.attach(alternative)

    attachment = EmailMessage(policy=SMTP)
    if media_kind == 'video':
        maintype, subtype, filename = 'video', 'mp4', f'ai-daily-news-{date_str}.mp4'
    else:
        if media_kind != 'audio':
            raise RuntimeError(f'Unknown media attachment kind: {media_kind}')
        maintype, subtype, filename = 'audio', 'mpeg', f'ai-daily-news-{date_str}.mp3'
    attachment.add_attachment(
        media_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=filename,
        disposition='attachment',
    )
    message.attach(attachment)
    return message


def send_batch(host: str, port: int, sender: str, password: str, recipients: list[str], message: MIMEMultipart) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
        server.login(sender, password)
        refused = server.sendmail(sender, recipients, message.as_bytes(policy=SMTP))
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def main() -> int:
    args = parse_args()
    email_config = read_send_email_config()
    audience, delay, batch_pause, retry_attempts, retry_delay = resolve_delivery_options(
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
    mp4_path = resolve_optional_artifact(
        artifact_dir,
        args.date,
        [
            'daily-news-video-{date}.mp4',
            'ai-daily-news-video-{date}.mp4',
        ],
    )

    html_content = html_path.read_text(encoding='utf-8')
    media_path = mp3_path
    media_kind = 'audio'
    if mp4_path is not None:
        html_content = append_daily_site_link(html_content)
        video_limit = email_video_attachment_limit_bytes()
        mp4_size = mp4_path.stat().st_size
        if env_truthy('AI_DAILY_EMAIL_ATTACH_VIDEO', True) and mp4_size <= video_limit:
            media_path = mp4_path
            media_kind = 'video'
        else:
            reason = 'disabled' if not env_truthy('AI_DAILY_EMAIL_ATTACH_VIDEO', True) else f'size={mp4_size} limit={video_limit}'
            print(
                f'MP4_ATTACHMENT_SKIPPED reason={reason} path={mp4_path} '
                f'url={public_video_url(args.date)}',
                flush=True,
            )
    print(
        f'MEDIA_ATTACHMENT_SELECTED kind={media_kind} path={media_path} size={media_path.stat().st_size}',
        flush=True,
    )
    if media_kind == 'video':
        delay = max(delay, float(os.environ.get('AI_DAILY_VIDEO_SEND_DELAY', '90')))
        batch_pause = max(batch_pause, float(os.environ.get('AI_DAILY_VIDEO_BATCH_PAUSE', '600')))
        print(
            f'VIDEO_ATTACHMENT_THROTTLE send_delay={delay}s batch_pause={batch_pause}s',
            flush=True,
        )
    recipients = read_recipients(audience)
    status_path = delivery_status_path(artifact_dir, args.date, args.phase)
    delivery_status = load_delivery_status(status_path, args.date, args.phase, audience)
    already_sent = set(delivery_status['sent'])
    pending_recipients = [recipient for recipient in recipients if recipient.lower() not in already_sent]
    skipped = len(recipients) - len(pending_recipients)
    if skipped:
        print(
            f'DELIVERY_STATUS_RESTORED path={status_path} already_sent={skipped} pending={len(pending_recipients)}',
            flush=True,
        )
    batch_size = recipient_batch_size(media_kind)
    recipient_batches = chunked(pending_recipients, batch_size)
    success = skipped

    if args.phase:
        print(f'Phase: {args.phase}', flush=True)
    print(f'Audience: {audience}', flush=True)
    print(
        f'RECIPIENT_BATCHING batch_size={batch_size} batches={len(recipient_batches)} '
        f'pending={len(pending_recipients)} total={len(recipients)}',
        flush=True,
    )
    if not recipient_batches:
        write_delivery_status(status_path, delivery_status)
        print(f'NO_PENDING_RECIPIENTS status={status_path}', flush=True)
        print(f'成功: {success} / {len(recipients)}', flush=True)
        return 0
    host, port, sender, password = read_smtp_config()

    for index, batch in enumerate(recipient_batches, start=1):
        to_header = batch[0] if len(batch) == 1 else 'undisclosed-recipients:;'
        batch_label = ','.join(batch)
        message = build_message(
            args.date,
            sender,
            to_header,
            html_content,
            media_path,
            media_kind,
        )
        if args.dry_run:
            print(
                f'OK [{index}/{len(recipient_batches)}] DRY-RUN batch_size={len(batch)} recipients={batch_label}',
                flush=True,
            )
            success += len(batch)
            continue

        last_error: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            try:
                send_batch(host, port, sender, password, batch, message)
                print(
                    f'OK [{index}/{len(recipient_batches)}] batch_size={len(batch)} recipients={batch_label}',
                    flush=True,
                )
                success += len(batch)
                mark_delivery_status(delivery_status, batch, 'sent')
                write_delivery_status(status_path, delivery_status)
                last_error = None
                break
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                print(
                    f'WARN [{index}/{len(recipient_batches)}] attempt={attempt} '
                    f'batch_size={len(batch)} recipients={batch_label}: {exc}',
                    flush=True,
                )
                if attempt < retry_attempts:
                    sleep_seconds = flow_limit_cooldown_seconds() if is_flow_limit_error(exc) else retry_delay
                    if is_flow_limit_error(exc):
                        print(
                            f'WARN smtp_flow_limit_cooldown recipients={batch_label} sleep={sleep_seconds}s',
                            flush=True,
                        )
                    time.sleep(sleep_seconds)
        if last_error is not None:
            mark_delivery_status(delivery_status, batch, 'failed', last_error)
            write_delivery_status(status_path, delivery_status)
            print(f'FAIL batch_size={len(batch)} recipients={batch_label}: {last_error}', flush=True)

        if index < len(recipient_batches):
            time.sleep(delay)
            if index % 10 == 0:
                time.sleep(batch_pause)

    print(f'成功: {success} / {len(recipients)}', flush=True)
    return 0 if success == len(recipients) else 1


if __name__ == '__main__':
    raise SystemExit(main())
