#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
FIXTURE_DATE = '2026-06-24'
FIXTURE_HTML = SKILL_DIR / 'samples' / f'{FIXTURE_DATE}.html'
VOICE_SAMPLE = REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_anna_s2.mp3'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build deterministic end-to-end artifacts for CI')
    parser.add_argument('--date', default=date.today().isoformat(), help='Issue date in YYYY-MM-DD format')
    parser.add_argument('--output-dir', default='dist', help='Artifact output directory')
    return parser.parse_args()


def render_html(issue_date: str, output_path: Path) -> None:
    html = FIXTURE_HTML.read_text(encoding='utf-8')
    display_date = datetime.strptime(issue_date, '%Y-%m-%d')
    chinese_date = f'{display_date.year}年{display_date.month}月{display_date.day}日'
    weekdays = '一二三四五六日'
    weekday = f'星期{weekdays[display_date.weekday()]}'

    html = html.replace(f'每日AI热点新闻 — {FIXTURE_DATE}', f'每日AI热点新闻 — {issue_date}')
    html = html.replace('2026年6月24日 星期三', f'{chinese_date} {weekday}', 1)
    html = html.replace(f'试运营阶段 · {FIXTURE_DATE}', f'GitHub Actions 测试运行 · {issue_date}')
    html = html.replace(
        '<tr><td style="padding:22px 36px 18px;">',
        '<tr><td style="padding:12px 36px;background:#eff6ff;color:#1d4ed8;'
        'font-size:13px;">GitHub Actions 端到端测试：内容使用已验证夹具，'
        '采集模块将在下一阶段接入实时数据。</td></tr>'
        '<tr><td style="padding:22px 36px 18px;">',
        1,
    )
    output_path.write_text(html, encoding='utf-8')


def generate_test_podcast(output_path: Path) -> None:
    command = [
        'ffmpeg',
        '-y',
        '-stream_loop',
        '40',
        '-i',
        str(VOICE_SAMPLE),
        '-t',
        '180',
        '-codec:a',
        'libmp3lame',
        '-b:a',
        '64k',
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            'ffprobe',
            '-v',
            'error',
            '-show_entries',
            'format=duration',
            '-of',
            'default=noprint_wrappers=1:nokey=1',
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    args = parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / f'ai-daily-news-html-{args.date}.html'
    podcast_path = output_dir / f'ai-daily-news-podcast-{args.date}.mp3'
    render_html(args.date, html_path)
    generate_test_podcast(podcast_path)

    tmp_html = Path('/tmp') / html_path.name
    tmp_podcast = Path('/tmp') / podcast_path.name
    shutil.copy2(html_path, tmp_html)
    shutil.copy2(podcast_path, tmp_podcast)
    shutil.copy2(html_path, SKILL_DIR / 'samples' / html_path.name.replace('ai-daily-news-html-', ''))

    report = {
        'mode': 'github-actions-fixture-test',
        'date': args.date,
        'recipient': 'yyc54321@126.com',
        'html': {'path': str(html_path), 'bytes': html_path.stat().st_size},
        'podcast': {
            'path': str(podcast_path),
            'bytes': podcast_path.stat().st_size,
            'duration_seconds': round(media_duration(podcast_path), 2),
        },
    }
    report_path = output_dir / f'pipeline-report-{args.date}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
