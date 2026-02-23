"""Storage SCP server implementation."""

from __future__ import annotations

import logging
from typing import Any

from pynetdicom import AE, evt

from app.core.exceptions import SCPConfigError
from app.scp.handler import StorageHandler
from app.scp.models import SCPConfig

logger = logging.getLogger(__name__)


class StorageSCP:
    """Storage SCP server wrapper for PyNetDICOM AE lifecycle."""

    def __init__(self, config: SCPConfig) -> None:
        if not config.enabled:
            raise SCPConfigError(
                "Storage SCP is disabled",
                {"enabled": config.enabled},
            )

        self.config = config
        self.handler = StorageHandler(config)
        self.ae = AE(ae_title=config.ae_title)

        for sop_class_uid in config.supported_sop_classes:
            self.ae.add_supported_context(sop_class_uid)

        self._evt_handlers: list[tuple[Any, Any]] = [
            (evt.EVT_C_STORE, self.handler.handle_store),
        ]

    def start(self) -> None:
        """Start Storage SCP server (blocking call)."""
        logger.info(
            "Starting Storage SCP: ae_title=%s, port=%s, storage_dir=%s",
            self.config.ae_title,
            self.config.port,
            self.config.storage_dir,
        )
        self.ae.start_server(
            (self.config.bind_address, self.config.port),
            evt_handlers=self._evt_handlers,
            block=True,
        )

    def shutdown(self) -> None:
        """Shutdown Storage SCP server."""
        self.ae.shutdown()
