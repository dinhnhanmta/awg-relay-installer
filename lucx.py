"""Install the pinned LucX release on a fresh relay; preserve existing panels."""
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import socket
import sqlite3
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path, PurePosixPath

CONFIG = Path(__file__).with_name('lucx.json')
MAIN = Path('/usr/local/x-ui')
DBDIR = Path('/etc/x-ui')
LOGDIR = Path('/var/log/x-ui')
UNIT = Path('/etc/systemd/system/x-ui.service')
PANEL_INFO = DBDIR / 'awg-installer-panel.json'
PORT = 2053


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def install_state(main=MAIN, dbdir=DBDIR, unit=UNIT):
    binary = (main / 'x-ui').is_file()
    database = (dbdir / 'x-ui.db').exists()
    if binary and database and unit.is_file():
        return 'existing'
    require(not (binary or database or unit.exists() or main.exists()),
            'Phát hiện bản LucX cài dở/dữ liệu cũ. Giữ nguyên dữ liệu; kiểm tra trước khi cài tiếp.')
    return 'fresh'


def download_verified(asset, dest):
    require(asset['url'].startswith('https://github.com/'), 'Nguồn LucX/geodata không hợp lệ.')
    digest = hashlib.sha256()
    size = 0
    req = urllib.request.Request(asset['url'], headers={'User-Agent': 'awg-relay-installer'})
    with urllib.request.urlopen(req, timeout=90) as response, dest.open('xb') as out:
        for data in iter(lambda: response.read(1024 * 1024), b''):
            size += len(data)
            require(size <= asset['bytes'], 'Gói upstream lớn hơn kích thước đã ghim.')
            digest.update(data)
            out.write(data)
    require(size == asset['bytes'] and digest.hexdigest() == asset['sha256'],
            'SHA256/kích thước LucX hoặc geodata không đúng. Chưa cài panel.')


def extract_release(archive_path, target):
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        require(len(members) < 3000 and sum(m.size for m in members) < 1024**3,
                'Gói LucX vượt giới hạn giải nén.')
        seen = set()
        for member in members:
            parts = PurePosixPath(member.name)
            require(parts.parts and parts.parts[0] == 'x-ui' and not parts.is_absolute()
                    and '..' not in parts.parts and '\\' not in member.name
                    and (member.isfile() or member.isdir()) and member.name not in seen,
                    'Đường dẫn/loại file trong LucX không hợp lệ.')
            seen.add(member.name)
            dest = target.joinpath(*parts.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True, mode=0o755)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            with dest.open('xb') as out:
                shutil.copyfileobj(archive.extractfile(member), out)
            dest.chmod(0o755 if member.mode & 0o111 else 0o644)
    folder = target / 'x-ui'
    for name in ['x-ui', 'x-ui.sh', 'x-ui.service.debian', 'bin/xray-linux-amd64']:
        require((folder / name).is_file(), 'Gói LucX thiếu thành phần: ' + name)
    return folder


def new_access(relay_ip, cert_dir):
    public = str(ipaddress.IPv4Address(relay_ip))
    path = '/' + secrets.token_urlsafe(18) + '/'
    return {'version': json.loads(CONFIG.read_text())['version'], 'url': f'https://{public}:{PORT}{path}',
            'username': 'admin_' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24),
            'port': PORT, 'base_path': path, 'cert': str(cert_dir / 'panel.crt'),
            'key': str(cert_dir / 'panel.key'), 'listen': '0.0.0.0'}


def panel_environment(dbdir, bindir, logdir):
    env = os.environ.copy()
    env.update(XUI_DB_FOLDER=str(dbdir), XUI_BIN_FOLDER=str(bindir), XUI_LOG_FOLDER=str(logdir))
    env.pop('XUI_DB_DSN', None)
    env['XUI_DB_TYPE'] = 'sqlite'
    return env


def run_logged(args, log, cwd=None, env=None):
    # Never append the argument list: panel passwords are supplied to upstream's CLI.
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    require(result.returncode == 0, 'Cài LucX thất bại; xem log cục bộ: ' + log.name)


def configure_database(binary, dbdir, bindir, logdir, info, log):
    run_logged([binary, 'setting', '-username', info['username'], '-password', info['password'],
                '-port', str(info['port']), '-webBasePath', info['base_path'],
                '-listenIP', info['listen'], '-webCert', info['cert'], '-webCertKey', info['key']],
               log, cwd=binary.parent, env=panel_environment(dbdir, bindir, logdir))
    # Upstream CLI can print an error but still return 0; verify the resulting DB.
    with closing(sqlite3.connect(dbdir / 'x-ui.db')) as db:
        # The CLI can exit with committed data still in -wal. Flush it before
        # moving only the .db out of staging, or HTTPS/login settings are lost.
        checkpoint = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        require(checkpoint[0] == 0, 'Database LucX mới vẫn đang bận; chưa chuyển file DB.')
        values = dict(db.execute('select key,value from settings'))
        user = db.execute('select username,password from users order by id limit 1').fetchone()
    expected = {'webPort': str(info['port']), 'webBasePath': info['base_path'],
                'webListen': info['listen'], 'webCertFile': info['cert'], 'webKeyFile': info['key']}
    require(user is not None and user[0] == info['username'] and all(values.get(k) == v for k, v in expected.items()),
            'LucX CLI chưa tạo đúng tài khoản/HTTPS. Chưa khởi động panel.')
    info['credential_fingerprint'] = hashlib.sha256(user[1].encode()).hexdigest()


def saved_access(info_file=PANEL_INFO, dbdir=DBDIR):
    """A retry can re-display our fresh login, never credentials invalidated by restore/edit."""
    if not info_file.is_file() or not (dbdir / 'x-ui.db').is_file():
        return None
    try:
        info = json.loads(info_file.read_text(encoding='utf-8'))
        with closing(sqlite3.connect('file:' + str(dbdir / 'x-ui.db') + '?mode=ro', uri=True)) as db:
            user = db.execute('select username,password from users order by id limit 1').fetchone()
            settings = dict(db.execute('select key,value from settings'))
        if (user and user[0] == info['username'] and
                hashlib.sha256(user[1].encode()).hexdigest() == info['credential_fingerprint'] and
                settings.get('webBasePath') == info['base_path'] and
                settings.get('webCertFile') == info['cert'] and settings.get('webPort') == str(info['port'])):
            return info
    except (OSError, ValueError, KeyError, sqlite3.Error):
        pass
    return None


def prepare_lucx(relay_ip, dry_run=False):
    if dry_run:
        print('DRY RUN: tự cài LucX đã ghim nếu chưa có; tạo panel HTTPS và tài khoản riêng; không thay đổi máy.')
        return None
    require(not Path('/sys/class/net/awg32').exists(), 'Cài relay mới chỉ dùng trên VPS mới, awg32 đang tồn tại.')
    if install_state() == 'existing':
        print('LucX đã có sẵn: giữ nguyên phiên bản, database và thiết lập đăng nhập.', flush=True)
        return None
    require(shutil.disk_usage('/usr/local').free > 800 * 1024 * 1024,
            'Cần ít nhất 800 MiB trống để tải/giải nén LucX.')
    with socket.socket() as probe:
        try:
            probe.bind(('0.0.0.0', PORT))
        except OSError as exc:
            raise RuntimeError('Cổng panel 2053 đang được dùng; chưa cài LucX.') from exc
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    subprocess.run(['apt-get', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', 'install', '-y', '--no-install-recommends', 'openssl', 'ca-certificates'], check=True)
    DBDIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOGDIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = DBDIR / 'awg-installer-lucx.log'
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    print('Tải LucX ' + config['version'] + ' chính thức (~163 MB), kiểm tra SHA256...', flush=True)
    with log_path.open('a') as log, tempfile.TemporaryDirectory(prefix='.lucx-stage-', dir='/usr/local') as stage:
        log_path.chmod(0o600)
        stage = Path(stage)
        package = stage / 'release.tar.gz'
        download_verified(config['release'], package)
        extracted = extract_release(package, stage)
        for name, asset in config['geodata'].items():
            download_verified(asset, extracted / 'bin' / name)
        cert_dir = DBDIR / 'cert'
        cert_dir.mkdir(mode=0o700, exist_ok=True)
        info = new_access(relay_ip, cert_dir)
        run_logged(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes',
                    '-days', '365', '-subj', '/CN=' + relay_ip,
                    '-addext', 'subjectAltName=IP:' + relay_ip + ',IP:127.0.0.1',
                    '-keyout', info['key'], '-out', info['cert']], log)
        Path(info['key']).chmod(0o600)
        with tempfile.TemporaryDirectory(prefix='.lucx-db-', dir=DBDIR) as dbtmp:
            configure_database(extracted / 'x-ui', Path(dbtmp), extracted / 'bin', LOGDIR, info, log)
            require(install_state() == 'fresh', 'Trạng thái máy đã thay đổi trong lúc cài; giữ nguyên dữ liệu.')
            UNIT.write_bytes((extracted / 'x-ui.service.debian').read_bytes())
            UNIT.chmod(0o644)
            shutil.copyfile(extracted / 'x-ui.sh', '/usr/bin/x-ui')
            Path('/usr/bin/x-ui').chmod(0o755)
            extracted.rename(MAIN)
            (Path(dbtmp) / 'x-ui.db').rename(DBDIR / 'x-ui.db')
            (DBDIR / 'x-ui.db').chmod(0o600)
            with PANEL_INFO.open('x') as out:
                PANEL_INFO.chmod(0o600)
                json.dump(info, out, indent=2)
            (DBDIR / 'install-source').write_text('github\n')
    return info


def finish_lucx(info):
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'x-ui.service'], check=True)
    if info is None:
        info = saved_access()
    if info is None:
        print('Hạ tầng đã sẵn sàng. Mở panel LucX hiện có và Restore .db.')
        return
    # Permit the setup panel through an already-active UFW; do not enable UFW.
    if shutil.which('ufw'):
        status = subprocess.run(['ufw', 'status'], capture_output=True, text=True)
        if 'Status: active' in status.stdout:
            subprocess.run(['ufw', 'allow', str(PORT) + '/tcp', 'comment', 'LucX setup panel'], check=True)
    context = ssl.create_default_context(cafile=info['cert'])
    local = f"https://127.0.0.1:{info['port']}{info['base_path']}"
    for _ in range(40):
        try:
            with urllib.request.urlopen(local, context=context, timeout=2) as response:
                require(response.status == 200, 'Panel HTTPS chưa sẵn sàng.')
            break
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    else:
        raise RuntimeError('Panel chưa mở được. Xem journalctl -u x-ui; thông tin đăng nhập đã lưu tại ' + str(PANEL_INFO))
    print('\nPANEL ĐÃ SẴN SÀNG — mở URL sau và Restore file .db mới nhất:')
    print('URL:', info['url'])
    print('Username:', info['username'])
    print('Password:', info['password'])
    print('HTTPS dùng chứng chỉ tự ký; trình duyệt sẽ yêu cầu chấp nhận chứng chỉ lần đầu.')
    print('Firewall nhà cung cấp cần cho TCP 2053. Thông tin lưu riêng tại:', PANEL_INFO)
    print('Khi Restore: chọn Keep host settings để giữ URL/HTTPS mới; tài khoản có thể trở về tài khoản trong backup.')
