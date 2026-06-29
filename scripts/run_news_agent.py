#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / 'state' / 'recent-news.json'

READY = 0
MISSING = 10
INVALID = 20
FAILED = 30
STALE = 40
ERROR = 50

MIN_SIZES = {
    'candidate_articles': 500,
    'articles': 500,
    'html': 15 * 1024,
    'podcast_script': 500,
    'podcast_script_text': 500,
    'podcast_moss_input': 500,
    'audio': 1_000_000,
    'pipeline_report': 500,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the DeepAgent-backed AI daily-news material workflow')
    parser.add_argument('--date', default=date.today().isoformat(), help='YYYY-MM-DD')
    parser.add_argument('--output-dir', default='dist')
    parser.add_argument(
        '--published-site-dir',
        help='Optional gh-pages checkout. If local dist is missing, restore same-day artifacts from it before generation.',
    )
    parser.add_argument('--check-only', action='store_true', help='Only validate manifest and declared artifacts')
    parser.add_argument('--force-regenerate', action='store_true', help='Ignore an existing ready manifest')
    parser.add_argument(
        '--skip-agent-preflight',
        action='store_true',
        help='Debug escape hatch: run deterministic pipeline without invoking DeepAgent',
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def manifest_path(output_dir: Path, issue_date: str) -> Path:
    return output_dir / f'manifest-{issue_date}.json'


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def artifact_paths(output_dir: Path, issue_date: str) -> dict[str, Path]:
    return {
        'candidate_articles': output_dir / f'candidate-news-{issue_date}.json',
        'articles': output_dir / f'articles-{issue_date}.json',
        'legacy_articles': output_dir / f'news-data-{issue_date}.json',
        'html': output_dir / f'daily-news-{issue_date}.html',
        'legacy_html': output_dir / f'ai-daily-news-html-{issue_date}.html',
        'podcast_script': output_dir / f'podcast-script-{issue_date}.json',
        'podcast_script_text': output_dir / f'podcast-script-{issue_date}.txt',
        'podcast_moss_input': output_dir / f'podcast-moss-input-{issue_date}.txt',
        'audio': output_dir / f'daily-news-podcast-{issue_date}.mp3',
        'legacy_audio': output_dir / f'ai-daily-news-podcast-{issue_date}.mp3',
        'pipeline_report': output_dir / f'pipeline-report-{issue_date}.json',
    }


def public_artifacts(paths: dict[str, Path]) -> dict[str, str]:
    return {key: rel(path) for key, path in paths.items()}


def load_recent_titles() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {'window_days': 7, 'days': {}}
    try:
        state = read_json(STATE_PATH)
    except json.JSONDecodeError:
        return {'window_days': 7, 'days': {}}
    if not isinstance(state, dict):
        return {'window_days': 7, 'days': {}}
    state.setdefault('window_days', 7)
    state.setdefault('days', {})
    return state


def summarize_recent_titles() -> str:
    """Return recent candidate and selected news titles used for seven-day deduplication."""
    state = load_recent_titles()
    days = state.get('days') if isinstance(state.get('days'), dict) else {}
    summary: dict[str, dict[str, list[str]]] = {}
    for day, payload in sorted(days.items(), reverse=True):
        if not isinstance(payload, dict):
            continue
        summary[day] = {
            'candidates': [str(item.get('title', '')) for item in payload.get('candidates', []) if isinstance(item, dict)],
            'selected': [str(item.get('title', '')) for item in payload.get('selected', []) if isinstance(item, dict)],
        }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def inspect_workspace(issue_date: str, output_dir_name: str) -> str:
    """Inspect same-day manifest and artifact presence for the AI daily-news workspace."""
    output_dir = (REPO_ROOT / output_dir_name).resolve()
    paths = artifact_paths(output_dir, issue_date)
    payload = {
        'date': issue_date,
        'output_dir': rel(output_dir) if output_dir.exists() else output_dir_name,
        'manifest': rel(manifest_path(output_dir, issue_date)),
        'artifacts': {
            key: {
                'path': rel(path) if path.exists() else path.as_posix(),
                'exists': path.exists(),
                'bytes': path.stat().st_size if path.exists() else 0,
            }
            for key, path in paths.items()
        },
        'recent_titles': json.loads(summarize_recent_titles()),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def create_news_agent():
    try:
        from deepagents import create_deep_agent
        try:
            from deepagents.backends import FilesystemBackend
        except ImportError:
            from deepagents import FilesystemBackend  # type: ignore
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            'DeepAgent dependencies are missing. Install with: python -m pip install -r requirements.txt'
        ) from exc

    api_key = os.environ.get('OPENCODE_GO_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('OPENCODE_GO_API_KEY is required for DeepAgent preflight')

    endpoint = os.environ.get('OPENCODE_GO_BASE_URL', 'https://opencode.ai/zen/go/v1').rstrip('/')
    models = [
        item.strip()
        for item in os.environ.get('OPENCODE_GO_MODELS', 'deepseek-v4-flash,deepseek-v4-pro,mimo-v2.5').split(',')
        if item.strip()
    ]
    model_name = os.environ.get('AI_DAILY_AGENT_MODEL') or (models[0] if models else 'deepseek-v4-flash')
    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=endpoint,
        temperature=0,
    )
    backend = FilesystemBackend(root_dir=str(REPO_ROOT.resolve()), virtual_mode=False)
    return create_deep_agent(
        model=model,
        tools=[summarize_recent_titles, inspect_workspace],
        backend=backend,
        skills=['.'],
        system_prompt=(
            'You are the AI Daily News production agent. Use the project skills and tools to prepare a concise '
            'run plan. Do not send email, upload files, mutate recipient configuration, or write delivery markers.'
        ),
    )


def run_agent_preflight(issue_date: str, output_dir: Path) -> dict[str, Any]:
    agent = create_news_agent()
    prompt = f'''
Run preflight for the AI Daily News materials job.

Required actions:
1. Use summarize_recent_titles.
2. Use inspect_workspace with issue_date="{issue_date}" and output_dir_name="{output_dir.relative_to(REPO_ROOT).as_posix()}".
3. Read the ai-daily-news and moss-ttsd skills if relevant.
4. Return a short JSON object with keys: pass, risks, required_next_step.

Important boundaries:
- You do not send email.
- You do not upload files.
- You do not change recipients or SMTP config.
- The deterministic supervisor will run generation and validation after your preflight.
'''.strip()
    result = agent.invoke(
        {'messages': [{'role': 'user', 'content': prompt}]},
        config={'configurable': {'thread_id': f'ai-daily-news-{issue_date}'}},
    )
    messages = result.get('messages', []) if isinstance(result, dict) else []
    content = ''
    if messages:
        last = messages[-1]
        content = getattr(last, 'content', '') or (last.get('content', '') if isinstance(last, dict) else '')
    return {
        'provider': 'deepagents',
        'model': os.environ.get('AI_DAILY_AGENT_MODEL')
        or os.environ.get('OPENCODE_GO_MODELS', 'deepseek-v4-flash').split(',')[0].strip(),
        'preflight': str(content).strip(),
    }


def run_pipeline(issue_date: str, output_dir: Path) -> None:
    command = [
        sys.executable,
        str(REPO_ROOT / 'scripts' / 'run_live_pipeline.py'),
        '--date',
        issue_date,
        '--output-dir',
        rel(output_dir),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def copy_if_needed(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.resolve() == dst.resolve():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def normalize_artifacts(output_dir: Path, issue_date: str) -> dict[str, Path]:
    paths = artifact_paths(output_dir, issue_date)
    copy_if_needed(paths['legacy_articles'], paths['articles'])
    copy_if_needed(paths['legacy_html'], paths['html'])
    copy_if_needed(paths['legacy_audio'], paths['audio'])

    podcast_json = paths['podcast_script']
    podcast_txt = paths['podcast_script_text']
    if podcast_json.exists() and not podcast_txt.exists():
        podcast = read_json(podcast_json)
        dialogue = podcast.get('dialogue') if isinstance(podcast, dict) else []
        lines = [
            f'[{item["speaker"]}] {item["text"]}'
            for item in dialogue
            if isinstance(item, dict) and item.get('speaker') and item.get('text')
        ]
        podcast_txt.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    tmp = Path('/tmp')
    copy_if_needed(paths['legacy_html'], tmp / paths['legacy_html'].name)
    copy_if_needed(paths['legacy_audio'], tmp / paths['legacy_audio'].name)
    return paths


def restore_from_published_site(site_dir: Path, output_dir: Path, issue_date: str) -> bool:
    issue_root = site_dir / 'api' / 'issues' / issue_date
    manifest = issue_root / 'manifest.json'
    if not manifest.exists():
        return False

    mappings = [
        (manifest, output_dir / f'manifest-{issue_date}.json'),
        (issue_root / 'candidate-news.json', output_dir / f'candidate-news-{issue_date}.json'),
        (issue_root / 'articles.json', output_dir / f'articles-{issue_date}.json'),
        (issue_root / 'podcast-script.json', output_dir / f'podcast-script-{issue_date}.json'),
        (issue_root / 'podcast-script.txt', output_dir / f'podcast-script-{issue_date}.txt'),
        (issue_root / 'podcast-moss-input.txt', output_dir / f'podcast-moss-input-{issue_date}.txt'),
        (issue_root / 'pipeline-report.json', output_dir / f'pipeline-report-{issue_date}.json'),
        (site_dir / 'html' / f'{issue_date}.html', output_dir / f'daily-news-{issue_date}.html'),
        (site_dir / 'audio' / f'{issue_date}.mp3', output_dir / f'daily-news-podcast-{issue_date}.mp3'),
    ]
    missing = [str(src) for src, _ in mappings if not src.exists()]
    if missing:
        print(json.dumps({'status': 'published_restore_incomplete', 'missing': missing}, ensure_ascii=False, indent=2))
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    for src, dst in mappings:
        copy_if_needed(src, dst)
    return True


def compact_title_items(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    raw = read_json(path)
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title', '')).strip()
        url = str(item.get('url', '')).strip()
        if title:
            items.append({'title': title, 'url': url})
    return items


def update_recent_state(issue_date: str, paths: dict[str, Path]) -> dict[str, int]:
    state = load_recent_titles()
    window_days = int(state.get('window_days') or 7)
    days = state.setdefault('days', {})
    if not isinstance(days, dict):
        days = {}
        state['days'] = days
    days[issue_date] = {
        'candidates': compact_title_items(paths['candidate_articles']),
        'selected': compact_title_items(paths['articles']),
    }

    cutoff = datetime.strptime(issue_date, '%Y-%m-%d').date() - timedelta(days=window_days - 1)
    for day in list(days):
        try:
            parsed = datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError:
            del days[day]
            continue
        if parsed < cutoff:
            del days[day]
    write_json(STATE_PATH, state)
    return {
        'candidate_count': len(days[issue_date]['candidates']),
        'selected_count': len(days[issue_date]['selected']),
    }


def validate_artifacts(paths: dict[str, Path]) -> list[str]:
    issues: list[str] = []
    for key, min_size in MIN_SIZES.items():
        path = paths[key]
        if not path.exists():
            issues.append(f'missing {key}: {path}')
            continue
        size = path.stat().st_size
        if size < min_size:
            issues.append(f'{key} too small: {size} < {min_size}')
    if paths['audio'].exists() and paths['audio'].stat().st_size > 8 * 1024 * 1024:
        issues.append(f'audio too large: {paths["audio"].stat().st_size} > 8388608')
    return issues


def write_manifest(
    output_dir: Path,
    issue_date: str,
    status: str,
    paths: dict[str, Path],
    agent_metadata: dict[str, Any] | None,
    memory_update: dict[str, int] | None,
    issues: list[str] | None = None,
    error: str | None = None,
) -> Path:
    report = read_json(paths['pipeline_report']) if paths['pipeline_report'].exists() else {}
    manifest = {
        'schema_version': 1,
        'date': issue_date,
        'status': status,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'artifacts': public_artifacts(paths),
        'quality': {
            'deterministic': 'pass' if not issues and status == 'ready' else 'fail',
            'agent_review': 'pass' if agent_metadata else 'not_run',
            'issues': issues or [],
        },
        'repair': {
            'attempts': 0,
            'items': [],
        },
        'memory_update': memory_update or {'candidate_count': 0, 'selected_count': 0},
        'agent': agent_metadata,
        'pipeline_report': report,
    }
    if error:
        manifest['error'] = error
    path = manifest_path(output_dir, issue_date)
    write_json(path, manifest)
    return path


def validate_manifest(output_dir: Path, issue_date: str) -> tuple[int, dict[str, Any]]:
    path = manifest_path(output_dir, issue_date)
    if not path.exists():
        return MISSING, {'status': 'missing', 'reason': f'missing manifest: {path}'}
    try:
        manifest = read_json(path)
    except Exception as exc:
        return INVALID, {'status': 'invalid', 'reason': f'cannot read manifest: {exc}'}
    if not isinstance(manifest, dict):
        return INVALID, {'status': 'invalid', 'reason': 'manifest is not an object'}
    if manifest.get('date') != issue_date:
        return STALE, {'status': 'stale', 'reason': f'manifest date={manifest.get("date")} expected={issue_date}'}
    if manifest.get('status') in {'failed', 'needs_human_review', 'partial'}:
        return FAILED, {'status': manifest.get('status'), 'reason': manifest.get('error') or 'manifest is not ready'}
    if manifest.get('status') != 'ready':
        return INVALID, {'status': 'invalid', 'reason': f'unknown manifest status: {manifest.get("status")}'}
    quality = manifest.get('quality')
    if not isinstance(quality, dict):
        return INVALID, {'status': 'invalid', 'reason': 'missing quality object'}
    if quality.get('deterministic') != 'pass':
        return FAILED, {'status': 'failed', 'reason': 'deterministic quality is not pass'}
    if quality.get('agent_review') not in {'pass', 'not_run'}:
        return FAILED, {'status': 'failed', 'reason': 'agent review is not pass'}
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, dict):
        return INVALID, {'status': 'invalid', 'reason': 'missing artifacts object'}
    for key, min_size in MIN_SIZES.items():
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            return INVALID, {'status': 'invalid', 'reason': f'missing artifact key: {key}'}
        artifact = (REPO_ROOT / value).resolve()
        if not artifact.exists():
            return INVALID, {'status': 'invalid', 'reason': f'artifact missing: {key} {artifact}'}
        if artifact.stat().st_size < min_size:
            return INVALID, {'status': 'invalid', 'reason': f'artifact too small: {key} {artifact.stat().st_size}'}
    return READY, {'status': 'ready', 'manifest': rel(path)}


def main() -> int:
    args = parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    published_site_dir = (REPO_ROOT / args.published_site_dir).resolve() if args.published_site_dir else None

    if published_site_dir and not args.force_regenerate:
        local_code, _ = validate_manifest(output_dir, args.date)
        if local_code != READY and restore_from_published_site(published_site_dir, output_dir, args.date):
            restored_code, restored = validate_manifest(output_dir, args.date)
            if restored_code == READY:
                print(json.dumps({'status': 'restored_from_published_site', **restored}, ensure_ascii=False, indent=2))
                if args.check_only:
                    return READY

    if args.check_only:
        code, result = validate_manifest(output_dir, args.date)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code

    if not args.force_regenerate:
        code, result = validate_manifest(output_dir, args.date)
        if code == READY:
            print(json.dumps({'status': 'already_ready', **result}, ensure_ascii=False, indent=2))
            return READY

    paths = artifact_paths(output_dir, args.date)
    agent_metadata: dict[str, Any] | None = None
    try:
        if not args.skip_agent_preflight:
            agent_metadata = run_agent_preflight(args.date, output_dir)
        run_pipeline(args.date, output_dir)
        paths = normalize_artifacts(output_dir, args.date)
        issues = validate_artifacts(paths)
        memory_update = update_recent_state(args.date, paths)
        status = 'ready' if not issues else 'failed'
        manifest = write_manifest(
            output_dir=output_dir,
            issue_date=args.date,
            status=status,
            paths=paths,
            agent_metadata=agent_metadata,
            memory_update=memory_update,
            issues=issues,
        )
        result = {'status': status, 'manifest': rel(manifest), 'issues': issues}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return READY if status == 'ready' else FAILED
    except Exception as exc:
        paths = normalize_artifacts(output_dir, args.date)
        manifest = write_manifest(
            output_dir=output_dir,
            issue_date=args.date,
            status='failed',
            paths=paths,
            agent_metadata=agent_metadata,
            memory_update=None,
            issues=[str(exc)],
            error=traceback.format_exc(),
        )
        print(json.dumps({'status': 'failed', 'manifest': rel(manifest), 'error': str(exc)}, ensure_ascii=False, indent=2))
        return ERROR


if __name__ == '__main__':
    raise SystemExit(main())
