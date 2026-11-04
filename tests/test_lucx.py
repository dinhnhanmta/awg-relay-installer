import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lucx


class LucxTests(unittest.TestCase):
    def test_fresh_and_existing_panel_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main, db, unit = root / 'main', root / 'db', root / 'x-ui.service'
            self.assertEqual(lucx.install_state(main, db, unit), 'fresh')
            main.mkdir();db.mkdir()
            (main / 'x-ui').write_bytes(b'program')
            (db / 'x-ui.db').write_bytes(b'preserve-me')
            unit.write_text('unit')
            self.assertEqual(lucx.install_state(main, db, unit), 'existing')
            self.assertEqual((db / 'x-ui.db').read_bytes(), b'preserve-me')
            unit.unlink()
            with self.assertRaisesRegex(RuntimeError, 'dữ liệu'):
                lucx.install_state(main, db, unit)

    def test_existing_panel_is_not_reconfigured(self):
        with patch.object(lucx, 'install_state', return_value='existing'), \
             patch.object(lucx.subprocess, 'run') as run, \
             patch.object(lucx, 'download_verified') as download:
            self.assertIsNone(lucx.prepare_lucx('8.8.8.8'))
        run.assert_not_called()
        download.assert_not_called()

    def test_dry_run_never_installs(self):
        with patch.object(lucx.subprocess, 'run') as run, \
             patch.object(lucx, 'download_verified') as download:
            lucx.prepare_lucx('8.8.8.8', dry_run=True)
        run.assert_not_called()
        download.assert_not_called()

    def test_random_private_credentials_and_https(self):
        a = lucx.new_access('8.8.8.8', Path('/etc/x-ui/cert'))
        b = lucx.new_access('8.8.8.8', Path('/etc/x-ui/cert'))
        self.assertTrue(a['url'].startswith('https://8.8.8.8:2053/'))
        self.assertNotEqual(a['password'], b['password'])
        self.assertNotEqual(a['base_path'], b['base_path'])
        self.assertGreaterEqual(len(a['password']), 32)

    def test_download_checksum_failure(self):
        asset = {'url': 'https://github.com/example/release', 'bytes': 4,
                 'sha256': hashlib.sha256(b'good').hexdigest()}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(lucx.urllib.request, 'urlopen', return_value=io.BytesIO(b'evil')):
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                lucx.download_verified(asset, Path(tmp) / 'download')

    def test_release_rejects_links_and_escape(self):
        for name, kind in [('x-ui/../../escape', tarfile.REGTYPE), ('x-ui/link', tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'release.tar.gz'
                with tarfile.open(path, 'w:gz') as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = '/etc/passwd'
                    archive.addfile(member)
                with self.assertRaisesRegex(RuntimeError, 'Đường dẫn'):
                    lucx.extract_release(path, Path(tmp) / 'output')


if __name__ == '__main__':
    unittest.main()
