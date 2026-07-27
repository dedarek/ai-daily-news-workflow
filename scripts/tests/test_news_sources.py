import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from news_sources.daheiai import parse_daheiai_rss
from news_sources.hex2077 import parse_hex_daily_html
from news_sources.satori import parse_satori_html


class SourceParserTests(unittest.TestCase):
    def test_hex2077(self):
        raw = """
        <h2>产品发布</h2><ul><li><strong>模型 A 正式发布</strong>
        模型 A 带来新的推理能力。
        <a href="https://example.com/news/a">原文</a></li></ul>
        """
        items = parse_hex_daily_html(raw)
        self.assertEqual(items[0].url, "https://example.com/news/a")

    def test_satori_dates_and_cards(self):
        raw = """
        <title>每日 AI 速览 · 2026-07-26</title>
        <div class="meta">生成于 2026-07-27 04:12</div>
        <article class="card">
        <p class="title"><a href="https://example.com/a">Agent 模型 A 发布</a></p>
        <div class="src">Example · 07-26 18:00 UTC+8</div>
        <p class="sum">这是完整摘要。</p></article>
        """
        content_date, generated_at, items = parse_satori_html(raw)
        self.assertEqual(content_date, "2026-07-26")
        self.assertTrue(generated_at.startswith("2026-07-27"))
        self.assertEqual(len(items), 1)

    def test_daheiai_rss_time(self):
        raw = """<rss><channel><item>
        <title>第 1563 期</title>
        <link>https://news.daheiai.com/1563</link>
        <pubDate>Mon, 27 Jul 2026 08:01:00 +0800</pubDate>
        <description>本期 AI 速报摘要</description>
        </item></channel></rss>"""
        items, newest, entries = parse_daheiai_rss(raw, "2026-07-27")
        self.assertEqual(entries, 1)
        self.assertEqual(newest.date().isoformat(), "2026-07-27")
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
