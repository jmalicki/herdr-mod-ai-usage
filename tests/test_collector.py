import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector


class UsageTests(unittest.TestCase):
    def test_missing_and_invalid_percent_are_not_zero(self):
        for value in (None, 'bad', float('nan'), float('inf'), -1, 101, True):
            self.assertIsNone(collector.window('5h', value, None))
        self.assertEqual(collector.window('5h', 0, None)['used'], 0)

    def test_codex_multi_bucket_preserves_every_window(self):
        rows = collector.codex_windows({'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 12, 'windowDurationMins': 300, 'resetsAt': 2000},
                      'secondary': {'usedPercent': 80, 'windowDurationMins': 10080, 'resetsAt': 9000}},
            'other': {'limitName': 'Review', 'primary': {'usedPercent': 0, 'windowDurationMins': 60}}
        }})
        self.assertEqual([r['label'] for r in rows], ['5h', '7d', 'Review · 1h'])
        self.assertIsNone(rows[2]['resets_at'])

    def test_claude_epoch_iso_and_scoped_models(self):
        rows = collector.claude_windows({'rate_limits': {
            'five_hour': {'used_percentage': 10, 'resets_at': 2000},
            'seven_day': {'utilization': 100, 'resets_at': '2026-11-03T00:00:00Z'},
            'seven_day_opus': None,
            'model_scoped': [{'display_name': 'Example', 'utilization': 0, 'resets_at': None}]
        }})
        self.assertEqual([r['used'] for r in rows], [10, 100, 0])
        self.assertGreater(rows[1]['resets_at'], rows[0]['resets_at'])
        self.assertIsNone(rows[2]['resets_at'])

    def test_failed_refresh_retains_observed_time_and_marks_error(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            old = dict(name='Codex', windows=[dict(used=80)], observed_at=10, checked_at=10)
            (state / 'codex.json').write_text(json.dumps(old))
            with patch.object(collector, 'fetch', side_effect=RuntimeError('Offline')):
                data = collector.collect_provider('Codex', state)
            self.assertEqual(data['observed_at'], 10)
            self.assertEqual(data['windows'], old['windows'])
            self.assertEqual(data['error'], 'Offline')

    def test_refresh_click_cooldown(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            with patch.object(collector, 'fetch', return_value=dict(name='Claude', windows=[], observed_at=10)) as fetch:
                collector.collect_provider('Claude', state)
                collector.collect_provider('Claude', state, force=True)
            self.assertEqual(fetch.call_count, 1)

    def test_json_process_skips_unrelated_messages(self):
        code = "import json,sys; request=json.loads(input()); print('not JSON'); print(json.dumps({'id':99})); print(json.dumps(request),flush=True); input()"
        with tempfile.TemporaryDirectory() as folder:
            process = collector.JsonProcess([sys.executable, '-c', code], folder)
            try:
                process.send({'id': 1})
                self.assertEqual(process.receive(lambda m: m.get('id') == 1), {'id': 1})
            finally:
                process.close()
            self.assertIsNotNone(process.process.returncode)


if __name__ == '__main__':
    unittest.main()
