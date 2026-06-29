#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def absolute(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def render_index(latest: dict, issues: list[dict]) -> str:
    rows = ''.join(
        f'<li><a href="{item["html_url"]}">{item["issue_date"]}</a>'
        f' · {item["article_count"]} 条 · <a href="{item["audio_url"]}">播客</a></li>'
        for item in issues[:30]
    )
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AI Daily News Content API</title>
  <style>
    body{{max-width:820px;margin:40px auto;padding:0 20px;font:16px/1.7 system-ui;color:#1f2937}}
    code{{background:#f3f4f6;padding:2px 6px;border-radius:4px}} a{{color:#2563eb}}
  </style>
</head>
<body>
  <h1>AI Daily News Content API</h1>
  <p>最新一期：<a href="{latest["html_url"]}">{latest["issue_date"]}</a></p>
  <h2>API</h2>
  <ul>
    <li><a href="api/latest.json"><code>/api/latest.json</code></a></li>
    <li><a href="feed.json"><code>/feed.json</code></a></li>
    <li><code>/api/issues/YYYY-MM-DD/index.json</code></li>
    <li><code>/api/issues/YYYY-MM-DD/articles.json</code></li>
    <li><code>/api/issues/YYYY-MM-DD/podcast-script.json</code></li>
  </ul>
  <h2>最近期次</h2>
  <ul>{rows}</ul>
</body>
</html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description='Update the static AI Daily News content service')
    parser.add_argument('--date', required=True)
    parser.add_argument('--dist-dir', default='dist')
    parser.add_argument('--site-dir', required=True)
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')

    dist = (REPO_ROOT / args.dist_dir).resolve()
    site = Path(args.site_dir).resolve()
    site.mkdir(parents=True, exist_ok=True)
    report_path = dist / f'pipeline-report-{args.date}.json'
    articles_path = dist / f'news-data-{args.date}.json'
    script_path = dist / f'podcast-script-{args.date}.json'
    html_path = dist / f'ai-daily-news-html-{args.date}.html'
    audio_path = dist / f'ai-daily-news-podcast-{args.date}.mp3'
    required = [report_path, articles_path, script_path, html_path, audio_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f'Missing content artifacts: {missing}')

    report = read_json(report_path)
    articles = read_json(articles_path)
    podcast_script = read_json(script_path)
    issue_root = site / 'api' / 'issues' / args.date
    write_json(issue_root / 'articles.json', articles)
    write_json(issue_root / 'podcast-script.json', podcast_script)

    published_html = site / 'html' / f'{args.date}.html'
    published_audio = site / 'audio' / f'{args.date}.mp3'
    published_html.parent.mkdir(parents=True, exist_ok=True)
    published_audio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, published_html)
    shutil.copy2(audio_path, published_audio)

    issue = {
        'schema_version': 1,
        'issue_date': args.date,
        'content_date': report['content_date'],
        'published_at': datetime.now(timezone.utc).isoformat(),
        'article_count': len(articles),
        'podcast_turns': len(podcast_script['dialogue']),
        'tts_mode': report['tts_mode'],
        'tts_model': report.get('tts_model'),
        'tts_reference_files': report.get('tts_reference_files'),
        'llm': report['llm'],
        'articles_url': absolute(args.base_url, f'api/issues/{args.date}/articles.json'),
        'podcast_script_url': absolute(args.base_url, f'api/issues/{args.date}/podcast-script.json'),
        'html_url': absolute(args.base_url, f'html/{args.date}.html'),
        'audio_url': absolute(args.base_url, f'audio/{args.date}.mp3'),
    }
    write_json(issue_root / 'index.json', issue)
    write_json(site / 'api' / 'latest.json', issue)

    feed_path = site / 'feed.json'
    feed = read_json(feed_path) if feed_path.exists() else {'schema_version': 1, 'issues': []}
    existing = {
        item['issue_date']: item
        for item in feed.get('issues', [])
        if isinstance(item, dict) and item.get('issue_date')
    }
    existing[args.date] = issue
    feed['issues'] = sorted(existing.values(), key=lambda item: item['issue_date'], reverse=True)
    write_json(feed_path, feed)
    (site / 'index.html').write_text(render_index(issue, feed['issues']), encoding='utf-8')
    (site / '.nojekyll').touch()
    (site / '404.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Not Found</title><h1>404</h1>',
        encoding='utf-8',
    )
    print(json.dumps(issue, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
