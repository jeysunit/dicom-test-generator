#!/usr/bin/env bash
# 画面の静的な物（htmx・Lucide のアイコン）を、版を固定して取り、sha256 を確かめて置く
# （docs/spec/12a_web_screens_and_cli.md 10.1）。置いた物は commit する。利用者はこれを流さなくてよい。
#
# 使い方: bash scripts/fetch_web_assets.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC="$ROOT/app/web/static"
CACHE="$ROOT/.cache/web-assets"

HTMX_VERSION="v2.0.9"
HTMX_URL="https://github.com/bigskysoftware/htmx/releases/download/$HTMX_VERSION/htmx.min.js"
HTMX_SHA256="57d9191515339922bd1356d7b2d80b1ee3b29f1b3a2c65a078bb8b2e8fd9ae5f"

LUCIDE_VERSION="1.48.0"
LUCIDE_URL="https://github.com/lucide-icons/lucide/releases/download/$LUCIDE_VERSION/lucide-icons-$LUCIDE_VERSION.zip"
LUCIDE_SHA256="e27a6b58bebc563581f89668a5a652782075a85a07568e4fd8051a17ce81dba6"
LUCIDE_LICENSE_URL="https://raw.githubusercontent.com/lucide-icons/lucide/$LUCIDE_VERSION/LICENSE"
# LICENSE の git の blob の SHA-1（GitHub の contents API の sha）
LUCIDE_LICENSE_BLOB="718bb3f0e44153809972abed31839375804bf652"
ICONS=(activity check copy info moon refresh-cw search send sun triangle-alert)

mkdir -p "$CACHE" "$STATIC/icons"

fetch() {
  local url="$1" out="$2"
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 -o "$out" "$url"
}

check_sha256() {
  local file="$1" expected="$2"
  local actual
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
  if [[ "$actual" != "$expected" ]]; then
    echo "sha256 mismatch: $file (expected $expected, got $actual)" >&2
    exit 1
  fi
}

fetch "$HTMX_URL" "$CACHE/htmx.min.js"
check_sha256 "$CACHE/htmx.min.js" "$HTMX_SHA256"
cp "$CACHE/htmx.min.js" "$STATIC/htmx.min.js"

fetch "$LUCIDE_URL" "$CACHE/lucide.zip"
check_sha256 "$CACHE/lucide.zip" "$LUCIDE_SHA256"
python3 - "$CACHE/lucide.zip" "$STATIC/icons" "${ICONS[@]}" <<'PY'
import sys
import zipfile
from pathlib import Path

archive, target, *names = sys.argv[1:]
with zipfile.ZipFile(archive) as zf:
    members = {Path(info.filename).name: info for info in zf.infolist() if not info.is_dir()}
    for name in names:
        info = members.get(f"{name}.svg")
        if info is None:
            sys.exit(f"icon not found in the archive: {name}.svg")
        Path(target, f"{name}.svg").write_bytes(zf.read(info))
PY

fetch "$LUCIDE_LICENSE_URL" "$CACHE/LICENSE"
actual_blob="$(git hash-object "$CACHE/LICENSE")"
if [[ "$actual_blob" != "$LUCIDE_LICENSE_BLOB" ]]; then
  echo "Lucide LICENSE does not match the pinned blob ($actual_blob)" >&2
  exit 1
fi
cp "$CACHE/LICENSE" "$STATIC/icons/LICENSE"

echo "htmx $HTMX_VERSION and Lucide $LUCIDE_VERSION icons are in $STATIC"
