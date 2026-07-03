#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


def prompt_template(path: Path, name: str) -> str:
    text = path.read_text(encoding='utf-8')
    start = f'<!-- prompt:{name}:start -->'
    end = f'<!-- prompt:{name}:end -->'
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index < 0 or end_index < 0 or end_index <= start_index:
        raise RuntimeError(f'Missing prompt block: {name} in {path}')
    return text[start_index + len(start):end_index].strip()


def render_prompt(path: Path, name: str, **values: str) -> str:
    prompt = prompt_template(path, name)
    placeholders = set(re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', prompt))
    missing = sorted(item for item in placeholders if item not in values)
    if missing:
        raise RuntimeError(f'Missing placeholder values in prompt {name}: {missing}')
    for key, value in values.items():
        prompt = prompt.replace('{' + key + '}', value)
    return prompt
