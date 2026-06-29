#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from run_live_pipeline import request_deepseek_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'


def get_bytes(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': 'ai-daily-news-review/1.0'})
    with urlopen(request, timeout=60) as response:
        return response.read()


def get_json(url: str):
    return json.loads(get_bytes(url).decode('utf-8'))


def write_podcast_text(path: Path, podcast_script: dict) -> None:
    lines: list[str] = []
    for item in podcast_script.get('dialogue') or []:
        speaker = str(item.get('speaker', '')).strip()
        text = str(item.get('text', '')).strip()
        if speaker and text:
            lines.append(f'[{speaker}] {text}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare and LLM-review an already published daily issue')
    parser.add_argument('--date', required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output-dir', default='review-dist')
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')

    base = args.base_url.rstrip('/')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    latest = get_json(f'{base}/api/latest.json')
    if latest.get('issue_date') != args.date:
        raise RuntimeError(
            f'Latest public issue is {latest.get("issue_date")}, expected {args.date}; '
            'morning publication is not ready'
        )

    articles = get_json(latest['articles_url'])
    podcast_script = get_json(latest['podcast_script_url'])
    html_bytes = get_bytes(latest['html_url'])
    audio_bytes = get_bytes(latest['audio_url'])

    (output_dir / f'articles-{args.date}.json').write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (output_dir / f'podcast-script-{args.date}.json').write_text(
        json.dumps(podcast_script, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (output_dir / f'daily-news-{args.date}.html').write_bytes(html_bytes)
    (output_dir / f'daily-news-podcast-{args.date}.mp3').write_bytes(audio_bytes)
    write_podcast_text(output_dir / f'podcast-script-{args.date}.txt', podcast_script)

    deterministic_issues: list[str] = []
    if latest.get('tts_mode') != 'siliconflow-moss-reference-live':
        deterministic_issues.append(f'tts_mode={latest.get("tts_mode")} is not siliconflow-moss-reference-live')
    expected_reference_files = {
        'S1': 'moss-ttsd/references/voice_laochen_s1.wav',
        'S2': 'moss-ttsd/references/voice_anna_s2.mp3',
    }
    if latest.get('tts_reference_files') != expected_reference_files:
        deterministic_issues.append(f'tts_reference_files={latest.get("tts_reference_files")} do not match expected MOSS references')
    urls = [item.get('url') for item in articles]
    if len(articles) < 8:
        deterministic_issues.append(f'article_count={len(articles)} < 8')
    if len(set(urls)) != len(urls):
        deterministic_issues.append('duplicate article URLs')
    short_bodies = [
        item.get('title', '')
        for item in articles
        if len(str(item.get('summary', ''))) < 120
    ]
    if short_bodies:
        deterministic_issues.append(f'short article bodies: {short_bodies}')
    dialogue = podcast_script.get('dialogue') or []
    if len(dialogue) < 12:
        deterministic_issues.append(f'podcast_turns={len(dialogue)} < 12')
    if len(html_bytes) < 15 * 1024:
        deterministic_issues.append(f'html_bytes={len(html_bytes)} < 15360')
    if not 1_000_000 <= len(audio_bytes) <= 8 * 1024 * 1024:
        deterministic_issues.append(f'audio_bytes={len(audio_bytes)} outside allowed range')

    api_key = os.environ.get('OPENCODE_GO_API_KEY', '')
    if not api_key:
        raise RuntimeError('OPENCODE_GO_API_KEY is required for afternoon quality review')
    endpoint = os.environ.get('OPENCODE_GO_BASE_URL', 'https://opencode.ai/zen/go/v1').rstrip('/')
    models = [
        item.strip()
        for item in os.environ.get(
            'OPENCODE_GO_MODELS',
            'deepseek-v4-flash,deepseek-v4-pro,mimo-v2.5',
        ).split(',')
        if item.strip()
    ]
    review_prompt = f'''
你是AI行业日报的终审编辑。请独立检查以下成品，输出JSON：
{{
  "pass": true,
  "score": 0到100的整数,
  "summary": "一句话结论",
  "issues": ["问题"],
  "checks": {{
    "factual_consistency": "pass或fail",
    "duplication": "pass或fail",
    "readability": "pass或fail",
    "editorial_quality": "pass或fail",
    "podcast_quality": "pass或fail"
  }}
}}

判定标准：
- 标题、正文和锐评之间不得明显矛盾。
- 不得有明显重复事件或重复观点。
- 正文应清楚、具体、可读，不得充斥模板化空话。
- 锐评必须与对应新闻相关。
- 播客应为自然双人对话，不得机械报幕。
- 如果没有严重问题，pass=true；轻微措辞问题可列入issues但不必判失败。

确定性检查结果：
{json.dumps(deterministic_issues, ensure_ascii=False)}

新闻：
{json.dumps(articles, ensure_ascii=False)}

播客口播稿：
{json.dumps(podcast_script, ensure_ascii=False)}
'''.strip()
    review, usage, model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt='你是严格但务实的中文AI日报终审编辑，只输出合法JSON。',
        user_prompt=review_prompt,
    )
    score = int(review.get('score', 0))
    checks = review.get('checks') or {}
    factual_pass = checks.get('factual_consistency') != 'fail'
    delivery_approved = not deterministic_issues and factual_pass and score >= 50
    report = {
        'issue_date': args.date,
        'reviewed_at': datetime.now().astimezone().isoformat(),
        'pass': delivery_approved,
        'delivery_approved': delivery_approved,
        'llm_recommendation_pass': review.get('pass') is True,
        'deterministic_issues': deterministic_issues,
        'llm_review': review,
        'review_model': model,
        'usage': usage,
    }
    report_path = output_dir / f'quality-review-{args.date}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    html_path = Path('/tmp') / f'ai-daily-news-html-{args.date}.html'
    audio_path = Path('/tmp') / f'ai-daily-news-podcast-{args.date}.mp3'
    html_path.write_bytes(html_bytes)
    audio_path.write_bytes(audio_bytes)
    sample_path = SKILL_DIR / 'samples' / f'{args.date}.html'
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, sample_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if delivery_approved else 20


if __name__ == '__main__':
    raise SystemExit(main())
