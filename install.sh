#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE_URL='https://raw.githubusercontent.com/dinhnhanmta/awg-relay-installer/v1.0.0'
BOOTSTRAP_SHA256='4cb1ad1984889c7a90427181722ce31ad1a38710bebfe3bb26d64d597069e829'
CONFIG_SHA256='c70176b5f8d0c70b0ee4b654e01cad0f4824650ea7c77460ed5001aa9047aee8'

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
AWG relay installer — Ubuntu 24.04 amd64, chạy bằng root.
Không truyền tham số: menu chọn exit/relay/kiểm tra/đổi IP, hỏi IP và mật khẩu.
Tùy chọn: --role exit|relay|check-relay|check-exit|repoint-relay|allow-relay
          --relay-ip IP --exit-ip IP [--nic NIC] [--dry-run]
Mật khẩu nhập ẩn; không đưa mật khẩu lên dòng lệnh hoặc GitHub.
LucX do bạn tự cài, dữ liệu khách dùng Backup/Restore .db của panel.
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
  rm -f -- "$work_dir/bootstrap.py" "$work_dir/bundle.json"
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/bootstrap.py" -o "$work_dir/bootstrap.py"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 "$BASE_URL/bundle.json" -o "$work_dir/bundle.json"
printf '%s  %s\n' "$BOOTSTRAP_SHA256" "$work_dir/bootstrap.py" "$CONFIG_SHA256" "$work_dir/bundle.json" | sha256sum -c -
/usr/bin/python3 "$work_dir/bootstrap.py" "$@"
