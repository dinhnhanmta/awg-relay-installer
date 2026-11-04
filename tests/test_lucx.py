import hashlib
import io
import json
import sqlite3
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import closing
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

    def test_retry_does_not_show_credentials_after_password_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = lucx.new_access('8.8.8.8', root)
            info['credential_fingerprint'] = hashlib.sha256(b'initial-hash').hexdigest()
            private = root / 'panel.json'
            private.write_text(json.dumps(info))
            with closing(sqlite3.connect(root / 'x-ui.db')) as db, db:
                db.execute('create table users(id integer,username text,password text)')
                db.execute('insert into users values(1,?,?)', (info['username'], 'initial-hash'))
                db.execute('create table settings(key text,value text)')
                db.executemany('insert into settings values(?,?)',
                               [('webBasePath', info['base_path']), ('webCertFile', info['cert']), ('webPort', str(info['port']))])
            self.assertEqual(lucx.saved_access(private, root)['username'], info['username'])
            with closing(sqlite3.connect(root / 'x-ui.db')) as db, db:
                db.execute('update users set password=?', ('changed-hash',))
            self.assertIsNone(lucx.saved_access(private, root))

    def test_staged_wal_is_flushed_before_database_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info = lucx.new_access('8.8.8.8', root)
            with closing(sqlite3.connect(root / 'x-ui.db')) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('PRAGMA wal_autocheckpoint=0')
                writer.execute('create table users(id integer,username text,password text)')
                writer.execute('create table settings(key text,value text)')
                writer.execute('insert into users values(1,?,?)', (info['username'], 'test-hash'))
                writer.executemany('insert into settings values(?,?)', [
                    ('webPort', str(info['port'])), ('webBasePath', info['base_path']),
                    ('webListen', info['listen']), ('webCertFile', info['cert']), ('webKeyFile', info['key'])])
                writer.commit()
                with patch.object(lucx, 'run_logged'):
                    lucx.configure_database(root / 'x-ui', root, root, root, info, None)
                shutil.copyfile(root / 'x-ui.db', root / 'moved.db')
                with closing(sqlite3.connect(root / 'moved.db')) as moved:
                    self.assertEqual(moved.execute('select username from users').fetchone()[0], info['username'])

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
