"""CT の線量の報告（X-Ray Radiation Dose SR）の内容の木（ADR-0031。PS3.16 TID 10011）."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydicom.dataset import Dataset

from app.core.dose_sr import (
    DEVICE_OBSERVER_UID,
    InstanceReference,
    dose_events_of,
    dose_sr_content,
    evidence_sequence,
)
from app.core.exceptions import DICOMBuildError
from app.core.models import SeriesConfig

STUDY_UID = "2.25.1"
DEVICE_UID = "2.25.2"


def _series() -> list[SeriesConfig]:
    return [
        SeriesConfig(series_number=1, num_images=1, kind="localizer"),
        SeriesConfig(series_number=2, num_images=60, kind="axial", slice_spacing=5.0),
        SeriesConfig(series_number=3, num_images=83, kind="coronal", slice_spacing=3.0),
        SeriesConfig(series_number=4, num_images=1, kind="dose_report"),
        SeriesConfig(series_number=5, num_images=1, kind="dose_sr", modality="SR"),
    ]


def _content(series: list[SeriesConfig] | None = None) -> Dataset:
    series = series or _series()
    events = dose_events_of(series, [f"2.25.1{index}" for index in range(10)][: _count(series)])
    return dose_sr_content(events, STUDY_UID, "20261025", "090000", DEVICE_UID)


def _count(series: list[SeriesConfig]) -> int:
    return sum(1 for s in series if s.kind in ("localizer", "axial"))


def _walk(item: Dataset) -> Iterator[Dataset]:
    yield item
    for child in item.get("ContentSequence", []):
        yield from _walk(child)


def _name(item: Dataset) -> str:
    return item.ConceptNameCodeSequence[0].CodeMeaning


def _find(item: Dataset, meaning: str) -> list[Dataset]:
    return [node for node in _walk(item) if _name(node) == meaning]


def _number(item: Dataset) -> tuple[float, str]:
    measured = item.MeasuredValueSequence[0]
    return float(measured.NumericValue), measured.MeasurementUnitsCodeSequence[0].CodeValue


def test_root_is_the_dose_report_container_with_the_template_id() -> None:
    root = _content()

    assert root.ValueType == "CONTAINER"
    assert root.ConceptNameCodeSequence[0].CodeValue == "113701"
    assert root.ConceptNameCodeSequence[0].CodingSchemeDesignator == "DCM"
    assert root.ContinuityOfContent == "SEPARATE"
    (template,) = root.ContentTemplateSequence
    assert (template.MappingResource, template.TemplateIdentifier) == ("DCMR", "10011")


def test_tid_10011_mandatory_rows_are_under_the_root() -> None:
    children = list(_content().ContentSequence)

    assert [(c.RelationshipType, _name(c)) for c in children[:7]] == [
        ("HAS CONCEPT MOD", "Procedure reported"),
        ("HAS OBS CONTEXT", "Observer Type"),
        ("HAS OBS CONTEXT", "Device Observer UID"),
        ("HAS OBS CONTEXT", "Start of X-Ray Irradiation"),
        ("HAS OBS CONTEXT", "End of X-Ray Irradiation"),
        ("HAS OBS CONTEXT", "Scope of Accumulation"),
        ("CONTAINS", "CT Accumulated Dose Data"),
    ]
    assert [_name(c) for c in children[-1:]] == ["Source of Dose Information"]
    procedure = children[0].ConceptCodeSequence[0]
    assert (procedure.CodeValue, procedure.CodingSchemeDesignator) == ("77477000", "SCT")
    assert children[2].UID == DEVICE_UID
    assert DEVICE_OBSERVER_UID[0] == "121012"


def test_procedure_reported_has_the_intent_row() -> None:
    """TID 10011 の行 3（Has Intent。M。値は CID 3629）."""
    (procedure,) = _find(_content(), "Procedure reported")

    (intent,) = procedure.ContentSequence
    assert intent.RelationshipType == "HAS CONCEPT MOD"
    assert intent.ValueType == "CODE"
    assert intent.ConceptNameCodeSequence[0].CodeValue == "363703001"
    assert intent.ConceptCodeSequence[0].CodeValue == "261004008"  # Diagnostic Intent


def test_scope_of_accumulation_is_the_study_with_its_uid() -> None:
    (scope,) = _find(_content(), "Scope of Accumulation")

    assert scope.ConceptCodeSequence[0].CodeValue == "113014"
    (uid_item,) = scope.ContentSequence
    assert uid_item.RelationshipType == "HAS PROPERTIES"
    assert uid_item.ConceptNameCodeSequence[0].CodeValue == "110180"
    assert uid_item.UID == STUDY_UID


def test_start_and_end_are_date_times_in_order() -> None:
    (start,) = _find(_content(), "Start of X-Ray Irradiation")
    (end,) = _find(_content(), "End of X-Ray Irradiation")

    assert start.DateTime == "20261025090000"
    assert end.DateTime > start.DateTime
    assert len(end.DateTime) == 14


def test_events_are_the_localizer_and_axial_series_only() -> None:
    root = _content()

    events = _find(root, "CT Acquisition")
    assert len(events) == 2  # 位置決め 1 + 軸位 1。冠状断と線量の画面・SR は撮影ではない
    types = [
        _find(event, "CT Acquisition Type")[0].ConceptCodeSequence[0].CodeValue
        for event in events
    ]
    # 位置決めは Constant Angle、軸位は Spiral（CID 10013）
    assert types == ["113805", "116152004"]
    uids = [_find(event, "Irradiation Event UID")[0].UID for event in events]
    assert len(set(uids)) == 2


def test_accumulated_dose_matches_the_events() -> None:
    root = _content()

    (accumulated,) = _find(root, "CT Accumulated Dose Data")
    total, events_unit = _number(_find(accumulated, "Total Number of Irradiation Events")[0])
    dlp_total, dlp_unit = _number(_find(accumulated, "CT Dose Length Product Total")[0])
    event_dlps = [_number(item)[0] for item in _find(root, "DLP")]
    assert (total, events_unit) == (2.0, "{events}")
    assert dlp_unit == "mGy.cm"
    # 軸位 60 枚 × 5mm = 30cm、CTDIvol 10 mGy で DLP 300。位置決めは 0.1 mGy × 0.5cm
    assert event_dlps == pytest.approx([0.05, 300.0])
    assert dlp_total == pytest.approx(sum(event_dlps))


def test_spiral_event_has_pitch_and_exposed_range_but_the_scout_does_not() -> None:
    scout, spiral = _find(_content(), "CT Acquisition")

    assert not _find(scout, "Pitch Factor")
    assert not _find(scout, "Exposed Range")
    assert _number(_find(spiral, "Pitch Factor")[0])[1] == "{ratio}"
    # Exposed Range は Spiral のとき必須（TID 10014 の行 3）
    assert _number(_find(spiral, "Exposed Range")[0]) == (300.0, "mm")


@pytest.mark.parametrize(
    ("meaning", "unit"),
    [
        ("Exposure Time", "s"),
        ("Scanning Length", "mm"),
        ("Nominal Single Collimation Width", "mm"),
        ("Nominal Total Collimation Width", "mm"),
        ("Number of X-Ray Sources", "{X-Ray sources}"),
        ("KVP", "kV"),
        ("Maximum X-Ray Tube Current", "mA"),
        ("X-Ray Tube Current", "mA"),
        ("Mean CTDIvol", "mGy"),
        ("DLP", "mGy.cm"),
    ],
)
def test_each_event_has_the_mandatory_numbers_with_ucum_units(meaning: str, unit: str) -> None:
    for event in _find(_content(), "CT Acquisition"):
        (item,) = _find(event, meaning)
        assert item.ValueType == "NUM"
        assert _number(item)[1] == unit
        assert item.MeasuredValueSequence[0].MeasurementUnitsCodeSequence[0].CodingSchemeDesignator == (
            "UCUM"
        )


def test_exposure_time_per_rotation_is_only_for_the_spiral() -> None:
    """TID 10013 の行 19 は Constant Angle 以外で必須。位置決めは管球が回らない."""
    scout, spiral = _find(_content(), "CT Acquisition")

    assert not _find(scout, "Exposure Time per Rotation")
    assert _number(_find(spiral, "Exposure Time per Rotation")[0]) == (0.5, "s")


def test_mr_localizer_is_not_an_irradiation_event() -> None:
    series = [
        SeriesConfig(series_number=1, num_images=3, kind="localizer", modality="MR"),
        SeriesConfig(series_number=2, num_images=10, kind="axial", modality="CT"),
        SeriesConfig(series_number=3, num_images=1, kind="dose_sr", modality="SR"),
    ]

    (event,) = dose_events_of(series, ["2.25.20"])
    assert event.series.series_number == 2
    with pytest.raises(DICOMBuildError, match="at least one localizer or axial"):
        dose_events_of(series[:1] + series[2:], [])


def test_evidence_groups_the_instances_by_study_and_series() -> None:
    refs = [
        InstanceReference("2.25.1", "2.25.31", "1.2.840.10008.5.1.4.1.1.2", "2.25.41"),
        InstanceReference("2.25.1", "2.25.31", "1.2.840.10008.5.1.4.1.1.2", "2.25.42"),
        InstanceReference("2.25.1", "2.25.32", "1.2.840.10008.5.1.4.1.1.7", "2.25.43"),
    ]

    (study,) = evidence_sequence(refs)

    assert study.StudyInstanceUID == "2.25.1"
    first, second = study.ReferencedSeriesSequence
    assert first.SeriesInstanceUID == "2.25.31"
    assert [s.ReferencedSOPInstanceUID for s in first.ReferencedSOPSequence] == [
        "2.25.41",
        "2.25.42",
    ]
    (screen,) = second.ReferencedSOPSequence
    assert screen.ReferencedSOPClassUID == "1.2.840.10008.5.1.4.1.1.7"


def test_each_event_has_the_codes_and_the_phantom() -> None:
    for event in _find(_content(), "CT Acquisition"):
        (region,) = _find(event, "Target Region")
        assert region.ConceptCodeSequence[0].CodeValue == "38266002"
        (phantom,) = _find(event, "CTDIw Phantom Type")
        code = phantom.ConceptCodeSequence[0]
        # CID 4053 の表の Code Meaning のとおり
        assert (code.CodeValue, code.CodingSchemeDesignator, code.CodeMeaning) == (
            "113691",
            "DCM",
            "IEC 320mm Body CT Dosimetry Phantom",
        )
        assert len(_find(event, "CT Acquisition Parameters")) == 1
        assert len(_find(event, "CT X-Ray Source Parameters")) == 1
        assert len(_find(event, "CT Dose")) == 1


def test_every_item_has_a_relationship_and_a_value_type() -> None:
    for node in list(_walk(_content()))[1:]:
        assert node.RelationshipType in {
            "CONTAINS",
            "HAS CONCEPT MOD",
            "HAS OBS CONTEXT",
            "HAS PROPERTIES",
        }
        assert node.ValueType in {"CONTAINER", "CODE", "NUM", "UIDREF", "DATETIME", "TEXT"}
        if node.ValueType == "CONTAINER":
            assert node.ContinuityOfContent == "SEPARATE"


def test_a_report_without_an_exposure_is_refused() -> None:
    series = [SeriesConfig(series_number=1, num_images=1, kind="dose_sr", modality="SR")]

    with pytest.raises(DICOMBuildError, match="at least one localizer or axial"):
        dose_events_of(series, [])


def test_event_uids_must_match_the_exposures() -> None:
    with pytest.raises(DICOMBuildError, match="needs 2 irradiation event UIDs"):
        dose_events_of(_series(), ["2.25.9"])


def test_invalid_study_time_is_a_build_error() -> None:
    events = dose_events_of(_series(), ["2.25.10", "2.25.11"])

    with pytest.raises(DICOMBuildError, match="Invalid study date or time"):
        dose_sr_content(events, STUDY_UID, "20261025", "9999", DEVICE_UID)
