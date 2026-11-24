"""Validation regressions using synthetic files only (no game assets).

    python -m unittest discover -s tools/test -p "test_*.py"
"""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research'))
from ds2 import addoncheck  # noqa: E402


def inventory(files):
    return {p: (hashlib.md5(data).hexdigest(), len(data)) for p, data in files.items()}


class AddonCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = {'level/main.str': b'original', 'level/main.toc': b'toc old'}
        self.variant = {'level/main.str': b'variant!', 'level/main.toc': b'toc new'}
        self.want = inventory(self.reference)
        patch = mock.patch.object(addoncheck, 'expected', return_value=self.want)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(addoncheck, 'KNOWN_VARIANTS', {
            addoncheck.fingerprint(inventory(self.variant)): 'synthetic variant',
        })
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, files):
        for name, data in files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def test_original_still_accepted(self):
        self.write(self.reference)
        self.assertEqual(addoncheck.check(self.root), [])

    def test_complete_variant_accepted(self):
        self.write(self.variant)
        self.assertEqual(addoncheck.check(self.root), [])

    def test_unknown_same_size_change_rejected(self):
        self.write({**self.variant, 'level/main.str': b'corrupt!'})
        self.assertEqual(addoncheck.check(self.root), [
            'different contents: level/main.str', 'different contents: level/main.toc',
        ])

    def test_mixed_versions_rejected(self):
        self.write({**self.variant, 'level/main.str': self.reference['level/main.str']})
        self.assertEqual(addoncheck.check(self.root), ['different contents: level/main.toc'])

    def test_missing_file_rejected(self):
        self.write({'level/main.str': self.variant['level/main.str']})
        self.assertIn('missing: level/main.toc', addoncheck.check(self.root))

    def test_wrong_size_rejected(self):
        self.write({**self.variant, 'level/main.str': b'truncated'})
        self.assertIn('wrong size: level/main.str (9 bytes, expected 8)', addoncheck.check(self.root))

    def test_extra_files_ignored(self):
        self.write({**self.variant, 'notes.txt': b'not part of the DLC'})
        self.assertEqual(addoncheck.check(self.root), [])

    def test_case_insensitive_paths(self):
        self.write({p.upper(): data for p, data in self.variant.items()})
        self.assertEqual(addoncheck.check(self.root), [])

    def test_progress_callback(self):
        self.write(self.variant)
        progress = mock.Mock()
        addoncheck.check(self.root, progress=progress)
        progress.assert_called_once_with(0, 2)

    def test_fingerprint_is_stable(self):
        entries = inventory(self.variant)
        rows = ''.join('%s %d %s\n' % (md5, size, path)
                       for path, (md5, size) in sorted(entries.items()))
        expected = hashlib.sha256(rows.encode('utf-8')).hexdigest()
        self.assertEqual(addoncheck.fingerprint(dict(reversed(list(entries.items())))), expected)


if __name__ == '__main__':
    unittest.main()
