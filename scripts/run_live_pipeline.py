#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prompt_loader import prompt_template as prompt_template_from_file
from prompt_loader import render_prompt as render_prompt_from_file

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
NEWS_PROMPTS_FILE = SKILL_DIR / 'references' / 'news-prompts.md'
PODCAST_PROMPTS_FILE = SKILL_DIR / 'references' / 'podcast-prompts.md'
STATE_PATH = REPO_ROOT / 'state' / 'recent-news.json'
SOURCE_ROOT = 'https://hex2077.dev/docs'
FORBIDDEN_URL_PARTS = ('hex2077.dev', 'aibase.com', 'hubtoday', 'wappoc_appmsgcaptcha')
SECTION_ORDER = ['🔥 今日焦点', '🚀 产品发布', '💼 行业动态', '💡 前沿研究', '🔓 开源热榜', '🤖 Agent & 工具']
MOSS_TTS_MODEL = 'fnlp/MOSS-TTSD-v0.5'
DEFAULT_MOSS_TTS_SPEED = 1.02
DEFAULT_TTS_LEADING_SILENCE_SECONDS = 0.35
MOSS_REFERENCE_VOICES = {
    'S1': {
        'path': REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_laochen_s1.wav',
        'text_env': 'MOSS_TTS_S1_REFERENCE_TEXT',
        'default_text': '今天我们来聊几个AI行业里的关键变化，重点看它们对产品和企业落地意味着什么。',
    },
    'S2': {
        'path': REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_anna_s2.mp3',
        'text_env': 'MOSS_TTS_S2_REFERENCE_TEXT',
        'default_text': '我更关心这些变化什么时候能真正落到用户手里，以及企业该怎么判断投入产出。',
    },
}


@dataclass
class Article:
    title: str
    summary: str
    url: str
    section: str
    review: str = ''
    source_text: str = ''
    source_text_status: str = ''


class DailyPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_depth = 0
        self.heading_text: list[str] = []
        self.current_heading = ''
        self.in_li = False
        self.li_depth = 0
        self.li_text: list[str] = []
        self.li_links: list[str] = []
        self.li_strong_depth = 0
        self.li_title: list[str] = []
        self.li_title_complete = False
        self.items: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in ('h2', 'h3'):
            self.heading_depth += 1
            self.heading_text = []
        if tag == 'li' and not self.in_li:
            self.in_li = True
            self.li_depth = 1
            self.li_text = []
            self.li_links = []
            self.li_title = []
            self.li_title_complete = False
        elif self.in_li:
            if tag == 'li':
                self.li_depth += 1
            if tag == 'strong':
                self.li_strong_depth += 1
            if tag == 'a':
                href = attrs_dict.get('href') or ''
                if href.startswith(('http://', 'https://')):
                    self.li_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ('h2', 'h3') and self.heading_depth:
            self.current_heading = clean_text(''.join(self.heading_text))
            self.heading_depth -= 1
        if not self.in_li:
            return
        if tag == 'strong' and self.li_strong_depth:
            self.li_strong_depth -= 1
            if self.li_title:
                self.li_title_complete = True
        if tag == 'li':
            self.li_depth -= 1
            if self.li_depth == 0:
                title = clean_text(''.join(self.li_title))
                body = clean_text(''.join(self.li_text))
                url = next((u for u in self.li_links if valid_article_url(u)), '')
                if title and body and url:
                    self.items.append((self.current_heading, title, body))
                    self.items[-1] = (self.current_heading, title, f'{body}\n{url}')
                self.in_li = False

    def handle_data(self, data: str) -> None:
        if self.heading_depth:
            self.heading_text.append(data)
        if self.in_li:
            self.li_text.append(data)
            if self.li_strong_depth and not self.li_title_complete:
                self.li_title.append(data)


class SourceTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style', 'svg', 'noscript'}:
            self.skip_depth += 1
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'blockquote', 'figcaption'}:
            self.parts.append('。')

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style', 'svg', 'noscript'} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'blockquote', 'figcaption'}:
            self.parts.append('。')

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        text = clean_text(' '.join(self.parts))
        text = re.sub(r'(。\s*){2,}', '。', text)
        return text.lstrip('。 ')


def clean_text(text: str) -> str:
    text = re.sub(r'\(AI资讯\)', '', text, flags=re.I)
    text = text.replace('🚀', '').replace('(✧∀✧)', '').replace('⭐', '')
    return re.sub(r'\s+', ' ', text).strip()


def validate_podcast_dialogue(dialogue: list[dict[str, str]]) -> list[str]:
    issues: list[str] = []
    if not 10 <= len(dialogue) <= 22:
        issues.append(f'podcast_turns={len(dialogue)} outside accepted 10-22')

    for index, turn in enumerate(dialogue):
        speaker = turn.get('speaker')
        text = clean_text(str(turn.get('text', '')))
        if speaker not in ('S1', 'S2'):
            issues.append(f'turn {index + 1} invalid speaker={speaker}')
            continue
        if not text:
            issues.append(f'turn {index + 1} empty text')
            continue
        if not 10 <= len(text) <= 130:
            issues.append(f'turn {index + 1} text length={len(text)} outside accepted 10-130')
        expected = 'S1' if index % 2 == 0 else 'S2'
        if speaker != expected:
            issues.append(f'turn {index + 1} speaker={speaker} expected {expected}')

    texts = [turn.get('text', '') for turn in dialogue]
    if texts:
        stiff_first_turns = sum(
            1
            for text in texts[:2]
            if re.match(r'^[\u4e00-\u9fa5A-Za-z0-9]+(发布|公布|推出|宣布|曝出|即将|将于|通过|采用|认为)', text)
        )
        if stiff_first_turns:
            issues.append('podcast starts directly with news facts instead of an opening')

    banned_phrases = (
        '第一条新闻',
        '第二条新闻',
        '第三条新闻',
        '接下来我们聊',
        '我们再看',
        '下面来看',
        '值得关注的是',
        '这项动态围绕',
        '后续观察重点',
    )
    banned_hits = [phrase for phrase in banned_phrases if any(phrase in text for text in texts)]
    if banned_hits:
        issues.append(f'banned broadcast phrases: {banned_hits}')

    return issues


def valid_article_url(url: str) -> bool:
    lower = url.lower()
    if any(part in lower for part in FORBIDDEN_URL_PARTS):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc) and parsed.path not in ('', '/')


def prompt_template(name: str) -> str:
    return prompt_template_from_file(PODCAST_PROMPTS_FILE, name)


def render_prompt(name: str, **values: str) -> str:
    return render_prompt_from_file(PODCAST_PROMPTS_FILE, name, **values)


def section_for(source_heading: str, index: int) -> str:
    heading = source_heading.lower()
    if index == 0:
        return '🔥 今日焦点'
    if '开源' in source_heading:
        return '🔓 开源热榜'
    if '研究' in source_heading:
        return '💡 前沿研究'
    if any(word in heading for word in ('agent', '工具', '社媒')):
        return '🤖 Agent & 工具'
    if any(word in source_heading for word in ('产品', '功能', '发布')):
        return '🚀 产品发布'
    return '💼 行业动态'


def expand_summary(title: str, raw: str) -> str:
    raw = clean_text(raw)
    raw = raw.removeprefix(title).lstrip('。 ')
    sentences = [s.strip() for s in re.split(r'(?<=[。！？])', raw) if s.strip()]
    base = ''.join(sentences[:5]).strip() or raw
    if base and not base.endswith(('。', '！', '？')):
        base += '。'
    return base[:420]


def fetch_latest(issue_date: str) -> tuple[str, str, str]:
    start = datetime.strptime(issue_date, '%Y-%m-%d').date()
    errors: list[str] = []
    for offset in range(4):
        candidate = start - timedelta(days=offset)
        candidate_str = candidate.isoformat()
        url = f'{SOURCE_ROOT}/{candidate_str[:7]}/{candidate_str}/'
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 AI-Daily-News-Workflow/1.0'})
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode('utf-8', errors='replace')
            if len(raw) > 10_000:
                return candidate_str, url, raw
        except Exception as exc:
            errors.append(f'{candidate_str}: {type(exc).__name__}')
    raise RuntimeError('No daily source page available: ' + ', '.join(errors))


def extract_source_text(raw_html: str) -> str:
    raw_html = re.sub(r'(?is)<(script|style|svg|noscript).*?</\1>', ' ', raw_html)
    parser = SourceTextParser()
    parser.feed(raw_html)
    text = parser.text()
    boilerplate_patterns = (
        r'Copyright.*',
        r'All rights reserved.*',
        r'登录后.*',
        r'打开.*?App.*',
        r'分享到.*',
    )
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, ' ', text, flags=re.I)
    return clean_text(text)[:5000]


def fetch_source_text(url: str, fallback: str) -> tuple[str, str]:
    try:
        request = Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 AI-Daily-News-Workflow/1.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
        )
        with urlopen(request, timeout=25) as response:
            content_type = response.headers.get('Content-Type', '')
            raw = response.read(1_500_000)
        if 'html' not in content_type.lower() and b'<html' not in raw[:1000].lower():
            return fallback, 'fallback'
        encoding = 'utf-8'
        match = re.search(r'charset=([\w.-]+)', content_type, flags=re.I)
        if match:
            encoding = match.group(1)
        text = extract_source_text(raw.decode(encoding, errors='replace'))
        return (text, 'fetched') if len(text) >= 200 else (fallback, 'fallback')
    except Exception as exc:
        print(f'WARN source_text_fetch_failed url={url} error={type(exc).__name__}', flush=True)
        return fallback, 'fallback'


def parse_articles(raw_html: str, limit: int = 15) -> list[Article]:
    parser = DailyPageParser()
    parser.feed(raw_html)
    articles: list[Article] = []
    seen: set[tuple[str, str]] = set()
    for heading, title, body_and_url in parser.items:
        body, url = body_and_url.rsplit('\n', 1)
        key = (title.lower(), url)
        if key in seen or not valid_article_url(url):
            continue
        if any(word in heading for word in ('多渠道', '摘要')):
            continue
        seen.add(key)
        articles.append(
            Article(
                title=title.rstrip('。'),
                summary=expand_summary(title, body),
                url=url,
                section=section_for(heading, len(articles)),
            )
        )
        if len(articles) >= limit:
            break
    if len(articles) < 8:
        raise RuntimeError(f'Only {len(articles)} valid live articles were parsed')
    return articles


def enrich_articles_with_source_text(articles: list[Article]) -> list[Article]:
    enriched: list[Article] = []
    for article in articles:
        source_text, source_text_status = fetch_source_text(article.url, article.summary)
        enriched.append(
            Article(
                title=article.title,
                summary=article.summary,
                url=article.url,
                section=article.section,
                review=article.review,
                source_text=source_text,
                source_text_status=source_text_status,
            )
        )
    return enriched


def load_recent_titles_for_selection(exclude_date: str) -> dict[str, dict[str, list[dict[str, str]]]]:
    if not STATE_PATH.exists():
        return {}
    try:
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    days = state.get('days') if isinstance(state, dict) else {}
    if not isinstance(days, dict):
        return {}

    recent: dict[str, dict[str, list[dict[str, str]]]] = {}
    for day, payload in sorted(days.items(), reverse=True):
        if day == exclude_date or not isinstance(payload, dict):
            continue
        recent[day] = {
            'candidates': [
                {
                    'date': str(item.get('date') or day),
                    'title': str(item.get('title', '')).strip(),
                    'summary': str(item.get('summary', '')).strip()[:260],
                    'url': str(item.get('url', '')).strip(),
                }
                for item in payload.get('candidates', [])
                if isinstance(item, dict) and str(item.get('title', '')).strip()
            ],
            'selected': [
                {
                    'date': str(item.get('date') or day),
                    'title': str(item.get('title', '')).strip(),
                    'summary': str(item.get('summary', '')).strip()[:260],
                    'url': str(item.get('url', '')).strip(),
                }
                for item in payload.get('selected', [])
                if isinstance(item, dict) and str(item.get('title', '')).strip()
            ],
        }
    return recent


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        raise RuntimeError('LLM response did not contain a JSON object')
    return json.loads(text[start:end + 1])


def request_deepseek_json(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict, dict, str]:
    model_errors: list[str] = []
    for model_index, model in enumerate(models):
        payload = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'response_format': {'type': 'json_object'},
            'reasoning_effort': 'low',
            'temperature': 0.3,
        }).encode('utf-8')
        last_error = ''
        for attempt in range(1, 4):
            request = Request(
                f'{endpoint}/chat/completions',
                data=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'ai-daily-news-workflow/1.0',
                },
                method='POST',
            )
            try:
                with urlopen(request, timeout=240) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                choice = response_data['choices'][0]
                if choice.get('finish_reason') != 'stop':
                    raise RuntimeError(f"incomplete response: finish_reason={choice.get('finish_reason')}")
                try:
                    result = extract_json_object(choice['message']['content'])
                except (json.JSONDecodeError, RuntimeError) as exc:
                    raise RuntimeError(f'invalid JSON response: {exc}') from exc
                return result, response_data.get('usage') or {}, model
            except HTTPError as exc:
                error_body = exc.read().decode('utf-8', errors='replace')[:1000]
                last_error = f'HTTP {exc.code}: {error_body}'
                retryable = exc.code in (429, 500, 502, 503, 504)
                if not retryable:
                    break
                if attempt < 3:
                    retry_after = exc.headers.get('Retry-After')
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else 20 * attempt
                    print(
                        f'OpenCode Go model={model} transient HTTP {exc.code}; '
                        f'retrying in {delay}s ({attempt}/3)',
                        flush=True,
                    )
                    time.sleep(delay)
            except RuntimeError as exc:
                last_error = str(exc)
                if attempt < 3:
                    delay = 8 * attempt
                    print(
                        f'OpenCode Go model={model} {exc}; regenerating in {delay}s ({attempt}/3)',
                        flush=True,
                    )
                    time.sleep(delay)
        model_errors.append(f'{model}: {last_error or "no valid response"}')
        if model_index < len(models) - 1:
            print(f'OpenCode Go switching model {model} -> {models[model_index + 1]}', flush=True)
    raise RuntimeError('OpenCode Go model chain exhausted: ' + ' | '.join(model_errors))


def llm_config() -> tuple[str, list[str]]:
    endpoint = os.environ.get('OPENCODE_GO_BASE_URL', 'https://opencode.ai/zen/go/v1').rstrip('/')
    configured_models = os.environ.get(
        'OPENCODE_GO_MODELS',
        'deepseek-v4-flash,deepseek-v4-pro,mimo-v2.5',
    )
    models = [model.strip() for model in configured_models.split(',') if model.strip()]
    if not models:
        raise RuntimeError('OPENCODE_GO_MODELS must contain at least one model')
    return endpoint, models


def generate_digest_summary(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    system_prompt: str,
    articles: list[Article],
) -> tuple[str, dict, str]:
    prompt = render_prompt_from_file(
        NEWS_PROMPTS_FILE,
        'digest_summary_user',
        articles_json=json.dumps([asdict(item) for item in articles], ensure_ascii=False),
    )
    result, usage, model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=prompt,
    )
    summary = clean_text(str(result.get('summary', '')))
    if not 30 <= len(summary) <= 140:
        summary = '今天的AI动态集中在模型能力、产品落地与开源生态的持续演进，企业应用和开发者工具仍是主要竞争焦点。'
    return summary, usage, model


def call_deepseek(
    candidate_articles: list[Article],
    api_key: str,
    issue_date: str,
) -> tuple[list[Article], list[dict[str, str]], str, dict]:
    endpoint, models = llm_config()
    candidates = [
        {
            'title': item.title,
            'source_summary': item.summary,
            'url': item.url,
            'suggested_section': item.section,
        }
        for item in candidate_articles
    ]
    system_prompt = prompt_template_from_file(NEWS_PROMPTS_FILE, 'editorial_system')
    selection_prompt = render_prompt_from_file(
        NEWS_PROMPTS_FILE,
        'selection_user',
        section_order_json=json.dumps(SECTION_ORDER, ensure_ascii=False),
        recent_titles_json=json.dumps(load_recent_titles_for_selection(issue_date), ensure_ascii=False),
        candidates_json=json.dumps(candidates, ensure_ascii=False),
    )
    selection_result, selection_usage, selection_model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=selection_prompt,
    )
    candidate_map = {item.url: item for item in candidate_articles}
    selected: list[tuple[Article, str]] = []
    seen_urls: set[str] = set()
    for item in selection_result.get('selection', []):
        url = str(item.get('url', '')).strip()
        section = str(item.get('section', '')).strip()
        if url in candidate_map and url not in seen_urls and section in SECTION_ORDER:
            selected.append((candidate_map[url], section))
            seen_urls.add(url)
    if len(selected) != 12:
        raise RuntimeError(f'LLM selected {len(selected)} valid articles; expected exactly 12')
    focus_count = sum(section == '🔥 今日焦点' for _, section in selected)
    if selected[0][1] != '🔥 今日焦点' or focus_count != 1:
        raise RuntimeError(f'LLM selection focus validation failed: first={selected[0][1]}, count={focus_count}')

    selected_sections = [section for _, section in selected]
    selected_sources = enrich_articles_with_source_text([source for source, _ in selected])
    selected = list(zip(selected_sources, selected_sections))

    articles: list[Article] = []
    editorial_calls: list[dict] = []
    for batch_start in range(0, len(selected), 4):
        batch = selected[batch_start:batch_start + 4]
        batch_input = [
            {
                'title': source.title,
                'source_summary': source.summary,
                'source_text': source.source_text,
                'source_text_status': source.source_text_status,
                'url': source.url,
                'section': section,
            }
            for source, section in batch
        ]
        batch_prompt = render_prompt_from_file(
            NEWS_PROMPTS_FILE,
            'editorial_batch_user',
            batch_input_json=json.dumps(batch_input, ensure_ascii=False),
        )
        batch_result, batch_usage, batch_model = request_deepseek_json(
            endpoint=endpoint,
            models=models,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=batch_prompt,
        )
        editorial_calls.append({'model': batch_model, 'usage': batch_usage})
        generated_items = batch_result.get('articles', [])
        if len(generated_items) != len(batch):
            raise RuntimeError(
                f'LLM editorial batch returned {len(generated_items)} items; expected {len(batch)}'
            )
        for item, (source, section) in zip(generated_items, batch):
            body = clean_text(str(item.get('body', '')))
            if len(body) < 120:
                body = clean_text(f'{body} {source.summary}')
            article = Article(
                title=clean_text(str(item.get('title', ''))),
                summary=body,
                url=source.url,
                section=section,
                review=clean_text(str(item.get('review', ''))),
            )
            if (
                article.title
                and len(article.summary) >= 120
                and article.review
            ):
                articles.append(article)
            else:
                raise RuntimeError(f'LLM editorial item invalid for source URL: {source.url}')

    digest_summary, digest_usage, digest_model = generate_digest_summary(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=system_prompt,
        articles=articles,
    )
    dialogue, podcast_metadata = generate_podcast_dialogue(articles, api_key)
    podcast_details = podcast_metadata.get('call_details', {})
    metadata = {
        'provider': 'opencode-go',
        'model_chain': models,
        'endpoint': endpoint,
        'calls': 2 + len(editorial_calls) + int(podcast_metadata.get('calls', 1)),
        'call_details': {
            'selection': {'model': selection_model, 'usage': selection_usage},
            'editorial_batches': editorial_calls,
            'digest_summary': {'model': digest_model, 'usage': digest_usage},
            'podcast': podcast_details.get('podcast'),
            'podcast_review': podcast_details.get('podcast_review'),
            'podcast_attempts': podcast_details.get('podcast_attempts'),
        },
    }
    return articles, dialogue, digest_summary, metadata


def build_podcast_prompt(articles: list[Article], repair_instruction: str = '') -> str:
    podcast_prompt = render_prompt(
        'podcast_generation_user',
        articles_json=json.dumps([asdict(item) for item in articles], ensure_ascii=False),
    )
    if repair_instruction:
        podcast_prompt += '\n' + render_prompt(
            'podcast_generation_repair',
            repair_instruction=repair_instruction,
        )
    return podcast_prompt


def parse_podcast_dialogue(podcast_result: dict) -> list[dict[str, str]]:
    dialogue: list[dict[str, str]] = []
    for item in podcast_result.get('podcast_dialogue', []):
        if not isinstance(item, dict):
            continue
        speaker = str(item.get('speaker', '')).strip()
        text = clean_text(str(item.get('text', '')))
        dialogue.append({'speaker': speaker, 'text': text})
    return dialogue


def generate_podcast_dialogue_once(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    articles: list[Article],
    repair_instruction: str = '',
) -> tuple[list[dict[str, str]], dict, str]:
    podcast_prompt = build_podcast_prompt(articles, repair_instruction)
    podcast_result, podcast_usage, podcast_model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=prompt_template('podcast_generation_system'),
        user_prompt=podcast_prompt,
    )
    return parse_podcast_dialogue(podcast_result), podcast_usage, podcast_model


def review_podcast_dialogue(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    articles: list[Article],
    dialogue: list[dict[str, str]],
    structure_issues: list[str],
) -> tuple[dict, dict, str]:
    review_prompt = render_prompt(
        'podcast_review_user',
        structure_issues_json=json.dumps(structure_issues, ensure_ascii=False),
        articles_json=json.dumps([asdict(item) for item in articles], ensure_ascii=False),
        dialogue_json=json.dumps(dialogue, ensure_ascii=False),
    )
    review, usage, model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=prompt_template('podcast_review_system'),
        user_prompt=review_prompt,
    )
    issues = review.get('issues')
    if not isinstance(issues, list):
        issues = [str(issues)] if issues else []
    return {
        'pass': review.get('pass') is True,
        'issues': [str(item) for item in issues],
        'repair_instruction': str(review.get('repair_instruction') or '').strip(),
    }, usage, model


def generate_podcast_dialogue(articles: list[Article], api_key: str) -> tuple[list[dict[str, str]], dict]:
    endpoint, models = llm_config()
    attempts: list[dict] = []
    repair_instruction = ''
    final_dialogue: list[dict[str, str]] = []

    for attempt in range(1, 3):
        dialogue, podcast_usage, podcast_model = generate_podcast_dialogue_once(
            endpoint=endpoint,
            models=models,
            api_key=api_key,
            articles=articles,
            repair_instruction=repair_instruction,
        )
        final_dialogue = dialogue
        structure_issues = validate_podcast_dialogue(dialogue)
        review, review_usage, review_model = review_podcast_dialogue(
            endpoint=endpoint,
            models=models,
            api_key=api_key,
            articles=articles,
            dialogue=dialogue,
            structure_issues=structure_issues,
        )

        attempts.append({
            'attempt': attempt,
            'generation': {'model': podcast_model, 'usage': podcast_usage},
            'structure_issues': structure_issues,
            'review': review,
            'review_model': review_model,
            'review_usage': review_usage,
        })

        if not structure_issues and review.get('pass') is True:
            metadata = {
                'provider': 'opencode-go',
                'model_chain': models,
                'endpoint': endpoint,
                'calls': sum(1 + (1 if item.get('review') is not None else 0) for item in attempts),
                'call_details': {
                    'podcast': {'model': podcast_model, 'usage': podcast_usage},
                    'podcast_review': {'model': review_model, 'usage': review_usage},
                    'podcast_attempts': attempts,
                },
            }
            return dialogue, metadata

        repair_parts: list[str] = []
        if structure_issues:
            repair_parts.append('结构问题：' + '；'.join(structure_issues))
        review_instruction = review.get('repair_instruction') or '；'.join(review.get('issues') or [])
        if review_instruction:
            repair_parts.append('AI自检意见：' + review_instruction)
        repair_instruction = '\n'.join(repair_parts)
        if not repair_instruction:
            repair_instruction = '对话质量未通过，请增强自然开场、真实互动、分歧和判断，并保持不新增事实。'

    raise RuntimeError(
        'LLM podcast dialogue quality failed after repair loop: '
        + json.dumps({'attempts': attempts, 'final_dialogue': final_dialogue}, ensure_ascii=False)
    )


def render_html(
    issue_date: str,
    content_date: str,
    articles: list[Article],
    output_path: Path,
    digest_summary: str,
) -> None:
    dt = datetime.strptime(issue_date, '%Y-%m-%d')
    weekdays = '一二三四五六日'
    display_date = f'{dt.year}年{dt.month}月{dt.day}日 星期{weekdays[dt.weekday()]}'
    grouped = {section: [] for section in SECTION_ORDER}
    for article in articles:
        grouped.setdefault(article.section, []).append(article)

    parts = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>每日AI热点新闻 — {html.escape(issue_date)}</title>',
        '</head>',
        '<body style="margin:0;padding:0;font-family:\'PingFang SC\',\'Microsoft YaHei\',\'Helvetica Neue\',Arial,sans-serif;background-color:#eef1f5;">',
        '<table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">',
        '<tr><td align="center">',
        '<table width="700" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border:1px solid #c9cdd4;border-radius:10px;overflow:hidden;">',
        '<tr><td style="background-color:#3b82f6;padding:28px 30px;text-align:center;border-bottom:4px solid #1d4ed8;">',
        '<h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;letter-spacing:0.5px;">📰 每日AI热点新闻（试运营）</h1>',
        f'<p style="color:rgba(255,255,255,0.85);margin:8px 0 0 0;font-size:13px;">{display_date}</p>',
        '</td></tr>',
        '<tr><td style="padding:22px 36px 18px;">',
        f'<p style="color:#374151;font-size:15px;line-height:1.9;margin:0;">{html.escape(digest_summary)}</p>',
        '</td></tr>',
    ]
    for section in SECTION_ORDER:
        section_articles = grouped.get(section) or []
        if not section_articles:
            continue
        parts.extend([
            '<tr><td style="padding:0 36px"><hr style="border:none;border-top:1px solid #e5e7eb;margin:0;"></td></tr>',
            '<tr><td style="padding:22px 36px 26px;">',
            f'<h2 style="font-size:17px;font-weight:700;color:#111827;margin:0 0 16px;padding-bottom:8px;border-bottom:2px solid #dbeafe;">{html.escape(section)}</h2>',
        ])
        for article in section_articles:
            escaped_url = html.escape(article.url, quote=True)
            review = f'AI锐评：{html.escape(article.review)}'
            is_focus = section == '🔥 今日焦点'
            card_style = (
                'margin-bottom:16px;border:1px solid #fca5a5;border-radius:8px;overflow:hidden;'
                if is_focus else
                'margin-bottom:16px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;'
            )
            cell_style = (
                'padding:14px 18px;background-color:#ffffff;border-left:4px solid #ef4444;'
                if is_focus else
                'padding:14px 18px;background-color:#f8fafc;'
            )
            parts.extend([
                f'<table width="100%" cellpadding="0" cellspacing="0" style="{card_style}">',
                f'<tr><td style="{cell_style}">',
            ])
            if is_focus:
                parts.append('<span style="display:inline-block;background-color:#ef4444;color:#ffffff;font-size:11px;padding:2px 10px;border-radius:10px;font-weight:600;margin-bottom:8px;">焦点</span>')
            parts.extend([
                '<h3 style="font-size:15px;font-weight:700;margin:8px 0 6px;line-height:1.6;">' if is_focus else '<h3 style="font-size:15px;font-weight:700;margin:0 0 6px;line-height:1.6;">',
                f'<a href="{escaped_url}" style="color:#2563EB;text-decoration:none;">{html.escape(article.title)}</a>',
                '</h3>',
                f'<p data-role="news-body" style="font-size:14px;line-height:2;color:#475569;margin:0 0 8px;">{html.escape(article.summary)}</p>',
                '<table width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:8px 12px;background-color:#fffbeb;border-left:3px solid #f59e0b;border-radius:0 4px 4px 0;">',
                f'<p style="font-size:13px;color:#6B7280;font-style:italic;margin:0;line-height:1.8;">{review}</p>',
                '</td></tr></table>',
                f'<p style="font-size:12px;color:#64748b;margin:8px 0 0;">🔗 <a href="{escaped_url}" style="color:#2563EB;text-decoration:none;word-break:break-all;">{html.escape(article.url)}</a></p>',
                '</td></tr></table>',
            ])
        parts.append('</td></tr>')
    parts.extend([
        '<tr><td style="padding:20px 36px;text-align:center;background-color:#f8fafc;">',
        '<p style="font-size:12px;color:#9ca3af;margin:0;line-height:1.6;">',
        f'每日AI热点新闻 · 试运营阶段 · {html.escape(issue_date)}<br>',
        f'内容采集日期：{html.escape(content_date)} · 本邮件由AI自动生成，内容仅供参考。<br>',
        '如有问题请联系：penglei4@lenovo.com',
        '</p>',
        '</td></tr>',
        '</table>',
        '</td></tr>',
        '</table>',
        '</body>',
        '</html>',
    ])
    output_path.write_text(''.join(parts), encoding='utf-8')


def encode_reference_audio(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f'MOSS reference voice missing or empty: {path}')
    mime_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def moss_reference_payload() -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for speaker in ('S1', 'S2'):
        config = MOSS_REFERENCE_VOICES[speaker]
        reference_text = os.environ.get(config['text_env'])
        if not reference_text:
            print(
                f'warning: {config["text_env"]} is not set; using fallback reference text for {speaker}. '
                'For best MOSS-TTSD quality, set it to the exact transcript of the reference audio.',
                flush=True,
            )
            reference_text = config['default_text']
        references.append({
            'audio': encode_reference_audio(config['path']),
            'text': reference_text,
        })
    return references


def moss_dialogue_input(dialogue: list[dict[str, str]]) -> str:
    return ''.join(f'[{turn["speaker"]}]{turn["text"]}' for turn in dialogue)


def moss_tts_speed() -> float:
    raw = os.environ.get('MOSS_TTS_SPEED', str(DEFAULT_MOSS_TTS_SPEED))
    try:
        speed = float(raw)
    except ValueError as exc:
        raise RuntimeError(f'MOSS_TTS_SPEED must be a number, got {raw!r}') from exc
    if not 0.8 <= speed <= 1.3:
        raise RuntimeError(f'MOSS_TTS_SPEED must be between 0.8 and 1.3, got {speed}')
    return speed


def tts_leading_silence_seconds() -> float:
    raw = os.environ.get('MOSS_TTS_LEADING_SILENCE_SECONDS', str(DEFAULT_TTS_LEADING_SILENCE_SECONDS))
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise RuntimeError(f'MOSS_TTS_LEADING_SILENCE_SECONDS must be a number, got {raw!r}') from exc
    if not 0 <= seconds <= 2:
        raise RuntimeError(f'MOSS_TTS_LEADING_SILENCE_SECONDS must be between 0 and 2, got {seconds}')
    return seconds


def prepend_audio_silence(path: Path, seconds: float) -> None:
    if seconds <= 0:
        return
    padded = path.with_name(path.stem + '-padded.mp3')
    result = subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-f',
            'lavfi',
            '-t',
            f'{seconds:.3f}',
            '-i',
            'anullsrc=r=24000:cl=mono',
            '-i',
            str(path),
            '-filter_complex',
            '[0:a][1:a]concat=n=2:v=0:a=1[a]',
            '-map',
            '[a]',
            '-codec:a',
            'libmp3lame',
            '-b:a',
            '64k',
            str(padded),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'ffmpeg failed to prepend TTS silence: {result.stderr[-1000:]}')
    padded_size = padded.stat().st_size
    if padded_size <= 0:
        padded.unlink(missing_ok=True)
        raise RuntimeError('ffmpeg padded output is empty')
    padded.replace(path)


def synthesize_siliconflow_moss(dialogue: list[dict[str, str]], output_path: Path, api_key: str) -> bool:
    speed = moss_tts_speed()
    payload = json.dumps({
        'model': MOSS_TTS_MODEL,
        'stream': True,
        'input': moss_dialogue_input(dialogue),
        'references': moss_reference_payload(),
        'max_tokens': 4096,
        'response_format': 'mp3',
        'speed': speed,
        'gain': 0,
    }).encode()
    request = Request(
        'https://api.siliconflow.cn/v1/audio/speech',
        data=payload,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=240) as response:
            audio = response.read()
    except HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='ignore')[:500]
        print(f'MOSS-TTSD failed: HTTP {exc.code} {error_body}')
        return False
    except Exception as exc:
        print(f'MOSS-TTSD failed: {exc}')
        return False
    if len(audio) < 100_000:
        print(f'MOSS-TTSD output too small: {len(audio)} bytes')
        return False
    output_path.write_bytes(audio)
    if output_path.stat().st_size > 8 * 1024 * 1024:
        compressed = output_path.with_name(output_path.stem + '-compressed.mp3')
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', str(output_path), '-codec:a', 'libmp3lame', '-b:a', '48k', str(compressed)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and compressed.stat().st_size < output_path.stat().st_size:
            compressed.replace(output_path)
        elif compressed.exists():
            compressed.unlink()
    return output_path.exists() and output_path.stat().st_size > 100_000


def duration(path: Path) -> float:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the live daily-news collection and rendering pipeline')
    parser.add_argument('--date', default=date.today().isoformat())
    parser.add_argument('--output-dir', default='dist')
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    content_date, source_url, raw_html = fetch_latest(args.date)
    candidates = parse_articles(raw_html)
    llm_api_key = os.environ.get('OPENCODE_GO_API_KEY', '')
    if not llm_api_key:
        raise RuntimeError('OPENCODE_GO_API_KEY is required; refusing to generate a non-LLM issue')
    articles, dialogue, digest_summary, llm_metadata = call_deepseek(candidates, llm_api_key, args.date)
    html_path = output_dir / f'ai-daily-news-html-{args.date}.html'
    podcast_path = output_dir / f'ai-daily-news-podcast-{args.date}.mp3'
    data_path = output_dir / f'news-data-{args.date}.json'
    candidate_data_path = output_dir / f'candidate-news-{args.date}.json'
    podcast_script_path = output_dir / f'podcast-script-{args.date}.json'
    podcast_script_text_path = output_dir / f'podcast-script-{args.date}.txt'
    moss_input_path = output_dir / f'podcast-moss-input-{args.date}.txt'
    render_html(args.date, content_date, articles, html_path, digest_summary)
    candidate_data_path.write_text(
        json.dumps([asdict(a) for a in candidates], ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    data_path.write_text(json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2), encoding='utf-8')
    podcast_script_path.write_text(
        json.dumps(
            {
                'issue_date': args.date,
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
    podcast_script_text_path.write_text(
        '\n'.join(f'[{turn["speaker"]}] {turn["text"]}' for turn in dialogue) + '\n',
        encoding='utf-8',
    )
    moss_input_path.write_text(moss_dialogue_input(dialogue), encoding='utf-8')

    api_key = os.environ.get('SILICONFLOW_API_KEY', '')
    if not api_key:
        raise RuntimeError('SILICONFLOW_API_KEY is required; refusing to generate podcast audio')
    if not synthesize_siliconflow_moss(dialogue, podcast_path, api_key):
        raise RuntimeError('SiliconFlow MOSS-TTSD failed; refusing to publish podcast audio')
    leading_silence_seconds = tts_leading_silence_seconds()
    prepend_audio_silence(podcast_path, leading_silence_seconds)
    tts_mode = 'siliconflow-moss-reference-live'

    tmp_html = Path('/tmp') / html_path.name
    tmp_podcast = Path('/tmp') / podcast_path.name
    shutil.copy2(html_path, tmp_html)
    shutil.copy2(podcast_path, tmp_podcast)
    shutil.copy2(html_path, SKILL_DIR / 'samples' / f'{args.date}.html')

    report = {
        'mode': 'live-collection',
        'issue_date': args.date,
        'content_date': content_date,
        'source_url': source_url,
        'recipient': 'yyc54321@126.com',
        'article_count': len(articles),
        'candidate_count': len(candidates),
        'candidate_data_file': candidate_data_path.name,
        'llm': llm_metadata,
        'digest_summary': digest_summary,
        'podcast_turns': len(dialogue),
        'podcast_script_file': podcast_script_path.name,
        'podcast_script_text_file': podcast_script_text_path.name,
        'podcast_moss_input_file': moss_input_path.name,
        'tts_mode': tts_mode,
        'tts_model': MOSS_TTS_MODEL,
        'tts_speed': moss_tts_speed(),
        'tts_leading_silence_seconds': leading_silence_seconds,
        'tts_reference_files': {
            speaker: MOSS_REFERENCE_VOICES[speaker]['path'].relative_to(REPO_ROOT).as_posix()
            for speaker in ('S1', 'S2')
        },
        'html_bytes': html_path.stat().st_size,
        'podcast_bytes': podcast_path.stat().st_size,
        'podcast_duration_seconds': round(duration(podcast_path), 2),
    }
    (output_dir / f'pipeline-report-{args.date}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
