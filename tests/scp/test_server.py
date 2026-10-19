from __future__ import annotations

from unittest.mock import Mock

import pytest
from pynetdicom import AE
from pynetdicom.sop_class import Verification

from app.core.exceptions import SCPConfigError
from app.scp.server import StorageSCP
from app.scp.models import SCPConfig

LOCALHOST = "127.0.0.1"
STATUS_SUCCESS = 0x0000


class DummyAE:
    def __init__(self, ae_title: str) -> None:
        self.ae_title = ae_title
        self.add_supported_context = Mock()
        self.start_server = Mock()
        self.shutdown = Mock()


def test_storage_scp_disabled_raises_config_error() -> None:
    config = SCPConfig(enabled=False)

    with pytest.raises(SCPConfigError, match="Storage SCP is disabled"):
        StorageSCP(config)


def test_storage_scp_enabled_initializes_instance() -> None:
    config = SCPConfig(enabled=True)

    scp = StorageSCP(config)

    assert scp.config == config
    assert scp.handler is not None
    assert scp.ae is not None


def test_storage_scp_adds_supported_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SCPConfig(
        enabled=True,
        supported_sop_classes=[
            "1.2.840.10008.5.1.4.1.1.2",
            "1.2.840.10008.5.1.4.1.1.4",
            "1.2.840.10008.5.1.4.1.1.7",
        ],
    )

    dummy_ae = DummyAE(ae_title=config.ae_title)

    monkeypatch.setattr("app.scp.server.AE", lambda ae_title: dummy_ae)

    StorageSCP(config)

    # 設定の SOP Class の分と、常に足す Verification の1つ（spec/11 の確定事項 9）
    assert dummy_ae.add_supported_context.call_count == len(config.supported_sop_classes) + 1


def test_storage_scp_start_calls_ae_start_server(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SCPConfig(enabled=True, bind_address="127.0.0.1", port=11115)
    dummy_ae = DummyAE(ae_title=config.ae_title)
    monkeypatch.setattr("app.scp.server.AE", lambda ae_title: dummy_ae)

    scp = StorageSCP(config)
    scp.start()

    dummy_ae.start_server.assert_called_once()
    args, kwargs = dummy_ae.start_server.call_args
    assert args[0] == ("127.0.0.1", 11115)
    assert kwargs["block"] is True
    assert "evt_handlers" in kwargs


def test_storage_scp_shutdown_calls_ae_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SCPConfig(enabled=True)
    dummy_ae = DummyAE(ae_title=config.ae_title)
    monkeypatch.setattr("app.scp.server.AE", lambda ae_title: dummy_ae)

    scp = StorageSCP(config)
    scp.shutdown()

    dummy_ae.shutdown.assert_called_once_with()


def test_storage_scp_supports_verification_context() -> None:
    """supported_sop_classes に無くても Verification を受ける（spec/11 の確定事項 9）."""
    scp = StorageSCP(SCPConfig(enabled=True, supported_sop_classes=["1.2.840.10008.5.1.4.1.1.2"]))

    uids = [context.abstract_syntax for context in scp.ae.supported_contexts]

    assert Verification in uids


def test_storage_scp_answers_c_echo_with_success(tmp_path) -> None:
    """pynetdicom の SCU からの C-ECHO に 0x0000 を返す（手元の空いているポート）."""
    scp = StorageSCP(
        SCPConfig(enabled=True, bind_address=LOCALHOST, storage_dir=str(tmp_path / "scp_storage"))
    )
    server = scp.ae.start_server((LOCALHOST, 0), block=False, evt_handlers=scp._evt_handlers)
    try:
        port = int(server.server_address[1])
        scu = AE(ae_title="ECHO_SCU")
        scu.add_requested_context(Verification)
        assoc = scu.associate(LOCALHOST, port, ae_title=scp.config.ae_title)
        assert assoc.is_established
        try:
            status = assoc.send_c_echo()
        finally:
            assoc.release()
    finally:
        server.shutdown()

    assert status.Status == STATUS_SUCCESS
