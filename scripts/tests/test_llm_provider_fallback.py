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
    def test_provider_chain_is_lenovo_only(self) -> None:
        providers = pipeline.llm_provider_chain(
            'https://lenovo.test/v1',
            ['lenovo-model'],
            'lenovo-key',
        )

        self.assertEqual([provider['name'] for provider in providers], ['lenovo'])
        self.assertEqual(providers[0]['models'], ['lenovo-model'])
        self.assertEqual(providers[0]['chat_template_kwargs'], {'enable_thinking': False})

    def test_selection_uses_three_lenovo_only_attempts(self) -> None:
        plan = pipeline.selection_provider_plan(
            'https://lenovo.test/v1',
            ['lenovo-model'],
            'lenovo-key',
        )

        self.assertEqual(plan, [None, None, None])

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
        self.assertEqual(model, 'lenovo:qwen35-122b-a10b-fp8')
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
