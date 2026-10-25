"""CT の線量の報告（X-Ray Radiation Dose SR）の内容の木（ADR-0029）.

PS3.16 の TID 10011「CT Radiation Dose」の、必須（M）と、必須の条件を満たす（MC）
行だけを作る最小の形。TID 10012「CT Accumulated Dose Data」と、撮影ごとの
TID 10013「CT Irradiation Event Data」を含む。値は架空で、実際の線量ではない。
通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.valuerep import format_number_as_ds

from .exceptions import DICOMBuildError
from .models import SeriesConfig
from .series_layout import dose_events, series_dose

# X-Ray Radiation Dose SR Storage の SOP Class UID（PS3.4 B.5）
XRAY_RADIATION_DOSE_SR_STORAGE = "1.2.840.10008.5.1.4.1.1.88.67"

CODE_DCM = "DCM"
CODE_SCT = "SCT"
CODE_UCUM = "UCUM"
TEMPLATE_RESOURCE = "DCMR"
TEMPLATE_ID = "10011"
# 撮影の日時の書式（DT。PS3.5 6.2）
DATETIME_FORMAT = "%Y%m%d%H%M%S"
SECONDS_PER_EVENT = 30

# 架空の撮影条件（実際の装置の値ではない）
EXPOSURE_TIME_S = 10.0
SINGLE_COLLIMATION_MM = 0.625
TOTAL_COLLIMATION_MM = 40.0
PITCH_FACTOR = 0.9
KVP = 120.0
MAX_TUBE_CURRENT_MA = 400.0
TUBE_CURRENT_MA = 250.0
EXPOSURE_TIME_PER_ROTATION_S = 0.5

# Code Sequence の三つ組（値・体系・意味）
Code = tuple[str, str, str]
PROCEDURE_REPORTED: Code = ("121058", CODE_DCM, "Procedure reported")
CT_XRAY: Code = ("77477000", CODE_SCT, "Computed Tomography X-Ray")
REPORT_TITLE: Code = ("113701", CODE_DCM, "X-Ray Radiation Dose Report")
OBSERVER_TYPE: Code = ("121005", CODE_DCM, "Observer Type")
DEVICE: Code = ("121007", CODE_DCM, "Device")
DEVICE_OBSERVER_UID: Code = ("121012", CODE_DCM, "Device Observer UID")
START_OF_IRRADIATION: Code = ("113809", CODE_DCM, "Start of X-Ray Irradiation")
END_OF_IRRADIATION: Code = ("113810", CODE_DCM, "End of X-Ray Irradiation")
SCOPE_OF_ACCUMULATION: Code = ("113705", CODE_DCM, "Scope of Accumulation")
SCOPE_STUDY: Code = ("113014", CODE_DCM, "Study")
STUDY_INSTANCE_UID: Code = ("110180", CODE_DCM, "Study Instance UID")
ACCUMULATED_DOSE: Code = ("113811", CODE_DCM, "CT Accumulated Dose Data")
TOTAL_EVENTS: Code = ("113812", CODE_DCM, "Total Number of Irradiation Events")
DLP_TOTAL: Code = ("113813", CODE_DCM, "CT Dose Length Product Total")
CT_ACQUISITION: Code = ("113819", CODE_DCM, "CT Acquisition")
TARGET_REGION: Code = ("123014", CODE_DCM, "Target Region")
ENTIRE_BODY: Code = ("38266002", CODE_SCT, "Entire body")
ACQUISITION_TYPE: Code = ("113820", CODE_DCM, "CT Acquisition Type")
SPIRAL: Code = ("116152004", CODE_SCT, "Spiral Acquisition")
STATIONARY: Code = ("113806", CODE_DCM, "Stationary Acquisition")
IRRADIATION_EVENT_UID: Code = ("113769", CODE_DCM, "Irradiation Event UID")
ACQUISITION_PARAMETERS: Code = ("113822", CODE_DCM, "CT Acquisition Parameters")
EXPOSURE_TIME: Code = ("113824", CODE_DCM, "Exposure Time")
SCANNING_LENGTH: Code = ("113825", CODE_DCM, "Scanning Length")
EXPOSED_RANGE: Code = ("113899", CODE_DCM, "Exposed Range")
SINGLE_COLLIMATION: Code = ("113826", CODE_DCM, "Nominal Single Collimation Width")
TOTAL_COLLIMATION: Code = ("113827", CODE_DCM, "Nominal Total Collimation Width")
PITCH: Code = ("113828", CODE_DCM, "Pitch Factor")
NUMBER_OF_SOURCES: Code = ("113823", CODE_DCM, "Number of X-Ray Sources")
SOURCE_PARAMETERS: Code = ("113831", CODE_DCM, "CT X-Ray Source Parameters")
SOURCE_ID: Code = ("113832", CODE_DCM, "Identification of the X-Ray Source")
KVP_CODE: Code = ("113733", CODE_DCM, "KVP")
MAX_TUBE_CURRENT: Code = ("113833", CODE_DCM, "Maximum X-Ray Tube Current")
TUBE_CURRENT: Code = ("113734", CODE_DCM, "X-Ray Tube Current")
TIME_PER_ROTATION: Code = ("113834", CODE_DCM, "Exposure Time per Rotation")
CT_DOSE: Code = ("113829", CODE_DCM, "CT Dose")
MEAN_CTDIVOL: Code = ("113830", CODE_DCM, "Mean CTDIvol")
CTDIW_PHANTOM: Code = ("113835", CODE_DCM, "CTDIw Phantom Type")
BODY_PHANTOM: Code = ("113691", CODE_DCM, "IEC 320mm Body CT Dosimetry Phantom")
DLP: Code = ("113838", CODE_DCM, "DLP")
SOURCE_OF_DOSE: Code = ("113854", CODE_DCM, "Source of Dose Information")
AUTOMATED_COLLECTION: Code = ("113856", CODE_DCM, "Automated Data Collection")

UNIT_EVENTS: Code = ("{events}", CODE_UCUM, "events")
UNIT_SOURCES: Code = ("{X-Ray sources}", CODE_UCUM, "X-Ray sources")
UNIT_RATIO: Code = ("{ratio}", CODE_UCUM, "ratio")
UNIT_MGY: Code = ("mGy", CODE_UCUM, "mGy")
UNIT_MGY_CM: Code = ("mGy.cm", CODE_UCUM, "mGy.cm")
UNIT_KV: Code = ("kV", CODE_UCUM, "kV")
UNIT_MA: Code = ("mA", CODE_UCUM, "mA")
UNIT_S: Code = ("s", CODE_UCUM, "s")
UNIT_MM: Code = ("mm", CODE_UCUM, "mm")


@dataclass(frozen=True)
class DoseEvent:
    """線量の報告に載せる撮影1回（位置決めか軸位のシリーズ1つ）."""

    series: SeriesConfig
    uid: str
    ctdi_vol_mgy: float
    dlp_mgy_cm: float
    scanning_length_mm: float

    @property
    def spiral(self) -> bool:
        return self.series.kind == "axial"


def dose_events_of(series_list: list[SeriesConfig], event_uids: list[str]) -> list[DoseEvent]:
    """シリーズの並びから撮影を取り出す。撮影ごとの UID は呼び出し側が渡す."""
    rows = dose_events(series_list)
    if not rows:
        raise DICOMBuildError(
            "A dose report SR needs at least one localizer or axial series in the exam",
            tag="ContentSequence",
        )
    if len(event_uids) != len(rows):
        raise DICOMBuildError(
            f"Dose report needs {len(rows)} irradiation event UIDs, got {len(event_uids)}",
            tag="ContentSequence",
        )
    events = []
    for series, uid in zip(rows, event_uids, strict=True):
        ctdi, dlp = series_dose(series)
        events.append(
            DoseEvent(
                series=series,
                uid=uid,
                ctdi_vol_mgy=ctdi,
                dlp_mgy_cm=dlp,
                scanning_length_mm=series.num_images * series.slice_spacing,
            )
        )
    return events


def _code(code: Code) -> Dataset:
    value, scheme, meaning = code
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def _item(relationship: str, value_type: str, name: Code) -> Dataset:
    item = Dataset()
    item.RelationshipType = relationship
    item.ValueType = value_type
    item.ConceptNameCodeSequence = Sequence([_code(name)])
    return item


def _children(parent: Dataset, children: list[Dataset]) -> Dataset:
    parent.ContentSequence = Sequence(children)
    return parent


def _container(relationship: str, name: Code, children: list[Dataset]) -> Dataset:
    item = _item(relationship, "CONTAINER", name)
    item.ContinuityOfContent = "SEPARATE"
    return _children(item, children)


def _code_item(relationship: str, name: Code, value: Code) -> Dataset:
    item = _item(relationship, "CODE", name)
    item.ConceptCodeSequence = Sequence([_code(value)])
    return item


def _num(relationship: str, name: Code, value: float, unit: Code) -> Dataset:
    item = _item(relationship, "NUM", name)
    measured = Dataset()
    measured.NumericValue = format_number_as_ds(round(float(value), 6))
    measured.MeasurementUnitsCodeSequence = Sequence([_code(unit)])
    item.MeasuredValueSequence = Sequence([measured])
    return item


def _uidref(relationship: str, name: Code, uid: str) -> Dataset:
    item = _item(relationship, "UIDREF", name)
    item.UID = uid
    return item


def _text(relationship: str, name: Code, text: str) -> Dataset:
    item = _item(relationship, "TEXT", name)
    item.TextValue = text
    return item


def _datetime(relationship: str, name: Code, value: datetime) -> Dataset:
    item = _item(relationship, "DATETIME", name)
    item.DateTime = value.strftime(DATETIME_FORMAT)
    return item


def _event_item(event: DoseEvent) -> Dataset:
    """TID 10013「CT Irradiation Event Data」の必須の行."""
    spiral = event.spiral
    parameters = [
        _num("CONTAINS", EXPOSURE_TIME, EXPOSURE_TIME_S, UNIT_S),
        _num("CONTAINS", SCANNING_LENGTH, event.scanning_length_mm, UNIT_MM),
    ]
    if spiral:
        # Exposed Range は Spiral Acquisition のとき必須（TID 10014 の行 3）
        parameters.append(
            _num("CONTAINS", EXPOSED_RANGE, event.scanning_length_mm, UNIT_MM)
        )
    parameters += [
        _num("CONTAINS", SINGLE_COLLIMATION, SINGLE_COLLIMATION_MM, UNIT_MM),
        _num("CONTAINS", TOTAL_COLLIMATION, TOTAL_COLLIMATION_MM, UNIT_MM),
    ]
    if spiral:
        # Pitch Factor は Spiral か Sequenced のとき必須（TID 10013 の行 12）
        parameters.append(_num("CONTAINS", PITCH, PITCH_FACTOR, UNIT_RATIO))
    parameters += [
        _num("CONTAINS", NUMBER_OF_SOURCES, 1, UNIT_SOURCES),
        _container(
            "CONTAINS",
            SOURCE_PARAMETERS,
            [
                _text("CONTAINS", SOURCE_ID, "A"),
                _num("CONTAINS", KVP_CODE, KVP, UNIT_KV),
                _num("CONTAINS", MAX_TUBE_CURRENT, MAX_TUBE_CURRENT_MA, UNIT_MA),
                _num("CONTAINS", TUBE_CURRENT, TUBE_CURRENT_MA, UNIT_MA),
                _num("CONTAINS", TIME_PER_ROTATION, EXPOSURE_TIME_PER_ROTATION_S, UNIT_S),
            ],
        ),
    ]
    return _container(
        "CONTAINS",
        CT_ACQUISITION,
        [
            _code_item("CONTAINS", TARGET_REGION, ENTIRE_BODY),
            _code_item("CONTAINS", ACQUISITION_TYPE, SPIRAL if spiral else STATIONARY),
            _uidref("CONTAINS", IRRADIATION_EVENT_UID, event.uid),
            _container("CONTAINS", ACQUISITION_PARAMETERS, parameters),
            _container(
                "CONTAINS",
                CT_DOSE,
                [
                    _num("CONTAINS", MEAN_CTDIVOL, event.ctdi_vol_mgy, UNIT_MGY),
                    _code_item("CONTAINS", CTDIW_PHANTOM, BODY_PHANTOM),
                    _num("CONTAINS", DLP, event.dlp_mgy_cm, UNIT_MGY_CM),
                ],
            ),
        ],
    )


def dose_sr_content(
    events: list[DoseEvent],
    study_instance_uid: str,
    study_date: str,
    study_time: str,
    device_observer_uid: str,
) -> Dataset:
    """SR Document Content Module（PS3.3 C.17.3）の根の項目と、TID 10011 の木を作る.

    返す Dataset の属性（ValueType・ConceptNameCodeSequence・ContinuityOfContent・
    ContentTemplateSequence・ContentSequence）を、SR の Dataset にそのまま写す。
    """
    try:
        start = datetime.strptime(study_date + study_time, DATETIME_FORMAT)
    except ValueError as exc:
        raise DICOMBuildError(
            f"Invalid study date or time for the dose report: {exc}", tag="ContentSequence"
        ) from exc
    end = start + timedelta(seconds=SECONDS_PER_EVENT * len(events))
    root = Dataset()
    root.ValueType = "CONTAINER"
    root.ConceptNameCodeSequence = Sequence([_code(REPORT_TITLE)])
    root.ContinuityOfContent = "SEPARATE"
    template = Dataset()
    template.MappingResource = TEMPLATE_RESOURCE
    template.TemplateIdentifier = TEMPLATE_ID
    root.ContentTemplateSequence = Sequence([template])
    scope = _code_item("HAS OBS CONTEXT", SCOPE_OF_ACCUMULATION, SCOPE_STUDY)
    _children(scope, [_uidref("HAS PROPERTIES", STUDY_INSTANCE_UID, study_instance_uid)])
    root.ContentSequence = Sequence(
        [
            _code_item("HAS CONCEPT MOD", PROCEDURE_REPORTED, CT_XRAY),
            _code_item("HAS OBS CONTEXT", OBSERVER_TYPE, DEVICE),
            _uidref("HAS OBS CONTEXT", DEVICE_OBSERVER_UID, device_observer_uid),
            _datetime("HAS OBS CONTEXT", START_OF_IRRADIATION, start),
            _datetime("HAS OBS CONTEXT", END_OF_IRRADIATION, end),
            scope,
            _container(
                "CONTAINS",
                ACCUMULATED_DOSE,
                [
                    _num("CONTAINS", TOTAL_EVENTS, len(events), UNIT_EVENTS),
                    _num("CONTAINS", DLP_TOTAL, sum(e.dlp_mgy_cm for e in events), UNIT_MGY_CM),
                ],
            ),
            *[_event_item(event) for event in events],
            _code_item("CONTAINS", SOURCE_OF_DOSE, AUTOMATED_COLLECTION),
        ]
    )
    return root
