from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from news_dedup import (  # noqa: E402
    exact_recent_url_matches,
    filter_state_to_delivered,
    high_confidence_event_matches,
    recent_sent_articles,
)


def article(day: str, title: str, url: str) -> dict[str, str]:
    return {
        "date": day,
        "title": title,
        "summary": f"{title} 的摘要",
        "url": url,
    }


class SentNewsDedupeTests(unittest.TestCase):
    def test_only_delivery_marked_days_are_restored(self) -> None:
        state = {
            "window_days": 7,
            "days": {
                "2026-08-18": {"selected": [article("2026-08-18", "已发送", "https://a.test/1")]},
                "2026-08-19": {"selected": [article("2026-08-19", "未发送", "https://a.test/2")]},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            marker = site / "state" / "deliveries" / "2026-08-18" / "morning.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}", encoding="utf-8")
            filtered = filter_state_to_delivered(state, site)
        self.assertEqual(list(filtered["days"]), ["2026-08-18"])

    def test_previous_seven_days_use_selected_not_candidates(self) -> None:
        days = {}
        for day in range(11, 21):
            date = f"2026-08-{day:02d}"
            days[date] = {
                "candidates": [article(date, f"候选{day}", f"https://candidate.test/{day}")],
                "selected": [article(date, f"已发送{day}", f"https://sent.test/{day}")],
            }
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "recent-news.json"
            state_path.write_text(
                json.dumps({"window_days": 7, "days": days}, ensure_ascii=False),
                encoding="utf-8",
            )
            recent = recent_sent_articles(state_path, "2026-08-20", window_days=7)
        self.assertEqual(set(recent), {f"2026-08-{day:02d}" for day in range(13, 20)})
        titles = [item["title"] for records in recent.values() for item in records]
        self.assertTrue(all(title.startswith("已发送") for title in titles))

    def test_tracking_parameters_do_not_bypass_exact_url_gate(self) -> None:
        recent = {
            "2026-08-19": [
                article(
                    "2026-08-19",
                    "同一新闻",
                    "https://example.com/story?utm_source=mail",
                )
            ]
        }
        matches = exact_recent_url_matches(["https://example.com/story"], recent)
        self.assertIn("https://example.com/story", matches)

    def test_same_acquisition_from_another_site_is_blocked(self) -> None:
        recent = {
            "2026-08-19": [
                {
                    "date": "2026-08-19",
                    "title": "Stripe以70亿美元收购OpenRouter",
                    "summary": "Stripe 收购 OpenRouter，获得模型路由与开发者分发渠道。",
                    "url": "https://latent.example/stripe-openrouter",
                }
            ]
        }
        candidates = [
            {
                "title": "Stripe买下模型路由口",
                "summary": "TechCrunch分析交易算盘，Stripe买下OpenRouter并整合支付与推理账本。",
                "url": "https://tech.example/stripe-openrouter-analysis",
            }
        ]
        matches = high_confidence_event_matches(candidates, recent)
        match = matches["https://tech.example/stripe-openrouter-analysis"]
        self.assertEqual(match["actions"], ["acquisition"])
        self.assertEqual(match["entities"], ["openrouter", "stripe"])


if __name__ == "__main__":
    unittest.main()
