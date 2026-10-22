#!/usr/bin/env python3
"""Web 画面のキャプチャを docs/images/ に PNG で保存する.

使い方:
    pip install playwright
    playwright install chromium
    DTG_URL=http://127.0.0.1:8080 DTG_WEB_PASSWORD_FILE=/path/to/password.txt \\
        python scripts/capture_screens.py

- 認証が無い画面（ループバックで待ち受け、パスワードのファイルが無い）なら
  DTG_WEB_PASSWORD_FILE は不要
- 撮る画面：ワークリスト（取得した後）、撮影、PACS、設定
- 画面には架空の患者の値だけが写ることを、保存した画像を見て確認する
終了コード：0=成功、2=引数・環境の誤り。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "images"
VIEWPORT = {"width": 1280, "height": 800}
USERNAME = "dtg"


def read_password() -> str | None:
    path = os.environ.get("DTG_WEB_PASSWORD_FILE")
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8").strip()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright が無い。pip install playwright と playwright install chromium を実行する",
              file=sys.stderr)
        return 2

    base_url = os.environ.get("DTG_URL", "http://127.0.0.1:8080").rstrip("/")
    password = read_password()
    credentials = {"username": USERNAME, "password": password} if password else None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, http_credentials=credentials)
        page = context.new_page()

        page.goto(f"{base_url}/worklist")
        page.get_by_role("button", name="ワークリストを取得").click()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUTPUT_DIR / "worklist.png", full_page=True)

        page.goto(f"{base_url}/exam")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUTPUT_DIR / "exam.png", full_page=True)

        page.goto(f"{base_url}/pacs")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUTPUT_DIR / "pacs.png", full_page=True)

        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=OUTPUT_DIR / "settings.png", full_page=True)

        browser.close()

    for name in ("worklist", "exam", "pacs", "settings"):
        path = OUTPUT_DIR / f"{name}.png"
        print(f"{path} {path.stat().st_size // 1024} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
