from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_live_pipeline as pipeline  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class LlmProviderTests(unittest.TestCase):
    def test_selection_normalizes_section_labels_and_validates_focus(self) -> None:
        candidate_map = {
            f'https://example.test/{index}': pipeline.Article(
                title=f'news-{index}',
                summary='summary',
                url=f'https://example.test/{index}',
                section='产品发布',
            )
            for index in range(12)
        }
        result = {'selection': [
            {
                'url': f'https://example.test/{index}',
                'section': '今日焦点' if index == 0 else ' 产品发布 ',
            }
            for index in range(12)
        ]}

        selected, issues = pipeline.parse_and_validate_selection(result, candidate_map)

        self.assertEqual(issues, [])
        self.assertEqual(selected[0][1], '🔥 今日焦点')
        self.assertTrue(all(section in pipeline.SECTION_ORDER for _, section in selected))

    def test_selection_accepts_fewer_than_target_when_candidates_are_valid(self) -> None:
        candidate_map = {
            f'https://example.test/{index}': pipeline.Article(
                title=f'news-{index}',
                summary='summary',
                url=f'https://example.test/{index}',
                section='💼 行业动态',
            )
            for index in range(9)
        }
        result = {
            'selection': [
                {'url': url, 'section': '💼 行业动态'}
                for url in candidate_map
            ]
        }

        selected, issues = pipeline.parse_and_validate_selection(result, candidate_map)

        self.assertEqual(len(selected), 9)
        self.assertEqual(issues, [])
        self.assertEqual(selected[0][1], '🔥 今日焦点')

    def test_call_deepseek_keeps_nine_articles_and_handles_partial_batch(self) -> None:
        candidates = [
            pipeline.Article(
                title=f'news-{index}',
                summary='这是一条足够作为降级编辑输入的来源摘要。',
                url=f'https://example.test/{index}',
                section='💼 行业动态',
            )
            for index in range(9)
        ]

        def fake_request(**kwargs):
            task_name = kwargs['task_name']
            if task_name.startswith('selection_'):
                return (
                    {
                        'selection': [
                            {'url': item.url, 'section': '💼 行业动态'}
                            for item in candidates
                        ]
                    },
                    {},
                    'lenovo:test-model',
                )
            if task_name.startswith('editorial_batch_'):
                # Force the deterministic source fallback, including the final
                # one-item batch produced by nine selected articles.
                return {'articles': []}, {}, 'lenovo:test-model'
            if task_name == 'digest_summary':
                return {'summary': '今日新闻摘要'}, {}, 'lenovo:test-model'
            raise AssertionError(f'unexpected task: {task_name}')

        with (
            patch.object(pipeline, 'llm_config', return_value=('https://lenovo.test/v1', ['test-model'])),
            patch.object(pipeline, 'load_recent_titles_for_selection', return_value={}),
            patch.object(pipeline, 'request_deepseek_json', side_effect=fake_request),
            patch.object(pipeline, 'enrich_articles_with_source_text', side_effect=lambda items: items),
            patch.object(
                pipeline,
                'generate_podcast_dialogue',
                return_value=([{'speaker': 'S1', 'text': '播客内容'}], {'calls': 1}),
            ),
        ):
            articles, dialogue, summary, _metadata = pipeline.call_deepseek(
                candidates,
                'test-key',
                '2026-09-01',
            )

        self.assertEqual(len(articles), 9)
        self.assertEqual(len(dialogue), 1)
        self.assertEqual(summary, '今日新闻摘要')
        self.assertTrue(all(article.title for article in articles))

    def test_provider_chain_is_lenovo_only(self) -> None:
        providers = pipeline.llm_provider_chain(
            'https://lenovo.test/v1',
            ['lenovo-model'],
            'lenovo-key',
        )

        self.assertEqual([provider['name'] for provider in providers], ['lenovo'])
        self.assertEqual(providers[0]['models'], ['lenovo-model'])
        self.assertEqual(providers[0]['chat_template_kwargs'], {'enable_thinking': False})

    def test_selection_uses_five_lenovo_only_attempts(self) -> None:
        plan = pipeline.selection_provider_plan(
            'https://lenovo.test/v1',
            ['lenovo-model'],
            'lenovo-key',
        )

        self.assertEqual(plan, [None, None, None, None, None])

    def test_request_uses_lenovo_even_when_nvidia_environment_exists(self) -> None:
        env = {
            'LENOVO_LLM_API_KEY': 'lenovo-key',
            'LENOVO_LLM_BASE_URL': 'https://lenovo.test/v1',
            'LENOVO_LLM_MODELS': 'must-be-ignored',
            'NVIDIA_API_KEY': 'nvidia-key',
            'NVIDIA_LLM_BASE_URL': 'https://nvidia.test/v1',
            'NVIDIA_LLM_MODELS': 'nvidia-model',
            'LLM_STREAM': 'false',
        }
        lenovo_response = FakeResponse(json.dumps({
            'choices': [{
                'message': {'content': '{"selection": []}'},
                'finish_reason': 'stop',
            }],
            'usage': {'total_tokens': 3},
        }).encode('utf-8'))

        with (
            patch.dict(pipeline.os.environ, env, clear=True),
            patch.object(pipeline, 'urlopen', return_value=lenovo_response) as mocked_open,
        ):
            endpoint, models = pipeline.llm_config()
            result, usage, model = pipeline.request_deepseek_json(
                endpoint=endpoint,
                models=models,
                api_key=pipeline.llm_api_key(),
                system_prompt='system',
                user_prompt='user',
                task_name='lenovo_only_test',
            )

        self.assertEqual(result, {'selection': []})
        self.assertEqual(usage, {'total_tokens': 3})
        self.assertEqual(model, 'lenovo:qwen38-27b')
        self.assertEqual(mocked_open.call_count, 1)
        request = mocked_open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://lenovo.test/v1/chat/completions')

    def test_nvidia_key_alone_is_not_accepted(self) -> None:
        env = {
            'NVIDIA_API_KEY': 'nvidia-key',
            'OPENCODE_GO_API_KEY': 'nvidia-key',
        }
        with patch.dict(pipeline.os.environ, env, clear=True):
            self.assertEqual(pipeline.llm_api_key(), '')
            self.assertFalse(pipeline.has_any_llm_api_key())


if __name__ == '__main__':
    unittest.main()
