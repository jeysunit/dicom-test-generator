"""ウェブの画面の試験の道具（docs/development.md の 4 章）."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from modality_peers import LOCALHOST

from app.modality.config import ModalityConfig
from app.web.app import create_app
from app.web.settings import WebConfig

OWN_AE = "DTG_CT01"
BASE_URL = "http://127.0.0.1:8080"
ORIGIN = BASE_URL
_CSRF_PATTERN = re.compile(r'name="csrf-token" content="([^"]+)"')
_KEY_PATTERN = re.compile(r'name="key" value="([0-9a-f]{10})"')


def modality_config(tmp_path: Path, worklist_port: int, storage_port: int) -> ModalityConfig:
    return ModalityConfig.model_validate(
        {
            "ae_title": OWN_AE,
            "station_name": OWN_AE,
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "worklist": {
                "ae_title": "RIS_TEST",
                "host": LOCALHOST,
                "port": worklist_port,
                "timeout_seconds": 5,
            },
            "destinations": [
                {
                    "name": "PACS_TEST",
                    "ae_title": "PACS_TEST",
                    "host": LOCALHOST,
                    "port": storage_port,
                    "timeout_seconds": 5,
                }
            ],
            "default_destination": "PACS_TEST",
            "default_pixel_mode": "simple_text",
        }
    )


def make_client(
    tmp_path: Path,
    worklist_port: int,
    storage_port: int,
    password: str | None = None,
    bind_address: str = "127.0.0.1",
) -> TestClient:
    app = create_app(
        modality_config(tmp_path, worklist_port, storage_port),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(bind_address=bind_address),
        password=password,
    )
    return TestClient(app, base_url=BASE_URL)


def csrf_token(client: TestClient, path: str = "/worklist", **kwargs) -> str:
    match = _CSRF_PATTERN.search(client.get(path, **kwargs).text)
    assert match, "the page must carry the CSRF token"
    return match.group(1)


def post_headers(token: str) -> dict[str, str]:
    """HTMX と同じ見出し：自分の住所の Origin と CSRF の token."""
    return {"Origin": ORIGIN, "X-CSRF-Token": token, "HX-Request": "true"}


def query_worklist(client: TestClient, **form: str) -> str:
    """ワークリストの画面の「ワークリスト検索」（HTMX の POST）."""
    token = csrf_token(client)
    response = client.post(
        "/worklist/query", data={"day": "today", **form}, headers=post_headers(token)
    )
    assert response.status_code == 200
    return response.text


def key_for(html: str, accession: str) -> str:
    """一覧の HTML から、受付番号の行の予約の鍵を取る."""
    for match in _KEY_PATTERN.finditer(html):
        row_end = html.find("</tr>", match.end())
        if accession in html[match.end() : row_end]:
            return match.group(1)
    raise AssertionError(f"no row for {accession}")
