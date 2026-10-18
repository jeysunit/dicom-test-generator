"""Association を張るときの共通の手順."""

from __future__ import annotations

from typing import Any

from pynetdicom import AE

from app.core.exceptions import AssociationError


def make_ae(own_ae_title: str, timeout_seconds: float) -> AE:
    """自分の AE を作り、ACSE・DIMSE・網の時間切れをそろえる."""
    ae = AE(ae_title=own_ae_title)
    ae.acse_timeout = timeout_seconds
    ae.dimse_timeout = timeout_seconds
    ae.network_timeout = timeout_seconds
    return ae


def association_error(assoc: Any, ae_title: str, host: str, port: int) -> AssociationError:
    """張れなかった Association の理由を AssociationError にする."""
    # pynetdicom は、つながらない（接続の拒否・時間切れ）も aborted として返す
    if getattr(assoc, "is_rejected", False):
        reason = "association rejected by the peer"
    else:
        reason = "could not connect (refused, aborted or timed out)"
    return AssociationError(
        f"Association failed: {reason}",
        {"peer": ae_title, "host": host, "port": port},
    )
