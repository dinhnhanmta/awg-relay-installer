#!/usr/bin/env python3
"""Download and authenticate the private recovery payload, then run its installer."""
import argparse
import getpass
import hashlib
import io
import ipaddress
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lucx import prepare_lucx, finish_lucx

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b'AWGKIT1\0'
HEADER_SIZE = 36
ROLES = ('exit', 'relay', 'check-relay', 'check-exit', 'repoint-relay', 'allow-relay')
CONFIG_PATH = Path(__file__).with_name('bundle.json')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def decrypt(data, password):
    require(len(data) >= HEADER_SIZE + 16 and data[:8] == MAGIC, 'Sai định dạng gói mã hóa.')
    header = data[:HEADER_SIZE]
    salt, nonce = header[8:24], header[24:36]
    key = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode('utf-8'))
    try:
        return AESGCM(key).decrypt(nonce, data[HEADER_SIZE:], header)
    except InvalidTag as exc:
        raise RuntimeError('Mật khẩu không đúng hoặc gói đã bị thay đổi. Chưa chạy phục hồi.') from exc


def fetch(url, maximum=12 * 1024 * 1024):
    require(url.startswith('https://raw.githubusercontent.com/'), 'Nguồn tải không hợp lệ.')
    request = urllib.request.Request(url, headers={'User-Agent': 'awg-relay-installer'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(maximum + 1)
    require(len(data) <= maximum, 'Gói tải xuống lớn hơn giới hạn.')
    return data


def extract_verified(plain, target):
    """Only regular files under the exact expected prefix; no links or path traversal."""
    with tarfile.open(fileobj=io.BytesIO(plain), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) <= 200, 'Quá nhiều file trong gói.')
        require(sum(m.size for m in members) <= 64 * 1024 * 1024, 'Gói giải nén quá lớn.')
        seen = set()
        for member in members:
            name = PurePosixPath(member.name)
            require(member.isfile() and name.parts and name.parts[0] == 'vpn-infrastructure'
                    and not name.is_absolute() and '..' not in name.parts and '\\' not in member.name,
                    'Đường dẫn hoặc loại file không hợp lệ.')
            require(member.name not in seen, 'File trùng tên trong gói.')
            seen.add(member.name)
            path = target.joinpath(*name.parts)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open('xb') as out:
                os.chmod(path, 0o700 if member.mode & 0o111 else 0o600)
                out.write(archive.extractfile(member).read())
    root = target / 'vpn-infrastructure'
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        parts = PurePosixPath(name)
        require(not parts.is_absolute() and '..' not in parts.parts and '\\' not in name,
                'Manifest chứa đường dẫn không hợp lệ.')
        path = root.joinpath(*parts.parts)
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                'Checksum file bên trong không đúng.')
    require(manifest.get('customer_database_included') is False, 'Gói phải tách database khách hàng.')
    return root


def read_line(prompt):
    # Read from the controlling terminal even when install.sh is downloaded through curl.
    try:
        with open('/dev/tty', 'r+') as terminal:
            terminal.write(prompt)
            terminal.flush()
            result = terminal.readline()
    except OSError as exc:
        raise RuntimeError('Cần terminal tương tác hoặc truyền --role/--relay-ip/--exit-ip.') from exc
    require(bool(result), 'Terminal đã đóng.')
    return result.strip()


def public_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise RuntimeError('IP phải là IPv4 công khai.') from exc
    require(ip.is_global, 'Dùng IP công khai của VPS, không dùng IP nội bộ.')
    return str(ip)


def choose_role():
    print('Chọn công việc:\n  1. Cài exit mới\n  2. Cài relay mới\n'
          '  3. Kiểm tra relay\n  4. Kiểm tra exit\n'
          '  5. Đổi IP exit trên relay đang giữ\n  6. Cho phép IP relay mới trên exit đang giữ')
    selected = read_line('Lựa chọn [1-6]: ')
    require(selected in tuple(map(str, range(1, 7))), 'Lựa chọn không hợp lệ.')
    return ROLES[int(selected) - 1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=ROLES)
    parser.add_argument('--relay-ip')
    parser.add_argument('--exit-ip')
    parser.add_argument('--nic')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--password-file', type=Path, help='File mật khẩu cục bộ; không truyền mật khẩu trên dòng lệnh')
    parser.add_argument('--bundle-file', type=Path, help='Dùng gói mã hóa đã tải thay vì tải từ GitHub')
    args = parser.parse_args(argv)
    if not args.dry_run:
        require(sys.platform == 'linux' and os.geteuid() == 0, 'Đăng nhập root trên Ubuntu 24.04 amd64.')
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    role = args.role or choose_role()
    require(not args.dry_run or role in ('relay', 'exit'), '--dry-run dùng với relay hoặc exit.')
    needs_relay = role in ('relay', 'exit', 'allow-relay')
    needs_exit = role in ('relay', 'exit', 'repoint-relay')
    relay = public_ip(args.relay_ip or read_line('IP công khai relay: ')) if needs_relay else None
    exit_ip = public_ip(args.exit_ip or read_line('IP công khai exit: ')) if needs_exit else None
    require(not (relay and exit_ip and relay == exit_ip), 'Relay và exit phải khác VPS.')
    if args.password_file:
        require(args.password_file.is_file(), 'Không tìm thấy file mật khẩu.')
        if sys.platform == 'linux':
            require(args.password_file.stat().st_mode & 0o077 == 0, 'Đặt quyền file mật khẩu thành 600.')
        password = args.password_file.read_text(encoding='utf-8').strip()
    else:
        password = getpass.getpass('Mật khẩu khôi phục (không hiện ký tự): ')
    require(bool(password), 'Mật khẩu không được để trống.')
    data = args.bundle_file.read_bytes() if args.bundle_file else fetch(config['payload_url'])
    require(hashlib.sha256(data).hexdigest() == config['encrypted_sha256'], 'Checksum gói tải về không đúng.')
    plain = decrypt(data, password)
    del password
    require(hashlib.sha256(plain).hexdigest() == config['plaintext_sha256'], 'Checksum sau giải mã không đúng.')
    temp_parent = '/root' if sys.platform == 'linux' and os.geteuid() == 0 else None
    with tempfile.TemporaryDirectory(prefix='awg-installer-', dir=temp_parent) as tmp:
        os.chmod(tmp, 0o700)
        root = extract_verified(plain, Path(tmp))
        del plain
        command = [sys.executable, str(root / 'restore.py'), role]
        if relay:
            command += ['--relay-ip', relay]
        if exit_ip:
            command += ['--exit-ip', exit_ip]
        if args.nic:
            command += ['--nic', args.nic]
        if args.dry_run:
            command += ['--dry-run']
        print('Đã xác thực gói. Bắt đầu:', role, flush=True)
        panel_info = prepare_lucx(relay, dry_run=args.dry_run) if role == 'relay' else None
        result = subprocess.call(command)
        if result == 0 and role == 'relay' and not args.dry_run:
            finish_lucx(panel_info)
        return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, tarfile.TarError) as exc:
        print('LỖI:', exc, file=sys.stderr)
        sys.exit(1)
