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

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
SOURCE_ROOT = 'https://hex2077.dev/docs'
FORBIDDEN_URL_PARTS = ('hex2077.dev', 'aibase.com', 'hubtoday', 'wappoc_appmsgcaptcha')
SECTION_ORDER = ['🔥 今日焦点', '🚀 产品发布', '💼 行业动态', '💡 前沿研究', '🔓 开源热榜', '🤖 Agent & 工具']
MOSS_TTS_MODEL = 'fnlp/MOSS-TTSD-v0.5'
DEFAULT_MOSS_TTS_SPEED = 1.08
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


def clean_text(text: str) -> str:
    text = re.sub(r'\(AI资讯\)', '', text, flags=re.I)
    text = text.replace('🚀', '').replace('(✧∀✧)', '').replace('⭐', '')
    return re.sub(r'\s+', ' ', text).strip()


def validate_podcast_dialogue(dialogue: list[dict[str, str]]) -> list[str]:
    issues: list[str] = []
    if not 12 <= len(dialogue) <= 18:
        issues.append(f'podcast_turns={len(dialogue)} outside 12-18')

    for index, turn in enumerate(dialogue):
        expected = 'S1' if index % 2 == 0 else 'S2'
        if turn.get('speaker') != expected:
            issues.append(f'turn {index + 1} speaker={turn.get("speaker")} expected {expected}')
            break

    texts = [turn.get('text', '') for turn in dialogue]
    if texts:
        opening_markers = ('大家好', '早上好', '中午好', '下午好', '今天', '欢迎', '开场', '又到了')
        if not any(marker in texts[0] for marker in opening_markers):
            issues.append('podcast opening missing conversational greeting/context')
        stiff_first_turns = sum(
            1
            for text in texts[:2]
            if re.match(r'^[\u4e00-\u9fa5A-Za-z0-9]+(发布|公布|推出|宣布|曝出|即将|将于|通过|采用|认为)', text)
        )
        if stiff_first_turns:
            issues.append('podcast starts directly with news facts instead of an opening')

    question_count = sum(
        1
        for text in texts
        if any(marker in text for marker in ('？', '?', '吗', '呢', '怎么', '为什么', '是不是', '意味着什么'))
    )
    if question_count < 3:
        issues.append(f'question_turns={question_count} < 3')

    connective_count = sum(
        1
        for text in texts
        if any(marker in text for marker in ('但', '不过', '所以', '换句话说', '你是说', '我担心', '问题是', '关键是', '反过来'))
    )
    if connective_count < 5:
        issues.append(f'connected_turns={connective_count} < 5')

    challenge_count = sum(
        1
        for text in texts
        if any(marker in text for marker in ('我不太同意', '不一定', '未必', '风险', '问题', '担心', '挑战', '代价'))
    )
    if challenge_count < 2:
        issues.append(f'challenge_turns={challenge_count} < 2')

    stiff_opening_count = sum(
        1
        for text in texts
        if re.match(r'^[\u4e00-\u9fa5A-Za-z0-9]+(发布|公布|推出|宣布|曝出|即将|将于|通过|采用|认为)', text)
    )
    if stiff_opening_count > max(3, len(texts) // 4):
        issues.append(f'stiff_news_openings={stiff_opening_count} too many')

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


def call_deepseek(candidate_articles: list[Article], api_key: str) -> tuple[list[Article], list[dict[str, str]], dict]:
    endpoint, models = llm_config()
    candidates = [
        {'title': item.title, 'source_summary': item.summary, 'url': item.url, 'suggested_section': item.section}
        for item in candidate_articles
    ]
    system_prompt = (
        '你是中文AI行业日报主编。只使用输入候选中的事实和URL，不得编造事实、数字、机构、'
        '模型能力或链接。输出必须是单个合法JSON对象，不要Markdown。'
    )
    selection_prompt = f'''
从以下候选中选择恰好12条最值得进入AI日报的新闻，按事件去重并分类。
只输出JSON：{{"selection":[{{"url":"候选中的原始URL","section":"栏目"}}]}}
规则：
- URL必须原样复制候选URL，不得创造或修改。
- section只能是：{json.dumps(SECTION_ORDER, ensure_ascii=False)}。
- 第一项必须是“🔥 今日焦点”，全文仅允许一个“🔥 今日焦点”。
- 尽量覆盖产品、行业、研究、开源或工具中的至少4类。

候选：
{json.dumps(candidates, ensure_ascii=False)}
'''.strip()
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

    articles: list[Article] = []
    editorial_calls: list[dict] = []
    for batch_start in range(0, len(selected), 4):
        batch = selected[batch_start:batch_start + 4]
        batch_input = [
            {
                'title': source.title,
                'source_summary': source.summary,
                'url': source.url,
                'section': section,
            }
            for source, section in batch
        ]
        batch_prompt = f'''
编辑以下4条新闻。只输出JSON：
{{"articles":[{{"title":"...","body":"...","review":"..."}}]}}
规则：
- 必须恰好输出4条并严格保持输入顺序。不要输出或改写URL、栏目。
- title简洁准确，不添加输入中没有的事实。
- body用中文写120-220字、至少4句，只能使用source_summary中的事实，不得补写泛泛背景。
- 禁止模板句和空话，例如“这项动态围绕”“值得关注的不是”“后续观察重点”“带来的连锁变化”。
- review写1-2句明确判断，基于事实，不写“值得关注”“意义重大”等空话。
- 不得提及聚合源名称。

输入：
{json.dumps(batch_input, ensure_ascii=False)}
'''.strip()
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

    dialogue, podcast_metadata = generate_podcast_dialogue(articles, api_key)
    metadata = {
        'provider': 'opencode-go',
        'model_chain': models,
        'endpoint': endpoint,
        'calls': 5,
        'call_details': {
            'selection': {'model': selection_model, 'usage': selection_usage},
            'editorial_batches': editorial_calls,
            'podcast': podcast_metadata['call_details']['podcast'],
        },
    }
    return articles, dialogue, metadata


def generate_podcast_dialogue(articles: list[Article], api_key: str) -> tuple[list[dict[str, str]], dict]:
    endpoint, models = llm_config()
    podcast_prompt = f'''
基于以下已经校验通过的日报，生成12-18轮自然双人播客对话。
角色设定：
- S1是资深AI从业者
- S2是产品与应用经理
分别贡献不同视角的分析

对话要求：
- 这必须是一段真实对话，不是两个人轮流念新闻摘要。
- 围绕最重要的5-7条新闻深入讨论，有反应、补充、分歧和判断。
- 禁止使用“第一条新闻”“接下来我们聊”等机械报幕；每轮20-90个中文字符。
- 前2轮必须是自然开场：短开场问候/点题，并抛出今天的主线问题。
- 只使用输入日报中的事实，不得新增具体事实、数字或机构，不得提及聚合源名称。

输出要求：
只输出JSON：{{"podcast_dialogue":[{{"speaker":"S1","text":"..."}},{{"speaker":"S2","text":"..."}}]}}

日报：
{json.dumps([asdict(item) for item in articles], ensure_ascii=False)}
'''.strip()
    podcast_result, podcast_usage, podcast_model = request_deepseek_json(
        endpoint=endpoint,
        models=models,
        api_key=api_key,
        system_prompt='你是中文AI播客编剧。只使用输入日报中的事实，输出必须是合法JSON对象。',
        user_prompt=podcast_prompt,
    )
    dialogue: list[dict[str, str]] = []
    for item in podcast_result.get('podcast_dialogue', []):
        speaker = str(item.get('speaker', '')).strip()
        text = clean_text(str(item.get('text', '')))
        if speaker in ('S1', 'S2') and 20 <= len(text) <= 90:
            dialogue.append({'speaker': speaker, 'text': text})
    dialogue_issues = validate_podcast_dialogue(dialogue)
    if dialogue_issues:
        raise RuntimeError(f'LLM podcast dialogue quality failed: {dialogue_issues}')
    metadata = {
        'provider': 'opencode-go',
        'model_chain': models,
        'endpoint': endpoint,
        'calls': 1,
        'call_details': {
            'podcast': {'model': podcast_model, 'usage': podcast_usage},
        },
    }
    return dialogue, metadata


def render_html(issue_date: str, content_date: str, articles: list[Article], output_path: Path) -> None:
    dt = datetime.strptime(issue_date, '%Y-%m-%d')
    weekdays = '一二三四五六日'
    display_date = f'{dt.year}年{dt.month}月{dt.day}日 星期{weekdays[dt.weekday()]}'
    summary_titles = '；'.join(article.title for article in articles[:5])
    grouped = {section: [] for section in SECTION_ORDER}
    for article in articles:
        grouped.setdefault(article.section, []).append(article)

    parts = [
        '<!DOCTYPE html>',
        '<html><head><meta charset="utf-8"><style>',
        "body{font-family:'PingFang SC','Microsoft YaHei','Inter','Helvetica Neue',Arial,sans-serif;margin:0;padding:20px 0;background:#F9FAFB}",
        'table{border-collapse:collapse;width:100%;max-width:700px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:12px}',
        'td{padding:0}',
        '.header{background:#0F172A;padding:40px 36px 32px;text-align:center;border-radius:12px 12px 0 0}',
        '.header h1{color:#fff;margin:0;font-size:24px;font-weight:700;letter-spacing:1px}',
        '.header .date{color:#9CA3AF;font-size:13px;margin-top:10px;font-weight:400}',
        '.summary-wrap{padding:24px 36px 0}',
        '.summary{font-size:15px;line-height:1.8;color:#374151;margin:0}',
        '.section{padding:0 36px 28px}',
        '.section-divider{padding:0 36px}',
        '.section-divider hr{border:none;border-top:1px solid #E5E7EB;margin:16px 0}',
        '.section-title{font-size:17px;font-weight:700;color:#111827;margin:0 0 18px;padding-bottom:10px;border-bottom:2px solid #E2E8F0;letter-spacing:0.5px}',
        '.item{margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #F1F5F9}',
        '.item:last-child{border-bottom:none;padding-bottom:0}',
        '.item-title{font-size:15px;font-weight:700;margin:0 0 10px;line-height:1.6}',
        '.item-title a{color:#2563EB;text-decoration:none}',
        '.item-body{font-size:14px;line-height:2;color:#475569;margin:0 0 10px}',
        '.item-comment{font-size:13px;color:#6B7280;font-style:italic;margin:0 0 8px;padding:10px 14px;background:#fffbeb;border-left:3px solid #f59e0b;border-radius:0 6px 6px 0;line-height:1.8}',
        '.item-link{font-size:12px;color:#64748b;margin:0;line-height:1.8}',
        '.item-link a{color:#2563EB;text-decoration:none;word-break:break-all}',
        '.item-link a:hover{text-decoration:underline}',
        '.focus-badge{display:inline-block;background:linear-gradient(135deg,#ef4444,#f97316);color:#fff;font-size:11px;padding:2px 10px;border-radius:10px;margin-right:8px;font-weight:600;letter-spacing:0.5px;vertical-align:middle}',
        '.footer-wrap{padding:0}',
        '.footer{background:#F8FAFC;border-top:1px solid #E2E8F0;border-radius:0 0 12px 12px;padding:20px 36px;text-align:center;font-size:12px;color:#94a3b8;line-height:2}',
        '</style></head><body>',
        '<table><tr><td>',
        '<div class="header">',
        '<h1>📰 每日AI热点新闻（试运营）</h1>',
        f'<div class="date">{display_date}</div>',
        '</div>',
        '<div class="summary-wrap">',
        f'<div class="summary">今日关注：{html.escape(summary_titles)}。本期从产品、行业、研究与工具等方向筛选值得跟进的动态。</div>',
        '</div>',
    ]
    for section in SECTION_ORDER:
        section_articles = grouped.get(section) or []
        if not section_articles:
            continue
        parts.append('<div class="section-divider"><hr></div>')
        parts.append(f'<div class="section"><h2 class="section-title">{section}</h2>')
        for article in section_articles:
            escaped_url = html.escape(article.url, quote=True)
            review = f'AI锐评：{html.escape(article.review)}'
            focus_badge = '<span class="focus-badge">焦点</span>' if section == '🔥 今日焦点' else ''
            parts.extend([
                '<div class="item">',
                f'<div class="item-title">{focus_badge}<a href="{escaped_url}">{html.escape(article.title)}</a></div>',
                f'<p data-role="news-body" class="item-body">{html.escape(article.summary)}</p>',
                f'<div class="item-comment">{review}</div>',
                f'<div class="item-link">🔗 <a href="{escaped_url}">{escaped_url}</a></div>',
                '</div>',
            ])
        parts.append('</div>')
    parts.extend([
        '<div class="footer-wrap">',
        '<div class="footer">',
        '试运营期间有任何问题请联系：penglei4@lenovo.com<br>',
        '技术创新中心：-TIC@lenovo.com',
        f'<br>内容采集日期：{content_date} · 内容仅供参考',
        '</div>',
        '</div>',
        '</td></tr></table>',
        '</body></html>',
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
    articles, dialogue, llm_metadata = call_deepseek(candidates, llm_api_key)
    html_path = output_dir / f'ai-daily-news-html-{args.date}.html'
    podcast_path = output_dir / f'ai-daily-news-podcast-{args.date}.mp3'
    data_path = output_dir / f'news-data-{args.date}.json'
    candidate_data_path = output_dir / f'candidate-news-{args.date}.json'
    podcast_script_path = output_dir / f'podcast-script-{args.date}.json'
    podcast_script_text_path = output_dir / f'podcast-script-{args.date}.txt'
    moss_input_path = output_dir / f'podcast-moss-input-{args.date}.txt'
    render_html(args.date, content_date, articles, html_path)
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
        'podcast_turns': len(dialogue),
        'podcast_script_file': podcast_script_path.name,
        'podcast_script_text_file': podcast_script_text_path.name,
        'podcast_moss_input_file': moss_input_path.name,
        'tts_mode': tts_mode,
        'tts_model': MOSS_TTS_MODEL,
        'tts_speed': moss_tts_speed(),
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
