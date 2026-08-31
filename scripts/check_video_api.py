"""Probe the external video API without submitting a real generation job.

Usage:
    python scripts/check_video_api.py

Checks, in order:
1. Network reachability of the API base URL.
2. Token validity (401/403 means the token is rejected).
3. A 404 on a fake job id means the service is up and auth passed.
"""
from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = 'http://8.137.39.142:1234/api'
DEFAULT_TOKEN = 'lenovo-ssg-aics-tsd-tic-cd'


def main() -> int:
    base_url = os.environ.get('AI_DAILY_VIDEO_API_BASE_URL', DEFAULT_BASE_URL).rstrip('/')
    token = (
        os.environ.get('AI_DAILY_VIDEO_API_TOKEN')
        or os.environ.get('VIDEO_API_TOKEN')
        or DEFAULT_TOKEN
    )
    env_token = bool(
        os.environ.get('AI_DAILY_VIDEO_API_TOKEN') or os.environ.get('VIDEO_API_TOKEN')
    )
    print(f'base_url : {base_url}')
    print(f'token    : {"from env" if env_token else "built-in default"}')

    probe_url = f'{base_url}/jobs/__healthcheck_probe__'
    request = Request(probe_url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urlopen(request, timeout=15) as response:
            print(f'HTTP {response.status}: unexpected success; service is reachable')
            return 0
    except HTTPError as exc:
        body = exc.read(300).decode('utf-8', errors='replace')
        print(f'HTTP {exc.code}: {body}')
        if exc.code in (401, 403):
            print('RESULT: FAIL - token rejected, configure AI_DAILY_VIDEO_API_TOKEN')
            return 1
        if exc.code == 404:
            print('RESULT: OK - service reachable and token accepted (job not found is expected)')
            return 0
        print('RESULT: WARN - unexpected status, service may be partially available')
        return 2
    except URLError as exc:
        print(f'NETWORK ERROR: {exc.reason}')
        print('RESULT: FAIL - cannot reach the API server (check VPN / network)')
        return 1
    except TimeoutError:
        print('NETWORK ERROR: connection timed out')
        print('RESULT: FAIL - cannot reach the API server (check VPN / network)')
        return 1


if __name__ == '__main__':
    sys.exit(main())
