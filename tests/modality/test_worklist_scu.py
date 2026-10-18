"""C-FIND MWL の SCU の試験（手元の MWL の SCP を相手にする。spec/12 の 14 章）."""

from __future__ import annotations

from datetime import date

import pytest
from modality_peers import LOCALHOST, free_port

from app.core.exceptions import AssociationError, ValidationError, WorklistQueryError
from app.modality.config import WorklistPeerConfig
from app.modality.worklist_scu import (
    WorklistQuery,
    add_name_wildcards,
    build_query_identifier,
    parse_date_option,
    query_worklist,
)

OWN_AE = "DTG_CT01"


def _peer(scp, timeout: float = 5.0, query_character_set: str = "ISO_IR 192") -> WorklistPeerConfig:
    return WorklistPeerConfig(
        ae_title=scp.ae_title,
        host=LOCALHOST,
        port=scp.port,
        timeout_seconds=timeout,
        query_character_set=query_character_set,
    )


def _limited_peer(scp, **limits) -> WorklistPeerConfig:
    return WorklistPeerConfig(
        ae_title=scp.ae_title, host=LOCALHOST, port=scp.port, timeout_seconds=1, **limits
    )


def test_too_many_results_are_cancelled_with_error(worklist_scp) -> None:
    worklist_scp.repeat = 50

    with pytest.raises(WorklistQueryError) as exc_info:
        query_worklist(OWN_AE, _limited_peer(worklist_scp, max_results=10), WorklistQuery())

    assert exc_info.value.details["limit"] == "max_results=10"
    assert exc_info.value.details["received"] == 10


def test_too_large_item_is_cancelled_with_error(worklist_scp) -> None:
    worklist_scp.big_value_bytes = 200_000

    with pytest.raises(WorklistQueryError) as exc_info:
        query_worklist(
            OWN_AE, _limited_peer(worklist_scp, max_item_bytes=64 * 1024), WorklistQuery()
        )

    assert exc_info.value.details["limit"] == "max_item_bytes=65536"
    assert exc_info.value.details["received"] == 0


def test_total_size_limit_is_cancelled_with_error(worklist_scp) -> None:
    worklist_scp.repeat = 50

    with pytest.raises(WorklistQueryError) as exc_info:
        query_worklist(
            OWN_AE, _limited_peer(worklist_scp, max_total_bytes=4 * 1024), WorklistQuery()
        )

    assert exc_info.value.details["limit"] == "max_total_bytes=4096"


def test_peer_ignoring_cancel_is_stopped(worklist_scp) -> None:
    worklist_scp.endless_pending = True
    worklist_scp.ignore_cancel = True

    with pytest.raises(WorklistQueryError) as exc_info:
        query_worklist(OWN_AE, _peer(worklist_scp, timeout=0.5), WorklistQuery())

    assert worklist_scp.cancelled is True
    assert exc_info.value.details["limit"] == "time"


def _today_range() -> str:
    return parse_date_option("today", date.today())


def test_parse_date_option() -> None:
    today = date(2026, 10, 18)

    assert parse_date_option("today", today) == "20261018-20261018"
    assert parse_date_option("20261019", today) == "20261019-20261019"
    assert parse_date_option("20261001-20261031", today) == "20261001-20261031"
    for bad in ("2026-10-18", "20261031-20261001", "tomorrow", ""):
        with pytest.raises(ValidationError):
            parse_date_option(bad, today)


def test_add_name_wildcards() -> None:
    assert add_name_wildcards("YAMADA^TARO") == "YAMADA*^TARO*"
    assert add_name_wildcards("YAMADA") == "YAMADA*"
    assert add_name_wildcards("YAMA*") == "YAMA*"
    assert add_name_wildcards("") == ""


def test_query_identifier_ascii_has_no_character_set() -> None:
    ds = build_query_identifier(WorklistQuery(patient_id="P000001"), "ISO_IR 192")

    assert "SpecificCharacterSet" not in ds
    assert ds.ScheduledProcedureStepSequence[0].Modality == ""
    assert "RequestedProcedureCodeSequence" in ds


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("ISO_IR 192", "ISO_IR 192"),
        ("jis", ["", "ISO 2022 IR 87"]),
        ("jis_kana", ["ISO 2022 IR 13", "ISO 2022 IR 87"]),
    ],
)
def test_query_identifier_non_ascii_uses_query_character_set(setting, expected) -> None:
    ds = build_query_identifier(WorklistQuery(patient_name="山田"), setting)

    assert ds.SpecificCharacterSet == expected
    assert str(ds.PatientName) == "山田*"


def test_query_today_and_station(worklist_scp) -> None:
    query = WorklistQuery(date_range=_today_range(), modality="CT", station_ae_title=OWN_AE)

    result = query_worklist(OWN_AE, _peer(worklist_scp), query)

    assert [item.patient_id for item in result.items] == ["P000001", "P000002"]
    assert result.partial is False
    assert result.response_character_set == ["ISO_IR 192"]
    sent = worklist_scp.queries[0].ScheduledProcedureStepSequence[0]
    assert sent.ScheduledProcedureStepStartDate == _today_range()
    assert sent.ScheduledStationAETitle == OWN_AE


def test_query_by_modality_only(worklist_scp) -> None:
    result = query_worklist(OWN_AE, _peer(worklist_scp), WorklistQuery(modality="MR"))

    assert [item.patient_id for item in result.items] == ["P000003"]


def test_query_by_patient_and_accession(worklist_scp) -> None:
    by_patient = query_worklist(OWN_AE, _peer(worklist_scp), WorklistQuery(patient_id="P000002"))
    by_accession = query_worklist(
        OWN_AE, _peer(worklist_scp), WorklistQuery(accession_number="A0003")
    )

    assert [item.accession_number for item in by_patient.items] == ["A0002"]
    assert [item.patient_id for item in by_accession.items] == ["P000003"]


def test_query_reads_values_and_empty_type2(worklist_scp) -> None:
    result = query_worklist(OWN_AE, _peer(worklist_scp), WorklistQuery(patient_id="P000002"))
    item = result.items[0]

    assert item.patient_name == "SUZUKI^HANAKO=鈴木^花子=すずき^はなこ"
    assert item.birth_date == ""
    assert item.sex == ""
    assert item.study_instance_uid == ""


@pytest.mark.parametrize(
    "character_set",
    [["", "ISO 2022 IR 87"], ["ISO 2022 IR 13", "ISO 2022 IR 87"], ["ISO_IR 192"]],
)
def test_query_reads_response_character_set(worklist_scp, character_set) -> None:
    worklist_scp.character_set = character_set

    result = query_worklist(OWN_AE, _peer(worklist_scp), WorklistQuery(patient_id="P000001"))

    assert result.response_character_set == character_set
    assert result.items[0].patient_name == "YAMADA^TARO=山田^太郎=やまだ^たろう"
    assert result.items[0].requested_procedure_description == "胸部 CT"


def test_query_with_non_ascii_name_sends_character_set(worklist_scp) -> None:
    result = query_worklist(
        OWN_AE, _peer(worklist_scp, query_character_set="jis"), WorklistQuery(patient_name="SATO")
    )

    assert result.query_non_ascii is False
    assert [item.patient_id for item in result.items] == ["P000003"]

    query_worklist(
        OWN_AE, _peer(worklist_scp, query_character_set="jis"), WorklistQuery(patient_name="佐藤")
    )
    assert list(worklist_scp.queries[-1].SpecificCharacterSet) == ["", "ISO 2022 IR 87"]


def test_endless_pending_is_cancelled_and_partial(worklist_scp) -> None:
    worklist_scp.endless_pending = True

    result = query_worklist(OWN_AE, _peer(worklist_scp, timeout=0.5), WorklistQuery())

    assert result.partial is True
    assert worklist_scp.cancelled is True
    assert len(result.items) >= 1


def test_no_response_times_out(worklist_scp) -> None:
    worklist_scp.first_response_delay = 2.0

    with pytest.raises(WorklistQueryError):
        query_worklist(OWN_AE, _peer(worklist_scp, timeout=0.5), WorklistQuery())


def test_failure_status_raises(worklist_scp) -> None:
    worklist_scp.final_status = 0xA700

    with pytest.raises(WorklistQueryError) as exc_info:
        query_worklist(OWN_AE, _peer(worklist_scp), WorklistQuery())

    assert exc_info.value.details["status"] == "0xA700"


def test_unreachable_peer_raises_association_error() -> None:
    peer = WorklistPeerConfig(
        ae_title="RIS_TEST", host=LOCALHOST, port=free_port(), timeout_seconds=1
    )

    with pytest.raises(AssociationError):
        query_worklist(OWN_AE, peer, WorklistQuery())
