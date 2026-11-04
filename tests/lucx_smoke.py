"""Run ONLY on an ephemeral Ubuntu CI runner, never on a user's production VPS."""
import http.cookiejar
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lucx

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.geteuid() != 0:
    raise SystemExit('This smoke test runs only as root on an ephemeral GitHub Actions VM.')

try:
    # A real, empty LucX install. No customer backup or recovery password is used here.
    info = lucx.prepare_lucx('127.0.0.1')
    assert info is not None
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', 'x-ui'], check=True)
    context = ssl.create_default_context(cafile=info['cert'])
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                         urllib.request.HTTPCookieProcessor(cookies))
    opener.addheaders = [('X-Requested-With', 'XMLHttpRequest')]
    url = info['url']
    for _ in range(50):
        try:
            assert opener.open(url, timeout=3).status == 200
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('Fresh panel did not become available over verified HTTPS.')
    login = urllib.parse.urlencode({'username': info['username'], 'password': info['password']}).encode()
    csrf = json.load(opener.open(url + 'csrf-token', timeout=10))['obj']
    origin = urllib.parse.urlunsplit((*urllib.parse.urlsplit(url)[:2], '', '', ''))
    response = json.load(opener.open(urllib.request.Request(url + 'login', data=login,
                        headers={'X-CSRF-Token': csrf, 'Origin': origin}), timeout=10))
    assert response.get('success'), 'Fresh admin login failed'
    backup = opener.open(url + 'panel/api/server/getDb', timeout=15).read()
    assert backup.startswith(b'SQLite format 3\x00'), 'Database download did not return a real SQLite backup'
    boundary = 'test-only-lucx-restore-boundary'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="keepHostSettings"\r\n\r\ntrue\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="db"; filename="empty-panel.db"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode()
    body += backup + f'\r\n--{boundary}--\r\n'.encode()
    csrf = json.load(opener.open(url + 'csrf-token', timeout=10))['obj']
    request = urllib.request.Request(url + 'panel/api/server/importDB', data=body,
                                    headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                             'X-CSRF-Token': csrf, 'Origin': origin})
    assert json.load(opener.open(request, timeout=30)).get('success'), 'Panel DB restore failed'
    time.sleep(5)
    for _ in range(30):
        try:
            assert opener.open(url, timeout=3).status == 200
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('Panel did not return after DB import/restart')
    print('PASS: fresh pinned LucX, verified HTTPS, generated-admin login, DB backup/import, panel restart.')
except Exception:
    # Diagnostics are limited and redacted: never dump generated login or DB.
    status = subprocess.run(['systemctl', 'show', 'x-ui', '-p', 'ActiveState', '-p', 'Result',
                             '-p', 'ExecMainStatus'], capture_output=True, text=True)
    print(status.stdout)
    journal = subprocess.run(['journalctl', '-u', 'x-ui', '-n', '50', '--no-pager'],
                             capture_output=True, text=True).stdout
    for line in journal.splitlines():
        if any(word in line.lower() for word in ['error', 'failed', 'panic', 'denied', 'listen', 'certificate']):
            for field in ['username', 'password', 'base_path']:
                if 'info' in globals() and info and info.get(field):
                    line = line.replace(info[field], '<redacted>')
            print(line)
    raise
finally:
    subprocess.run(['systemctl', 'stop', 'x-ui'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
