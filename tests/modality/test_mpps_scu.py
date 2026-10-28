"""MPPS（N-CREATE・N-SET）の試験（docs/spec/12 の 6.4・8.4、docs/development.md の 4 章。Phase 3c）.

手元の偽の MPPS の相手（tests/modality_peers.py の MppsRecorder）を相手にする。
"""

from __future__ import annotations

import threading
from pathlib import Path

import pydicom
import pytest
from modality_peers import (
    LOCALHOST,
    MppsRecorder,
    WorklistSCP,
    free_port,
    start_mpps_recorder,
    start_server,
    write_service_profile,
)
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep, ModalityWorklistInformationFind

from app.core.exceptions import GenerationError, ModalityConfigError, MPPSError
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery
from app.services.profile_loader import PROFILE_DIRS_ENV

OWN_AE = "DTG_CT01"
STATUS_PROCESSING_FAILURE = 0x0110
STATUS_DUPLICATE_INSTANCE = 0x0111
# 偽の相手が応答を遅らせ、この道具の時間切れ（SHORT_TIMEOUT）より後にする＝応答が失われる形
SHORT_TIMEOUT = 1.0
LOST_RESPONSE_DELAY = 1.5


def _service(
    tmp_path: Path,
    worklist_port: int,
    mpps_port: int | None,
    *,
    use_mpps: bool = True,
    max_attempts: int = 0,
    mpps_timeout: float = 5,
) -> ModalityService:
    data: dict = {
        "ae_title": OWN_AE,
        "station_name": "DTG_STATION",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": worklist_port,
            "timeout_seconds": 5,
            "use_mpps": use_mpps,
        },
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
        "retry": {"max_attempts": max_attempts},
    }
    if mpps_port is not None:
        data["mpps"] = {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": mpps_port,
            "timeout_seconds": mpps_timeout,
        }
    return ModalityService(ModalityConfig.model_validate(data))


def _scheduled_exam(service: ModalityService, accession: str = "A0001", **extra):
    items = service.query_worklist(WorklistQuery()).items
    item = next(i for i in items if i.accession_number == accession)
    return service.exam(ExamRequest(worklist_key=item.key, **extra))


def test_in_progress_then_completed(tmp_path, worklist_scp, mpps_scp: MppsRecorder) -> None:
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _scheduled_exam(service, images_per_series=[1, 2])

    assert result.mpps is not None
    assert result.mpps.state == "COMPLETED"
    assert result.mpps.sent is True
    assert result.mpps.error == ""
    uid = result.mpps.sop_instance_uid
    created = mpps_scp.created[uid]
    # N-CREATE（IN PROGRESS）の値（6.4）
    assert created.PerformedProcedureStepStatus == "IN PROGRESS"
    assert "SOPClassUID" not in created and "SOPInstanceUID" not in created
    assert created.Modality == "CT"
    assert created.PerformedStationAETitle == OWN_AE
    assert created.PerformedStationName == "DTG_STATION"
    assert created.PatientID == "P000001"
    assert str(created.PatientName) == "YAMADA^TARO=山田^太郎=やまだ^たろう"
    assert created.PerformedProcedureStepStartDate
    assert created.PerformedProcedureStepEndDate == ""
    step = created.ScheduledStepAttributesSequence[0]
    assert step.StudyInstanceUID == "2.25.100000000000000000000000000000000001"
    assert step.AccessionNumber == "A0001"
    assert step.RequestedProcedureID == "RP0001"
    assert step.ScheduledProcedureStepID == "SPS0001"
    assert step.ScheduledProtocolCodeSequence[0].CodeValue == "PROT1"
    assert created.PerformedSeriesSequence == []
    # N-SET（COMPLETED）の値：Performed Series Sequence は作った画像から
    (set_uid, modification), = mpps_scp.sets
    assert set_uid == uid
    assert modification.PerformedProcedureStepStatus == "COMPLETED"
    assert modification.PerformedProcedureStepEndDate
    assert modification.PerformedProcedureStepEndTime
    images = [pydicom.dcmread(path) for path in result.files]
    series = modification.PerformedSeriesSequence
    assert {str(item.SeriesInstanceUID) for item in series} == {
        str(ds.SeriesInstanceUID) for ds in images
    }
    referenced = {
        (str(ref.ReferencedSOPClassUID), str(ref.ReferencedSOPInstanceUID))
        for item in series
        for ref in item.ReferencedImageSequence
    }
    assert referenced == {(str(ds.SOPClassUID), str(ds.SOPInstanceUID)) for ds in images}
    assert all(ds.PerformedProcedureStepID == created.PerformedProcedureStepID for ds in images)
    records = service.list_mpps()
    assert [(r.state, r.sent) for r in records] == [("COMPLETED", True)]


def test_emergency_exam_uses_unscheduled_form(tmp_path, worklist_scp, mpps_scp) -> None:
    """予約なしは Referenced Study Sequence を空にし、Study UID は画像とそろえる（6.4・8.4.1）."""
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")

    result = service.exam(ExamRequest(emergency_patient=patient))

    created = mpps_scp.created[result.mpps.sop_instance_uid]
    step = created.ScheduledStepAttributesSequence[0]
    assert step.ReferencedStudySequence == []
    assert step.AccessionNumber == ""
    assert step.StudyInstanceUID == result.study_instance_uid
    assert created.PatientID == "E0001"


@pytest.mark.parametrize("character_set", ["utf8", "jis", "jis_kana"])
def test_unknown_patient_with_empty_alphabetic_name_reaches_mpps_and_images(
    tmp_path, worklist_scp, mpps_scp, character_set
) -> None:
    """身元不明の患者（英字が空の氏名）は、MPPS と画像に同じ仮の ID・氏名で入る（IHE PIR の Case 6）.

    RIS は MPPS の PatientName の群を番号で読むので、空の英字の群（先頭の `=`）が崩れないこと。
    """
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    name = "=不明^不明=フメイ^フメイ"
    patient = ScheduledPatient(patient_id="TMP20261026083000", patient_name=name)

    result = service.exam(ExamRequest(emergency_patient=patient, charset=character_set))

    created = mpps_scp.created[result.mpps.sop_instance_uid]
    assert created.PatientID == "TMP20261026083000"
    assert str(created.PatientName) == name
    assert created.PatientName.components[0] == ""
    image = pydicom.dcmread(next(Path(result.output_dir).rglob("*.dcm")))
    assert image.PatientID == "TMP20261026083000"
    assert str(image.PatientName) == name
    if character_set != "utf8":
        # ISO 2022 では、空の英字の群の `=` の直後に文字集合の切り替えの ESC が続く
        raw = next(Path(result.output_dir).rglob("*.dcm")).read_bytes()
        assert b"=\x1b" in raw


def test_mpps_goes_to_worklist_peer_when_no_mpps_section(tmp_path, worklist_items, mpps_scp) -> None:
    """`modality.mpps:` が無ければワークリストの相手へ送る（8.4.1）."""
    # 同じポートで MWL と MPPS を受ける偽の相手
    scp = WorklistSCP(items=worklist_items)
    ae = AE(ae_title="RIS_TEST")
    ae.add_supported_context(ModalityWorklistInformationFind)
    ae.add_supported_context(ModalityPerformedProcedureStep)
    server, port = start_server(
        ae,
        [
            (evt.EVT_C_FIND, scp.handle_find),
            (evt.EVT_N_CREATE, mpps_scp.handle_create),
            (evt.EVT_N_SET, mpps_scp.handle_set),
        ],
    )
    try:
        service = _service(tmp_path, port, None)
        result = _scheduled_exam(service)
    finally:
        server.shutdown()

    assert result.mpps.sent is True
    assert result.mpps.sop_instance_uid in mpps_scp.created


def test_generation_failure_sends_discontinued(tmp_path, worklist_scp, mpps_scp, monkeypatch) -> None:
    """N-CREATE の後に撮影が止まったら DISCONTINUED を送り、誤りはそのまま上げる（8.4.1）."""
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    def broken(*_args, **_kwargs):
        raise GenerationError("synthetic failure")

    monkeypatch.setattr(service._generator, "generate", broken)

    with pytest.raises(GenerationError):
        _scheduled_exam(service)

    (uid, modification), = mpps_scp.sets
    assert uid in mpps_scp.created
    assert modification.PerformedProcedureStepStatus == "DISCONTINUED"
    # 画像が無くても Performed Series Sequence を空にしない（PS3.4 F.7.2 の表 F.7.2-1 の Note 2）
    (series,) = modification.PerformedSeriesSequence
    assert list(series.ReferencedImageSequence) == []
    assert [(r.state, r.sent) for r in service.list_mpps()] == [("DISCONTINUED", True)]


def test_peer_down_keeps_messages_and_retry_sends_in_order(tmp_path, worklist_scp, mpps_scp) -> None:
    """相手が落ちていても撮影は止めず、知らせを残して `mpps retry` で N-CREATE→N-SET の順に送る."""
    down_port = free_port()
    service = _service(tmp_path, worklist_scp.port, down_port)

    result = _scheduled_exam(service)

    assert len(result.files) == 1
    assert result.mpps.sent is False
    assert "Association" in result.mpps.error
    assert [(r.state, r.sent) for r in service.list_mpps()] == [("COMPLETED", False)]

    # 落ちていた相手が同じポートで戻る（送信先は行に固定。8.4.1）
    back, server = start_mpps_recorder(down_port)
    try:
        retried = service.retry_mpps()
    finally:
        server.shutdown()

    assert [(r.state, r.sent) for r in retried] == [("COMPLETED", True)]
    uid = result.mpps.sop_instance_uid
    assert back.created[uid].PerformedProcedureStepStatus == "IN PROGRESS"
    # 届いた順（偽の相手は、知らない Instance への N-SET を 0x0112 で断る）
    assert back.events == [("N-CREATE", uid, 0x0000), ("N-SET", uid, 0x0000)]
    assert mpps_scp.events == []
    assert service.retry_mpps() == []


def test_retry_goes_to_the_original_peer_after_config_change(
    tmp_path, worklist_scp, mpps_scp
) -> None:
    """設定の送信先を替えても、送り直しは行に固定した元の相手へ送る（新しい相手には送らない）."""
    down_port = free_port()
    _scheduled_exam(_service(tmp_path, worklist_scp.port, down_port))
    changed = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    with pytest.raises(MPPSError):
        changed.retry_mpps()

    assert mpps_scp.events == []
    record = changed.list_mpps()[0]
    assert (record.peer_host, record.peer_port) == (LOCALHOST, down_port)


def test_peer_refuses_create(tmp_path, worklist_scp, mpps_scp) -> None:
    """相手が Failure を返したら、N-SET を送らずに残す。撮影は止めない."""
    mpps_scp.create_statuses = [STATUS_PROCESSING_FAILURE]
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _scheduled_exam(service)

    assert result.files
    assert result.mpps.sent is False
    assert "0x0110" in result.mpps.error
    assert mpps_scp.sets == []


def test_peer_refuses_set(tmp_path, worklist_scp, mpps_scp) -> None:
    mpps_scp.set_status = STATUS_PROCESSING_FAILURE
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _scheduled_exam(service)

    assert result.mpps.sop_instance_uid in mpps_scp.created
    assert result.mpps.sent is False
    assert "0x0110" in result.mpps.error


def test_retry_treats_duplicate_create_as_sent(tmp_path, worklist_scp, mpps_scp) -> None:
    """N-CREATE が届いて応答だけ失われたとき、`mpps retry` の 0x0111 を送れた扱いにする（8.4.1）."""
    mpps_scp.create_delay_first = LOST_RESPONSE_DELAY
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port, mpps_timeout=SHORT_TIMEOUT)
    result = _scheduled_exam(service)
    assert result.mpps.sent is False

    retried = service.retry_mpps()

    uid = result.mpps.sop_instance_uid
    assert [(r.state, r.sent) for r in retried] == [("COMPLETED", True)]
    assert mpps_scp.events == [
        ("N-CREATE", uid, 0x0000),
        ("N-CREATE", uid, STATUS_DUPLICATE_INSTANCE),
        ("N-SET", uid, 0x0000),
    ]


def test_immediate_retry_treats_duplicate_create_as_sent(tmp_path, worklist_scp, mpps_scp) -> None:
    """すぐの2回目（`retry.max_attempts`）も送り直しなので、0x0111 を送れた扱いにする."""
    mpps_scp.create_delay_first = LOST_RESPONSE_DELAY
    service = _service(
        tmp_path, worklist_scp.port, mpps_scp.port, max_attempts=1, mpps_timeout=SHORT_TIMEOUT
    )

    result = _scheduled_exam(service)

    uid = result.mpps.sop_instance_uid
    assert result.mpps.sent is True
    assert [event[:2] for event in mpps_scp.events] == [
        ("N-CREATE", uid),
        ("N-CREATE", uid),
        ("N-SET", uid),
    ]


def test_retry_treats_final_set_refusal_as_sent(tmp_path, worklist_scp, mpps_scp) -> None:
    """N-SET が届いて応答だけ失われたとき、送り直しの 0x0110（終わった MPPS）を送れた扱いにする."""
    mpps_scp.set_delay_first = LOST_RESPONSE_DELAY
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port, mpps_timeout=SHORT_TIMEOUT)
    result = _scheduled_exam(service)
    assert result.mpps.sent is False

    retried = service.retry_mpps()

    uid = result.mpps.sop_instance_uid
    assert [(r.state, r.sent) for r in retried] == [("COMPLETED", True)]
    assert mpps_scp.events[-1] == ("N-SET", uid, STATUS_PROCESSING_FAILURE)
    assert len(mpps_scp.sets) == 1
    assert service.retry_mpps() == []


def test_first_set_refusal_is_not_treated_as_sent(tmp_path, worklist_scp, mpps_scp) -> None:
    """最初の N-SET の 0x0110 は失敗のまま（送れた扱いにするのは送り直しだけ）."""
    mpps_scp.set_status = STATUS_PROCESSING_FAILURE
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    assert _scheduled_exam(service).mpps.sent is False


def test_retry_of_forced_mpps_works_when_config_does_not_use_mpps(tmp_path, worklist_scp, mpps_scp) -> None:
    """`exam --mpps` で作って送れなかった知らせは、設定が使わない形でも送り直せる."""
    down_port = free_port()
    down = _service(tmp_path, worklist_scp.port, down_port, use_mpps=False)
    assert _scheduled_exam(down, mpps=True).mpps.sent is False

    back, server = start_mpps_recorder(down_port)
    try:
        retried = down.retry_mpps()
    finally:
        server.shutdown()
    assert [(r.state, r.sent) for r in retried] == [("COMPLETED", True)]
    assert len(back.sets) == 1


def test_retry_does_not_accept_processing_failure_from_a_failing_peer(
    tmp_path, worklist_scp, mpps_scp
) -> None:
    """相手が N-SET に 0x0110 を返し続けるなら、送り直しでも送れた扱いにしない（8.4.1）."""
    mpps_scp.set_status = STATUS_PROCESSING_FAILURE
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port, max_attempts=1)

    result = _scheduled_exam(service)
    assert result.mpps.sent is False

    with pytest.raises(MPPSError):
        service.retry_mpps()
    assert [(r.state, r.sent) for r in service.list_mpps()] == [("COMPLETED", False)]
    # 撮影のときの2回（1回目とすぐの2回目）と、`mpps retry` の2回
    assert [event[2] for event in mpps_scp.events if event[0] == "N-SET"] == [
        STATUS_PROCESSING_FAILURE
    ] * 4


def test_held_set_is_sent_as_a_first_send(tmp_path, worklist_scp, mpps_scp) -> None:
    """N-CREATE を待って保留した N-SET の初回の 0x0110 は失敗のまま（前に送っていない）."""
    mpps_scp.create_statuses = [STATUS_PROCESSING_FAILURE]
    mpps_scp.set_status = STATUS_PROCESSING_FAILURE
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    result = _scheduled_exam(service)
    assert result.mpps.sent is False
    assert [event[0] for event in mpps_scp.events] == ["N-CREATE"]

    with pytest.raises(MPPSError):
        service.retry_mpps()

    record = service.list_mpps()[0]
    assert record.create_sent is True
    assert record.set_sent is False
    assert [event[:1] + event[2:] for event in mpps_scp.events] == [
        ("N-CREATE", STATUS_PROCESSING_FAILURE),
        ("N-CREATE", 0x0000),
        ("N-SET", STATUS_PROCESSING_FAILURE),
    ]


def test_create_failure_then_duplicate_is_not_accepted(tmp_path, worklist_scp, mpps_scp) -> None:
    """前の N-CREATE が Failure で終わっていれば、0x0111 を送れた扱いにしない."""
    mpps_scp.create_statuses = [STATUS_PROCESSING_FAILURE, STATUS_DUPLICATE_INSTANCE]
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    _scheduled_exam(service)

    with pytest.raises(MPPSError):
        service.retry_mpps()
    assert service.list_mpps()[0].create_sent is False


def test_concurrent_retries_send_each_message_once(tmp_path, worklist_scp, mpps_scp) -> None:
    """2つの手順が同時に `mpps retry` しても、同じ知らせを重ねて送らない（送る権利の札）."""
    down_port = free_port()
    _scheduled_exam(_service(tmp_path, worklist_scp.port, down_port))
    back, server = start_mpps_recorder(down_port)
    back.create_delay_first = 0.5  # 1つ目が送っている間に、2つ目が同じ行を取りに来る
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def run() -> None:
        service = _service(tmp_path, worklist_scp.port, down_port)
        barrier.wait()
        try:
            service.retry_mpps()
            outcomes.append("sent")
        except MPPSError:
            outcomes.append("skipped")

    threads = [threading.Thread(target=run) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
    finally:
        server.shutdown()

    assert sorted(outcomes) == ["sent", "skipped"]
    assert [event[0] for event in back.events] == ["N-CREATE", "N-SET"]


def test_immediate_retries_follow_retry_max_attempts(tmp_path, worklist_scp, mpps_scp) -> None:
    mpps_scp.create_statuses = [STATUS_PROCESSING_FAILURE]
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port, max_attempts=1)

    result = _scheduled_exam(service)

    assert result.mpps.sent is True


def test_retry_with_mpps_disabled_is_config_error(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, None, use_mpps=False)
    with pytest.raises(ModalityConfigError):
        service.retry_mpps()


def test_retry_failing_raises_mpps_error(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, free_port())
    _scheduled_exam(service)

    with pytest.raises(MPPSError):
        service.retry_mpps()


def test_mpps_off_by_config_and_override(tmp_path, worklist_scp, mpps_scp) -> None:
    off = _service(tmp_path, worklist_scp.port, mpps_scp.port, use_mpps=False)
    assert _scheduled_exam(off).mpps is None
    assert mpps_scp.created == {}

    # 同じ予約の2回目以降は追加撮影（docs/spec/12 の 6.3）
    forced = _scheduled_exam(off, mpps=True, append=True)
    assert forced.mpps is not None and forced.mpps.sent is True

    on = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    assert _scheduled_exam(on, mpps=False, append=True).mpps is None


def test_profile_without_mpps_service_does_not_send(
    tmp_path, monkeypatch, worklist_scp, mpps_scp
) -> None:
    """装置のプロファイルが MPPS に対応しなければ、設定で選んでいても送らない（docs/spec/13 の 8）."""
    write_service_profile(tmp_path / "profiles", "dtg_no_mpps", mpps=False, storage_commitment=False)
    write_service_profile(tmp_path / "profiles", "dtg_with_mpps", mpps=True, storage_commitment=False)
    monkeypatch.setenv(PROFILE_DIRS_ENV, str(tmp_path / "profiles"))
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    assert _scheduled_exam(service, profile="dtg_no_mpps", mpps=True).mpps is None
    # 同じ予約の2回目は追加撮影（docs/spec/12 の 6.3）
    assert _scheduled_exam(service, profile="dtg_with_mpps", append=True).mpps.sent is True


def test_untrusted_values_do_not_escape(tmp_path, worklist_scp, worklist_items, mpps_scp) -> None:
    """予約の値（相手から来る値）は MPPS の値に写すだけで、パスにもログの書式にも使わない."""
    evil = dict(worklist_items[0])
    evil["accession_number"] = "../../x"
    evil["patient_id"] = "<script>"
    worklist_scp.items = [evil]
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _scheduled_exam(service, accession="../../x")

    created = mpps_scp.created[result.mpps.sop_instance_uid]
    assert created.ScheduledStepAttributesSequence[0].AccessionNumber == "../../x"
    assert created.PatientID == "<script>"
    output_root = (tmp_path / "output").resolve()
    assert Path(result.output_dir).resolve().parent == output_root
