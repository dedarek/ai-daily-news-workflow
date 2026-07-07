#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    'html': 10 * 1024,
    'podcast_script': 500,
    'podcast_script_text': 500,
    'podcast_moss_input': 500,
    'voice': 500,
    'audio': 1_000_000,
    'video': 100_000,
    'pipeline_report': 500,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the AI daily-news material workflow')
    parser.add_argument('--date', default=date.today().isoformat(), help='YYYY-MM-DD')
    parser.add_argument('--output-dir', default='dist')
    parser.add_argument(
        '--published-site-dir',
        help='Optional gh-pages checkout. If local dist is missing, restore same-day artifacts from it before generation.',
    )
    parser.add_argument('--check-only', action='store_true', help='Only validate manifest and declared artifacts')
    parser.add_argument('--force-regenerate', action='store_true', help='Ignore an existing ready manifest')
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
        'voice': output_dir / f'voice-{issue_date}.json',
        'audio': output_dir / f'daily-news-podcast-{issue_date}.mp3',
        'legacy_audio': output_dir / f'ai-daily-news-podcast-{issue_date}.mp3',
        'video': output_dir / f'daily-news-video-{issue_date}.mp4',
        'legacy_video': output_dir / f'ai-daily-news-video-{issue_date}.mp4',
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
    """Return recent candidate and selected news records used for seven-day deduplication."""
    state = load_recent_titles()
    days = state.get('days') if isinstance(state.get('days'), dict) else {}
    summary: dict[str, dict[str, list[dict[str, str]]]] = {}
    for day, payload in sorted(days.items(), reverse=True):
        if not isinstance(payload, dict):
            continue
        summary[day] = {
            'candidates': [
                {
                    'date': str(item.get('date') or day),
                    'title': str(item.get('title', '')),
                    'summary': str(item.get('summary', ''))[:260],
                    'url': str(item.get('url', '')),
                }
                for item in payload.get('candidates', [])
                if isinstance(item, dict)
            ],
            'selected': [
                {
                    'date': str(item.get('date') or day),
                    'title': str(item.get('title', '')),
                    'summary': str(item.get('summary', ''))[:260],
                    'url': str(item.get('url', '')),
                }
                for item in payload.get('selected', [])
                if isinstance(item, dict)
            ],
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
    copy_if_needed(paths['legacy_video'], paths['video'])

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
    copy_if_needed(paths['legacy_video'], tmp / paths['legacy_video'].name)
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
        (issue_root / 'voice.json', output_dir / f'voice-{issue_date}.json'),
        (issue_root / 'pipeline-report.json', output_dir / f'pipeline-report-{issue_date}.json'),
        (site_dir / 'html' / f'{issue_date}.html', output_dir / f'daily-news-{issue_date}.html'),
        (site_dir / 'audio' / f'{issue_date}.mp3', output_dir / f'daily-news-podcast-{issue_date}.mp3'),
        (site_dir / 'video' / f'{issue_date}.mp4', output_dir / f'daily-news-video-{issue_date}.mp4'),
    ]
    missing = [str(src) for src, _ in mappings if not src.exists()]
    if missing:
        print(json.dumps({'status': 'published_restore_incomplete', 'missing': missing}, ensure_ascii=False, indent=2))
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    for src, dst in mappings:
        copy_if_needed(src, dst)
    return True


def compact_title_items(path: Path, issue_date: str) -> list[dict[str, str]]:
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
        summary = str(item.get('summary') or item.get('body') or '').strip()
        if title:
            items.append({
                'date': issue_date,
                'title': title,
                'summary': summary[:500],
                'url': url,
            })
    return items


def restore_memory_from_site(site_dir: Path) -> bool:
    """生成前把 gh-pages 上累积的记忆恢复到本地 STATE_PATH，
    这样 run_live_pipeline 子进程选题时才能读到真实的最近若干天历史。"""
    src = site_dir / 'state' / 'recent-news.json'
    if not src.exists():
        return False
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, STATE_PATH)
    return True


def sync_memory_to_site(site_dir: Path) -> None:
    """生成并更新记忆后，把本地 STATE_PATH 写回 gh-pages checkout，
    让 workflow 的 publish 步骤（git add .）把更新后的记忆提交到 gh-pages 持久化。"""
    if not STATE_PATH.exists():
        return
    dst = site_dir / 'state' / 'recent-news.json'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATE_PATH, dst)


def update_recent_state(issue_date: str, paths: dict[str, Path]) -> dict[str, int]:
    state = load_recent_titles()
    window_days = int(state.get('window_days') or 7)
    days = state.setdefault('days', {})
    if not isinstance(days, dict):
        days = {}
        state['days'] = days
    days[issue_date] = {
        'candidates': compact_title_items(paths['candidate_articles'], issue_date),
        'selected': compact_title_items(paths['articles'], issue_date),
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
    if paths['voice'].exists():
        issues.extend(validate_voice_manifest(paths['voice']))
    return issues


def validate_voice_manifest(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        voice = read_json(path)
    except Exception as exc:
        return [f'voice manifest unreadable: {exc}']
    if not isinstance(voice, dict):
        return ['voice manifest is not an object']
    expected_keys = ['title', 'date', 'audio', 'duration', 'turns']
    expected_keys_with_video = ['title', 'date', 'audio', 'video', 'duration', 'turns']
    if list(voice.keys()) not in (expected_keys, expected_keys_with_video):
        issues.append(f'voice manifest keys must be exactly {expected_keys} or {expected_keys_with_video}')
    if not isinstance(voice.get('title'), str) or not voice.get('title'):
        issues.append('voice.title must be a non-empty string')
    if not isinstance(voice.get('date'), str):
        issues.append('voice.date must be a string')
    if not isinstance(voice.get('audio'), str) or not voice.get('audio'):
        issues.append('voice.audio must be a non-empty string')
    if 'video' in voice and (not isinstance(voice.get('video'), str) or not voice.get('video')):
        issues.append('voice.video must be a non-empty string when present')
    if not isinstance(voice.get('duration'), (int, float)) or voice.get('duration', 0) <= 0:
        issues.append('voice.duration must be positive')
    turns = voice.get('turns')
    if not isinstance(turns, list) or not turns:
        issues.append('voice.turns must be a non-empty array')
        return issues
    previous_end = 0.0
    for expected_index, item in enumerate(turns):
        if not isinstance(item, dict):
            issues.append(f'voice.turns[{expected_index}] must be an object')
            continue
        expected_turn_keys = ['index', 'roleLabel', 'text', 'start', 'end']
        if list(item.keys()) != expected_turn_keys:
            issues.append(f'voice.turns[{expected_index}] keys must be exactly {expected_turn_keys}')
        if item.get('index') != expected_index:
            issues.append(f'voice.turns[{expected_index}].index mismatch')
        if item.get('roleLabel') not in {'S1', 'S2'}:
            issues.append(f'voice.turns[{expected_index}].roleLabel must be S1 or S2')
        if not isinstance(item.get('text'), str) or not item.get('text').strip():
            issues.append(f'voice.turns[{expected_index}].text must be non-empty')
        start = item.get('start')
        end = item.get('end')
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            issues.append(f'voice.turns[{expected_index}] start/end invalid')
            continue
        if start < previous_end - 0.05:
            issues.append(f'voice.turns[{expected_index}].start overlaps previous turn')
        previous_end = end
    duration = voice.get('duration')
    if isinstance(duration, (int, float)) and previous_end > duration + 1.0:
        issues.append('voice.duration is shorter than last turn end')
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
    resolved_artifacts: dict[str, Path] = {}
    for key, min_size in MIN_SIZES.items():
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            return INVALID, {'status': 'invalid', 'reason': f'missing artifact key: {key}'}
        artifact = (REPO_ROOT / value).resolve()
        resolved_artifacts[key] = artifact
        if not artifact.exists():
            return INVALID, {'status': 'invalid', 'reason': f'artifact missing: {key} {artifact}'}
        if artifact.stat().st_size < min_size:
            return INVALID, {'status': 'invalid', 'reason': f'artifact too small: {key} {artifact.stat().st_size}'}
    voice_issues = validate_voice_manifest(resolved_artifacts['voice'])
    if voice_issues:
        return INVALID, {'status': 'invalid', 'reason': 'invalid voice manifest: ' + '; '.join(voice_issues)}
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
        if published_site_dir:
            restored = restore_memory_from_site(published_site_dir)
            print(json.dumps(
                {'memory_restore': 'ok' if restored else 'no_prior_memory'},
                ensure_ascii=False,
            ))
        run_pipeline(args.date, output_dir)
        paths = normalize_artifacts(output_dir, args.date)
        issues = validate_artifacts(paths)
        memory_update = update_recent_state(args.date, paths)
        if published_site_dir:
            sync_memory_to_site(published_site_dir)
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
