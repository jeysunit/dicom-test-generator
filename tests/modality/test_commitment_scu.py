"""保管の確認（Storage Commitment）の試験（docs/spec/12 の 8.3、docs/development.md の 4 章。Phase 3c）.

手元の偽の PACS（tests/modality_peers.py の CommitmentPACS）を相手に、
要求→結果→待ち行列の状態の一巡りを流す。実の PACS にはつながない。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError
from modality_peers import (
    LOCALHOST,
    REPORT_WAIT_SECONDS,
    CommitmentPACS,
    free_port,
    write_service_profile,
)
from pydicom.dataset import Dataset
from pynetdicom import AE, build_role
from pynetdicom.sop_class import StorageCommitmentPushModel

from app.core.exceptions import ModalityConfigError, ModalityError
from app.core.models import ScheduledPatient
from app.modality.commitment_scu import COMMITMENT_INSTANCE_UID
from app.modality.config import ModalityConfig
from app.modality.queue import COMMITMENT_NOT_REPORTED, QUEUE_DB_NAME, SendQueue
from app.modality.service import ExamRequest, ModalityService
from app.services.profile_loader import PROFILE_DIRS_ENV

OWN_AE = "DTG_CT01"
WAIT = 5.0
STATUS_PROCESSING_FAILURE = 0x0110
STATUS_NO_SUCH_EVENT_TYPE = 0x0113
# 1 MiB（MAX_REPORT_BYTES）を超える大きさになる参照の数（1件はおよそ 58 バイト。約 1.4 MB）
LARGE_REPORT_ITEMS = 24000


def _config(
    tmp_path: Path,
    pacs_port: int,
    listen_port: int,
    *,
    storage_commitment: bool = True,
    wait_seconds: float = 0,
    timeout_seconds: float = 600,
) -> ModalityConfig:
    return ModalityConfig.model_validate(
        {
            "ae_title": OWN_AE,
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "listen": {"bind_address": LOCALHOST, "port": listen_port},
            "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": free_port()},
            "destinations": [
                {
                    "name": "PACS_TEST",
                    "ae_title": "PACS_TEST",
                    "host": LOCALHOST,
                    "port": pacs_port,
                    "timeout_seconds": 5,
                    "storage_commitment": storage_commitment,
                    "commitment_wait_seconds": wait_seconds,
                    "commitment_timeout_seconds": timeout_seconds,
                }
            ],
            "default_destination": "PACS_TEST",
            "default_pixel_mode": "simple_text",
        }
    )


@pytest.fixture
def listen_port() -> int:
    return free_port()


@pytest.fixture
def service(
    tmp_path: Path, commitment_pacs: CommitmentPACS, listen_port: int
) -> Iterator[ModalityService]:
    commitment_pacs.listener_port = listen_port
    service = ModalityService(_config(tmp_path, commitment_pacs.port, listen_port))
    listener = service.start_commitment_listener()
    assert listener is not None
    yield service
    listener.shutdown()


def _exam_and_send(service: ModalityService, images: list[int] | None = None) -> int:
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    result = service.exam(
        ExamRequest(emergency_patient=patient, images_per_series=images or [2])
    )
    sent = service.send(result.output_dir)
    assert sent.status == "sent"
    return sent.job_id


def test_separate_association_round_trip(service, commitment_pacs) -> None:
    """要求→別の Association の結果→待ち行列の「確認済」（推奨の既定の道。8.3.1）."""
    job_id = _exam_and_send(service, [1, 2])

    state = service.request_commitment(job_id)
    assert state.status == "waiting"
    assert state.num_requested == 3

    final = service.wait_commitment(state.transaction_uid, WAIT)

    assert final.status == "confirmed"
    assert final.num_confirmed == 3
    # 相手が応答を受け取って記録するまで待つ（こちらが書いた後に相手が記録する）
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
    assert commitment_pacs.report_statuses == [0x0000]
    request = commitment_pacs.actions[0]
    assert request.TransactionUID == state.transaction_uid
    sent_uids = {str(ds.SOPInstanceUID) for ds in commitment_pacs.received}
    asked = {str(ref.ReferencedSOPInstanceUID) for ref in request.ReferencedSOPSequence}
    assert asked == sent_uids
    assert all(
        str(ref.ReferencedSOPClassUID) == "1.2.840.10008.5.1.4.1.1.2"
        for ref in request.ReferencedSOPSequence
    )
    job = service.queue.get_job(job_id)
    assert job.commitment == "confirmed"
    assert job.commitment_error == ""


def test_same_association_round_trip(tmp_path, commitment_pacs, listen_port) -> None:
    """同じ Association で返す相手：送り先に待つ秒を入れたときだけ受ける（8.3.1 の例外）."""
    commitment_pacs.report_path = "same"
    service = ModalityService(
        _config(tmp_path, commitment_pacs.port, listen_port, wait_seconds=5)
    )
    job_id = _exam_and_send(service)

    state = service.request_commitment(job_id)

    # 同じ Association で待つので、戻ったときには結果が入っている（待ち受けは立てていない）
    assert state.status == "confirmed"
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
    assert commitment_pacs.report_statuses == [0x0000]
    assert service.queue.get_job(job_id).commitment == "confirmed"


def test_partial_failure_marks_only_failed_images(service, commitment_pacs) -> None:
    job_id = _exam_and_send(service, [3])
    files = sorted(commitment_pacs.received, key=lambda ds: str(ds.SOPInstanceUID))
    commitment_pacs.fail_instance_uids = {str(files[0].SOPInstanceUID)}

    state = service.request_commitment(job_id)
    final = service.wait_commitment(state.transaction_uid, WAIT)

    assert final.status == "failed"
    assert final.num_confirmed == 2
    assert final.num_failed == 1
    job = service.queue.get_job(job_id)
    assert job.commitment == "failed"
    assert "1" in job.commitment_error


def test_event_type_one_with_failed_items_trusts_failed_list(service, commitment_pacs) -> None:
    """Event Type 1 でも Failed SOP Sequence があれば失敗にする（書いてある方を信じる）."""
    job_id = _exam_and_send(service, [2])
    commitment_pacs.fail_instance_uids = {str(commitment_pacs.received[0].SOPInstanceUID)}
    commitment_pacs.event_type = 1

    final = service.wait_commitment(service.request_commitment(job_id).transaction_uid, WAIT)

    assert final.status == "failed"
    assert final.num_failed == 1


def test_missing_items_in_report_are_failed(service, commitment_pacs) -> None:
    """要求したのに結果のどちらにも無い画像は「確認の失敗」にする."""
    job_id = _exam_and_send(service, [2])

    def drop_one(report: Dataset) -> None:
        report.ReferencedSOPSequence = report.ReferencedSOPSequence[:1]

    commitment_pacs.mutate_report = drop_one

    final = service.wait_commitment(service.request_commitment(job_id).transaction_uid, WAIT)

    assert final.status == "failed"
    assert final.num_confirmed == 1
    assert final.num_failed == 1


def _foreign_item() -> Dataset:
    foreign = Dataset()
    foreign.ReferencedSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    foreign.ReferencedSOPInstanceUID = "2.25.999"
    return foreign


def test_items_not_requested_are_ignored(service, commitment_pacs) -> None:
    """件数の上限の内なら、要求に無い組は捨てる（要求したのに無い組は失敗）."""
    job_id = _exam_and_send(service, [2])

    def replace_one(report: Dataset) -> None:
        report.ReferencedSOPSequence = [report.ReferencedSOPSequence[0], _foreign_item()]

    commitment_pacs.mutate_report = replace_one

    final = service.wait_commitment(service.request_commitment(job_id).transaction_uid, WAIT)

    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
    assert commitment_pacs.report_statuses == [0x0000]
    assert final.status == "failed"
    assert final.num_requested == 2
    assert (final.num_confirmed, final.num_failed) == (1, 1)


def test_more_references_than_requested_is_refused(service, commitment_pacs) -> None:
    """参照の件数が問うた数を超えれば、何も書かずに断る（8.3.2）."""
    job_id = _exam_and_send(service, [1])

    def add_foreign(report: Dataset) -> None:
        report.ReferencedSOPSequence = [*report.ReferencedSOPSequence, _foreign_item()]

    commitment_pacs.mutate_report = add_foreign

    service.request_commitment(job_id)
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)

    assert commitment_pacs.report_statuses == [STATUS_PROCESSING_FAILURE]
    assert service.queue.get_job(job_id).commitment == "waiting"


@pytest.mark.parametrize("transaction", ["unknown", "known"])
def test_large_report_is_refused_before_reading(
    service, commitment_pacs, listen_port, transaction, caplog
) -> None:
    """1 MiB を超える知らせは、Transaction UID を読む前に大きさで断る（8.3.2）."""
    job_id = _exam_and_send(service, [1])
    commitment_pacs.report_path = "none"
    state = service.request_commitment(job_id)
    big = Dataset()
    big.TransactionUID = state.transaction_uid if transaction == "known" else "2.25.4242"
    big.ReferencedSOPSequence = [_foreign_item() for _ in range(LARGE_REPORT_ITEMS)]
    ae = AE(ae_title="PACS_TEST")
    ae.add_requested_context(StorageCommitmentPushModel)
    assoc = ae.associate(
        LOCALHOST,
        listen_port,
        ae_title=OWN_AE,
        ext_neg=[build_role(StorageCommitmentPushModel, scp_role=True)],
    )
    assert assoc.is_established
    try:
        status, _ = assoc.send_n_event_report(
            big, 1, StorageCommitmentPushModel, COMMITMENT_INSTANCE_UID
        )
    finally:
        assoc.release()

    assert int(status.Status) == STATUS_PROCESSING_FAILURE
    assert service.queue.get_job(job_id).commitment == "waiting"
    # 件数の確かめより前に、大きさで断った
    assert "too large" in caplog.text
    assert "more references than requested" not in caplog.text


@pytest.mark.parametrize(
    ("mutate", "expected_status"),
    [
        (lambda report: setattr(report, "TransactionUID", "2.25.12345"), STATUS_PROCESSING_FAILURE),
        (lambda report: setattr(report, "TransactionUID", "../../etc/passwd"), STATUS_PROCESSING_FAILURE),
        (lambda report: delattr(report, "TransactionUID"), STATUS_PROCESSING_FAILURE),
    ],
    ids=["unknown-transaction", "not-a-uid", "missing-transaction"],
)
def test_bad_report_is_refused_and_state_stays_waiting(
    service, commitment_pacs, mutate, expected_status
) -> None:
    job_id = _exam_and_send(service, [1])
    commitment_pacs.mutate_report = mutate

    state = service.request_commitment(job_id)
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)

    assert commitment_pacs.report_statuses == [expected_status]
    assert service.queue.get_job(job_id).commitment == "waiting"
    assert service.wait_commitment(state.transaction_uid, 0.2).status == "waiting"


def test_unknown_event_type_is_refused(service, commitment_pacs) -> None:
    job_id = _exam_and_send(service, [1])
    commitment_pacs.event_type = 3

    service.request_commitment(job_id)
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)

    assert commitment_pacs.report_statuses == [STATUS_NO_SUCH_EVENT_TYPE]
    assert service.queue.get_job(job_id).commitment == "waiting"


def test_report_from_other_ae_is_refused(service, commitment_pacs) -> None:
    """別の道では、呼んできた AE が要求の送り先の AE と同じときだけ受ける（8.3.2）."""
    job_id = _exam_and_send(service, [1])
    commitment_pacs.calling_ae_title = "INTRUDER"

    service.request_commitment(job_id)
    assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)

    assert commitment_pacs.report_statuses == [STATUS_PROCESSING_FAILURE]
    assert service.queue.get_job(job_id).commitment == "waiting"


def test_listener_refuses_wrong_called_ae(service, listen_port) -> None:
    ae = AE(ae_title="PACS_TEST")
    ae.add_requested_context(StorageCommitmentPushModel)
    assoc = ae.associate(
        LOCALHOST,
        listen_port,
        ae_title="NOT_ME",
        ext_neg=[build_role(StorageCommitmentPushModel, scp_role=True)],
    )
    try:
        assert not assoc.is_established
        assert assoc.is_rejected
    finally:
        if assoc.is_established:
            assoc.release()


def test_listener_without_event_information_is_refused(service, listen_port) -> None:
    ae = AE(ae_title="PACS_TEST")
    ae.add_requested_context(StorageCommitmentPushModel)
    assoc = ae.associate(
        LOCALHOST,
        listen_port,
        ae_title=OWN_AE,
        ext_neg=[build_role(StorageCommitmentPushModel, scp_role=True)],
    )
    assert assoc.is_established
    try:
        status, _ = assoc.send_n_event_report(
            None, 1, StorageCommitmentPushModel, COMMITMENT_INSTANCE_UID
        )
    finally:
        assoc.release()
    assert int(status.Status) == STATUS_PROCESSING_FAILURE


def test_peer_down_marks_request_failed(tmp_path, listen_port, commitment_pacs) -> None:
    """N-ACTION を送れないときは「確認の失敗」にし、理由を残す（8.3.3）."""
    service = ModalityService(_config(tmp_path, commitment_pacs.port, listen_port))
    job_id = _exam_and_send(service)
    down = service.config.model_copy(
        update={
            "destinations": [
                service.config.destinations[0].model_copy(update={"port": free_port()})
            ]
        }
    )
    service_down = ModalityService(down)

    state = service_down.request_commitment(job_id)

    assert state.status == "failed"
    assert "Association" in state.error
    job = service_down.queue.get_job(job_id)
    assert job.commitment == "failed"
    assert job.commitment_error


def test_peer_refuses_action(service, commitment_pacs) -> None:
    job_id = _exam_and_send(service)
    commitment_pacs.action_status = STATUS_PROCESSING_FAILURE

    state = service.request_commitment(job_id)

    assert state.status == "failed"
    assert "0x0110" in state.error


def test_timeout_then_late_report_replaces_state(tmp_path, commitment_pacs, listen_port) -> None:
    """時間切れの後に来た結果は、その結果で置き換える（8.3.2）."""
    commitment_pacs.listener_port = listen_port
    commitment_pacs.report_path = "none"
    service = ModalityService(
        _config(tmp_path, commitment_pacs.port, listen_port, timeout_seconds=1)
    )
    listener = service.start_commitment_listener()
    try:
        job_id = _exam_and_send(service)
        state = service.request_commitment(job_id)
        _age_commitment(tmp_path, state.transaction_uid, seconds=5)

        assert service.queue.get_job(job_id).commitment == "timed_out"

        # 遅れて結果が来る（相手の最後の答えの方が確か）
        commitment_pacs.report_path = "separate"
        commitment_pacs._report(None, commitment_pacs.actions[0])
        assert commitment_pacs.report_statuses == [0x0000]
        assert service.queue.get_job(job_id).commitment == "confirmed"
    finally:
        listener.shutdown()


def test_request_only_for_sent_job(service, commitment_pacs) -> None:
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    result = service.exam(ExamRequest(emergency_patient=patient))
    job_id = service.queue.add_job(result.output_dir, "PACS_TEST", result.files)

    with pytest.raises(ModalityError):
        service.request_commitment(job_id)


def test_request_refused_when_destination_does_not_use_commitment(
    tmp_path, commitment_pacs, listen_port
) -> None:
    service = ModalityService(
        _config(tmp_path, commitment_pacs.port, listen_port, storage_commitment=False)
    )
    job_id = _exam_and_send(service)

    with pytest.raises(ModalityConfigError):
        service.request_commitment(job_id)
    assert service.queue.get_job(job_id).commitment == ""


def test_auto_commitment_after_send(tmp_path, commitment_pacs, listen_port) -> None:
    """画面のプロセス（auto_commitment）は「送れた」になったらすぐに求める（8.3.3）."""
    commitment_pacs.listener_port = listen_port
    service = ModalityService(
        _config(tmp_path, commitment_pacs.port, listen_port), auto_commitment=True
    )
    listener = service.start_commitment_listener()
    try:
        job_id = _exam_and_send(service)
        assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
        assert service.queue.get_job(job_id).commitment == "confirmed"
    finally:
        listener.shutdown()


def test_listener_not_started_without_commitment_destination(tmp_path, listen_port) -> None:
    service = ModalityService(
        _config(tmp_path, free_port(), listen_port, storage_commitment=False)
    )
    assert service.start_commitment_listener() is None


def test_listener_port_in_use_is_config_error(tmp_path, commitment_pacs, listen_port) -> None:
    first = ModalityService(_config(tmp_path, commitment_pacs.port, listen_port))
    listener = first.start_commitment_listener()
    try:
        second = ModalityService(_config(tmp_path, commitment_pacs.port, listen_port))
        with pytest.raises(ModalityConfigError):
            second.start_commitment_listener()
    finally:
        listener.shutdown()


def test_profile_without_commitment_service_is_not_requested(
    tmp_path, monkeypatch, commitment_pacs, listen_port
) -> None:
    """装置のプロファイルが保管の確認に対応しなければ求めない（docs/spec/13 の 8）."""
    write_service_profile(
        tmp_path / "profiles", "dtg_no_services", mpps=False, storage_commitment=False
    )
    monkeypatch.setenv(PROFILE_DIRS_ENV, str(tmp_path / "profiles"))
    service = ModalityService(
        _config(tmp_path, commitment_pacs.port, listen_port), auto_commitment=True
    )
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    result = service.exam(ExamRequest(emergency_patient=patient, profile="dtg_no_services"))
    sent = service.send(result.output_dir)

    assert sent.status == "sent"
    assert commitment_pacs.actions == []
    assert service.queue.get_job(sent.job_id).commitment == ""
    with pytest.raises(ModalityConfigError):
        service.request_commitment(sent.job_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commitment_wait_seconds", 61),
        ("commitment_wait_seconds", -1),
        ("commitment_timeout_seconds", 0),
        ("commitment_timeout_seconds", 86401),
    ],
)
def test_commitment_settings_out_of_range_are_refused(tmp_path, field, value) -> None:
    """設定の範囲（docs/spec/12 の 12 章）。同じ Association で長く待たせない."""
    data = _config(tmp_path, free_port(), free_port()).model_dump()
    data["destinations"][0][field] = value
    with pytest.raises(PydanticValidationError):
        ModalityConfig.model_validate(data)


def test_queue_writes_only_waiting_requests(tmp_path) -> None:
    """先に書いた方を上書きしない：結果の後の N-ACTION の失敗・2つ目の結果（8.3.2）."""
    queue = SendQueue(tmp_path / QUEUE_DB_NAME)
    job_id = queue.add_job(str(tmp_path), "PACS_TEST", ["a.dcm", "b.dcm"])
    refs = [("1.2.840.10008.5.1.4.1.1.2", "2.25.1"), ("1.2.840.10008.5.1.4.1.1.2", "2.25.2")]
    queue.add_commitment(job_id, "PACS_TEST", "PACS_TEST", "2.25.77", refs, 600)

    assert queue.record_commitment_report("2.25.77", {refs[0]}, {}) is True
    queue.fail_commitment("2.25.77", "N-ACTION timed out")
    assert queue.record_commitment_report("2.25.77", set(refs), {}) is False

    state = queue.get_commitment("2.25.77")
    assert state.status == "failed"
    assert (state.num_confirmed, state.num_failed) == (1, 1)
    assert state.error == "1 image(s) not committed"
    with closing(sqlite3.connect(tmp_path / QUEUE_DB_NAME)) as conn:
        notes = conn.execute(
            "SELECT note FROM commitment_items WHERE sop_instance_uid = '2.25.2'"
        ).fetchall()
    assert notes == [(COMMITMENT_NOT_REPORTED,)]


def _age_commitment(tmp_path: Path, transaction_uid: str, seconds: int) -> None:
    old = (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    db_path = tmp_path / "state" / QUEUE_DB_NAME
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "UPDATE commitments SET deadline = ? WHERE transaction_uid = ?",
            (old, transaction_uid),
        )
