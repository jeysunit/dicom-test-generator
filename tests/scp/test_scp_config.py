from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.exceptions import SCPConfigError
from app.scp.models import SCPConfig, load_scp_config


def test_scp_config_defaults() -> None:
    config = SCPConfig()

    assert config.enabled is False
    assert config.ae_title == "DICOM_GEN_SCP"
    assert config.port == 11112
    assert config.bind_address == "0.0.0.0"
    assert config.storage_dir == "scp_storage"
    assert config.duplicate_handling == "overwrite"
    assert config.supported_sop_classes == ["1.2.840.10008.5.1.4.1.1.2"]


@pytest.mark.parametrize("invalid_port", [1023, 65536])
def test_scp_config_invalid_port_raises_validation_error(invalid_port: int) -> None:
    with pytest.raises(ValidationError):
        SCPConfig(port=invalid_port)


def test_load_scp_config_success(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.yaml"
    config_path.write_text(
        """
storage_scp:
  enabled: true
  ae_title: TEST_SCP
  port: 11113
  bind_address: 127.0.0.1
  storage_dir: incoming
  duplicate_handling: rename
  supported_sop_classes:
    - 1.2.840.10008.5.1.4.1.1.2
    - 1.2.840.10008.5.1.4.1.1.4
""".strip(),
        encoding="utf-8",
    )

    config = load_scp_config(config_path)

    assert config.enabled is True
    assert config.ae_title == "TEST_SCP"
    assert config.port == 11113
    assert config.bind_address == "127.0.0.1"
    assert config.storage_dir == "incoming"
    assert config.duplicate_handling == "rename"
    assert config.supported_sop_classes == [
        "1.2.840.10008.5.1.4.1.1.2",
        "1.2.840.10008.5.1.4.1.1.4",
    ]


def test_load_scp_config_missing_file_raises_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(SCPConfigError, match="Configuration file not found"):
        load_scp_config(missing_path)


def test_load_scp_config_missing_storage_scp_key_raises_error(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.yaml"
    config_path.write_text("app: {}\n", encoding="utf-8")

    with pytest.raises(SCPConfigError, match="Missing 'storage_scp' section"):
        load_scp_config(config_path)


def test_load_scp_config_invalid_yaml_raises_error(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.yaml"
    config_path.write_text("storage_scp: [invalid\n", encoding="utf-8")

    with pytest.raises(SCPConfigError, match="Invalid YAML format"):
        load_scp_config(config_path)
