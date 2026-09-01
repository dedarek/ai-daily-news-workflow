from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_live_pipeline as pipeline  # noqa: E402


class PodcastRepairLoopTests(unittest.TestCase):
    def test_structurally_sound_dialogue_can_be_accepted_with_harness_warnings(self) -> None:
        dialogue = [
            {
                'speaker': 'S1' if index % 2 == 0 else 'S2',
                'text': '这是一段包含事实解释、观点承接和行业判断的自然播客发言，用来满足客观发布质量底线，并帮助听众理解新闻之间的联系与实际影响。',
            }
            for index in range(20)
        ]

        self.assertEqual(pipeline.podcast_advisory_acceptance_issues(dialogue), [])

    def test_advisory_acceptance_only_rejects_broken_dialogue(self) -> None:
        dialogue = [
            {'speaker': 'S1', 'text': '内容太短。'},
            {'speaker': 'S1', 'text': '仍然太短。'},
        ]

        issues = pipeline.podcast_advisory_acceptance_issues(dialogue)

        self.assertEqual(issues, [])

    def test_repair_context_contains_failed_draft_and_harness_diagnostics(self) -> None:
        trajectory = [{
            'attempt': 1,
            'dialogue': [
                {'speaker': 'S1', 'text': '生硬的开场。'},
                {'speaker': 'S2', 'text': '重复上一句话。'},
            ],
            'structure_issues': [],
            'review_issues': ['共26轮，超过上限', '开场切入生硬'],
            'repair_instruction': '压缩重复内容并自然引出当天主线。',
        }]

        instruction = pipeline.build_cumulative_repair_instruction(trajectory)

        self.assertIn('共26轮，超过上限', instruction)
        self.assertIn('开场切入生硬', instruction)
        self.assertIn('压缩重复内容并自然引出当天主线', instruction)
        self.assertIn('生硬的开场', instruction)
        self.assertIn('总轮次固定为20轮', instruction)
        self.assertIn('逐项自检', instruction)


if __name__ == '__main__':
    unittest.main()
