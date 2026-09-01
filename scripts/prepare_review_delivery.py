#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from prompt_loader import prompt_template, render_prompt
from run_live_pipeline import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODELS, llm_api_key, request_deepseek_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
NEWS_PROMPTS_FILE = SKILL_DIR / 'references' / 'news-prompts.md'


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


def write_json_file(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def email_safe_html(html_bytes: bytes) -> bytes:
    html_text = html_bytes.decode('utf-8', errors='replace')
    # The published page contains a browser video player. Email delivery adds its
    # own email-safe video entry later in send_all.py, matching morning delivery.
    html_text = re.sub(
        r'<table data-role="video-player"(?:(?!</table>).)*</table>',
        '',
        html_text,
        flags=re.S,
    )
    return html_text.encode('utf-8')


def load_published_issue(base: str, issue_date: str) -> tuple[dict, dict]:
    manifest = get_json(f'{base}/api/issues/{issue_date}/manifest.json')
    if manifest.get('date') != issue_date:
        raise RuntimeError(f'Manifest date is {manifest.get("date")}, expected {issue_date}')
    if manifest.get('status') != 'ready':
        raise RuntimeError(f'Morning manifest is not ready: status={manifest.get("status")}')
    published = manifest.get('published_artifacts')
    if not isinstance(published, dict):
        raise RuntimeError('Morning manifest missing published_artifacts')
    return manifest, published


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare and LLM-review an already published daily issue')
    parser.add_argument('--date', required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output-dir', default='review-dist')
    parser.add_argument(
        '--review-warn-only',
        action='store_true',
        help='Write the LLM review report but do not block delivery on review score or recommendation.',
    )
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')

    base = args.base_url.rstrip('/')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, published = load_published_issue(base, args.date)

    articles = get_json(published['articles'])
    candidate_articles = get_json(published['candidate_articles']) if published.get('candidate_articles') else []
    podcast_script = get_json(published['podcast_script'])
    voice = get_json(published['voice']) if published.get('voice') else None
    html_bytes = get_bytes(published['html'])
    audio_bytes = get_bytes(published['audio'])
    report_from_manifest = manifest.get('pipeline_report') if isinstance(manifest.get('pipeline_report'), dict) else {}
    tts_mode = report_from_manifest.get('tts_mode')
    video_required = tts_mode == 'video-api-audio-video'
    video_url = published.get('video')
    video_bytes = get_bytes(video_url) if video_url else None
    write_json_file(output_dir / f'manifest-{args.date}.json', manifest)
    if candidate_articles:
        write_json_file(output_dir / f'candidate-news-{args.date}.json', candidate_articles)

    (output_dir / f'articles-{args.date}.json').write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    (output_dir / f'podcast-script-{args.date}.json').write_text(
        json.dumps(podcast_script, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    if voice:
        write_json_file(output_dir / f'voice-{args.date}.json', voice)
    (output_dir / f'daily-news-{args.date}.html').write_bytes(email_safe_html(html_bytes))
    (output_dir / f'daily-news-podcast-{args.date}.mp3').write_bytes(audio_bytes)
    if video_bytes is not None:
        (output_dir / f'daily-news-video-{args.date}.mp4').write_bytes(video_bytes)
    write_podcast_text(output_dir / f'podcast-script-{args.date}.txt', podcast_script)

    deterministic_issues: list[str] = []
    allowed_tts_modes = {'video-api-audio-video', 'siliconflow-moss-reference-live'}
    if tts_mode not in allowed_tts_modes:
        deterministic_issues.append(
            f'tts_mode={tts_mode} is not one of {sorted(allowed_tts_modes)}'
        )
    urls = [item.get('url') for item in articles]
    if not articles:
        deterministic_issues.append('article_count=0')
    if len(set(urls)) != len(urls):
        deterministic_issues.append('duplicate article URLs')
    incomplete_articles = [
        item.get('title', '') or item.get('url', '')
        for item in articles
        if not str(item.get('title', '')).strip()
        or not str(item.get('summary', '')).strip()
        or not str(item.get('url', '')).strip()
    ]
    if incomplete_articles:
        deterministic_issues.append(f'incomplete article fields: {incomplete_articles}')
    dialogue = podcast_script.get('dialogue') or []
    if not dialogue:
        deterministic_issues.append('podcast dialogue is empty')
    if len(html_bytes) < 10 * 1024:
        deterministic_issues.append(f'html_bytes={len(html_bytes)} < 10240')
    if not 1_000_000 <= len(audio_bytes) <= 8 * 1024 * 1024:
        deterministic_issues.append(f'audio_bytes={len(audio_bytes)} outside allowed range')
    if video_required and video_bytes is None:
        deterministic_issues.append('video artifact is required for video-api-audio-video but missing')
    if video_bytes is not None and len(video_bytes) < 100_000:
        deterministic_issues.append(f'video_bytes={len(video_bytes)} < 100000')

    api_key = llm_api_key()
    if not api_key:
        raise RuntimeError('LENOVO_LLM_API_KEY is required for afternoon quality review')
    endpoint = os.environ.get('LENOVO_LLM_BASE_URL', DEFAULT_LLM_BASE_URL).rstrip('/')
    models = [DEFAULT_LLM_MODELS]
    review_prompt = render_prompt(
        NEWS_PROMPTS_FILE,
        'afternoon_review_user',
        deterministic_issues_json=json.dumps(deterministic_issues, ensure_ascii=False),
        articles_json=json.dumps(articles, ensure_ascii=False),
        podcast_script_json=json.dumps(podcast_script, ensure_ascii=False),
    )
    review, usage, model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=prompt_template(NEWS_PROMPTS_FILE, 'afternoon_review_system'),
        user_prompt=review_prompt,
        thinking_enabled=False,
        task_name='afternoon_review',
    )
    score = int(review.get('score', 0))
    checks = review.get('checks') or {}
    factual_pass = checks.get('factual_consistency') != 'fail'
    blocking_reasons: list[str] = []
    if deterministic_issues:
        blocking_reasons.extend(f'deterministic: {item}' for item in deterministic_issues)
    if not factual_pass:
        blocking_reasons.append('llm: factual_consistency=fail')
    if score < 50:
        blocking_reasons.append(f'llm advisory: score={score} < 50')
    # The Harness score is editorial feedback, not a second arbitrary count
    # gate. Factual conflicts and broken artifacts remain blocking.
    delivery_approved = not deterministic_issues and factual_pass
    report = {
        'issue_date': args.date,
        'reviewed_at': datetime.now().astimezone().isoformat(),
        'pass': delivery_approved,
        'delivery_approved': delivery_approved,
        'llm_recommendation_pass': review.get('pass') is True,
        'blocking_reasons': blocking_reasons,
        'deterministic_issues': deterministic_issues,
        'llm_review': review,
        'review_model': model,
        'usage': usage,
    }
    report_path = output_dir / f'quality-review-{args.date}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.review_warn_only and not delivery_approved:
        print('WARN afternoon_review_not_approved_but_delivery_continues=true', flush=True)
        return 0
    return 0 if delivery_approved else 20


if __name__ == '__main__':
    raise SystemExit(main())
