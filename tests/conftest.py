from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 手元の MWL・Storage の SCP（モダリティのダミーの試験。docs/development.md の 4 章）
# と、保管の確認・MPPS の偽の相手（Phase 3c。docs/spec/12 の 8.4.2）
from modality_peers import (  # noqa: E402, F401
    commitment_pacs,
    mpps_scp,
    storage_scp,
    worklist_items,
    worklist_scp,
)
from web_helpers import TEST_VERSION  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fixed_app_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", TEST_VERSION)
