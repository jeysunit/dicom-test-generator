"""C-STORE・C-ECHO の SCU（spec/12_modality_emulator.md 8 章）."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydicom import dcmread
from pydicom.errors import InvalidDicomError
from pynetdicom.sop_class import Verification

from app.core.exceptions import AssociationError, StoreError

from .association import association_error, make_ae
from .config import NodeConfig

logger = logging.getLogger(__name__)

STATUS_SUCCESS = 0x0000
# C-STORE の Warning（PS3.4 B.2.3）。送れた扱いにする
WARNING_STATUSES = frozenset({0x0001, 0xB000, 0xB006, 0xB007})
MAX_PRESENTATION_CONTEXTS = 128
MILLISECONDS_PER_SECOND = 1000

StoreOutcome = Literal["success", "warning", "failure"]


class EchoResult(BaseModel):
    model_config = {"frozen": True}

    ae_title: str
    host: str
    port: int
    elapsed_ms: int
    status: int


class StoreFileResult(BaseModel):
    model_config = {"frozen": True}

    path: str
    sop_instance_uid: str = ""
    sop_class_uid: str = ""  # 保管の確認で使う（Phase 3c。8.3.3）
    status: int | None = None
    outcome: StoreOutcome
    reason: str = ""

    @property
    def sent(self) -> bool:
        return self.outcome != "failure"


def echo(own_ae_title: str, node: NodeConfig, timeout_seconds: float) -> EchoResult:
    """C-ECHO で疎通を確かめる。つながらない・Success 以外なら AssociationError."""
    ae = make_ae(own_ae_title, timeout_seconds)
    ae.add_requested_context(Verification)
    started = time.monotonic()
    assoc = ae.associate(node.host, node.port, ae_title=node.ae_title)
    if not assoc.is_established:
        raise association_error(assoc, node.ae_title, node.host, node.port)
    try:
        status = assoc.send_c_echo()
    finally:
        if assoc.is_established:
            assoc.release()
    elapsed_ms = int((time.monotonic() - started) * MILLISECONDS_PER_SECOND)
    if not status:
        raise AssociationError(
            "C-ECHO timed out or the association was aborted",
            {"peer": node.ae_title, "host": node.host, "port": node.port},
        )
    code = int(status.Status)
    if code != STATUS_SUCCESS:
        raise AssociationError(
            f"C-ECHO failed with status 0x{code:04X}",
            {"peer": node.ae_title, "status": f"0x{code:04X}"},
        )
    logger.info("C-ECHO ok: peer=%s elapsed_ms=%s", node.ae_title, elapsed_ms)
    return EchoResult(
        ae_title=node.ae_title, host=node.host, port=node.port, elapsed_ms=elapsed_ms, status=code
    )


def store_files(
    own_ae_title: str,
    node: NodeConfig,
    paths: Sequence[Path],
    timeout_seconds: float,
    on_progress: Callable[[], None] | None = None,
) -> list[StoreFileResult]:
    """1つの検査の画像を、1つの Association で送る（8.2）.

    Association を張れなければ AssociationError。ファイルごとの成否は結果に残す。
    `on_progress` は1ファイルを送るたびに呼ぶ（待ち行列の送信中の時刻を進める）。
    そこで例外が起きたら（送る権利を失ったら）、残りを送らずに Association を閉じて上げる。
    """
    readable, results = _read_headers(paths)
    contexts: dict[str, set[str]] = {}
    for _path, _sop_uid, sop_class, transfer_syntax in readable:
        contexts.setdefault(sop_class, set()).add(transfer_syntax)
    if len(contexts) > MAX_PRESENTATION_CONTEXTS:
        raise StoreError(
            "Too many SOP Classes for one association",
            {"sop_classes": len(contexts), "max": MAX_PRESENTATION_CONTEXTS},
        )
    if not readable:
        return results

    ae = make_ae(own_ae_title, timeout_seconds)
    for sop_class, transfer_syntaxes in contexts.items():
        ae.add_requested_context(sop_class, sorted(transfer_syntaxes))
    logger.info(
        "C-STORE start: peer=%s files=%s", node.ae_title, len(readable)
    )
    assoc = ae.associate(node.host, node.port, ae_title=node.ae_title)
    if not assoc.is_established:
        raise association_error(assoc, node.ae_title, node.host, node.port)
    try:
        for path, sop_uid, sop_class, _ts in readable:
            result = _store_one(assoc, path, sop_uid)
            # 保管の確認で問う組のため、SOP Class UID も残す（8.3.3）
            results.append(result.model_copy(update={"sop_class_uid": sop_class}))
            if on_progress is not None:
                on_progress()
    finally:
        if assoc.is_established:
            assoc.release()
    sent = sum(1 for result in results if result.sent)
    logger.info("C-STORE done: peer=%s sent=%s/%s", node.ae_title, sent, len(results))
    return results


def _read_headers(
    paths: Sequence[Path],
) -> tuple[list[tuple[Path, str, str, str]], list[StoreFileResult]]:
    readable: list[tuple[Path, str, str, str]] = []
    failures: list[StoreFileResult] = []
    for path in paths:
        try:
            ds = dcmread(path, stop_before_pixels=True)
            sop_class = str(ds.SOPClassUID)
            sop_uid = str(ds.SOPInstanceUID)
            transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
        except (OSError, InvalidDicomError, AttributeError) as exc:
            failures.append(
                StoreFileResult(path=str(path), outcome="failure", reason=f"unreadable file: {exc}")
            )
            continue
        readable.append((path, sop_uid, sop_class, transfer_syntax))
    return readable, failures


def _store_one(assoc: object, path: Path, sop_uid: str) -> StoreFileResult:
    if not assoc.is_established:  # type: ignore[attr-defined]
        return StoreFileResult(
            path=str(path), sop_instance_uid=sop_uid, outcome="failure", reason="association lost"
        )
    try:
        status = assoc.send_c_store(path)  # type: ignore[attr-defined]
    except (ValueError, RuntimeError) as exc:
        return StoreFileResult(
            path=str(path),
            sop_instance_uid=sop_uid,
            outcome="failure",
            reason=f"{type(exc).__name__}: {exc}",
        )
    if not status:
        return StoreFileResult(
            path=str(path),
            sop_instance_uid=sop_uid,
            outcome="failure",
            reason="no response (timed out or aborted)",
        )
    code = int(status.Status)
    if code == STATUS_SUCCESS:
        outcome: StoreOutcome = "success"
    elif code in WARNING_STATUSES:
        outcome = "warning"
    else:
        outcome = "failure"
    return StoreFileResult(
        path=str(path),
        sop_instance_uid=sop_uid,
        status=code,
        outcome=outcome,
        reason="" if outcome == "success" else f"status 0x{code:04X}",
    )
