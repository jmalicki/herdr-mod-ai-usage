import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import google_api


class GoogleQuotaTests(unittest.TestCase):
    def test_gemini_chat_fraction_and_true_zero(self):
        body = [dict(data=dict(viewer=dict(rpcs=dict(getUsageInfo=dict(
            subscriptionTier='TIER1', pools=[
                dict(poolType='GXU_FIVE_HOURLY', percentageUsed=0, gxu=dict(windowRefreshesAt='2026-11-02T01:00:00Z')),
                dict(poolType='GXU_WEEKLY', percentageUsed=.42),
                dict(poolType='UNKNOWN', percentageUsed=.5)]))))) ]
        rows, plan = google_api.gemini_rows(body)
        self.assertEqual([(r['label'], r['used']) for r in rows], [('5h', 0), ('7d', 42)])
        self.assertEqual(plan, 'TIER1')
        self.assertIsNone(rows[1]['resets_at'])

    def test_signed_out_and_missing_chat_usage_do_not_become_zero(self):
        for body in ([dict(data=dict(viewer=None))], [], {}):
            with self.assertRaises(RuntimeError):
                google_api.gemini_rows(body)

    def test_antigravity_keeps_groups_and_skips_unknown_disabled(self):
        body = dict(response=dict(groups=[dict(displayName='Gemini', buckets=[
            dict(displayName='5h', remaining=dict(remainingFraction=.8)),
            dict(displayName='7d', remaining=dict(case='remainingFraction', value=0)),
            dict(displayName='Unknown', remaining={}),
            dict(displayName='Disabled', disabled=True, remainingFraction=.1),
        ]), dict(displayName='Claude + GPT', buckets=[
            dict(displayName='Weekly', remainingFraction=1, resetTime='2026-11-03T00:00:00Z')])]))
        rows = google_api.antigravity_rows(body)
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[0]['used'], 20)
        self.assertEqual(rows[1]['used'], 100)
        self.assertEqual(rows[2]['used'], 0)
        self.assertIn('Claude + GPT', rows[2]['label'])

    def test_invalid_fractions_are_unavailable(self):
        for value in (None, True, '0.5', -1, 2, math.nan, math.inf):
            self.assertIsNone(google_api.fraction(value))

    def test_auth_headers_cannot_be_sent_to_arbitrary_destinations(self):
        with self.assertRaises(RuntimeError):
            google_api.GoogleAPI().request('https://example.com/', headers={'Cookie': 'private'})

    def test_api_redirects_do_not_forward_authentication(self):
        import urllib.error
        error = urllib.error.HTTPError('https://gemini.google.com/', 302, 'Found', {}, None)
        with patch('urllib.request.build_opener') as build:
            build.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, 'session unavailable'):
                google_api.GoogleAPI().request('https://gemini.google.com/', headers={'Cookie': 'private'})
            handler = build.call_args[0][0]()
            self.assertIsNone(handler.redirect_request(None, None, None, None, None, None))


if __name__ == '__main__':
    unittest.main()
