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
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from news_dedup import (
    exact_recent_url_matches,
    flatten_recent_sent,
    high_confidence_event_matches,
    recent_sent_articles,
)
from news_sources import collect_news_sources
from prompt_loader import prompt_template as prompt_template_from_file
from prompt_loader import render_prompt as render_prompt_from_file

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
NEWS_PROMPTS_FILE = SKILL_DIR / 'references' / 'news-prompts.md'
PODCAST_PROMPTS_FILE = SKILL_DIR / 'references' / 'podcast-prompts.md'
STATE_PATH = REPO_ROOT / 'state' / 'recent-news.json'
NEWS_SOURCES_FILE = SKILL_DIR / 'references' / 'news-sources.json'
SOURCE_ROOT = 'https://hex2077.dev/docs'
FORBIDDEN_URL_PARTS = ('hex2077.dev', 'aibase.com', 'hubtoday', 'wappoc_appmsgcaptcha')
SECTION_ORDER = ['🔥 今日焦点', '🚀 产品发布', '💼 行业动态', '💡 前沿研究', '🔓 开源热榜', '🤖 Agent & 工具']
SECTION_BY_NAME = {section.split(' ', 1)[-1]: section for section in SECTION_ORDER}
DEFAULT_LLM_BASE_URL = 'https://aicloud-app.lenovo.com.cn/qwen38-27b/v1'
DEFAULT_LLM_MODELS = 'qwen38-27b'
DEFAULT_VIDEO_API_BASE_URL = 'http://8.137.39.142:1234/api'
DEFAULT_VIDEO_API_TOKEN = 'lenovo-ssg-aics-tsd-tic-cd'
DEFAULT_VIDEO_API_TITLE = 'AI热点新闻'
VIDEO_API_TRANSIENT_HTTP_CODES = {408, 429, 500, 502, 503, 504}


class VideoApiJobFailedError(RuntimeError):
    """Raised when the video API accepts a job but it later fails server-side."""
DEFAULT_MAX_PUBLISHED_VIDEO_BYTES = 49 * 1024 * 1024
MOSS_TTS_MODEL = 'fnlp/MOSS-TTSD-v0.5'
DEFAULT_MOSS_TTS_SPEED = 1.02
DEFAULT_TTS_LEADING_SILENCE_SECONDS = 0.35
DEFAULT_TTS_WARMUP_TEXT = ''
MOSS_REFERENCE_VOICES = {
    'S1': {
        'path': REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_laochen_s1.wav',
        'transcript_path': REPO_ROOT / 'moss-ttsd' / 'references' / 'S1.txt',
        'text_env': 'MOSS_TTS_S1_REFERENCE_TEXT',
        'default_text': '今天我们来聊几个AI行业里的关键变化，重点看它们对产品和企业落地意味着什么。',
    },
    'S2': {
        'path': REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_anna_s2.mp3',
        'transcript_path': REPO_ROOT / 'moss-ttsd' / 'references' / 'S2.txt',
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
    """仅检测真正损坏的结构（空列表、说话人字段错误、空文本），
    不对轮数、字数、用词做硬性限制——由 LLM review 动态判断内容质量。"""
    issues: list[str] = []
    if not dialogue:
        issues.append('podcast_turns=0 dialogue is empty')
        return issues

    for index, turn in enumerate(dialogue):
        speaker = turn.get('speaker')
        text = clean_text(str(turn.get('text', '')))
        if speaker not in ('S1', 'S2'):
            issues.append(f'turn {index + 1} invalid speaker={speaker!r}')
        elif not text:
            issues.append(f'turn {index + 1} empty text')

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


def normalize_section_label(raw: object) -> str:
    label = clean_text(str(raw or ''))
    if label in SECTION_ORDER:
        return label
    plain_label = re.sub(r'^[^\w\u4e00-\u9fff]+', '', label).strip()
    return SECTION_BY_NAME.get(plain_label, label)


def parse_and_validate_selection(
    selection_result: dict,
    candidate_map: dict[str, Article],
) -> tuple[list[tuple[Article, str]], list[str]]:
    selected: list[tuple[Article, str]] = []
    seen_urls: set[str] = set()
    for item in selection_result.get('selection') or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url', '')).strip()
        section = normalize_section_label(item.get('section'))
        if url in candidate_map and url not in seen_urls and section in SECTION_ORDER:
            selected.append((candidate_map[url], section))
            seen_urls.add(url)

    issues: list[str] = []
    if not selected:
        issues.append('没有任何候选新闻通过选择结果校验')

    # 栏目顺序和焦点栏是展示偏好，不应该因为模型把栏目标签写得不完美
    # 就让整期日报失败。保留第一条为焦点，并把重复焦点降级到候选自身栏目。
    if selected:
        normalized: list[tuple[Article, str]] = []
        focus_kept = False
        for index, (article, section) in enumerate(selected):
            if section == '🔥 今日焦点':
                if focus_kept:
                    section = normalize_section_label(article.section)
                    if section == '🔥 今日焦点':
                        section = '💼 行业动态'
                else:
                    focus_kept = True
            if index == 0 and section != '🔥 今日焦点':
                section = '🔥 今日焦点'
                focus_kept = True
            normalized.append((article, section))
        selected = normalized
    return selected, issues


def fallback_selection(candidates: list[Article]) -> list[tuple[Article, str]]:
    """Keep the pipeline useful when the model returns an empty valid JSON object."""
    selected: list[tuple[Article, str]] = []
    for index, article in enumerate(candidates[:12]):
        section = normalize_section_label(article.section)
        if index == 0:
            section = '🔥 今日焦点'
        elif section == '🔥 今日焦点':
            section = '💼 行业动态'
        selected.append((article, section))
    return selected


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
    allow_date_fallback = os.environ.get('AI_DAILY_ALLOW_SOURCE_DATE_FALLBACK', 'false').lower() in {
        '1',
        'true',
        'yes',
        'on',
    }
    max_offset = 3 if allow_date_fallback else 0
    for offset in range(max_offset + 1):
        candidate = start - timedelta(days=offset)
        candidate_str = candidate.isoformat()
        url = f'{SOURCE_ROOT}/{candidate_str[:7]}/{candidate_str}/'
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 AI-Daily-News-Workflow/1.0'})
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode('utf-8', errors='replace')
            if len(raw) > 10_000:
                return candidate_str, url, raw
            errors.append(f'{candidate_str}: source page too small ({len(raw)} bytes)')
        except Exception as exc:
            errors.append(f'{candidate_str}: {type(exc).__name__}')
    if allow_date_fallback:
        raise RuntimeError('No daily source page available: ' + ', '.join(errors))
    raise RuntimeError(
        f'Daily source page for {issue_date} is not available; refusing to use an older source date. '
        'Set AI_DAILY_ALLOW_SOURCE_DATE_FALLBACK=true only for explicit backfill/debug runs. '
        + ', '.join(errors)
    )


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
    except HTTPError as exc:
        print(
            f'WARN source_text_fetch_failed url={url} '
            f'error=HTTPError status={exc.code} reason={exc.reason}',
            flush=True,
        )
        return fallback, 'fallback'
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
    if not articles:
        raise RuntimeError('No valid live articles were parsed')
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


def load_recent_titles_for_selection(exclude_date: str) -> dict[str, list[dict[str, str]]]:
    # The restored state has already been filtered to successful delivery dates.
    # Only compare against articles that actually entered those sent issues; old
    # unselected candidates are irrelevant and previously overwhelmed the prompt.
    return recent_sent_articles(STATE_PATH, exclude_date, window_days=7)


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


def normalize_bearer_token(raw: str) -> str:
    token = raw.strip()
    if token.lower().startswith('bearer '):
        return token[7:].strip()
    return token


def llm_provider_chain(
    endpoint: str,
    models: list[str],
    api_key: str,
    *,
    thinking_enabled: bool | None = None,
) -> list[dict[str, object]]:
    del thinking_enabled
    lenovo_api_key = normalize_bearer_token(api_key)
    if not lenovo_api_key:
        return []
    return [{
        'name': 'lenovo',
        'endpoint': endpoint,
        'models': models,
        'api_key': lenovo_api_key,
        'chat_template_kwargs': {'enable_thinking': False},
    }]


def selection_provider_plan(
    endpoint: str,
    models: list[str],
    api_key: str,
) -> list[str | None]:
    """Allow dedupe feedback to converge across five Lenovo-only selections."""
    del endpoint, models, api_key
    return [None] * 5


def llm_api_key() -> str:
    return (
        os.environ.get('LENOVO_LLM_API_KEY')
        or os.environ.get('AI_DAILY_LENOVO_LLM_API_KEY')
        or ''
    )


def has_any_llm_api_key() -> bool:
    return bool(llm_api_key())


def llm_stream_enabled() -> bool:
    return os.environ.get('LLM_STREAM', 'true').lower() not in {'0', 'false', 'no'}


def read_non_stream_chat_completion(response) -> tuple[str, str, dict]:
    response_data = json.loads(response.read().decode('utf-8'))
    choice = response_data['choices'][0]
    content = choice['message']['content']
    return content, str(choice.get('finish_reason') or ''), response_data.get('usage') or {}


def read_stream_chat_completion(
    response,
    *,
    task_name: str,
    provider_name: str,
    model: str,
) -> tuple[str, str, dict]:
    content_parts: list[str] = []
    finish_reason = ''
    usage: dict = {}
    started = time.perf_counter()
    first_chunk_seconds: float | None = None
    first_content_seconds: float | None = None

    while True:
        raw_line = response.readline()
        if raw_line == b'':
            break
        line = raw_line.decode('utf-8', errors='replace').strip()
        if not line or line.startswith(':'):
            continue
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if data == '[DONE]':
            break
        if first_chunk_seconds is None:
            first_chunk_seconds = time.perf_counter() - started
            print(
                f'LLM stream task={task_name} provider={provider_name} model={model} '
                f'first_chunk={first_chunk_seconds:.2f}s',
                flush=True,
            )
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(event.get('usage'), dict):
            usage = event['usage']
        choices = event.get('choices') or []
        if not choices:
            continue
        choice = choices[0]
        if choice.get('finish_reason'):
            finish_reason = str(choice.get('finish_reason'))
        delta = choice.get('delta') or {}
        piece = delta.get('content')
        if piece is None:
            message = choice.get('message') or {}
            piece = message.get('content')
        if piece:
            if first_content_seconds is None:
                first_content_seconds = time.perf_counter() - started
                print(
                    f'LLM stream task={task_name} provider={provider_name} model={model} '
                    f'first_content={first_content_seconds:.2f}s',
                    flush=True,
                )
            content_parts.append(str(piece))

    content = ''.join(content_parts)
    if not content:
        raise RuntimeError(f'empty streaming response: finish_reason={finish_reason or "unknown"}')
    return content, finish_reason, usage


def read_chat_completion_response(
    response,
    *,
    task_name: str,
    provider_name: str,
    model: str,
    stream: bool,
) -> tuple[str, str, dict]:
    if stream:
        return read_stream_chat_completion(
            response,
            task_name=task_name,
            provider_name=provider_name,
            model=model,
        )
    return read_non_stream_chat_completion(response)


def request_deepseek_json(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    thinking_enabled: bool | None = None,
    task_name: str = 'unknown',
    provider_filter: str | None = None,
) -> tuple[dict, dict, str]:
    if not models:
        raise RuntimeError('LLM API model list is empty')
    try:
        request_timeout = max(30, int(os.environ.get('OPENCODE_GO_TIMEOUT_SECONDS', '600')))
    except ValueError:
        request_timeout = 600
    model_errors: list[str] = []
    providers = llm_provider_chain(endpoint, models, api_key, thinking_enabled=thinking_enabled)
    if provider_filter:
        providers = [
            provider
            for provider in providers
            if str(provider.get('name') or '') == provider_filter
        ]
        if not providers:
            raise RuntimeError(f'LLM provider unavailable for task={task_name}: {provider_filter}')
    for provider_index, provider in enumerate(providers):
        provider_name = str(provider['name'])
        provider_endpoint = str(provider['endpoint'])
        provider_api_key = str(provider['api_key'])
        provider_models = list(provider['models'])  # type: ignore[arg-type]
        for model_index, model in enumerate(provider_models):
            print(
                f'LLM API task={task_name} trying provider={provider_name} '
                f'model {model_index + 1}/{len(provider_models)}: {model}',
                flush=True,
            )
            try:
                max_tokens = max(1, int(os.environ.get('OPENCODE_GO_MAX_TOKENS', '16384')))
            except ValueError:
                max_tokens = 16384
            payload_body = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.3,
                'top_p': 0.95,
                'max_tokens': max_tokens,
                'stream': llm_stream_enabled(),
            }
            chat_template_kwargs = provider.get('chat_template_kwargs')
            if chat_template_kwargs:
                payload_body['chat_template_kwargs'] = chat_template_kwargs
            payload = json.dumps(payload_body).encode('utf-8')
            last_error = ''
            for attempt in range(1, 4):
                request = Request(
                    f'{provider_endpoint}/chat/completions',
                    data=payload,
                    headers={
                        'Authorization': f'Bearer {provider_api_key}',
                        'Content-Type': 'application/json',
                        'Accept': 'text/event-stream' if payload_body['stream'] else 'application/json',
                        'User-Agent': 'ai-daily-news-workflow/1.0',
                    },
                    method='POST',
                )
                try:
                    with urlopen(request, timeout=request_timeout) as response:
                        content, finish_reason, usage = read_chat_completion_response(
                            response,
                            task_name=task_name,
                            provider_name=provider_name,
                            model=str(model),
                            stream=bool(payload_body['stream']),
                        )
                    if finish_reason and finish_reason != 'stop':
                        raise RuntimeError(f'incomplete response: finish_reason={finish_reason}')
                    try:
                        result = extract_json_object(content)
                    except (json.JSONDecodeError, RuntimeError) as exc:
                        raise RuntimeError(f'invalid JSON response: {exc}') from exc
                    return result, usage, f'{provider_name}:{model}'
                except HTTPError as exc:
                    error_body = exc.read().decode('utf-8', errors='replace')[:1000]
                    last_error = f'HTTP {exc.code}: {error_body}'
                    retryable = exc.code in (429, 500, 502, 503, 504)
                    if not retryable:
                        break
                    if exc.code == 429 and model_index < len(provider_models) - 1:
                        print(
                            f'LLM API provider={provider_name} model={model} HTTP 429 rate limited; '
                            f'task={task_name} switching model instead of waiting',
                            flush=True,
                        )
                        break
                    if attempt < 3:
                        retry_after = exc.headers.get('Retry-After')
                        retry_after_delay = int(retry_after) if retry_after and retry_after.isdigit() else 20 * attempt
                        try:
                            max_delay = max(1, int(os.environ.get('OPENCODE_GO_MAX_RETRY_DELAY', '60')))
                        except ValueError:
                            max_delay = 60
                        delay = min(retry_after_delay, max_delay)
                        print(
                            f'LLM API provider={provider_name} model={model} transient HTTP {exc.code}; '
                            f'task={task_name} retrying in {delay}s ({attempt}/3)',
                            flush=True,
                        )
                        time.sleep(delay)
                except (TimeoutError, URLError, OSError) as exc:
                    last_error = f'network error: {type(exc).__name__}: {exc}'
                    if model_index < len(provider_models) - 1 or provider_index < len(providers) - 1:
                        print(
                            f'LLM API provider={provider_name} model={model} {last_error}; '
                            f'task={task_name} switching model instead of waiting',
                            flush=True,
                        )
                        break
                    if attempt < 3:
                        delay = 10 * attempt
                        print(
                            f'LLM API provider={provider_name} model={model} {last_error}; '
                            f'task={task_name} retrying in {delay}s ({attempt}/3)',
                            flush=True,
                        )
                        time.sleep(delay)
                except RuntimeError as exc:
                    last_error = str(exc)
                    if attempt < 3:
                        delay = 8 * attempt
                        print(
                            f'LLM API provider={provider_name} model={model} {exc}; '
                            f'task={task_name} regenerating in {delay}s ({attempt}/3)',
                            flush=True,
                        )
                        time.sleep(delay)
            model_errors.append(f'{provider_name}:{model}: {last_error or "no valid response"}')
            if model_index < len(provider_models) - 1:
                print(
                    f'LLM API switching model {provider_name}:{model} -> '
                    f'{provider_name}:{provider_models[model_index + 1]} task={task_name}',
                    flush=True,
                )
        if provider_index < len(providers) - 1:
            print(
                f'LLM API provider {provider_name} exhausted; '
                f'switching to {providers[provider_index + 1]["name"]} task={task_name}',
                flush=True,
            )
    raise RuntimeError('LLM API model chain exhausted: ' + ' | '.join(model_errors))


def llm_config() -> tuple[str, list[str]]:
    endpoint = os.environ.get('LENOVO_LLM_BASE_URL', DEFAULT_LLM_BASE_URL).rstrip('/')
    return endpoint, [DEFAULT_LLM_MODELS]


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
        task_name='digest_summary',
    )
    summary = clean_text(str(result.get('summary', '')))
    if not summary:
        summary = '今天的AI动态集中在模型能力、产品落地与开源生态的持续演进，企业应用和开发者工具仍是主要竞争焦点。'
    return summary, usage, model


def review_cross_day_duplicates(
    *,
    endpoint: str,
    models: list[str],
    api_key: str,
    selected: list[tuple[Article, str]],
    recent_sent: dict[str, list[dict[str, str]]],
    attempt: int,
    provider_filter: str | None = None,
) -> tuple[list[dict[str, str]], dict, str]:
    current_payload = [
        {
            'title': source.title,
            'summary': source.summary,
            'url': source.url,
            'section': section,
        }
        for source, section in selected
    ]
    recent_payload = flatten_recent_sent(recent_sent)
    prompt = render_prompt_from_file(
        NEWS_PROMPTS_FILE,
        'cross_day_dedupe_user',
        current_selection_json=json.dumps(current_payload, ensure_ascii=False),
        recent_sent_json=json.dumps(recent_payload, ensure_ascii=False),
    )
    current_urls = {item['url'] for item in current_payload}
    previous_urls = {item['url'] for item in recent_payload}
    system_prompt = prompt_template_from_file(NEWS_PROMPTS_FILE, 'cross_day_dedupe_system')

    usage: dict = {}
    model = ''
    for review_attempt in range(1, 3):
        try:
            result, usage, model = request_deepseek_json(
                endpoint=endpoint,
                models=models,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=prompt,
                task_name=f'cross_day_dedupe_review_{attempt}_{review_attempt}',
                thinking_enabled=False,
                provider_filter=provider_filter,
            )
        except Exception as exc:
            if review_attempt < 2:
                print(
                    'WARN cross_day_dedupe_error_retry '
                    f'attempt={attempt} review_attempt={review_attempt} error={exc}',
                    flush=True,
                )
                continue
            print(
                'WARN cross_day_dedupe_skipped '
                f'attempt={attempt} error={exc}',
                flush=True,
            )
            return [], usage, model
        raw_duplicates = result.get('duplicates')
        if not isinstance(raw_duplicates, list):
            invalid_items: list = [raw_duplicates]
            duplicates = []
        else:
            duplicates = []
            invalid_items = []
            seen_current: set[str] = set()
            for item in raw_duplicates:
                if not isinstance(item, dict):
                    invalid_items.append(item)
                    continue
                current_url = str(item.get('current_url', '')).strip()
                previous_url = str(item.get('previous_url', '')).strip()
                reason = clean_text(str(item.get('reason', '')))
                if current_url not in current_urls or previous_url not in previous_urls or not reason:
                    invalid_items.append(item)
                    continue
                if current_url in seen_current:
                    continue
                seen_current.add(current_url)
                duplicates.append({
                    'current_url': current_url,
                    'previous_url': previous_url,
                    'reason': reason,
                })
        if not invalid_items:
            return duplicates, usage, model
        if review_attempt < 2:
            print(
                'WARN cross_day_dedupe_invalid_retry '
                f'attempt={attempt} review_attempt={review_attempt} '
                f'invalid={json.dumps(invalid_items, ensure_ascii=False)}',
                flush=True,
            )
            continue
        print(
            'WARN cross_day_dedupe_invalid_dropped '
            f'attempt={attempt} kept={len(duplicates)} '
            f'invalid={json.dumps(invalid_items, ensure_ascii=False)}',
            flush=True,
        )
    return duplicates, usage, model


def call_deepseek(
    candidate_articles: list[Article],
    api_key: str,
    issue_date: str,
) -> tuple[list[Article], list[dict[str, str]], str, dict]:
    endpoint, models = llm_config()
    system_prompt = prompt_template_from_file(NEWS_PROMPTS_FILE, 'editorial_system')
    recent_sent = load_recent_titles_for_selection(issue_date)
    exact_matches = exact_recent_url_matches(
        [item.url for item in candidate_articles],
        recent_sent,
    )
    event_matches = high_confidence_event_matches(
        [
            {'title': item.title, 'summary': item.summary, 'url': item.url}
            for item in candidate_articles
        ],
        recent_sent,
    )
    blocked_urls = set(exact_matches) | set(event_matches)
    selection_calls: list[dict] = []
    dedupe_reviews: list[dict] = []
    selected: list[tuple[Article, str]] = []
    selection_usage: dict = {}
    selection_model = ''

    provider_plan = selection_provider_plan(endpoint, models, api_key)
    for selection_attempt, provider_filter in enumerate(provider_plan, start=1):
        available_articles = [
            item for item in candidate_articles if item.url not in blocked_urls
        ]
        if not available_articles:
            raise RuntimeError(
                'Cross-day dedupe left no usable candidates: '
                f'{len(blocked_urls)} blocked'
            )
        candidates = [
            {
                'title': item.title,
                'source_summary': item.summary,
                'url': item.url,
                'suggested_section': item.section,
            }
            for item in available_articles
        ]
        base_selection_prompt = render_prompt_from_file(
            NEWS_PROMPTS_FILE,
            'selection_user',
            section_order_json=json.dumps(SECTION_ORDER, ensure_ascii=False),
            recent_titles_json=json.dumps(recent_sent, ensure_ascii=False),
            candidates_json=json.dumps(candidates, ensure_ascii=False),
        )
        candidate_map = {item.url: item for item in available_articles}
        selection_result: dict = {}
        validation_issues: list[str] = []
        for validation_attempt in range(1, 4):
            selection_prompt = base_selection_prompt
            if validation_issues:
                selection_prompt += (
                    '\n\n上一份输出未通过格式校验，请根据诊断重新选择。不得忽略诊断：\n'
                    + json.dumps(validation_issues, ensure_ascii=False)
                    + '\n上一份输出：\n'
                    + json.dumps(selection_result, ensure_ascii=False)
                )
            task_name = f'selection_{selection_attempt}'
            if validation_attempt > 1:
                task_name += f'_retry_{validation_attempt - 1}'
            selection_result, selection_usage, selection_model = request_deepseek_json(
                endpoint=endpoint,
                models=models,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=selection_prompt,
                task_name=task_name,
                provider_filter=provider_filter,
            )
            selected, validation_issues = parse_and_validate_selection(selection_result, candidate_map)
            selection_calls.append({
                'attempt': selection_attempt,
                'validation_attempt': validation_attempt,
                'model': selection_model,
                'usage': selection_usage,
                'candidate_count': len(available_articles),
                'target_count': min(12, len(available_articles)),
                'validation_issues': validation_issues,
            })
            if not validation_issues:
                break
            if validation_attempt < 3:
                print(
                    'WARN selection_validation_retry '
                    f'attempt={selection_attempt} validation_attempt={validation_attempt} '
                    f'issues={json.dumps(validation_issues, ensure_ascii=False)}',
                    flush=True,
                )
        else:
            if not selected:
                selected = fallback_selection(available_articles)
                if selected:
                    print(
                        'WARN selection_fallback_used '
                        f'candidate_count={len(available_articles)} '
                        'reason=model returned no usable selection',
                        flush=True,
                    )
            if not selected:
                raise RuntimeError(
                    'LLM selection produced no usable news after 3 retries: '
                    + '; '.join(validation_issues)
                )
            print(
                'WARN selection_validation_degraded '
                f'issues={json.dumps(validation_issues, ensure_ascii=False)}',
                flush=True,
            )

        if len(selected) < 12:
            print(
                'WARN selection_below_target '
                f'selected={len(selected)} target=12 available={len(available_articles)}',
                flush=True,
            )

        duplicates: list[dict[str, str]] = []
        review_usage: dict = {}
        review_model = ''
        if recent_sent:
            duplicates, review_usage, review_model = review_cross_day_duplicates(
                endpoint=endpoint,
                models=models,
                api_key=api_key,
                selected=selected,
                recent_sent=recent_sent,
                attempt=selection_attempt,
                provider_filter=provider_filter,
            )
        dedupe_reviews.append({
            'attempt': selection_attempt,
            'model': review_model or None,
            'usage': review_usage,
            'duplicates': duplicates,
        })
        if not duplicates:
            break
        newly_blocked = {item['current_url'] for item in duplicates}
        blocked_urls.update(newly_blocked)
        print(
            'WARN cross_day_duplicates_detected '
            f'attempt={selection_attempt} blocked={json.dumps(sorted(newly_blocked), ensure_ascii=False)}',
            flush=True,
        )
    else:
        raise RuntimeError(
            f'Cross-day dedupe review failed after {len(provider_plan)} Lenovo selection attempts'
        )

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
            task_name=f'editorial_batch_{batch_start // 4 + 1}',
        )
        editorial_calls.append({'model': batch_model, 'usage': batch_usage})
        generated_items = batch_result.get('articles', [])
        if not isinstance(generated_items, list):
            generated_items = []
        if len(generated_items) != len(batch):
            print(
                'WARN editorial_batch_count_degraded '
                f'returned={len(generated_items)} expected={len(batch)}; '
                'missing items will use source fallback',
                flush=True,
            )
        for index, (source, section) in enumerate(batch):
            item = generated_items[index] if index < len(generated_items) else {}
            if not isinstance(item, dict):
                item = {}
            body = clean_text(str(item.get('body', '')))
            if not body:
                body = clean_text(source.source_text or source.summary or source.title)
            if len(body) < 80:
                body = clean_text(f'{body} {source.summary}')
            title = clean_text(str(item.get('title', ''))) or source.title
            review = clean_text(str(item.get('review', ''))) or '基于来源内容整理，重点关注其实际影响与落地限制。'
            article = Article(
                title=title,
                summary=body,
                url=source.url,
                section=section,
                review=review,
            )
            if article.title and article.summary and article.review:
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
        'calls': (
            len(selection_calls)
            + sum(1 for item in dedupe_reviews if item.get('model'))
            + 1
            + len(editorial_calls)
            + int(podcast_metadata.get('calls', 1))
        ),
        'call_details': {
            'selection': {
                'model': selection_model,
                'usage': selection_usage,
                'selected_count': len(selected),
                'target_count': min(12, len(candidate_articles)),
                'degraded': len(selected) < 12,
            },
            'selection_attempts': selection_calls,
            'cross_day_dedupe': {
                'window_days': 7,
                'recent_sent_count': len(flatten_recent_sent(recent_sent)),
                'exact_url_blocks': [
                    {
                        'current_url': current_url,
                        'previous_url': previous.get('url', ''),
                        'previous_date': previous.get('date', ''),
                    }
                    for current_url, previous in exact_matches.items()
                ],
                'high_confidence_event_blocks': [
                    {
                        'current_url': current_url,
                        'previous_url': match['previous'].get('url', ''),
                        'previous_date': match['previous'].get('date', ''),
                        'actions': match['actions'],
                        'entities': match['entities'],
                    }
                    for current_url, match in event_matches.items()
                ],
                'reviews': dedupe_reviews,
                'final_pass': bool(dedupe_reviews and not dedupe_reviews[-1]['duplicates'])
                if recent_sent
                else True,
            },
            'editorial_batches': editorial_calls,
            'digest_summary': {'model': digest_model, 'usage': digest_usage},
            'podcast': podcast_details.get('podcast'),
            'podcast_review': podcast_details.get('podcast_review'),
            'podcast_attempts': podcast_details.get('podcast_attempts'),
            'podcast_harness': podcast_metadata.get('harness'),
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
    attempt: int = 1,
    provider_filter: str | None = None,
) -> tuple[list[dict[str, str]], dict, str]:
    podcast_prompt = build_podcast_prompt(articles, repair_instruction)
    podcast_result, podcast_usage, podcast_model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt=prompt_template('podcast_generation_system'),
        user_prompt=podcast_prompt,
        task_name=f'podcast_generation_attempt_{attempt}',
        provider_filter=provider_filter,
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
    attempt: int = 1,
    provider_filter: str | None = None,
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
        task_name=f'podcast_review_attempt_{attempt}',
        provider_filter=provider_filter,
    )
    issues = review.get('issues')
    if not isinstance(issues, list):
        issues = [str(issues)] if issues else []
    return {
        'pass': review.get('pass') is True,
        'issues': [str(item) for item in issues],
        'repair_instruction': str(review.get('repair_instruction') or '').strip(),
    }, usage, model


def build_cumulative_repair_instruction(trajectory: list[dict]) -> str:
    """把失败原稿和历次 Harness 诊断交给下一轮做定向修复。"""
    if not trajectory:
        return ''
    lines = [
        f'这是第 {len(trajectory) + 1} 次生成，任务是修订上一版，不是脱离诊断重新创作。',
        '以下是历次 Harness 的完整诊断；本次必须逐项关闭仍然存在的问题：',
    ]
    for record in trajectory:
        parts: list[str] = []
        if record.get('structure_issues'):
            parts.append('结构损坏：' + '；'.join(record['structure_issues']))
        if record.get('review_issues'):
            parts.append('质量问题：' + '；'.join(record['review_issues']))
        if record.get('repair_instruction'):
            parts.append('Harness修复指令：' + str(record['repair_instruction']))
        detail = '；'.join(parts) if parts else '（未记录具体问题）'
        lines.append(f'- 第{record["attempt"]}次：{detail}')

    latest = trajectory[-1]
    lines.extend([
        '上一版完整对话如下。请直接以它为修订底稿：',
        json.dumps(latest.get('dialogue') or [], ensure_ascii=False),
        '本轮输出前请在内部逐项自检（不要输出自检过程）：',
        '1. 总轮次固定为20轮，S1/S2严格交替；',
        '2. S1首句自然引出当天主线，不使用问候或寒暄，也不要直接抛生硬的宏大结论；',
        '3. 只重点展开5条最重要新闻；删除复述和同义重复，每轮都要带来追问、解释、分歧、判断或新角度；',
        '4. 每轮尽量35-95字，只使用日报已有事实；',
        '5. 对照上面的每条Harness诊断确认已经修复后，再输出JSON。',
    ])
    return '\n'.join(lines)


def _podcast_metadata(
    models: list[str],
    endpoint: str,
    attempts: list[dict],
    best: dict,
    harness: dict,
    *,
    provider_filter: str | None = None,
) -> dict:
    return {
        'provider': 'lenovo',
        'provider_filter': provider_filter or 'default',
        'model_chain': models,
        'endpoint': endpoint,
        'calls': len(attempts) * 2,
        'call_details': {
            'podcast': {'model': best['podcast_model'], 'usage': best['podcast_usage']},
            'podcast_review': {'model': best['review_model'], 'usage': best['review_usage']},
            'podcast_attempts': attempts,
        },
        'harness': harness,
    }


def _generate_podcast_dialogue_loop(
    articles: list[Article],
    api_key: str,
    *,
    provider_filter: str | None = None,
) -> tuple[list[dict[str, str]], dict]:
    """
    生成 & 审核播客对话的 Deep Agent Loop 实现。

    Loop 理念（区别于机械重试）：
      - 生成（Deep Agent）→ LLM Harness 终审 → 不达标则把【完整历史轨迹】丢回 agent 继续优化
      - agent 带记忆地迭代：每轮都能看到自己历次被指出的问题，而非孤立重来
      - 始终保留【历史最优】的一版（而不是最后一版）
      - 预算上限只是护栏；到顶或连续无改善（停滞）才收敛，收敛时返回历史最优并明确标注未通过
      - 真正损坏（空对话/说话人字段错）视为不通过，必须修；内容质量交给 LLM Harness 判断
    """
    endpoint, models = llm_config()
    max_attempts = 5
    attempts: list[dict] = []
    trajectory: list[dict] = []
    best: dict | None = None
    prev_score: int | None = None
    stall = 0

    def score_of(structure_issues: list[str], review: dict) -> int:
        # 结构损坏权重远高于内容问题，确保"真损坏"优先被修掉
        return len(structure_issues) * 100 + len(review.get('issues') or [])

    for attempt in range(1, max_attempts + 1):
        repair_instruction = build_cumulative_repair_instruction(trajectory)
        dialogue, podcast_usage, podcast_model = generate_podcast_dialogue_once(
            endpoint=endpoint,
            models=models,
            api_key=api_key,
            articles=articles,
            repair_instruction=repair_instruction,
            attempt=attempt,
            provider_filter=provider_filter,
        )
        structure_issues = validate_podcast_dialogue(dialogue)
        review, review_usage, review_model = review_podcast_dialogue(
            endpoint=endpoint,
            models=models,
            api_key=api_key,
            articles=articles,
            dialogue=dialogue,
            structure_issues=structure_issues,
            attempt=attempt,
            provider_filter=provider_filter,
        )

        attempts.append({
            'attempt': attempt,
            'generation': {'model': podcast_model, 'usage': podcast_usage},
            'structure_issues': structure_issues,
            'review': review,
            'review_model': review_model,
            'review_usage': review_usage,
        })

        score = score_of(structure_issues, review)
        candidate = {
            'score': score,
            'attempt': attempt,
            'dialogue': dialogue,
            'review': review,
            'structure_issues': structure_issues,
            'podcast_model': podcast_model,
            'podcast_usage': podcast_usage,
            'review_model': review_model,
            'review_usage': review_usage,
        }
        # 同分时优先保留带着更多 Harness 反馈修订过的较新版本。
        if best is None or score <= best['score']:
            best = candidate

        # 通过门禁：LLM Harness 认可，且没有真正的结构损坏
        review_pass = review.get('pass') is True and not structure_issues
        if review_pass:
            harness = {
                'attempts': attempt,
                'best_attempt': attempt,
                'final_pass': True,
                'final_issues': review.get('issues') or [],
                'structure_issues': structure_issues,
                'loop_exhausted': False,
                'converged': False,
            }
            return dialogue, _podcast_metadata(
                models,
                endpoint,
                attempts,
                candidate,
                harness,
                provider_filter=provider_filter,
            )

        # 把本轮问题并入累积轨迹，供下一轮 agent 带记忆优化
        trajectory.append({
            'attempt': attempt,
            'dialogue': dialogue,
            'structure_issues': structure_issues,
            'review_issues': review.get('issues') or [],
            'repair_instruction': review.get('repair_instruction') or '',
        })

        # 停滞检测：连续两轮没有任何改善，说明模型卡住，提前收敛到历史最优
        if prev_score is not None and score >= prev_score:
            stall += 1
        else:
            stall = 0
        prev_score = score
        if stall >= 2:
            print(
                f'warning: podcast loop converged at attempt {attempt} without pass '
                f'(no improvement in {stall} rounds); returning best attempt #{best["attempt"]}',
                flush=True,
            )
            break

    # 预算耗尽或停滞收敛：返回历史最优（而非最后一次），并明确标注未通过
    assert best is not None
    harness = {
        'attempts': len(attempts),
        'best_attempt': best['attempt'],
        'final_pass': False,
        'final_issues': best['review'].get('issues') or [],
        'structure_issues': best['structure_issues'],
        'loop_exhausted': True,
        'converged': stall >= 2,
    }
    print(
        f'warning: podcast dialogue loop did not pass after {len(attempts)} attempts; '
        f'returning best attempt #{best["attempt"]} (score={best["score"]}) for final failure decision',
        flush=True,
    )
    return best['dialogue'], _podcast_metadata(
        models,
        endpoint,
        attempts,
        best,
        harness,
        provider_filter=provider_filter,
    )


def podcast_harness_passed(metadata: dict) -> bool:
    return bool((metadata.get('harness') or {}).get('final_pass') is True)


def podcast_advisory_acceptance_issues(dialogue: list[dict[str, str]]) -> list[str]:
    """Return objective blockers for using the best draft after Harness exhaustion."""
    # 轮数、单轮字数和交替方式交给 Harness 做质量判断。这里仅阻断
    # 语音合成无法处理的结构损坏，避免“最佳草稿”被二次机械门禁拦截。
    return validate_podcast_dialogue(dialogue)


def podcast_failure_summary(metadata: dict) -> str:
    harness = metadata.get('harness') or {}
    issues = harness.get('final_issues') or []
    structure_issues = harness.get('structure_issues') or []
    parts = [
        f'provider_filter={metadata.get("provider_filter") or "default"}',
        f'attempts={harness.get("attempts")}',
        f'best_attempt={harness.get("best_attempt")}',
    ]
    if structure_issues:
        parts.append('structure_issues=' + '; '.join(str(item) for item in structure_issues[:3]))
    if issues:
        parts.append('issues=' + '; '.join(str(item) for item in issues[:3]))
    return ' | '.join(parts)


def generate_podcast_dialogue(articles: list[Article], api_key: str) -> tuple[list[dict[str, str]], dict]:
    dialogue, metadata = _generate_podcast_dialogue_loop(articles, api_key)
    if podcast_harness_passed(metadata):
        return dialogue, metadata

    advisory_blockers = podcast_advisory_acceptance_issues(dialogue)
    if not advisory_blockers:
        harness = metadata.setdefault('harness', {})
        harness['accepted_with_warnings'] = True
        harness['advisory_issues'] = list(harness.get('final_issues') or [])
        print(
            'WARN podcast_harness_advisory_accept '
            + podcast_failure_summary(metadata),
            flush=True,
        )
        return dialogue, metadata

    raise RuntimeError(
        'podcast dialogue harness failed; refusing to call video API. '
        + podcast_failure_summary(metadata)
        + ' | objective_blockers=' + '; '.join(advisory_blockers[:3])
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
        f'<title>每日AI热点新闻（博客试运营） — {html.escape(issue_date)}</title>',
        '</head>',
        '<body style="margin:0;padding:0;font-family:\'PingFang SC\',\'Microsoft YaHei\',\'Helvetica Neue\',Arial,sans-serif;background-color:#eef1f5;">',
        '<table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;">',
        '<tr><td align="center">',
        '<table width="700" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border:1px solid #c9cdd4;border-radius:10px;overflow:hidden;">',
        '<tr><td style="background-color:#3b82f6;padding:28px 30px;text-align:center;border-bottom:4px solid #1d4ed8;">',
        '<h1 style="color:#ffffff;margin:0;font-size:22px;font-weight:700;letter-spacing:0.5px;">📰 每日AI热点新闻（博客试运营）</h1>',
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
        f'每日AI热点新闻 · {html.escape(issue_date)}<br>',
        f'内容采集日期：{html.escape(content_date)}<br>',
        '联系我们：penglei4@lenovo.com',
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


def moss_reference_payload(speakers: tuple[str, ...] = ('S1', 'S2')) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for speaker in speakers:
        config = MOSS_REFERENCE_VOICES[speaker]
        reference_text = os.environ.get(config['text_env'])
        transcript_path = config.get('transcript_path')
        if not reference_text and isinstance(transcript_path, Path) and transcript_path.exists():
            reference_text = transcript_path.read_text(encoding='utf-8').strip()
        if not reference_text:
            raise RuntimeError(
                f'{config["text_env"]} or {config["transcript_path"].relative_to(REPO_ROOT).as_posix()} '
                f'is required. MOSS-TTSD needs the exact transcript of '
                f'{config["path"].relative_to(REPO_ROOT).as_posix()}; refusing to use mismatched fallback text.'
            )
        references.append({
            'audio': encode_reference_audio(config['path']),
            'text': reference_text,
        })
    return references


def moss_dialogue_input(dialogue: list[dict[str, str]]) -> str:
    return ''.join(f'[{turn["speaker"]}]{turn["text"]}' for turn in dialogue)


def build_multipart_form(
    fields: dict[str, str],
    files: dict[str, Path],
) -> tuple[str, bytes]:
    boundary = f'----ai-daily-news-{uuid.uuid4().hex}'
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\n'.encode('ascii'))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('utf-8'))
        chunks.append(str(value).encode('utf-8'))
        chunks.append(b'\r\n')
    for name, path in files.items():
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        chunks.append(f'--{boundary}\r\n'.encode('ascii'))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                f'Content-Type: {content_type}\r\n\r\n'
            ).encode('utf-8')
        )
        chunks.append(path.read_bytes())
        chunks.append(b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode('ascii'))
    return boundary, b''.join(chunks)


def video_api_base_url() -> str:
    return os.environ.get('AI_DAILY_VIDEO_API_BASE_URL', DEFAULT_VIDEO_API_BASE_URL).rstrip('/')


def video_api_base_url_candidates() -> list[str]:
    configured = video_api_base_url()
    candidates = [configured]
    if configured.startswith('https://'):
        candidates.append('http://' + configured[len('https://'):])
    deduped: list[str] = []
    for item in candidates:
        if item not in deduped:
            deduped.append(item)
    return deduped


def is_tls_protocol_error(exc: Exception) -> bool:
    text = str(getattr(exc, 'reason', exc)).lower()
    return 'wrong_version_number' in text or 'wrong version number' in text


def video_api_error_body(exc: HTTPError) -> str:
    try:
        return exc.read().decode('utf-8', errors='replace')[:500]
    except Exception:
        return ''


def video_api_retry_delay(attempt: int, exc: HTTPError | None = None) -> float:
    max_delay = float(os.environ.get('AI_DAILY_VIDEO_API_MAX_RETRY_SECONDS', '120'))
    if exc is not None:
        retry_after = exc.headers.get('Retry-After')
        if retry_after:
            try:
                return min(max_delay, max(1.0, float(retry_after)))
            except ValueError:
                pass
    base_delay = float(os.environ.get('AI_DAILY_VIDEO_API_RETRY_SECONDS', '20'))
    return min(max_delay, base_delay * (2 ** max(0, attempt - 1)))


def video_api_token() -> str:
    return (
        os.environ.get('AI_DAILY_VIDEO_API_TOKEN')
        or os.environ.get('VIDEO_API_TOKEN')
        or os.environ.get('YOUR_TOKEN')
        or DEFAULT_VIDEO_API_TOKEN
    ).strip()


def video_api_day(issue_date: str) -> str:
    return os.environ.get('AI_DAILY_VIDEO_API_DAY') or f'{issue_date}-{datetime.now().strftime("%H%M")}'


def video_api_json(url: str, token: str, *, timeout: float = 60) -> dict:
    request = Request(
        url,
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'ai-daily-news-workflow/1.0'},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def submit_video_api_job(script_path: Path, issue_date: str, token: str, base_url: str) -> tuple[str, dict]:
    if not script_path.is_file():
        raise RuntimeError(f'video API script file missing: {script_path}')
    title = os.environ.get('AI_DAILY_VIDEO_API_TITLE', DEFAULT_VIDEO_API_TITLE)
    day = video_api_day(issue_date)
    print(
        'VIDEO_API submit '
        f'base_url={base_url.rstrip("/")} '
        f'script_file={script_path.name} '
        f'script_bytes={script_path.stat().st_size} '
        f'day={day} title={title}',
        flush=True,
    )
    boundary, body = build_multipart_form(
        fields={'day': day, 'title': title},
        files={'script_file': script_path},
    )
    request = Request(
        f'{base_url.rstrip("/")}/videos/generate',
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(body)),
            'User-Agent': 'ai-daily-news-workflow/1.0',
        },
        method='POST',
    )
    with urlopen(request, timeout=float(os.environ.get('AI_DAILY_VIDEO_API_SUBMIT_TIMEOUT_SECONDS', '120'))) as response:
        payload = json.loads(response.read().decode('utf-8'))
    job_id = str(payload.get('job_id') or '').strip()
    if not job_id:
        raise RuntimeError(f'video API response missing job_id: {payload}')
    print(f'VIDEO_API accepted job_id={job_id}', flush=True)
    return job_id, payload


def wait_video_api_job(job_id: str, token: str, base_url: str) -> dict:
    timeout_seconds = float(os.environ.get('AI_DAILY_VIDEO_API_TIMEOUT_SECONDS', '1800'))
    poll_seconds = float(os.environ.get('AI_DAILY_VIDEO_API_POLL_SECONDS', '60'))
    deadline = time.time() + timeout_seconds
    last_payload: dict = {}
    while time.time() < deadline:
        try:
            payload = video_api_json(f'{base_url.rstrip("/")}/jobs/{job_id}', token, timeout=60)
        except HTTPError as exc:
            body = video_api_error_body(exc)
            if exc.code in VIDEO_API_TRANSIENT_HTTP_CODES:
                print(
                    f'WARN video_api_poll_transient job={job_id} status={exc.code}; '
                    f'retry_in={poll_seconds}s body={body[:200]}',
                    flush=True,
                )
                time.sleep(poll_seconds)
                continue
            raise RuntimeError(f'video API poll failed: HTTP {exc.code}: {body}') from exc
        last_payload = payload
        status = str(payload.get('status') or '').strip().lower()
        print(f'VIDEO_API job={job_id} status={status}', flush=True)
        if status == 'succeeded':
            return payload
        if status == 'failed':
            raise VideoApiJobFailedError(f'video API job failed: {payload}')
        time.sleep(poll_seconds)
    raise RuntimeError(f'video API job timed out after {timeout_seconds}s: {last_payload}')


def download_video_api_zip(job_id: str, token: str, zip_path: Path, base_url: str) -> None:
    attempts = max(1, int(os.environ.get('AI_DAILY_VIDEO_API_DOWNLOAD_ATTEMPTS', '3')))
    for attempt in range(1, attempts + 1):
        request = Request(
            f'{base_url.rstrip("/")}/jobs/{job_id}/download',
            headers={'Authorization': f'Bearer {token}', 'User-Agent': 'ai-daily-news-workflow/1.0'},
        )
        try:
            with urlopen(request, timeout=float(os.environ.get('AI_DAILY_VIDEO_API_DOWNLOAD_TIMEOUT_SECONDS', '300'))) as response:
                zip_path.write_bytes(response.read())
            break
        except HTTPError as exc:
            body = video_api_error_body(exc)
            if exc.code in VIDEO_API_TRANSIENT_HTTP_CODES and attempt < attempts:
                delay = video_api_retry_delay(attempt, exc)
                print(
                    f'WARN video_api_download_transient job={job_id} status={exc.code} '
                    f'attempt={attempt}/{attempts}; retry_in={delay:.1f}s body={body[:200]}',
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f'video API download failed: HTTP {exc.code}: {body}') from exc
    if not zip_path.exists() or zip_path.stat().st_size < 1000:
        raise RuntimeError(f'video API download is empty or too small: {zip_path}')


def extract_largest_zip_member(zip_path: Path, suffix: str, output_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(suffix)
        ]
        if not candidates:
            raise RuntimeError(f'video API zip missing *{suffix}: {zip_path}')
        selected = max(candidates, key=lambda info: info.file_size)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(selected) as src, output_path.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f'extracted media is empty: {output_path}')


def generate_video_api_media(
    script_path: Path,
    audio_path: Path,
    video_path: Path,
    voice_path: Path,
    issue_date: str,
    dialogue: list[dict[str, str]],
) -> tuple[dict, dict]:
    token = video_api_token()
    if not token:
        raise RuntimeError('AI_DAILY_VIDEO_API_TOKEN is required; refusing to generate podcast audio/video')
    job_retry_attempts = max(1, int(os.environ.get('AI_DAILY_VIDEO_API_JOB_RETRY_ATTEMPTS', '3')))
    for job_attempt in range(1, job_retry_attempts + 1):
        submit_error: Exception | None = None
        used_base_url = ''
        for candidate_base_url in video_api_base_url_candidates():
            attempts = max(1, int(os.environ.get('AI_DAILY_VIDEO_API_SUBMIT_ATTEMPTS', '6')))
            for attempt in range(1, attempts + 1):
                try:
                    job_id, submit_payload = submit_video_api_job(script_path, issue_date, token, candidate_base_url)
                    used_base_url = candidate_base_url.rstrip('/')
                    break
                except HTTPError as exc:
                    body = video_api_error_body(exc)
                    submit_error = RuntimeError(f'HTTP {exc.code}: {body}')
                    if exc.code in VIDEO_API_TRANSIENT_HTTP_CODES and attempt < attempts:
                        delay = video_api_retry_delay(attempt, exc)
                        print(
                            f'WARN video_api_submit_transient base_url={candidate_base_url} '
                            f'status={exc.code} attempt={attempt}/{attempts}; '
                            f'retry_in={delay:.1f}s body={body[:200]}',
                            flush=True,
                        )
                        time.sleep(delay)
                        continue
                    raise RuntimeError(f'video API submit failed: HTTP {exc.code}: {body}') from exc
                except URLError as exc:
                    submit_error = exc
                    if candidate_base_url.startswith('https://') and is_tls_protocol_error(exc):
                        print(
                            'WARN video_api_tls_protocol_error '
                            f'base_url={candidate_base_url}; retrying with http fallback',
                            flush=True,
                        )
                        break
                    if attempt < attempts:
                        delay = video_api_retry_delay(attempt)
                        print(
                            f'WARN video_api_submit_network base_url={candidate_base_url} '
                            f'attempt={attempt}/{attempts}; retry_in={delay:.1f}s error={exc}',
                            flush=True,
                        )
                        time.sleep(delay)
                        continue
                    raise
            if used_base_url:
                break
            if (
                isinstance(submit_error, URLError)
                and candidate_base_url.startswith('https://')
                and is_tls_protocol_error(submit_error)
            ):
                continue
            if candidate_base_url.startswith('https://') and len(video_api_base_url_candidates()) > 1:
                continue
            if submit_error is not None:
                raise RuntimeError(f'video API submit failed: {submit_error}')
        else:
            raise RuntimeError(f'video API submit failed: {submit_error}')

        try:
            final_payload = wait_video_api_job(job_id, token, used_base_url)
            break
        except VideoApiJobFailedError as exc:
            if job_attempt >= job_retry_attempts:
                raise
            delay = video_api_retry_delay(job_attempt)
            print(
                f'WARN video_api_job_failed_retry job={job_id} '
                f'attempt={job_attempt}/{job_retry_attempts}; retry_in={delay:.1f}s error={exc}',
                flush=True,
            )
            time.sleep(delay)
    zip_path = audio_path.with_name(f'video-api-result-{issue_date}.zip')
    download_video_api_zip(job_id, token, zip_path, used_base_url)
    print(f'VIDEO_API downloaded zip={zip_path.name} bytes={zip_path.stat().st_size}', flush=True)
    extract_largest_zip_member(zip_path, '.mp3', audio_path)
    extract_largest_zip_member(zip_path, '.mp4', video_path)
    compress_audio_if_large(audio_path)
    compress_video_if_large(video_path)

    total_duration = duration(audio_path)
    voice_manifest = {
        'title': DEFAULT_VIDEO_API_TITLE,
        'date': issue_date,
        'audio': audio_path.relative_to(REPO_ROOT).as_posix(),
        'video': video_path.relative_to(REPO_ROOT).as_posix(),
        'duration': round(total_duration, 2),
        'turns': estimated_voice_turns(dialogue, total_duration),
    }
    voice_path.write_text(json.dumps(voice_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return voice_manifest, {
        'provider': 'video-api',
        'base_url': used_base_url,
        'job_id': job_id,
        'submit_response': submit_payload,
        'final_response': final_payload,
        'zip_file': zip_path.name,
        'video_file': video_path.name,
    }


def voice_speaker_name(role_label: str) -> str:
    return {'S1': 'host', 'S2': 'analyst'}.get(role_label, role_label.lower())


def tts_warmup_text() -> str:
    return os.environ.get('MOSS_TTS_WARMUP_TEXT', DEFAULT_TTS_WARMUP_TEXT).strip()


def apply_tts_warmup(dialogue: list[dict[str, str]]) -> list[dict[str, str]]:
    """Prepend a fixed greeting so MOSS-TTSD cold-start degradation lands on a
    throwaway line instead of the first real sentence.

    - Idempotent: skips if the first turn already starts with the warmup text.
    - Merges into the first S1 turn when possible (keeps turn count and the
      S1/S2 alternation intact); otherwise inserts a standalone S1 turn.
    """
    warmup = tts_warmup_text()
    if not warmup or not dialogue:
        return dialogue
    first = dialogue[0]
    if first.get('text', '').startswith(warmup):
        return dialogue
    if first.get('speaker') == 'S1':
        merged = dict(first)
        merged['text'] = f'{warmup}{first.get("text", "")}'
        return [merged, *dialogue[1:]]
    return [{'speaker': 'S1', 'text': warmup}, *dialogue]


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


def compress_audio_if_large(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> None:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return
    compressed = path.with_name(path.stem + '-compressed.mp3')
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', str(path), '-codec:a', 'libmp3lame', '-b:a', '48k', str(compressed)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and compressed.exists() and compressed.stat().st_size < path.stat().st_size:
        compressed.replace(path)
    elif compressed.exists():
        compressed.unlink()


def max_published_video_bytes() -> int:
    raw = os.environ.get('AI_DAILY_MAX_PUBLISHED_VIDEO_BYTES')
    if not raw:
        return DEFAULT_MAX_PUBLISHED_VIDEO_BYTES
    try:
        return max(1_000_000, int(raw))
    except ValueError:
        return DEFAULT_MAX_PUBLISHED_VIDEO_BYTES


def compress_video_if_large(path: Path, *, max_bytes: int | None = None) -> None:
    if os.environ.get('AI_DAILY_COMPRESS_VIDEO', 'true').lower() in {'0', 'false', 'no'}:
        return
    if max_bytes is None:
        max_bytes = max_published_video_bytes()
    if not path.exists() or path.stat().st_size <= max_bytes:
        return
    original_size = path.stat().st_size
    try:
        video_duration = max(1.0, duration(path))
    except Exception as exc:
        print(f'WARN video_compress_skipped cannot probe duration: {exc}', flush=True)
        return

    try:
        audio_bps = max(16000, int(os.environ.get('AI_DAILY_VIDEO_AUDIO_BITRATE_BPS', '64000')))
    except ValueError:
        audio_bps = 64000
    target_total_bps = int(max_bytes * 8 * 0.85 / video_duration)
    target_video_bps = max(200_000, target_total_bps - audio_bps)
    target_video_kbps = max(200, target_video_bps // 1000)
    compressed = path.with_name(path.stem + '-compressed.mp4')
    print(
        f'WARN video_too_large size={original_size} max={max_bytes}; '
        f'reencoding target_video_bitrate={target_video_kbps}k',
        flush=True,
    )
    result = subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-i',
            str(path),
            '-c:v',
            'libx264',
            '-preset',
            os.environ.get('AI_DAILY_VIDEO_COMPRESS_PRESET', 'veryfast'),
            '-b:v',
            f'{target_video_kbps}k',
            '-maxrate',
            f'{target_video_kbps}k',
            '-bufsize',
            f'{target_video_kbps * 2}k',
            '-c:a',
            'aac',
            '-b:a',
            f'{audio_bps // 1000}k',
            '-movflags',
            '+faststart',
            str(compressed),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f'WARN video_compress_failed: {result.stderr[-1000:]}', flush=True)
        compressed.unlink(missing_ok=True)
        return
    if not compressed.exists() or compressed.stat().st_size <= 0:
        print('WARN video_compress_failed: empty output', flush=True)
        compressed.unlink(missing_ok=True)
        return
    compressed_size = compressed.stat().st_size
    if compressed_size < original_size:
        compressed.replace(path)
        print(f'VIDEO_COMPRESSED original={original_size} compressed={compressed_size}', flush=True)
        return
    print(f'WARN video_compress_not_smaller original={original_size} compressed={compressed_size}', flush=True)
    compressed.unlink(missing_ok=True)


def synthesize_siliconflow_moss(
    dialogue: list[dict[str, str]],
    output_path: Path,
    api_key: str,
    *,
    references: list[dict[str, str]] | None = None,
    min_bytes: int = 100_000,
    compress_if_large: bool = True,
) -> bool:
    speed = moss_tts_speed()
    payload = json.dumps({
        'model': MOSS_TTS_MODEL,
        'stream': True,
        'input': moss_dialogue_input(dialogue),
        'references': references if references is not None else moss_reference_payload(),
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
    if len(audio) < min_bytes:
        print(f'MOSS-TTSD output too small: {len(audio)} bytes')
        return False
    output_path.write_bytes(audio)
    if compress_if_large:
        compress_audio_if_large(output_path)
    return output_path.exists() and output_path.stat().st_size > min_bytes


def concat_audio_chunks(chunk_paths: list[Path], output_path: Path) -> None:
    if not chunk_paths:
        raise RuntimeError('No audio chunks to concatenate')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = output_path.with_name(output_path.stem + '-concat.txt')

    def concat_file_line(path: Path) -> str:
        escaped = path.resolve().as_posix().replace("'", r"'\''")
        return f"file '{escaped}'\n"

    concat_list.write_text(
        ''.join(concat_file_line(path) for path in chunk_paths),
        encoding='utf-8',
    )
    copy_result = subprocess.run(
        ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_list), '-c', 'copy', str(output_path)],
        capture_output=True,
        text=True,
    )
    if copy_result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return
    reencode_result = subprocess.run(
        [
            'ffmpeg',
            '-y',
            '-f',
            'concat',
            '-safe',
            '0',
            '-i',
            str(concat_list),
            '-codec:a',
            'libmp3lame',
            '-b:a',
            '64k',
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if reencode_result.returncode != 0:
        raise RuntimeError(f'ffmpeg concat failed: {reencode_result.stderr[-1000:]}')
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError('ffmpeg concat output is empty')


def estimated_voice_turns(
    dialogue: list[dict[str, str]],
    total_duration: float,
    *,
    start_offset: float = 0.0,
) -> list[dict[str, object]]:
    weights = [max(1, len(str(turn.get('text', '')).strip())) for turn in dialogue]
    total_weight = max(1, sum(weights))
    cursor = min(max(0.0, start_offset), total_duration)
    available_duration = max(0.0, total_duration - cursor)
    turns: list[dict[str, object]] = []
    for index, (turn, weight) in enumerate(zip(dialogue, weights)):
        role_label = str(turn.get('speaker', '')).strip()
        text = str(turn.get('text', '')).strip()
        if role_label not in MOSS_REFERENCE_VOICES or not text:
            raise RuntimeError(f'Invalid podcast turn for voice timeline at index={index}: {turn!r}')
        end = total_duration if index == len(dialogue) - 1 else min(
            total_duration,
            cursor + available_duration * weight / total_weight,
        )
        turns.append({
            'index': index,
            'roleLabel': role_label,
            'text': text,
            'start': round(cursor, 2),
            'end': round(end, 2),
        })
        cursor = end
    return turns


def synthesize_siliconflow_moss_single(
    dialogue: list[dict[str, str]],
    output_path: Path,
    voice_path: Path,
    issue_date: str,
    api_key: str,
    *,
    leading_silence_seconds: float = 0.0,
) -> dict:
    if not synthesize_siliconflow_moss(
        dialogue,
        output_path,
        api_key,
        references=moss_reference_payload(('S1', 'S2')),
        min_bytes=100_000,
        compress_if_large=True,
    ):
        raise RuntimeError('SiliconFlow MOSS-TTSD failed for full dialogue synthesis')
    if leading_silence_seconds > 0:
        prepend_audio_silence(output_path, leading_silence_seconds)
    total_duration = duration(output_path)
    voice_manifest = {
        'title': 'AI热点新闻',
        'date': issue_date,
        'audio': output_path.relative_to(REPO_ROOT).as_posix(),
        'duration': round(total_duration, 2),
        'turns': estimated_voice_turns(dialogue, total_duration, start_offset=leading_silence_seconds),
    }
    voice_path.write_text(json.dumps(voice_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return voice_manifest


def synthesize_siliconflow_moss_turns(
    dialogue: list[dict[str, str]],
    output_path: Path,
    voice_path: Path,
    issue_date: str,
    api_key: str,
    *,
    leading_silence_seconds: float = 0.0,
) -> dict:
    chunk_dir = output_path.parent / 'voice-chunks' / issue_date
    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunk_paths: list[Path] = []
    turns: list[dict[str, object]] = []
    cursor = leading_silence_seconds
    for index, turn in enumerate(dialogue):
        role_label = str(turn.get('speaker', '')).strip()
        text = str(turn.get('text', '')).strip()
        if role_label not in MOSS_REFERENCE_VOICES or not text:
            raise RuntimeError(f'Invalid podcast turn for voice generation at index={index}: {turn!r}')

        chunk_path = chunk_dir / f'{index:03d}-{role_label}.mp3'
        single_turn_dialogue = [{'speaker': 'S1', 'text': text}]
        references = moss_reference_payload((role_label,))
        if not synthesize_siliconflow_moss(
            single_turn_dialogue,
            chunk_path,
            api_key,
            references=references,
            min_bytes=5_000,
            compress_if_large=False,
        ):
            raise RuntimeError(f'SiliconFlow MOSS-TTSD failed for turn index={index} speaker={role_label}')

        chunk_duration = duration(chunk_path)
        start = cursor
        end = start + chunk_duration
        turns.append({
            'index': index,
            'roleLabel': role_label,
            'text': text,
            'start': round(start, 2),
            'end': round(end, 2),
        })
        cursor = end
        chunk_paths.append(chunk_path)

    concat_audio_chunks(chunk_paths, output_path)
    if leading_silence_seconds > 0:
        prepend_audio_silence(output_path, leading_silence_seconds)
    compress_audio_if_large(output_path)

    voice_manifest = {
        'title': 'AI热点新闻',
        'date': issue_date,
        'audio': output_path.relative_to(REPO_ROOT).as_posix(),
        'duration': round(duration(output_path), 2),
        'turns': turns,
    }
    voice_path.write_text(json.dumps(voice_manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return voice_manifest


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

    source_candidates, source_health = collect_news_sources(args.date, NEWS_SOURCES_FILE)
    source_health_path = output_dir / f'source-health-{args.date}.json'
    source_health_path.write_text(
        json.dumps(source_health, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(json.dumps(source_health, ensure_ascii=False, indent=2), flush=True)
    if not source_health['pipeline_can_continue']:
        raise RuntimeError(
            'News sources did not provide any usable candidates: '
            f'{source_health["candidate_count_after_dedup"]}'
        )
    if source_health['candidate_count_after_dedup'] < source_health['minimum_usable_candidates']:
        print(
            'WARN source_candidates_below_target '
            f'available={source_health["candidate_count_after_dedup"]} '
            f'target={source_health["minimum_usable_candidates"]}; continuing with available news',
            flush=True,
        )
    candidates = [
        Article(
            title=item.title,
            summary=item.summary,
            url=item.url,
            section=item.section,
        )
        for item in source_candidates
    ]
    content_date = args.date
    successful_sources = [
        item for item in source_health['sources'] if item['status'] == 'ok'
    ]
    source_url = successful_sources[0]['source_url']
    api_key = llm_api_key()
    if not api_key:
        raise RuntimeError('LENOVO_LLM_API_KEY is required; refusing to generate a non-LLM issue')
    articles, dialogue, digest_summary, llm_metadata = call_deepseek(candidates, api_key, args.date)
    html_path = output_dir / f'ai-daily-news-html-{args.date}.html'
    podcast_path = output_dir / f'ai-daily-news-podcast-{args.date}.mp3'
    video_path = output_dir / f'ai-daily-news-video-{args.date}.mp4'
    data_path = output_dir / f'news-data-{args.date}.json'
    candidate_data_path = output_dir / f'candidate-news-{args.date}.json'
    podcast_script_path = output_dir / f'podcast-script-{args.date}.json'
    podcast_script_text_path = output_dir / f'podcast-script-{args.date}.txt'
    moss_input_path = output_dir / f'podcast-moss-input-{args.date}.txt'
    voice_path = output_dir / f'voice-{args.date}.json'
    dialogue = apply_tts_warmup(dialogue)
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

    voice_manifest, video_api_metadata = generate_video_api_media(
        podcast_script_text_path,
        podcast_path,
        video_path,
        voice_path,
        args.date,
        dialogue,
    )
    tts_mode = 'video-api-audio-video'

    tmp_html = Path('/tmp') / html_path.name
    tmp_podcast = Path('/tmp') / podcast_path.name
    tmp_video = Path('/tmp') / video_path.name
    shutil.copy2(html_path, tmp_html)
    shutil.copy2(podcast_path, tmp_podcast)
    shutil.copy2(video_path, tmp_video)
    shutil.copy2(html_path, SKILL_DIR / 'samples' / f'{args.date}.html')

    report = {
        'mode': 'live-collection',
        'issue_date': args.date,
        'content_date': content_date,
        'source_url': source_url,
        'source_urls': [item['source_url'] for item in successful_sources],
        'source_health_file': source_health_path.name,
        'source_health': source_health,
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
        'voice_file': voice_path.name,
        'voice_turns': len(voice_manifest['turns']),
        'tts_mode': tts_mode,
        'tts_synthesis_mode': 'external_video_api',
        'voice_timing_source': 'estimated_text_weight',
        'tts_model': None,
        'tts_speed': None,
        'tts_leading_silence_seconds': 0,
        'tts_reference_files': None,
        'video_api': video_api_metadata,
        'html_bytes': html_path.stat().st_size,
        'podcast_bytes': podcast_path.stat().st_size,
        'video_bytes': video_path.stat().st_size,
        'podcast_duration_seconds': round(duration(podcast_path), 2),
    }
    (output_dir / f'pipeline-report-{args.date}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
