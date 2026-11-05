"""Package privacy checks use artificial fixtures, never real credentials."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import build_private_bundle as bundle


class BundleTests(unittest.TestCase):
    def test_allowlist_excludes_private_history_and_env(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'app.py').write_text('print("fixture")', encoding='utf-8')
            (root / '.local').mkdir()
            (root / '.local' / 'private.json').write_text('PRIVATE-DATA-MARKER')
            (root / '.env').write_text('PRIVATE-DATA-MARKER')
            with patch.object(bundle, 'FILES', ('app.py',)), patch.object(bundle, 'EXAMPLES', {}):
                path, manifest = bundle.build(root)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(set(archive.namelist()), {'trade-local/app.py', 'trade-local/MANIFEST.json'})
                self.assertNotIn(b'PRIVATE-DATA-MARKER', b''.join(archive.read(n) for n in archive.namelist()))
            self.assertEqual(len(manifest['files']), 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_or_key_like_content_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'app.py'
            file.write_text('sk-' + 'x' * 25)
            with patch.object(bundle, 'FILES', ('app.py',)), patch.object(bundle, 'EXAMPLES', {}):
                with self.assertRaisesRegex(ValueError, '凭据'):
                    bundle.build(root)
                file.unlink()
                (root / 'other.py').write_text('fixture')
                file.symlink_to(root / 'other.py')
                with self.assertRaisesRegex(ValueError, '符号链接'):
                    bundle.build(root)
            self.assertEqual(list((root / 'deliverables').glob('*.zip')), [])


if __name__ == '__main__':
    unittest.main()
