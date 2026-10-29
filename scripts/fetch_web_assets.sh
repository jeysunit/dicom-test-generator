#!/usr/bin/env bash
# 画面の静的な物（htmx・Lucide の LICENSE）を、版を固定して取り、sha256 を確かめて置く
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
LUCIDE_LICENSE_URL="https://raw.githubusercontent.com/lucide-icons/lucide/$LUCIDE_VERSION/LICENSE"
# LICENSE の git の blob の SHA-1（GitHub の contents API の sha）
LUCIDE_LICENSE_BLOB="718bb3f0e44153809972abed31839375804bf652"

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

# 絵そのものは ui-kit の icons.svg に入っている。ここに置くのは、その元の Lucide の LICENSE（ISC）だけ
fetch "$LUCIDE_LICENSE_URL" "$CACHE/LICENSE"
actual_blob="$(git hash-object "$CACHE/LICENSE")"
if [[ "$actual_blob" != "$LUCIDE_LICENSE_BLOB" ]]; then
  echo "Lucide LICENSE does not match the pinned blob ($actual_blob)" >&2
  exit 1
fi
cp "$CACHE/LICENSE" "$STATIC/icons/LICENSE"

echo "htmx $HTMX_VERSION and the Lucide $LUCIDE_VERSION LICENSE are in $STATIC"
