#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_lib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = SKILL_DIR / 'samples'
TMP = Path('/tmp')

FORBIDDEN_MARKERS = [
    'hubtoday',
    'hex2077',
    'hextra',
    'aibase.com',
    'wappoc_appmsgcaptcha',
    'mp.weixin.qq.com/mp/wappoc',
]

FORBIDDEN_PHRASES = [
    'HubToday 归档',
    'HubToday 当日页',
    'HubToday 援引',
    'HubToday 页面',
    'hex2077 归档',
    'hex2077 当日页',
    '聚合页提到',
    '聚合页显示',
    '归档将这条新闻描述为',
    '归档把这条新闻',
    '当日页把这条新闻',
]

FOOTER_HINTS = ('联系我们', 'contact', '联系', '技术创新中心')


def strip_tags(text: str) -> str:
    text = re.sub(r'<script\b[^>]*>.*?</script>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<style\b[^>]*>.*?</style>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def count_body_blocks(html: str) -> int:
    blocks: list[str] = []
    for m in re.finditer(r'<(?P<tag>div|p|td)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>', html, flags=re.I | re.S):
        tag = m.group('tag').lower()
        attrs = (m.group('attrs') or '').lower()
        body = m.group('body') or ''
        include = False
        if 'data-role="news-body"' in attrs or "data-role='news-body'" in attrs:
            include = True
        elif tag == 'td':
            include = True
        elif 'line-height' in attrs:
            include = True
        if not include:
            continue
        text = strip_tags(body)
        if len(text) >= 80:
            blocks.append(text)
    return len(list(dict.fromkeys(blocks)))


def gather_links(html: str) -> tuple[list[str], list[str]]:
    pairs = re.findall(r'<a\b[^>]*href=["\'](https?://[^"\'>\s]+)["\'][^>]*>(.*?)</a>', html, flags=re.I | re.S)
    filtered: list[str] = []
    roots: list[str] = []
    for url, anchor_html in pairs:
        if any(bad in url.lower() for bad in FORBIDDEN_MARKERS):
            continue
        text = strip_tags(anchor_html).lower()
        if any(hint in text for hint in FOOTER_HINTS):
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            continue
        if parsed.path in ('', '/') and not parsed.query and not parsed.fragment:
            roots.append(url)
        filtered.append(url)
    return list(dict.fromkeys(filtered)), list(dict.fromkeys(roots))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Validate AI Daily News HTML against hard quality gates')
    p.add_argument('--date', required=True, help='YYYY-MM-DD')
    p.add_argument('--path', help='HTML path, default /tmp/ai-daily-news-html-YYYY-MM-DD.html')
    p.add_argument('--check-sample', action='store_true', help='Also validate samples/YYYY-MM-DD.html matches same hard gates')
    return p.parse_args()


def validate_path(path: Path, *, label: str) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    facts: list[str] = []
    if not path.exists():
        return [f'{label}: MISSING {path}'], facts
    raw = path.read_bytes()
    text = raw.decode('utf-8', errors='replace')
    lower = text.lower()

    facts.append(f'{label}: path={path}')
    facts.append(f'{label}: size_bytes={len(raw)}')

    if b'&#x' in raw:
        failures.append(f'{label}: HTML_ENTITY_BUG')

    # 结构稳定性门禁：新闻正文必须使用 <p data-role="news-body">，禁止误用 <td>
    p_body_count = len(re.findall(r'<p\b[^>]*data-role=["\']news-body["\'][^>]*>', text, flags=re.I))
    td_body_count = len(re.findall(r'<td\b[^>]*data-role=["\']news-body["\'][^>]*>', text, flags=re.I))
    h2_titles = [strip_tags(x) for x in re.findall(r'<h2\b[^>]*>(.*?)</h2>', text, flags=re.I | re.S)]
    facts.append(f'{label}: p_news_body={p_body_count}')
    facts.append(f'{label}: td_news_body={td_body_count}')
    facts.append(f"{label}: h2_titles={' | '.join(h2_titles)}")
    if td_body_count != 0:
        failures.append(f'{label}: INVALID_NEWS_BODY_TAG td count={td_body_count}')
    if p_body_count < 8:
        failures.append(f'{label}: P_NEWS_BODY_TOO_FEW {p_body_count} < 8')

    # 一致性门禁：默认保持“今日焦点”第一，其余栏目按既定顺序出现；避免每天顺序飘
    preferred_order = [
        '🔥 今日焦点',
        '🚀 产品发布',
        '💼 行业动态',
        '📜 政策 & 监管',
        '💡 前沿研究',
        '🔓 开源热榜',
        '🤖 Agent & 工具',
        '💰 商业 & 融资',
        '🇨🇳 国内 AI',
    ]
    idx_map = {name: i for i, name in enumerate(preferred_order)}
    filtered_h2 = [t for t in h2_titles if t in idx_map]
    if filtered_h2:
        if filtered_h2[0] != '🔥 今日焦点':
            failures.append(f"{label}: FIRST_SECTION_NOT_FOCUS {filtered_h2[0]}")
        order_indexes = [idx_map[t] for t in filtered_h2]
        if order_indexes != sorted(order_indexes):
            failures.append(f"{label}: SECTION_ORDER_DRIFT {' > '.join(filtered_h2)}")

    for marker in FORBIDDEN_MARKERS:
        count = lower.count(marker.lower())
        facts.append(f'{label}: marker[{marker}]={count}')
        if count != 0:
            failures.append(f'{label}: FORBIDDEN_MARKER {marker} count={count}')

    plain = strip_tags(text)
    for phrase in FORBIDDEN_PHRASES:
        count = plain.count(phrase)
        facts.append(f'{label}: phrase[{phrase}]={count}')
        if count != 0:
            failures.append(f'{label}: FORBIDDEN_PHRASE {phrase} count={count}')

    unique_links, root_links = gather_links(text)
    body_blocks = count_body_blocks(text)
    facts.append(f'{label}: unique_links={len(unique_links)}')
    facts.append(f'{label}: root_links={len(root_links)}')
    facts.append(f'{label}: body_blocks_ge80={body_blocks}')
    if len(unique_links) < 8:
        failures.append(f'{label}: UNIQUE_LINKS_TOO_FEW {len(unique_links)} < 8')
    if root_links:
        failures.append(f'{label}: ROOT_LINKS_PRESENT ' + ', '.join(root_links[:5]))
    if body_blocks < 8:
        failures.append(f'{label}: BODY_BLOCKS_TOO_FEW {body_blocks} < 8')

    return failures, facts


def main() -> int:
    args = parse_args()
    html_path = Path(args.path) if args.path else TMP / f'ai-daily-news-html-{args.date}.html'
    failures, facts = validate_path(html_path, label='html')

    if args.check_sample:
        sample_path = SAMPLES_DIR / f'{args.date}.html'
        f2, facts2 = validate_path(sample_path, label='sample')
        failures.extend(f2)
        facts.extend(facts2)

    for line in facts:
        print(line)

    if failures:
        print('VALIDATION: FAIL')
        for item in failures:
            print(item)
        return 20

    print('VALIDATION: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
