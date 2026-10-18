from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from web_helpers import make_client


@pytest.fixture
def client(tmp_path, worklist_scp, storage_scp) -> TestClient:
    return make_client(tmp_path, worklist_scp.port, storage_scp.port)
