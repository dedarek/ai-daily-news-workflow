#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'skill' / 'scripts'))

import check_and_distribute
import check_manifest_ready
import dispatch_daily_workflow
import run_news_agent
import send_all
import upload_delivery_artifacts


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _seed_text_only_dist(dist: Path, issue_date: str) -> None:
    sample_html = (REPO_ROOT / 'skill' / 'samples' / '2026-06-24.html').read_text(encoding='utf-8')
    (dist / f'daily-news-{issue_date}.html').write_text(sample_html, encoding='utf-8')
    articles = [
        {
            'title': 'Test AI News Item',
            'summary': 'Summary text ' * 40,
            'url': 'https://example.com/news-1',
            'source': 'Example',
        }
    ]
    _write_json(dist / f'candidate-news-{issue_date}.json', articles)
    _write_json(dist / f'articles-{issue_date}.json', articles)
    _write_json(
        dist / f'podcast-script-{issue_date}.json',
        {'dialogue': [{'speaker': 'S1', 'text': 'Hello ' * 120}]},
    )
    (dist / f'podcast-script-{issue_date}.txt').write_text('[S1] ' + 'Hello ' * 120, encoding='utf-8')
    (dist / f'podcast-moss-input-{issue_date}.txt').write_text('[S1] ' + 'Hello ' * 120, encoding='utf-8')
    _write_json(
        dist / f'pipeline-report-{issue_date}.json',
        {
            'issue_date': issue_date,
            'content_date': issue_date,
            'tts_mode': 'text-only',
            'llm': {'model': 'test-model'},
            'video_api': {'error': 'video service retired'},
            'padding': 'x' * 500,
        },
    )


class TextOnlyFallbackTests(unittest.TestCase):
    def test_run_news_agent_allows_missing_media_only_in_text_only_mode(self) -> None:
        issue_date = '2026-11-20'
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            dist = Path(tmp) / 'dist'
            dist.mkdir()
            _seed_text_only_dist(dist, issue_date)
            paths = run_news_agent.artifact_paths(dist, issue_date)
            self.assertEqual(run_news_agent.validate_artifacts(paths), [])

            run_news_agent.write_manifest(
                output_dir=dist,
                issue_date=issue_date,
                status='ready',
                paths=paths,
                agent_metadata=None,
                memory_update={'candidate_count': 1, 'selected_count': 1},
                issues=[],
            )
            code, info = run_news_agent.validate_manifest(dist, issue_date)
            self.assertEqual(code, run_news_agent.READY, info)

            # 非 text-only 模式下缺少音视频必须仍被拦截
            report_path = paths['pipeline_report']
            report = json.loads(report_path.read_text(encoding='utf-8'))
            report['tts_mode'] = 'video-api-audio-video'
            _write_json(report_path, report)
            issues = run_news_agent.validate_artifacts(paths)
            self.assertTrue(any('missing audio' in item for item in issues), issues)

    def test_check_and_distribute_recognizes_text_only_issue(self) -> None:
        issue_date = '2026-11-20'
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            _seed_text_only_dist(dist, issue_date)
            self.assertTrue(check_and_distribute.text_only_issue(dist, issue_date))
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / 'skill' / 'scripts' / 'check_and_distribute.py'),
                    '--date',
                    issue_date,
                    '--artifact-dir',
                    str(dist),
                    '--dry-run',
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('MP3: skipped (text-only issue', proc.stdout)

    def test_check_and_distribute_recognizes_text_only_from_review_manifest(self) -> None:
        issue_date = '2026-11-20'
        with tempfile.TemporaryDirectory() as tmp:
            review_dist = Path(tmp)
            _seed_text_only_dist(review_dist, issue_date)
            report_path = review_dist / f'pipeline-report-{issue_date}.json'
            embedded_report = json.loads(report_path.read_text(encoding='utf-8'))
            report_path.unlink()
            _write_json(
                review_dist / f'manifest-{issue_date}.json',
                {'date': issue_date, 'status': 'ready', 'pipeline_report': embedded_report},
            )
            self.assertTrue(check_and_distribute.text_only_issue(review_dist, issue_date))

    def test_send_all_builds_message_without_media_attachment(self) -> None:
        msg = send_all.build_message(
            date_str='2026-11-20',
            sender='bot@example.com',
            to_header='user@example.com',
            html_content='<html><body><p>日报正文</p></body></html>',
            media_path=None,
            media_kind='audio',
        )
        attachments = [part for part in msg.walk() if part.get_content_disposition() == 'attachment']
        self.assertEqual(attachments, [])

    def test_build_content_site_and_upload_dry_run_without_media(self) -> None:
        issue_date = '2026-11-20'
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            dist = root / 'dist'
            site = root / 'site'
            dist.mkdir()
            _seed_text_only_dist(dist, issue_date)
            paths = run_news_agent.artifact_paths(dist, issue_date)
            run_news_agent.write_manifest(
                output_dir=dist,
                issue_date=issue_date,
                status='ready',
                paths=paths,
                agent_metadata=None,
                memory_update={'candidate_count': 1, 'selected_count': 1},
                issues=[],
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / 'scripts' / 'build_content_site.py'),
                    '--date',
                    issue_date,
                    '--dist-dir',
                    str(dist),
                    '--site-dir',
                    str(site),
                    '--base-url',
                    'https://example.github.io/ai-daily-news-workflow',
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            issue_json = json.loads((site / 'api' / 'issues' / issue_date / 'index.json').read_text(encoding='utf-8'))
            self.assertIsNone(issue_json['audio_url'])
            self.assertIsNone(issue_json['video_url'])
            self.assertIsNone(issue_json['voice_url'])

            upload_proc = subprocess.run(
                [
                    'node',
                    str(REPO_ROOT / 'scripts' / 'upload_new_site_artifacts.mjs'),
                    '--date',
                    issue_date,
                    '--artifact-dir',
                    str(dist),
                    '--api-key',
                    'test-key-for-dry-run',
                    '--dry-run',
                    'true',
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(upload_proc.returncode, 0, upload_proc.stdout + upload_proc.stderr)
            self.assertIn('"audio_bytes": 0', upload_proc.stdout)
            self.assertIn('"video_bytes": 0', upload_proc.stdout)

            published_manifest = site / 'api' / 'issues' / issue_date / 'manifest.json'
            ready, reason = check_manifest_ready.is_ready(published_manifest)
            self.assertTrue(ready, reason)

            manifest_payload = json.loads(published_manifest.read_text(encoding='utf-8'))
            orig_get = dispatch_daily_workflow.get_json_url
            dispatch_daily_workflow.get_json_url = lambda url, timeout=30: (200, manifest_payload, '')
            try:
                ok, msg = dispatch_daily_workflow.manifest_ready('https://example.com', issue_date)
                self.assertTrue(ok, msg)
            finally:
                dispatch_daily_workflow.get_json_url = orig_get

    def test_upload_delivery_artifacts_skips_optional_missing_mp3(self) -> None:
        issue_date = '2026-11-20'
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            dist = Path(tmp)
            _write_json(dist / f'articles-{issue_date}.json', [{'title': 'x'}])
            cfg = upload_delivery_artifacts.read_config()
            files = upload_delivery_artifacts.collect_configured_files(dist, issue_date, cfg['files'])
            self.assertEqual([field for field, _ in files], ['jsons'])

            non_optional = [{'path': 'daily-news-podcast-{date}.mp3', 'field': 'docs'}]
            with self.assertRaises(FileNotFoundError):
                upload_delivery_artifacts.collect_configured_files(dist, issue_date, non_optional)


if __name__ == '__main__':
    unittest.main()
