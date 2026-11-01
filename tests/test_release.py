import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_release


class ReleaseTests(unittest.TestCase):
    def test_release_contains_only_allowlisted_public_files_and_valid_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            archive = build_release.build('example-name', '0.1.0', output)
            with zipfile.ZipFile(archive) as package:
                actual = set(package.namelist())
                self.assertEqual(actual, {f'example-name-0.1.0/{name}' for name in build_release.FILES})
                self.assertIsNone(package.testzip())
                self.assertIn('example-name-0.1.0/mods/plan-usage/check.svg', actual)
                self.assertFalse(any('backups/' in name or 'installation.json' in name for name in actual))
            self.assertEqual((output / 'SHA256SUMS').read_text(),
                             f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n')

    def test_invalid_release_names_and_versions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, version in [('../escape', '0.1.0'), ('fine', '../../escape'), ('bad name', '0.1.0')]:
                with self.assertRaises(ValueError):
                    build_release.build(name, version, Path(folder))


if __name__ == '__main__':
    unittest.main()
