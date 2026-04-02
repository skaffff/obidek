#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST="letaky"
REMOTE_DIR="/var/www/obidek"
SKIP_INSTALL="false"

usage() {
  cat <<'EOF'
Usage: scripts/deploy.sh [options]

Options:
  --host <ssh-host>        SSH host alias from ~/.ssh/config (default: letaky)
  --remote-dir <path>      Remote target directory (default: /var/www/obidek)
  --skip-install           Skip pip install on remote (faster deploy)
  -h, --help               Show this help

Examples:
  scripts/deploy.sh
  scripts/deploy.sh --host letaky --remote-dir /var/www/obidek
  scripts/deploy.sh --skip-install
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="$2"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

echo "==> Syncing files to ${HOST}:${REMOTE_DIR}"
rsync -az --delete --progress \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  "$ROOT_DIR/" "${HOST}:${REMOTE_DIR}/"

echo "==> Running remote setup and menu refresh"
ssh "$HOST" "REMOTE_DIR='$REMOTE_DIR' SKIP_INSTALL='$SKIP_INSTALL' bash -s" <<'EOF'
set -euo pipefail

cd "$REMOTE_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if [[ "$SKIP_INSTALL" != "true" ]]; then
  pip install --quiet -r requirements.txt
fi

python3 scraper/update_menus.py --config config/restaurants.yaml --output data/current_menu.json

echo "Remote deploy complete: $REMOTE_DIR"
EOF

echo "==> Done"
echo "Open: https://obidek.nakashi.org"
