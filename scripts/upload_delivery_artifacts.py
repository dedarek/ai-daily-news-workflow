#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / 'skill' / 'references' / 'send-file-config.json'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Upload pre-send AI daily-news artifacts to a backend API')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--artifact-dir', help='Override directory containing files to upload')
    parser.add_argument(
        '--endpoint',
        default=os.environ.get('AI_DAILY_PRE_SEND_API_URL', ''),
        help='Override upload endpoint. Defaults to AI_DAILY_PRE_SEND_API_URL or send-file-config.json.',
    )
    parser.add_argument('--dry-run', action='store_true', help='Print the upload plan without sending')
    return parser.parse_args()


def read_config() -> dict:
    try:
        configured = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'Missing send file config: {CONFIG_FILE}') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid send file config JSON in {CONFIG_FILE}: {exc}') from exc
    if not isinstance(configured, dict):
        raise RuntimeError(f'Send file config must be a JSON object: {CONFIG_FILE}')
    return configured


def collect_files(artifact_dir: Path, date_str: str, fields_by_suffix: dict[str, str]) -> list[tuple[str, Path]]:
    if not artifact_dir.exists():
        raise FileNotFoundError(f'Missing artifact directory: {artifact_dir}')

    candidates = sorted(path for path in artifact_dir.iterdir() if path.is_file() and date_str in path.name)
    files: list[tuple[str, Path]] = []
    for path in candidates:
        field = fields_by_suffix.get(path.suffix.lower())
        if field:
            files.append((field, path))
    if not files:
        raise RuntimeError(f'No uploadable artifacts for {date_str} in {artifact_dir}')
    return files


def build_multipart(files: list[tuple[str, Path]]) -> tuple[str, bytes]:
    boundary = f'----ai-daily-news-{uuid.uuid4().hex}'
    chunks: list[bytes] = []
    for field, path in files:
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        chunks.append(f'--{boundary}\r\n'.encode('ascii'))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
                f'Content-Type: {content_type}\r\n\r\n'
            ).encode('utf-8')
        )
        chunks.append(path.read_bytes())
        chunks.append(b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode('ascii'))
    return boundary, b''.join(chunks)


def resolve_headers(config: dict) -> dict[str, str]:
    auth = config.get('auth')
    if not isinstance(auth, dict) or auth.get('enabled') is False:
        return {}

    header = str(auth.get('header') or 'Authorization').strip()
    scheme = str(auth.get('scheme') or '').strip()
    token = os.environ.get('AI_DAILY_PRE_SEND_API_TOKEN') or str(auth.get('token') or '').strip()
    if not header:
        raise RuntimeError('send-file config auth.header must not be blank')
    if not token:
        raise RuntimeError('send-file config auth token is blank. Set auth.token or AI_DAILY_PRE_SEND_API_TOKEN.')
    return {header: f'{scheme} {token}'.strip() if scheme else token}


def upload(
    endpoint: str,
    files: list[tuple[str, Path]],
    timeout_seconds: float,
    extra_headers: dict[str, str],
) -> tuple[int, str]:
    boundary, body = build_multipart(files)
    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body)),
        'User-Agent': 'ai-daily-news-workflow/1.0',
    }
    headers.update(extra_headers)
    request = Request(
        endpoint,
        data=body,
        headers=headers,
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode('utf-8', errors='replace')
            return response.status, response_body
    except HTTPError as exc:
        response_body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Upload failed: HTTP {exc.code}: {response_body[:1000]}') from exc


def main() -> int:
    args = parse_args()
    config = read_config()
    if config.get('enabled') is False:
        print('send-file config disabled; upload skipped', flush=True)
        return 0

    endpoint = (args.endpoint or config.get('endpoint') or '').strip()
    if not endpoint:
        raise RuntimeError('Missing upload endpoint. Set AI_DAILY_PRE_SEND_API_URL or send-file-config.json endpoint.')
    if not endpoint.startswith(('http://', 'https://')):
        raise RuntimeError(f'Invalid upload endpoint: {endpoint}')

    fields_by_suffix = config.get('fields_by_suffix')
    if not isinstance(fields_by_suffix, dict) or not fields_by_suffix:
        raise RuntimeError(f'send-file config requires non-empty fields_by_suffix: {CONFIG_FILE}')
    normalized_fields = {
        str(suffix).lower(): str(field)
        for suffix, field in fields_by_suffix.items()
        if str(suffix).startswith('.') and str(field).strip()
    }
    if not normalized_fields:
        raise RuntimeError(f'send-file config fields_by_suffix has no valid mappings: {CONFIG_FILE}')

    artifact_dir = Path(args.artifact_dir or config.get('artifact_dir') or 'review-dist').resolve()
    timeout_seconds = float(config.get('timeout_seconds', 120))
    extra_headers = resolve_headers(config)
    files = collect_files(artifact_dir, args.date, normalized_fields)
    plan = [
        {'field': field, 'file': str(path), 'bytes': path.stat().st_size}
        for field, path in files
    ]
    print(
        json.dumps(
            {'endpoint': endpoint, 'auth_headers': sorted(extra_headers), 'files': plan},
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    if args.dry_run:
        print('DRY_RUN: upload skipped', flush=True)
        return 0

    status, response_body = upload(endpoint, files, timeout_seconds, extra_headers)
    if not 200 <= status < 300:
        raise RuntimeError(f'Upload failed: HTTP {status}: {response_body[:1000]}')
    print(json.dumps({'status': status, 'response': response_body[:2000]}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
