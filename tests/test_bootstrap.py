import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('bootstrap', BASE / 'bootstrap.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def encrypt(plain, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    header = app.MAGIC + salt + nonce
    key = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode())
    return header + AESGCM(key).encrypt(nonce, plain, header)


def make_archive(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for name, data, kind in entries:
            m = tarfile.TarInfo(name)
            m.type = kind
            m.size = len(data) if kind == tarfile.REGTYPE else 0
            m.linkname = '/etc/passwd' if kind != tarfile.REGTYPE else ''
            archive.addfile(m, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    return buf.getvalue()


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'test-only-not-a-real-password'
        cls.plain = b'authenticated test payload'
        cls.encrypted = encrypt(cls.plain, cls.password)

    def test_round_trip(self):
        self.assertEqual(app.decrypt(self.encrypted, self.password), self.plain)

    def test_wrong_password(self):
        with self.assertRaisesRegex(RuntimeError, 'Mật khẩu'):
            app.decrypt(self.encrypted, 'incorrect')

    def test_corruption(self):
        damaged = bytearray(self.encrypted)
        damaged[-1] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'Mật khẩu'):
            app.decrypt(bytes(damaged), self.password)

    def test_invalid_header(self):
        with self.assertRaisesRegex(RuntimeError, 'định dạng'):
            app.decrypt(b'plain text is never an encrypted payload', self.password)

    def test_traversal_links_and_duplicate_names(self):
        cases = [
            [('vpn-infrastructure/../../escaped', b'x', tarfile.REGTYPE)],
            [('/etc/escaped', b'x', tarfile.REGTYPE)],
            [('vpn-infrastructure/link', b'', tarfile.SYMTYPE)],
            [('vpn-infrastructure/link', b'', tarfile.LNKTYPE)],
            [('vpn-infrastructure/x', b'a', tarfile.REGTYPE), ('vpn-infrastructure/x', b'b', tarfile.REGTYPE)],
        ]
        for entries in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError):
                    app.extract_verified(make_archive(entries), Path(tmp))

    def test_manifest_and_file_integrity(self):
        content = b'print("dry-run")\n'
        manifest = json.dumps({'customer_database_included': False,
                               'files': {'restore.py': hashlib.sha256(content).hexdigest()}}).encode()
        archive = make_archive([('vpn-infrastructure/restore.py', content, tarfile.REGTYPE),
                                ('vpn-infrastructure/manifest.json', manifest, tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as tmp:
            restored = app.extract_verified(archive, Path(tmp))
            self.assertEqual((restored / 'restore.py').read_bytes(), content)
        broken = make_archive([('vpn-infrastructure/restore.py', b'changed', tarfile.REGTYPE),
                               ('vpn-infrastructure/manifest.json', manifest, tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'Checksum'):
                app.extract_verified(broken, Path(tmp))

    def test_refuse_customer_database_bundle(self):
        manifest = json.dumps({'customer_database_included': True, 'files': {}}).encode()
        archive = make_archive([('vpn-infrastructure/manifest.json', manifest, tarfile.REGTYPE)])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'database'):
                app.extract_verified(archive, Path(tmp))

    def test_public_ip_validation(self):
        self.assertEqual(app.public_ip('8.8.8.8'), '8.8.8.8')
        for address in ['127.0.0.1', '192.168.1.1', '::1', 'not-an-ip']:
            with self.assertRaises(RuntimeError):
                app.public_ip(address)

    def test_published_checksums(self):
        config = json.loads((BASE / 'bundle.json').read_text())
        self.assertEqual(hashlib.sha256((BASE / 'infrastructure.enc').read_bytes()).hexdigest(),
                         config['encrypted_sha256'])
        shell = (BASE / 'install.sh').read_text(encoding='utf-8')
        for filename, name in [('bootstrap.py', 'BOOTSTRAP_SHA256'), ('bundle.json', 'CONFIG_SHA256')]:
            self.assertIn(name + "='" + hashlib.sha256((BASE / filename).read_bytes()).hexdigest() + "'", shell)
        self.assertFalse(config['customer_database_included'])


if __name__ == '__main__':
    unittest.main()
