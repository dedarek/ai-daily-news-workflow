#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from run_live_pipeline import (  # noqa: E402
    Article,
    MOSS_REFERENCE_VOICES,
    MOSS_TTS_MODEL,
    duration,
    generate_podcast_dialogue,
    moss_dialogue_input,
    moss_tts_speed,
    synthesize_siliconflow_moss,
)


def read_articles_source(source: str) -> tuple[object, str]:
    if source.startswith(('http://', 'https://')):
        request = Request(source, headers={'User-Agent': 'ai-daily-news-workflow/1.0'})
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8')), source

    path = Path(source)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return json.loads(path.read_text(encoding='utf-8')), str(path)


def load_articles(source: str) -> tuple[list[Article], str]:
    raw, resolved_source = read_articles_source(source)
    if isinstance(raw, dict):
        raw = raw.get('articles') or raw.get('items') or raw.get('data')
    if not isinstance(raw, list):
        raise RuntimeError(f'{resolved_source} must contain a JSON array or an object with articles/items/data')

    articles: list[Article] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f'article #{index} is not an object')
        title = str(item.get('title', '')).strip()
        summary = str(item.get('summary') or item.get('body') or item.get('source_summary') or '').strip()
        url = str(item.get('url') or item.get('source_url') or '').strip()
        section = str(item.get('section') or item.get('category') or '💼 行业动态').strip()
        review = str(item.get('review') or item.get('comment') or '').strip()
        if not title or not summary:
            raise RuntimeError(f'article #{index} missing title or summary/body')
        articles.append(Article(title=title, summary=summary, url=url, section=section, review=review))
    if len(articles) < 5:
        raise RuntimeError(f'need at least 5 articles for podcast generation, got {len(articles)}')
    return articles, resolved_source


def safe_duration(path: Path) -> float:
    try:
        return round(duration(path), 2)
    except Exception as exc:
        print(f'warning: failed to probe audio duration: {exc}', file=sys.stderr)
        return 0.0


def write_podcast_text(path: Path, dialogue: list[dict[str, str]]) -> None:
    lines = [f'[{turn["speaker"]}] {turn["text"]}' for turn in dialogue]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate podcast dialogue and audio from an existing articles JSON file')
    parser.add_argument('--date', default=date.today().isoformat())
    parser.add_argument('--articles', required=True, help='Path or URL to articles-YYYY-MM-DD.json or news-data-YYYY-MM-DD.json')
    parser.add_argument('--output-dir', default='tmp/podcast-test')
    parser.add_argument('--s1-reference-text', help='Exact transcript of moss-ttsd/references/voice_laochen_s1.wav')
    parser.add_argument('--s2-reference-text', help='Exact transcript of moss-ttsd/references/voice_anna_s2.mp3')
    parser.add_argument('--skip-audio', action='store_true', help='Only generate podcast script JSON/TXT, do not call TTS')
    args = parser.parse_args()

    datetime.strptime(args.date, '%Y-%m-%d')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    articles, articles_source = load_articles(args.articles)
    llm_api_key = os.environ.get('NVIDIA_API_KEY') or os.environ.get('OPENCODE_GO_API_KEY', '')
    if not llm_api_key:
        raise RuntimeError('NVIDIA_API_KEY or OPENCODE_GO_API_KEY is required to generate podcast dialogue')

    dialogue, podcast_metadata = generate_podcast_dialogue(articles, llm_api_key)

    script_json_path = output_dir / f'podcast-script-{args.date}.json'
    script_txt_path = output_dir / f'podcast-script-{args.date}.txt'
    moss_input_path = output_dir / f'podcast-moss-input-{args.date}.txt'
    audio_path = output_dir / f'daily-news-podcast-{args.date}.mp3'
    report_path = output_dir / f'podcast-only-report-{args.date}.json'

    script_json_path.write_text(
        json.dumps(
            {
                'issue_date': args.date,
                'source_articles_file': articles_source,
                'speakers': {
                    'S1': {'name': '老陈', 'role': '资深AI从业者'},
                    'S2': {'name': '小满', 'role': '产品与应用视角'},
                },
                'dialogue': dialogue,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    write_podcast_text(script_txt_path, dialogue)
    moss_input_path.write_text(moss_dialogue_input(dialogue), encoding='utf-8')

    tts_mode = 'skipped'
    podcast_bytes = 0
    podcast_duration = 0.0
    if not args.skip_audio:
        if args.s1_reference_text:
            os.environ['MOSS_TTS_S1_REFERENCE_TEXT'] = args.s1_reference_text
        if args.s2_reference_text:
            os.environ['MOSS_TTS_S2_REFERENCE_TEXT'] = args.s2_reference_text
        tts_api_key = os.environ.get('SILICONFLOW_API_KEY', '')
        if not tts_api_key:
            raise RuntimeError('SILICONFLOW_API_KEY is required unless --skip-audio is set')
        if not synthesize_siliconflow_moss(dialogue, audio_path, tts_api_key):
            raise RuntimeError('SiliconFlow MOSS-TTSD failed')
        tts_mode = 'siliconflow-moss-reference-live'
        podcast_bytes = audio_path.stat().st_size
        podcast_duration = safe_duration(audio_path)

    report = {
        'mode': 'podcast-only',
        'issue_date': args.date,
        'source_articles_file': articles_source,
        'article_count': len(articles),
        'podcast_turns': len(dialogue),
        'podcast_script_json': str(script_json_path),
        'podcast_script_txt': str(script_txt_path),
        'podcast_moss_input': str(moss_input_path),
        'podcast_audio': str(audio_path) if audio_path.exists() else None,
        'podcast_bytes': podcast_bytes,
        'podcast_duration_seconds': podcast_duration,
        'llm': podcast_metadata,
        'tts_mode': tts_mode,
        'tts_model': MOSS_TTS_MODEL if not args.skip_audio else None,
        'tts_speed': moss_tts_speed() if not args.skip_audio else None,
        'tts_reference_files': {
            speaker: MOSS_REFERENCE_VOICES[speaker]['path'].relative_to(REPO_ROOT).as_posix()
            for speaker in ('S1', 'S2')
        } if not args.skip_audio else None,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
