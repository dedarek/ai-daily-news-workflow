from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_live_pipeline as pipeline  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class LlmProviderFallbackTests(unittest.TestCase):
    def test_nvidia_precedes_lenovo_in_provider_chain(self) -> None:
        env = {
            'LENOVO_LLM_API_KEY': 'lenovo-key',
            'LENOVO_LLM_BASE_URL': 'https://lenovo.test/v1',
            'LENOVO_LLM_MODELS': 'lenovo-model',
        }
        with patch.dict(pipeline.os.environ, env, clear=True):
            providers = pipeline.llm_provider_chain(
                'https://nvidia.test/v1',
                ['nvidia-model'],
                'nvidia-key',
            )

        self.assertEqual([provider['name'] for provider in providers], ['nvidia', 'lenovo'])

    def test_selection_gets_final_lenovo_only_attempt(self) -> None:
        env = {
            'LENOVO_LLM_API_KEY': 'lenovo-key',
            'LENOVO_LLM_MODELS': 'lenovo-model',
        }
        with patch.dict(pipeline.os.environ, env, clear=True):
            plan = pipeline.selection_provider_plan(
                'https://nvidia.test/v1',
                ['nvidia-model'],
                'nvidia-key',
            )

        self.assertEqual(plan, [None, None, None, 'lenovo'])

    def test_lenovo_is_used_after_nvidia_non_retryable_failure(self) -> None:
        env = {
            'LENOVO_LLM_API_KEY': 'lenovo-key',
            'LENOVO_LLM_BASE_URL': 'https://lenovo.test/v1',
            'LENOVO_LLM_MODELS': 'lenovo-model',
            'LLM_STREAM': 'false',
        }
        nvidia_error = HTTPError(
            'https://nvidia.test/v1/chat/completions',
            401,
            'Unauthorized',
            {},
            io.BytesIO(b'{"error":"invalid key"}'),
        )
        lenovo_response = FakeResponse(json.dumps({
            'choices': [{
                'message': {'content': '{"selection": []}'},
                'finish_reason': 'stop',
            }],
            'usage': {'total_tokens': 3},
        }).encode('utf-8'))

        with (
            patch.dict(pipeline.os.environ, env, clear=True),
            patch.object(pipeline, 'urlopen', side_effect=[nvidia_error, lenovo_response]) as mocked_open,
        ):
            result, usage, model = pipeline.request_deepseek_json(
                endpoint='https://nvidia.test/v1',
                models=['nvidia-model'],
                api_key='nvidia-key',
                system_prompt='system',
                user_prompt='user',
                task_name='fallback_test',
            )

        self.assertEqual(result, {'selection': []})
        self.assertEqual(usage, {'total_tokens': 3})
        self.assertEqual(model, 'lenovo:lenovo-model')
        self.assertEqual(mocked_open.call_count, 2)

    def test_lenovo_still_works_without_nvidia_key(self) -> None:
        env = {
            'LENOVO_LLM_API_KEY': 'lenovo-key',
            'LENOVO_LLM_MODELS': 'lenovo-model',
        }
        with patch.dict(pipeline.os.environ, env, clear=True):
            providers = pipeline.llm_provider_chain(
                'https://nvidia.test/v1',
                ['nvidia-model'],
                '',
            )

        self.assertEqual([provider['name'] for provider in providers], ['lenovo'])
        with patch.dict(pipeline.os.environ, env, clear=True):
            plan = pipeline.selection_provider_plan(
                'https://nvidia.test/v1',
                ['nvidia-model'],
                '',
            )
        self.assertEqual(plan, [None, None, None])


if __name__ == '__main__':
    unittest.main()
