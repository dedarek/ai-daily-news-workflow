#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback is not used in CI.
    ZoneInfo = None  # type: ignore[assignment]


DEFAULT_REPO = 'dedarek/ai-daily-news-workflow'
DEFAULT_REF = 'main'
DEFAULT_BASE_URL = 'https://dedarek.github.io/ai-daily-news-workflow'
WORKFLOWS = {
    'morning': 'daily-news-test.yml',
    'afternoon': 'daily-news-afternoon-review.yml',
}


def shanghai_today() -> str:
    tz = ZoneInfo('Asia/Shanghai') if ZoneInfo else timezone(timedelta(hours=8))
    return datetime.now(tz).date().isoformat()


def get_json_url(url: str, *, timeout: float = 30) -> tuple[int, object | None, str]:
    request = Request(url, headers={'User-Agent': 'ai-daily-news-local-dispatch/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return response.status, json.loads(body), body
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return exc.code, None, body
    except Exception as exc:
        return 0, None, str(exc)


def manifest_ready(base_url: str, date_str: str) -> tuple[bool, str]:
    url = f'{base_url.rstrip("/")}/api/issues/{date_str}/manifest.json'
    status, payload, body = get_json_url(url)
    if status != 200:
        return False, f'manifest HTTP {status}: {body[:200]}'
    if not isinstance(payload, dict):
        return False, 'manifest is not a JSON object'
    if payload.get('status') != 'ready':
        return False, f"manifest status is {payload.get('status')!r}"
    published = payload.get('published_artifacts')
    if not isinstance(published, dict) or not published.get('html') or not published.get('audio'):
        return False, 'manifest missing html/audio artifacts'
    return True, 'ready'


def delivery_marker_exists(base_url: str, date_str: str, phase: str) -> tuple[bool, str]:
    url = f'{base_url.rstrip("/")}/state/deliveries/{date_str}/{phase}.json'
    status, payload, body = get_json_url(url)
    if status == 200 and isinstance(payload, dict):
        return True, 'delivery marker exists'
    if status == 404:
        return False, 'delivery marker missing'
    return False, f'delivery marker HTTP {status}: {body[:200]}'


def github_request(
    repo: str,
    path: str,
    token: str,
    *,
    method: str = 'GET',
    payload: dict | None = None,
    timeout: float = 30,
) -> tuple[int, object | None, str]:
    data = None
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'User-Agent': 'ai-daily-news-local-dispatch/1.0',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(
        f'https://api.github.com/repos/{repo}/{path.lstrip("/")}',
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            parsed = json.loads(body) if body else None
            return response.status, parsed, body
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, body


def workflow_has_active_run(repo: str, workflow: str, ref: str, token: str) -> tuple[bool, str]:
    status, payload, body = github_request(
        repo,
        f'actions/workflows/{workflow}/runs?branch={ref}&per_page=10',
        token,
    )
    if status != 200 or not isinstance(payload, dict):
        return False, f'cannot inspect active runs: HTTP {status}: {body[:200]}'
    runs = payload.get('workflow_runs')
    if not isinstance(runs, list):
        return False, 'workflow_runs missing'
    active = [
        run for run in runs
        if isinstance(run, dict)
        and run.get('event') == 'workflow_dispatch'
        and run.get('status') in {'queued', 'in_progress', 'waiting', 'requested', 'pending'}
    ]
    if active:
        run = active[0]
        return True, f"active run exists: {run.get('html_url') or run.get('id')}"
    return False, 'no active workflow_dispatch run'


def dispatch_workflow(repo: str, workflow: str, ref: str, token: str, inputs: dict[str, object]) -> tuple[bool, str]:
    status, _payload, body = github_request(
        repo,
        f'actions/workflows/{workflow}/dispatches',
        token,
        method='POST',
        payload={'ref': ref, 'inputs': inputs},
    )
    if status == 204:
        return True, 'dispatch accepted'
    return False, f'dispatch failed: HTTP {status}: {body[:500]}'


def build_inputs(phase: str) -> dict[str, object]:
    if phase == 'morning':
        # Existing workflow_dispatch semantics intentionally force regeneration.
        # This script only dispatches morning when the public manifest is missing/not ready.
        return {'send_email': True, 'force_regenerate': True}
    if phase == 'afternoon':
        return {'send_email': True, 'send_files': True}
    raise ValueError(f'unsupported phase: {phase}')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Locally dispatch AI Daily News GitHub workflows only when public artifacts are missing.',
    )
    parser.add_argument('phase', choices=('morning', 'afternoon'))
    parser.add_argument('--date', default=shanghai_today(), help='YYYY-MM-DD, defaults to today in Asia/Shanghai')
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', DEFAULT_REPO))
    parser.add_argument('--ref', default=os.environ.get('AI_DAILY_GITHUB_REF', DEFAULT_REF))
    parser.add_argument('--base-url', default=os.environ.get('AI_DAILY_CONTENT_BASE_URL', DEFAULT_BASE_URL))
    parser.add_argument('--token', default=os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or '')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--allow-duplicate-run', action='store_true')
    args = parser.parse_args()

    workflow = WORKFLOWS[args.phase]
    ready, manifest_reason = manifest_ready(args.base_url, args.date)
    print(json.dumps({
        'phase': args.phase,
        'date': args.date,
        'workflow': workflow,
        'manifest_ready': ready,
        'manifest_reason': manifest_reason,
    }, ensure_ascii=False))

    if args.phase == 'morning' and ready:
        print('SKIP: morning issue already published and ready')
        return 0

    if args.phase == 'afternoon':
        marker_exists, marker_reason = delivery_marker_exists(args.base_url, args.date, 'afternoon')
        print(json.dumps({'afternoon_marker_exists': marker_exists, 'marker_reason': marker_reason}, ensure_ascii=False))
        if marker_exists:
            print('SKIP: afternoon already delivered')
            return 0
        if not ready:
            print('SKIP: morning issue is not ready; do not dispatch afternoon')
            return 0

    inputs = build_inputs(args.phase)
    print(json.dumps({'dispatch_inputs': inputs, 'repo': args.repo, 'ref': args.ref}, ensure_ascii=False))

    if args.dry_run:
        print('DRY_RUN: dispatch skipped')
        return 0
    if not args.token:
        print('ERROR: set GITHUB_TOKEN or GH_TOKEN with Actions write permission', file=sys.stderr)
        return 2
    if not args.allow_duplicate_run:
        active, reason = workflow_has_active_run(args.repo, workflow, args.ref, args.token)
        print(json.dumps({'active_run': active, 'active_run_reason': reason}, ensure_ascii=False))
        if active:
            print('SKIP: workflow already active')
            return 0

    ok, reason = dispatch_workflow(args.repo, workflow, args.ref, args.token, inputs)
    print(reason)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
