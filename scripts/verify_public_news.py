"""Fail closed before any GitHub Pages push if changed assets include delivery data."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', re.I)
UNSAFE_JSON = {'recipient', 'recipients', 'endpoint', 'base_url', 'llm', 'call_details',
               'source_health', 'video_api', 'tts_reference_files', 'api_key', 'password'}


def recipients(text):
    data = json.loads(text)
    if not isinstance(data, dict) or not all(data.get(x) for x in ('admins', 'all')):
        raise ValueError('Private roster missing required audiences')
    if any(not isinstance(group, list) or any(not isinstance(x, str) or not EMAIL.fullmatch(x.strip())
                                               for x in group) for group in data.values()):
        raise ValueError('Invalid private roster')
    return {x.strip().lower() for group in data.values() for x in group}


def safe_text(value, private_addresses, forbidden_text):
    for a in EMAIL.findall(value):
        if a.lower() in private_addresses:
            raise ValueError('Public asset contains a private delivery address')
    if any(x.casefold() in value.casefold() for x in forbidden_text):
        raise ValueError('Public asset contains a private endpoint')


def walk(value):
    if isinstance(value, dict):
        if value.keys() & UNSAFE_JSON:
            raise ValueError('Public metadata contains an operational field')
        for v in value.values():
            walk(v)
    elif isinstance(value, list):
        for v in value:
            walk(v)


def main():
    site = Path(sys.argv[1]).resolve()
    private_addresses = recipients(os.environ['AI_DAILY_RECIPIENTS_JSON'])
    sender = os.getenv('AI_DAILY_SMTP_USER', '').strip().lower()
    if sender:
        private_addresses.add(sender)
    forbidden = [os.getenv(key, '').strip().rstrip('/') for key in (
        'LENOVO_LLM_BASE_URL', 'AI_DAILY_VIDEO_API_BASE_URL', 'AI_DAILY_PRE_SEND_API_URL')]
    changed = subprocess.check_output(['git', '-C', str(site), 'diff', '--cached', '--name-only',
                                       '--diff-filter=ACMR', '-z']).decode().strip('\x00').split('\x00')
    for name in filter(None, changed):
        if name.startswith(('state/delivery-progress/', 'state/deliveries/', 'reviews/')):
            raise ValueError('Private file in public publish set')
        target = site / name
        if target.suffix not in {'.json', '.txt', '.html'}:
            continue
        value = target.read_text(encoding='utf-8')
        safe_text(value, private_addresses, [x for x in forbidden if x])
        if target.name in {'feed.json', 'latest.json', 'manifest.json', 'pipeline-report.json', 'index.json'}:
            walk(json.loads(value))
    print('Public publish metadata passed privacy check')


if __name__ == '__main__':
    main()
