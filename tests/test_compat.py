from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compat import iso_timestamp
from collector import timestamp
from google_api import decrypt_cookie


class AppleCompatibilityTests(unittest.TestCase):
    def test_rfc3339_precision_supported_on_apple_python(self):
        expected = iso_timestamp('2026-11-01T20:00:00.123456+00:00')
        self.assertEqual(iso_timestamp('2026-11-01T20:00:00.123456789Z'), expected)
        self.assertEqual(timestamp('2026-11-01T20:00:00.123456789Z'), expected)
        self.assertEqual(iso_timestamp('2026-11-01T20:00:00.1Z'),
                         iso_timestamp('2026-11-01T20:00:00.100000Z'))
        self.assertIsNone(timestamp('not a timestamp'))

    @unittest.skipUnless(sys.platform == 'darwin', 'CommonCrypto is a macOS system library')
    def test_commoncrypto_decrypts_known_aes_cbc_pkcs7_fixture(self):
        # Independent fixture generated with OpenSSL using the key/IV below.
        encrypted = bytes.fromhex('5575d530fd7596af21862f2984609562')
        key = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        self.assertEqual(decrypt_cookie(encrypted, key), b'example-cookie')
        with self.assertRaises(RuntimeError):
            decrypt_cookie(encrypted[:-1], key)


if __name__ == '__main__':
    unittest.main()
