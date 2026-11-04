#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE_URL='https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/v1.1.1'
BOOTSTRAP_SHA256='4060a5533bfe7aa2388ae08d8925d02f3123d144004f7d414c37a5e2e27b1f1a'
CONFIG_SHA256='21ac68b64353c3bf9f23fb473b2b449a616860dfc4ea3fd747a1cf09f1f3cefb'
LUCX_SHA256='d16418a949bd54726fd6f11c20e267b000d5bb0a2a2af2e9d8246e3daf4df5a9'
LUCX_CONFIG_SHA256='8ff92621f0f75dba65a59050cdb988c51f617acaf54ff7d727225aecc93593fd'

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
AWG relay installer — Ubuntu 24.04 amd64, chạy bằng root.
Không truyền tham số: menu chọn exit/relay/kiểm tra/đổi IP, hỏi IP và mật khẩu.
Tùy chọn: --role exit|relay|check-relay|check-exit|repoint-relay|allow-relay
          --relay-ip IP --exit-ip IP [--nic NIC] [--dry-run]
Mật khẩu nhập ẩn; không đưa mật khẩu lên dòng lệnh hoặc GitHub.
Relay tự cài LucX và in URL/đăng nhập panel; bạn chỉ Restore .db.
HELP
  exit 0
fi

[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] || { echo 'Cần Ubuntu 24.04 amd64.' >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || { echo 'Đăng nhập root để chạy bộ cài.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Bộ cài dành cho Ubuntu 24.04.' >&2; exit 1; }

dry_run=0
for arg in "$@"; do [[ "$arg" != --dry-run ]] || dry_run=1; done
if ! command -v curl >/dev/null || ! /usr/bin/python3 -c 'import cryptography' 2>/dev/null; then
  [[ "$dry_run" -eq 0 ]] || { echo 'Dry-run cần cài sẵn curl, python3 và python3-cryptography.' >&2; exit 1; }
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y --no-install-recommends ca-certificates curl python3 python3-cryptography
fi

work_dir=$(mktemp -d /root/awg-bootstrap.XXXXXXXX)
cleanup() {
  rm -f -- "$work_dir/bootstrap.py" "$work_dir/bundle.json" "$work_dir/lucx.py" "$work_dir/lucx.json"
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/bootstrap.py" -o "$work_dir/bootstrap.py"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/bundle.json" -o "$work_dir/bundle.json"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/lucx.py" -o "$work_dir/lucx.py"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/lucx.json" -o "$work_dir/lucx.json"
printf '%s  %s\n' "$BOOTSTRAP_SHA256" "$work_dir/bootstrap.py" "$CONFIG_SHA256" "$work_dir/bundle.json" "$LUCX_SHA256" "$work_dir/lucx.py" "$LUCX_CONFIG_SHA256" "$work_dir/lucx.json" | sha256sum -c -
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$work_dir/bootstrap.py" "$@"
