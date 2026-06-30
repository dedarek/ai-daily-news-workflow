#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_lib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

TMP = Path('/tmp')
SKILL_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = SKILL_DIR / 'samples'
VALIDATOR = SKILL_DIR / 'scripts' / 'validate_html_quality.py'

MIN_HTML_BYTES = 10 * 1024
MIN_MP3_BYTES = 1_000_000
MAX_MP3_BYTES = 8 * 1024 * 1024
FORBIDDEN_MARKERS = [
    'hubtoday',
    'hex2077',
    'hextra',
    'aibase.com',
    'wappoc_appmsgcaptcha',
    'mp.weixin.qq.com/mp/wappoc',
]
FOOTER_HINTS = ('联系我们', 'contact', '联系', '技术创新中心')


def strip_tags(text: str) -> str:
    text = re.sub(r'<script\b[^>]*>.*?</script>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<style\b[^>]*>.*?</style>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='AI daily news quality gate + one-shot distribution runner')
    p.add_argument('--date', help='YYYY-MM-DD; default=today in local timezone via date command')
    p.add_argument(
        '--artifact-dir',
        help='Directory containing generated artifacts. Defaults to /tmp and skill/samples for legacy compatibility.',
    )
    p.add_argument('--dry-run', action='store_true', help='Only validate/generate plan; never run send-all')
    return p.parse_args()


def detect_date() -> str:
    out = subprocess.check_output(['date', '+%F'], text=True).strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', out):
        raise RuntimeError(f'Unexpected date output: {out!r}')
    return out


def file_info(path: Path) -> str:
    if not path.exists():
        return 'missing'
    return f'{path.stat().st_size} bytes'


def resolve_artifact(artifact_dir: Path, date_str: str, names: List[str]) -> Path:
    for name in names:
        path = artifact_dir / name.format(date=date_str)
        if path.is_file():
            return path
    return artifact_dir / names[0].format(date=date_str)


def gather_links(html: str) -> Tuple[List[str], List[str]]:
    pairs = re.findall(r'<a\b[^>]*href=["\'](https?://[^"\'>\s]+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S)
    filtered: List[str] = []
    root_links: List[str] = []
    for url, anchor_html in pairs:
        if any(bad in url.lower() for bad in FORBIDDEN_MARKERS):
            continue
        text = strip_tags(anchor_html).lower()
        if any(hint in text for hint in FOOTER_HINTS):
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            continue
        is_root = parsed.path in ('', '/') and not parsed.query and not parsed.fragment
        if is_root:
            root_links.append(url)
        filtered.append(url)
    unique = list(dict.fromkeys(filtered))
    unique_root = list(dict.fromkeys(root_links))
    return unique, unique_root


def count_body_blocks(html: str) -> int:
    blocks: List[str] = []

    for m in re.finditer(r'<p\b(?P<attrs>[^>]*)data-role=["\']news-body["\'][^>]*>(?P<body>.*?)</p>', html, flags=re.I | re.S):
        text = strip_tags(m.group('body') or '')
        if len(text) >= 80:
            blocks.append(text)

    for m in re.finditer(r'<(?P<tag>div|p|td)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>', html, flags=re.I | re.S):
        tag = m.group('tag').lower()
        attrs = m.group('attrs') or ''
        body = m.group('body') or ''
        attrs_l = attrs.lower()
        include = False
        if tag == 'p' and ('data-role="news-body"' in attrs_l or "data-role='news-body'" in attrs_l):
            include = True
        elif tag == 'td':
            include = True
        elif 'line-height' in attrs_l:
            include = True
        if not include:
            continue
        text = strip_tags(body)
        if len(text) >= 80:
            blocks.append(text)

    # 去重，避免外层 td 与内层 p 同一段重复计数过多
    dedup = list(dict.fromkeys(blocks))
    return len(dedup)


def ensure_send_script(date_str: str, dry_run: bool) -> Tuple[Path, bool, str]:
    bundled = SKILL_DIR / 'scripts' / 'send_all.py'
    if not bundled.exists():
        raise FileNotFoundError(f'Missing guarded sender: {bundled}')
    return bundled, False, 'bundled-audience-sender'


def detect_running(send_script: Path) -> bool:
    try:
        out = subprocess.check_output(['pgrep', '-af', str(send_script)], text=True)
    except subprocess.CalledProcessError:
        return False
    current_pid = os.getpid()
    for line in out.splitlines():
        parts = line.strip().split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        cmd = parts[1] if len(parts) > 1 else ''
        if pid != current_pid and str(send_script) in cmd:
            return True
    return False


def tail_lines(path: Path, n: int = 10) -> List[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return lines[-n:]


def parse_send_log(log_path: Path) -> Tuple[int | None, int | None, int, int]:
    if not log_path.exists():
        return None, None, 0, 0
    text = log_path.read_text(encoding='utf-8', errors='replace')
    m = re.search(r'成功:\s*(\d+)\s*/\s*(\d+)', text)
    success = total = None
    if m:
        success = int(m.group(1))
        total = int(m.group(2))
    success_lines = len(re.findall(r'^✅ \[\d+/\d+\]', text, flags=re.M))
    fail_lines = len(re.findall(r'^❌ ', text, flags=re.M))
    return success, total, success_lines, fail_lines


def main() -> int:
    args = parse_args()
    date_str = args.date or detect_date()

    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else TMP
    html_path = resolve_artifact(
        artifact_dir,
        date_str,
        [
            'daily-news-{date}.html',
            'ai-daily-news-html-{date}.html',
        ],
    )
    mp3_path = resolve_artifact(
        artifact_dir,
        date_str,
        [
            'daily-news-podcast-{date}.mp3',
            'ai-daily-news-podcast-{date}.mp3',
        ],
    )
    sample_path = None if args.artifact_dir else SAMPLES_DIR / f'{date_str}.html'
    log_path = TMP / f'send-log-{date_str}.txt'

    failures: List[str] = []
    facts: List[str] = []

    if not html_path.exists():
        failures.append(f'MISSING: {html_path}')
        html_text = ''
    else:
        html_size = html_path.stat().st_size
        facts.append(f'HTML: {html_path} ({html_size} bytes)')
        if html_size < MIN_HTML_BYTES:
            failures.append(f'HTML_TOO_SMALL: {html_path} = {html_size} bytes < {MIN_HTML_BYTES}')
        html_text = html_path.read_text(encoding='utf-8', errors='replace')
        if b'&#x' in html_path.read_bytes():
            failures.append(f'HTML_ENTITY_BUG: {html_path} contains &#x entities')

    if not mp3_path.exists():
        failures.append(f'MISSING: {mp3_path}')
    else:
        mp3_size = mp3_path.stat().st_size
        facts.append(f'MP3: {mp3_path} ({mp3_size} bytes)')
        if not (MIN_MP3_BYTES <= mp3_size <= MAX_MP3_BYTES):
            failures.append(f'MP3_SIZE_OUT_OF_RANGE: {mp3_path} = {mp3_size} bytes not in [{MIN_MP3_BYTES}, {MAX_MP3_BYTES}]')

    if sample_path is not None:
        if not sample_path.exists():
            failures.append(f'MISSING: {sample_path}')
        else:
            facts.append(f'SAMPLE: {sample_path} ({sample_path.stat().st_size} bytes)')

    if html_text:
        if not VALIDATOR.exists():
            failures.append(f'MISSING_VALIDATOR: {VALIDATOR}')
        else:
            validator = subprocess.run(
                [sys.executable, str(VALIDATOR), '--date', date_str, '--path', str(html_path)],
                text=True,
                capture_output=True,
            )
            validator_out = (validator.stdout or '').strip()
            if validator_out:
                for line in validator_out.splitlines():
                    facts.append(f'validator: {line}')
            validator_err = (validator.stderr or '').strip()
            if validator_err:
                facts.append(f'validator_stderr: {validator_err}')
            if validator.returncode != 0:
                failures.append(f'VALIDATOR_FAILED: exit={validator.returncode}')

    print(f'CHECK DATE: {date_str}')
    for line in facts:
        print(f'- {line}')

    if failures:
        print('\nQUALITY_GATE: FAIL')
        for item in failures:
            print(f'- {item}')
        print('EXECUTED_SEND_ALL: NO')
        return 20

    send_script, created, creation_note = ensure_send_script(date_str, args.dry_run)
    print('\nQUALITY_GATE: PASS')
    print(f'SEND_SCRIPT: {send_script} ({creation_note})')

    if args.dry_run:
        print('DRY_RUN: YES')
        print('EXECUTED_SEND_ALL: NO')
        return 0

    if detect_running(send_script):
        print(f'BLOCKED: send-all for {date_str} is already running')
        print('EXECUTED_SEND_ALL: NO')
        return 40

    if log_path.exists():
        print(f'BLOCKED: {log_path} already exists; refusing to risk duplicate distribution')
        print('EXECUTED_SEND_ALL: NO')
        return 41

    command = [sys.executable, '-u', str(send_script)]
    if send_script.name == 'send_all.py':
        command.extend(['--date', date_str, '--phase', 'afternoon'])
        if args.artifact_dir:
            command.extend(['--artifact-dir', str(artifact_dir)])

    with log_path.open('wb') as logf:
        proc = subprocess.run(command, stdout=logf, stderr=subprocess.STDOUT)

    success, total, success_lines, fail_lines = parse_send_log(log_path)
    tail = tail_lines(log_path, 10)

    print('EXECUTED_SEND_ALL: YES')
    print(f'SEND_LOG: {log_path}')
    if success is not None and total is not None:
        print(f'SUMMARY: success={success} total={total} failed={total - success}')
    else:
        print(f'SUMMARY: success_lines={success_lines} fail_lines={fail_lines} total=unknown')
    print('TAIL_LAST_10:')
    for line in tail:
        print(line)

    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
