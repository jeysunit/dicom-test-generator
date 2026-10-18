#!/usr/bin/env bash
# 画面の CSS（app/web/static/app.css）を Tailwind CSS の standalone の実行ファイルで作る
# （spec/12_modality_emulator.md 10.1）。Node は要らない。作った CSS は commit する。
# CI はこれを流し、commit された CSS と差が無いことを確かめる。
#
# 使い方: bash scripts/build_css.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$ROOT/.cache/tailwindcss"
VERSION="v4.3.3"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    ASSET="tailwindcss-linux-x64"
    SHA256="dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a"
    ;;
  Darwin-arm64)
    ASSET="tailwindcss-macos-arm64"
    SHA256="cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d"
    ;;
  *)
    echo "unsupported platform: $(uname -s)-$(uname -m) (add the asset and its sha256 here)" >&2
    exit 1
    ;;
esac

BIN="$CACHE/$VERSION/$ASSET"
if [[ ! -x "$BIN" ]]; then
  mkdir -p "$(dirname "$BIN")"
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 -o "$BIN.download" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"
  actual="$(sha256sum "$BIN.download" 2>/dev/null || shasum -a 256 "$BIN.download")"
  actual="${actual%% *}"
  if [[ "$actual" != "$SHA256" ]]; then
    echo "sha256 mismatch for $ASSET (expected $SHA256, got $actual)" >&2
    exit 1
  fi
  chmod +x "$BIN.download"
  mv "$BIN.download" "$BIN"
fi

"$BIN" --input "$ROOT/app/web/styles/input.css" --output "$ROOT/app/web/static/app.css" --minify
