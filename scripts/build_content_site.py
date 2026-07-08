#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
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


def insert_after_summary(html_content: str, block: str) -> str:
    if 'data-role="video-player"' in html_content:
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


def insert_video_player_after_summary(html_content: str, video_url: str) -> str:
    escaped_url = html.escape(video_url, quote=True)
    block = (
        '<table data-role="video-player" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:18px 0 0;border:1px solid #bfdbfe;border-radius:14px;'
        'overflow:hidden;background:#eff6ff;">'
        '<tr><td style="padding:16px 18px;">'
        '<p style="margin:0 0 10px;font-size:15px;font-weight:700;color:#1e3a8a;">'
        '每日AI热点新闻播客</p>'
        f'<video controls preload="metadata" style="width:100%;max-height:420px;'
        'display:block;border-radius:10px;background:#020617;" src="'
        f'{escaped_url}"></video>'
        f'<p style="margin:10px 0 0;font-size:13px;line-height:1.7;color:#334155;">'
        f'<a href="{escaped_url}" style="color:#2563EB;text-decoration:none;font-weight:700;">播放视频</a>'
        '</p>'
        '</td></tr></table>'
    )
    return insert_after_summary(html_content, block)


def first_existing(paths: list[Path], label: str) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(f'Missing content artifact for {label}: {[str(path) for path in paths]}')


def render_index(latest: dict, issues: list[dict]) -> str:
    row_parts: list[str] = []
    for item in issues[:30]:
        dialogue_url = item.get('podcast_dialogue_text_url') or item.get('podcast_script_text_url')
        dialogue_link = f' · <a href="{dialogue_url}">对话文本</a>' if dialogue_url else ''
        voice_url = item.get('voice_timeline_url') or item.get('voice_url')
        voice_link = f' · <a href="{voice_url}">带时间JSON</a>' if voice_url else ''
        video_url = item.get('video_url')
        video_link = f' · <a href="{video_url}">视频</a>' if video_url else ''
        row_parts.append(
            f'<li><a href="{item["html_url"]}">{item["issue_date"]}</a>'
            f' · {item["article_count"]} 条 · <a href="{item["audio_url"]}">音频</a>'
            f'{video_link}{dialogue_link}{voice_link}</li>'
        )
    rows = ''.join(row_parts)
    latest_dialogue_url = latest.get('podcast_dialogue_text_url') or latest.get('podcast_script_text_url')
    latest_voice_url = latest.get('voice_timeline_url') or latest.get('voice_url')
    latest_links = [
        f'<a href="{latest["html_url"]}">日报</a>',
        f'<a href="{latest["audio_url"]}">音频</a>',
    ]
    if latest.get('video_url'):
        latest_links.append(f'<a href="{latest["video_url"]}">视频</a>')
    if latest_dialogue_url:
        latest_links.append(f'<a href="{latest_dialogue_url}">对话文本</a>')
    if latest_voice_url:
        latest_links.append(f'<a href="{latest_voice_url}">带时间JSON</a>')
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
  <p>最新一期：{latest["issue_date"]} · {' · '.join(latest_links)}</p>
  <h2>API</h2>
  <ul>
    <li><a href="api/latest.json"><code>/api/latest.json</code></a></li>
    <li><a href="feed.json"><code>/feed.json</code></a></li>
    <li><code>/api/issues/YYYY-MM-DD/manifest.json</code></li>
    <li><code>/api/issues/YYYY-MM-DD/index.json</code></li>
    <li><code>/api/issues/YYYY-MM-DD/articles.json</code></li>
    <li><code>/api/issues/YYYY-MM-DD/podcast-script.json</code></li>
    <li><code>/podcast-dialogue/YYYY-MM-DD.txt</code></li>
    <li><code>/voice/YYYY-MM-DD.json</code></li>
    <li><code>/video/YYYY-MM-DD.mp4</code></li>
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
    manifest_path = first_existing([dist / f'manifest-{args.date}.json'], 'manifest')
    report_path = first_existing([dist / f'pipeline-report-{args.date}.json'], 'pipeline report')
    articles_path = first_existing(
        [dist / f'articles-{args.date}.json', dist / f'news-data-{args.date}.json'],
        'articles',
    )
    candidate_articles_path = first_existing([dist / f'candidate-news-{args.date}.json'], 'candidate articles')
    script_path = first_existing([dist / f'podcast-script-{args.date}.json'], 'podcast script')
    script_text_path = first_existing([dist / f'podcast-script-{args.date}.txt'], 'podcast script text')
    moss_input_path = first_existing([dist / f'podcast-moss-input-{args.date}.txt'], 'podcast moss input')
    voice_path = first_existing([dist / f'voice-{args.date}.json'], 'voice timeline')
    html_path = first_existing(
        [dist / f'daily-news-{args.date}.html', dist / f'ai-daily-news-html-{args.date}.html'],
        'html',
    )
    audio_path = first_existing(
        [dist / f'daily-news-podcast-{args.date}.mp3', dist / f'ai-daily-news-podcast-{args.date}.mp3'],
        'audio',
    )
    video_path = first_existing(
        [dist / f'daily-news-video-{args.date}.mp4', dist / f'ai-daily-news-video-{args.date}.mp4'],
        'video',
    )

    report = read_json(report_path)
    manifest = read_json(manifest_path)
    candidate_articles = read_json(candidate_articles_path)
    articles = read_json(articles_path)
    podcast_script = read_json(script_path)
    voice = read_json(voice_path)
    issue_root = site / 'api' / 'issues' / args.date
    write_json(issue_root / 'candidate-news.json', candidate_articles)
    write_json(issue_root / 'articles.json', articles)
    write_json(issue_root / 'podcast-script.json', podcast_script)
    shutil.copy2(script_text_path, issue_root / 'podcast-script.txt')
    shutil.copy2(moss_input_path, issue_root / 'podcast-moss-input.txt')
    write_json(issue_root / 'pipeline-report.json', report)

    published_html = site / 'html' / f'{args.date}.html'
    published_audio = site / 'audio' / f'{args.date}.mp3'
    published_video = site / 'video' / f'{args.date}.mp4'
    published_dialogue_text = site / 'podcast-dialogue' / f'{args.date}.txt'
    published_voice = site / 'voice' / f'{args.date}.json'
    published_html.parent.mkdir(parents=True, exist_ok=True)
    published_audio.parent.mkdir(parents=True, exist_ok=True)
    published_video.parent.mkdir(parents=True, exist_ok=True)
    published_dialogue_text.parent.mkdir(parents=True, exist_ok=True)
    published_voice.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, published_html)
    shutil.copy2(audio_path, published_audio)
    shutil.copy2(video_path, published_video)
    shutil.copy2(script_text_path, published_dialogue_text)

    issue = {
        'schema_version': 1,
        'issue_date': args.date,
        'content_date': report['content_date'],
        'published_at': datetime.now(timezone.utc).isoformat(),
        'article_count': len(articles),
        'podcast_turns': len(podcast_script['dialogue']),
        'tts_mode': report['tts_mode'],
        'tts_model': report.get('tts_model'),
        'tts_speed': report.get('tts_speed'),
        'tts_reference_files': report.get('tts_reference_files'),
        'llm': report['llm'],
        'articles_url': absolute(args.base_url, f'api/issues/{args.date}/articles.json'),
        'candidate_articles_url': absolute(args.base_url, f'api/issues/{args.date}/candidate-news.json'),
        'podcast_script_url': absolute(args.base_url, f'api/issues/{args.date}/podcast-script.json'),
        'podcast_script_text_url': absolute(args.base_url, f'api/issues/{args.date}/podcast-script.txt'),
        'podcast_dialogue_text_url': absolute(args.base_url, f'podcast-dialogue/{args.date}.txt'),
        'podcast_moss_input_url': absolute(args.base_url, f'api/issues/{args.date}/podcast-moss-input.txt'),
        'voice_url': absolute(args.base_url, f'api/issues/{args.date}/voice.json'),
        'voice_timeline_url': absolute(args.base_url, f'voice/{args.date}.json'),
        'manifest_url': absolute(args.base_url, f'api/issues/{args.date}/manifest.json'),
        'html_url': absolute(args.base_url, f'html/{args.date}.html'),
        'audio_url': absolute(args.base_url, f'audio/{args.date}.mp3'),
        'video_url': absolute(args.base_url, f'video/{args.date}.mp4'),
    }
    published_html.write_text(
        insert_video_player_after_summary(published_html.read_text(encoding='utf-8'), issue['video_url']),
        encoding='utf-8',
    )
    voice['audio'] = issue['audio_url']
    voice['video'] = issue['video_url']
    write_json(issue_root / 'voice.json', voice)
    write_json(published_voice, voice)
    manifest['published_artifacts'] = {
        'index': absolute(args.base_url, f'api/issues/{args.date}/index.json'),
        'candidate_articles': issue['candidate_articles_url'],
        'articles': issue['articles_url'],
        'podcast_script': issue['podcast_script_url'],
        'podcast_script_text': issue['podcast_script_text_url'],
        'podcast_dialogue_text': issue['podcast_dialogue_text_url'],
        'podcast_moss_input': issue['podcast_moss_input_url'],
        'voice': issue['voice_url'],
        'voice_timeline': issue['voice_timeline_url'],
        'html': issue['html_url'],
        'audio': issue['audio_url'],
        'video': issue['video_url'],
        'pipeline_report': absolute(args.base_url, f'api/issues/{args.date}/pipeline-report.json'),
    }
    write_json(issue_root / 'manifest.json', manifest)
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
