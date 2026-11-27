import json
import smtplib
import tempfile
import unittest
from pathlib import Path

from scripts.delivery_retry import run_delivery
from scripts.news_public_fields import public_index, public_manifest, public_report, PUBLIC_ORIGIN
from scripts.check_manifest_ready import is_ready
from scripts.verify_public_news import recipients, safe_text, walk

A, B = 'one@example.invalid', 'two@example.invalid'
D = '2026-11-28'


class PrivacyTests(unittest.TestCase):
    def test_public_projection_excludes_recipient_and_runtime(self):
        report = {'tts_mode': 'text-only', 'recipient': A, 'llm': {'endpoint': 'https://private.invalid'},
                  'digest_summary': 'headline', 'article_count': 12}
        html = PUBLIC_ORIGIN + 'html/' + D + '.html'
        manifest = public_manifest({'status': 'ready'}, report, {'html': html, 'audio': None}, D)
        index = public_index({'issue_date': D, 'html_url': html, 'llm': report['llm'],
                              'audio_url': 'https://private.invalid'})
        p = {'manifest': manifest, 'index': index, 'report': public_report(report, D)}
        walk(p)
        safe_text(json.dumps(p), {A, B}, ['https://private.invalid'])
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / 'manifest.json'
            fixture.write_text(json.dumps(manifest))
            self.assertTrue(is_ready(fixture)[0])
        self.assertEqual(index['html_url'], html)
        self.assertIsNone(index['audio_url'])

    def test_public_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'operational'):
            walk({'llm': {'endpoint': 'https://private.invalid'}})
        with self.assertRaisesRegex(ValueError, 'address'):
            safe_text(f'<p>{A}</p>', {A, B}, [])
        with self.assertRaisesRegex(ValueError, 'endpoint'):
            safe_text('https://private.invalid/x', set(), ['https://private.invalid'])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'recipients.json'
            p.write_text(json.dumps({'admins': [A], 'all': [A, B]}))
            self.assertEqual(recipients(p), {A, B})
            p.write_text(json.dumps({'all': [A]}))
            with self.assertRaises(ValueError):
                recipients(p)


class RetryTests(unittest.TestCase):
    @staticmethod
    def execute(status, send, calls, attempts=3):
        run_delivery([[A, B]], status, send, lambda s: calls.append(json.loads(json.dumps(s))),
                     attempts, lambda _: None, 0, lambda _: None)

    def test_partial_success_retries_only_the_refused_address(self):
        s = {'sent': {}, 'failed': {}}
        recipients_attempted, checkpoints = [], []
        def send(addrs):
            recipients_attempted.append(addrs)
            return {B: (450, b'retry')} if len(recipients_attempted) < 4 else {}
        self.execute(s, send, checkpoints)
        self.assertEqual(recipients_attempted, [[A, B], [B], [B]])
        self.assertIn(A, checkpoints[1]['sent'])
        self.assertIn(B, s['failed'])
        self.execute(json.loads(json.dumps(s)), send, checkpoints)
        self.assertEqual(recipients_attempted[-1], [B])
        self.assertEqual(set(checkpoints[-1]['sent']), {A, B})

    def test_transport_ambiguity_survives_and_is_not_resent(self):
        s = {'sent': {}, 'failed': {}}
        checkpoints = []
        def send(_):
            raise smtplib.SMTPServerDisconnected()
        self.execute(s, send, checkpoints)
        self.assertEqual(set(checkpoints[-1]['in_flight']), {A, B})
        self.execute(json.loads(json.dumps(s)), lambda _: self.fail('resubmitted'), checkpoints)

    def test_checkpoint_failure_prevents_smtp(self):
        def fail(_):
            raise RuntimeError('store unavailable')
        with self.assertRaisesRegex(RuntimeError, 'store unavailable'):
            run_delivery([[A, B]], {'sent': {}, 'failed': {}}, lambda _: self.fail('sent'),
                         fail, 3, lambda _: None, 0, lambda _: None)
