"""予約（ワークリストの1件）から画像への値の写し方（docs/spec/12_modality_emulator.md 5.4・6 章）.

Core Engine の Pure な処理。通信・ファイル・ログを使わない。
出典は IHE RAD TF-2x Appendix A の Table A.1-1（予約どおり）と
Table A.1-2（予約なし）。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator

from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence

from .exceptions import WorklistMappingError
from .uid_format import is_valid_uid
from .worklist_charset import TEXT_VRS
from .models import (
    PATIENT_ID_MAX_LENGTH,
    Patient,
    PatientName,
    ScheduledContext,
    ScheduledPatient,
    WorklistItem,
)

WORKLIST_KEY_LENGTH = 10
WORKLIST_KEY_SEPARATOR = "|"
ACCESSION_NUMBER_MAX_LENGTH = 16
STUDY_ID_MAX_LENGTH = 16
STUDY_DESCRIPTION_MAX_LENGTH = 64
CARRIER_SEX = "O"
CARRIER_PATIENT_NAME = "SCHEDULED^PATIENT"
# Patient の患者ID は 16 字まで（job の形）。予約・緊急の患者の患者ID は 64 字（LO）まで受けるので、
# 仮の Patient には先頭の 16 字を入れる。画像の PatientID は apply_scheduled_context が全体で上書きする
CARRIER_PATIENT_ID_LENGTH = 16
_REPLACEMENT_CHAR = "�"
_UID_VR = "UI"
_BIRTH_DATE_LENGTH = 8
_VALID_SEXES = frozenset({"", "M", "F", "O"})
DS_MAX_LENGTH = 16
_DECIMAL_STRING = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

# 応答の一番上から写す Sequence
_TOP_LEVEL_SEQUENCES = (
    "IssuerOfAccessionNumberSequence",
    "RequestedProcedureCodeSequence",
    "ReferencedStudySequence",
)
# 画像には写すが、SR Document（PS3.3 A.35.8）の IOD に無い属性（General Series Module）
_SR_ABSENT_ATTRIBUTES = (
    "RequestAttributesSequence",
    "PerformedProcedureStepID",
    "PerformedProcedureStepStartDate",
    "PerformedProcedureStepStartTime",
    "PerformedProcedureStepDescription",
)
# Modality Performed Procedure Step SOP Class（PS3.4 F.7）
MPPS_SOP_CLASS_UID = "1.2.840.10008.3.1.2.3.3"
# 予約なし（Table A.1-2）で出力しない属性
_SCHEDULED_ONLY_ATTRIBUTES = (
    "RequestAttributesSequence",
    "ReferencedStudySequence",
    "ProcedureCodeSequence",
    "IssuerOfAccessionNumberSequence",
)


def make_worklist_key(
    study_instance_uid: str,
    requested_procedure_id: str,
    scheduled_procedure_step_id: str,
    accession_number: str,
) -> str:
    """予約の鍵：4つの値を `|` で連ねた文字列の SHA-1 の先頭 10 桁（5.4）."""
    joined = WORKLIST_KEY_SEPARATOR.join(
        [study_instance_uid, requested_procedure_id, scheduled_procedure_step_id, accession_number]
    )
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:WORKLIST_KEY_LENGTH]


def worklist_item_from_identifier(identifier: Dataset) -> WorklistItem:
    """C-FIND の応答の Identifier を WorklistItem にする.

    文字コードで戻せなかった値（置き換えの字を含む値）は
    `unreadable_attributes` に名前を残す（5.4）。
    """
    unreadable: list[str] = []
    sps = _first_item(identifier, "ScheduledProcedureStepSequence")

    def text(ds: Dataset, keyword: str) -> str:
        value = ds.get(keyword)
        if value is None:
            return ""
        # 値に `\` があると pydicom は複数の値にする。元の文字列に戻して扱う
        result = "\\".join(str(v) for v in value) if isinstance(value, MultiValue) else str(value)
        if _REPLACEMENT_CHAR in result and keyword not in unreadable:
            unreadable.append(keyword)
        return result

    sequences: dict[str, list[dict]] = {}
    for keyword in _TOP_LEVEL_SEQUENCES:
        _collect_sequence(identifier, keyword, sequences, unreadable)
    _collect_sequence(sps, "ScheduledProtocolCodeSequence", sequences, unreadable)

    values = {
        "patient_name": text(identifier, "PatientName"),
        "patient_id": text(identifier, "PatientID"),
        "issuer_of_patient_id": text(identifier, "IssuerOfPatientID"),
        "birth_date": text(identifier, "PatientBirthDate"),
        "sex": text(identifier, "PatientSex"),
        "weight": text(identifier, "PatientWeight"),
        "size": text(identifier, "PatientSize"),
        "study_instance_uid": text(identifier, "StudyInstanceUID"),
        "accession_number": text(identifier, "AccessionNumber"),
        "referring_physician_name": text(identifier, "ReferringPhysicianName"),
        "requesting_physician": text(identifier, "RequestingPhysician"),
        "requested_procedure_id": text(identifier, "RequestedProcedureID"),
        "requested_procedure_description": text(identifier, "RequestedProcedureDescription"),
        "reason_for_requested_procedure": text(identifier, "ReasonForTheRequestedProcedure"),
        "institution_name": text(identifier, "InstitutionName"),
        # 標準の MWL に無いので、RIS によって最上位か予約の項目のどちらかに入る
        "body_part_examined": text(identifier, "BodyPartExamined")
        or text(sps, "BodyPartExamined"),
        "scheduled_procedure_step_id": text(sps, "ScheduledProcedureStepID"),
        "scheduled_procedure_step_description": text(sps, "ScheduledProcedureStepDescription"),
        "scheduled_start_date": text(sps, "ScheduledProcedureStepStartDate"),
        "scheduled_start_time": text(sps, "ScheduledProcedureStepStartTime"),
        "modality": text(sps, "Modality"),
        "scheduled_station_ae_title": text(sps, "ScheduledStationAETitle"),
    }
    key = make_worklist_key(
        values["study_instance_uid"],
        values["requested_procedure_id"],
        values["scheduled_procedure_step_id"],
        values["accession_number"],
    )
    return WorklistItem(
        key=key,
        specific_character_set=_character_set_terms(identifier),
        sequences=sequences,
        unreadable_attributes=unreadable,
        **values,
    )


def scheduled_context_from_item(
    item: WorklistItem,
    *,
    performed_procedure_step_id: str,
    specific_character_set: list[str],
    source_ae_title: str,
) -> ScheduledContext:
    """予約どおりの形（Table A.1-1）の ScheduledContext を作る."""
    if item.unreadable_attributes:
        attribute = item.unreadable_attributes[0]
        raise WorklistMappingError(
            f"予約の値を文字コードで読めません（{attribute}）",
            {"attribute": attribute, "worklist_key": item.key},
        )
    _check_length("PatientID", item.patient_id, PATIENT_ID_MAX_LENGTH, item.key)
    _check_length("AccessionNumber", item.accession_number, ACCESSION_NUMBER_MAX_LENGTH, item.key)
    _check_length("RequestedProcedureID", item.requested_procedure_id, STUDY_ID_MAX_LENGTH, item.key)
    _check_length(
        "RequestedProcedureDescription",
        item.requested_procedure_description,
        STUDY_DESCRIPTION_MAX_LENGTH,
        item.key,
    )
    _check_patient_values(item.birth_date, item.sex, item.key)
    _check_decimal_string("PatientWeight", item.weight, item.key)
    _check_decimal_string("PatientSize", item.size, item.key)
    if item.study_instance_uid and not is_valid_uid(item.study_instance_uid):
        raise WorklistMappingError(
            "予約の Study Instance UID が UID の形ではありません",
            {"attribute": "StudyInstanceUID", "worklist_key": item.key},
        )
    if not item.patient_id:
        raise WorklistMappingError(
            "予約に Patient ID がありません",
            {"attribute": "PatientID", "worklist_key": item.key},
        )

    patient = ScheduledPatient(
        patient_id=item.patient_id,
        patient_name=item.patient_name,
        issuer_of_patient_id=item.issuer_of_patient_id,
        birth_date=item.birth_date,
        sex=item.sex,
        weight=item.weight,
        size=item.size,
    )
    request = Dataset()
    request.RequestedProcedureID = item.requested_procedure_id
    request.RequestedProcedureDescription = item.requested_procedure_description
    request.ScheduledProcedureStepID = item.scheduled_procedure_step_id
    request.ScheduledProcedureStepDescription = item.scheduled_procedure_step_description
    protocol_codes = item.sequences.get("ScheduledProtocolCodeSequence")
    if protocol_codes:
        request.ScheduledProtocolCodeSequence = _sequence_from_json(protocol_codes)
    if item.reason_for_requested_procedure:
        request.ReasonForTheRequestedProcedure = item.reason_for_requested_procedure

    sequences: dict[str, list[dict]] = {}
    for source, target in (
        ("RequestedProcedureCodeSequence", "ProcedureCodeSequence"),
        ("IssuerOfAccessionNumberSequence", "IssuerOfAccessionNumberSequence"),
        ("ReferencedStudySequence", "ReferencedStudySequence"),
    ):
        if item.sequences.get(source):
            sequences[target] = item.sequences[source]

    return ScheduledContext(
        scheduled=True,
        patient=patient,
        study_instance_uid=item.study_instance_uid or None,
        accession_number=item.accession_number,
        referring_physician_name=item.referring_physician_name,
        study_id=item.requested_procedure_id,
        study_description=item.requested_procedure_description,
        performed_procedure_step_id=performed_procedure_step_id,
        institution_name=item.institution_name,
        request_attributes=request.to_json_dict(),
        sequences=sequences,
        specific_character_set=specific_character_set,
        source_ae_title=source_ae_title,
    )


def emergency_context(
    patient: ScheduledPatient,
    *,
    study_id: str,
    study_description: str,
    performed_procedure_step_id: str,
    specific_character_set: list[str],
    source_ae_title: str,
) -> ScheduledContext:
    """予約なしの形（Table A.1-2）の ScheduledContext を作る（緊急の患者）."""
    _check_length("StudyDescription", study_description, STUDY_DESCRIPTION_MAX_LENGTH, "")
    return ScheduledContext(
        scheduled=False,
        patient=patient,
        study_instance_uid=None,
        accession_number="",
        referring_physician_name="",
        study_id=study_id,
        study_description=study_description,
        performed_procedure_step_id=performed_procedure_step_id,
        request_attributes=None,
        sequences={},
        specific_character_set=specific_character_set,
        source_ae_title=source_ae_title,
    )


def apply_scheduled_context(ds: Dataset, ctx: ScheduledContext) -> None:
    """生成した画像のデータセットに、予約の値を写す（6.2 の表）.

    Study Instance UID・Study Date・Time・Modality・Series は生成の側で決める。
    この関数はそれ以外の予約の値を上書きする。
    """
    _apply_character_set(ds, ctx.specific_character_set)
    _apply_patient(ds, ctx)

    ds.AccessionNumber = ctx.accession_number
    ds.ReferringPhysicianName = ctx.referring_physician_name
    ds.StudyID = ctx.study_id
    if ctx.study_description:
        ds.StudyDescription = ctx.study_description
    elif ctx.study_description_fixed and "StudyDescription" in ds:
        del ds.StudyDescription

    for keyword in _SCHEDULED_ONLY_ATTRIBUTES:
        if keyword in ds:
            delattr(ds, keyword)
    for keyword, items in ctx.sequences.items():
        setattr(ds, keyword, _sequence_from_json(items))
    if ctx.request_attributes is not None:
        ds.RequestAttributesSequence = Sequence([Dataset.from_json(ctx.request_attributes)])

    if ctx.performed_procedure_step_sop_instance_uid:
        # MPPS を使うモダリティは、画像に MPPS への参照を入れる
        # （IHE RAD TF-2x A.1.3・A.2.2。PS3.3 C.7.3.1 の Type 3、項目は 1 つ）
        reference = Dataset()
        reference.ReferencedSOPClassUID = MPPS_SOP_CLASS_UID
        reference.ReferencedSOPInstanceUID = ctx.performed_procedure_step_sop_instance_uid
        ds.ReferencedPerformedProcedureStepSequence = Sequence([reference])
    ds.PerformedProcedureStepID = ctx.performed_procedure_step_id
    ds.PerformedProcedureStepStartDate = ctx.performed_procedure_step_start_date or ds.get(
        "StudyDate", ""
    )
    ds.PerformedProcedureStepStartTime = ctx.performed_procedure_step_start_time or ds.get(
        "StudyTime", ""
    )
    if ctx.performed_procedure_step_start_date and ctx.performed_procedure_step_start_time:
        # Content Date・Time は画像を作った日時（PS3.3 C.7.6.1）。追加撮影では Study の
        # 日時（最初の撮影）でなく、その撮影の日時にする
        ds.ContentDate = ctx.performed_procedure_step_start_date
        ds.ContentTime = ctx.performed_procedure_step_start_time
    if ctx.study_description:
        ds.PerformedProcedureStepDescription = ctx.study_description

    if ctx.institution_name:
        ds.InstitutionName = ctx.institution_name
    if ctx.source_ae_title and hasattr(ds, "file_meta"):
        ds.file_meta.SourceApplicationEntityTitle = ctx.source_ae_title
    if ctx.station_name:
        # 画像を作った装置の名前（PS3.3 C.7.5.1）。装置の設定の値を優先する
        ds.StationName = ctx.station_name


def apply_sr_request(ds: Dataset, ctx: ScheduledContext) -> None:
    """SR Document（PS3.3 A.35.8）の予約の値を、画像の形から SR の形に直す.

    画像の Request Attributes Sequence と Performed Procedure Step の ID・開始の日時・
    説明は General Series Module（C.7.3.1）の属性で、SR の IOD には無いので外す。
    予約の撮影では、代わりに SR Document General Module（C.17.2）の Referenced Request
    Sequence（Type 1C。予約を満たす文書で必須）に Referenced Request Macro（C.17-3c）を入れる。
    """
    for keyword in _SR_ABSENT_ATTRIBUTES:
        if keyword in ds:
            delattr(ds, keyword)
    if ctx.request_attributes is None:
        return
    request = Dataset.from_json(ctx.request_attributes)
    item = Dataset()
    item.StudyInstanceUID = ds.StudyInstanceUID
    item.ReferencedStudySequence = _sequence_from_json(
        ctx.sequences.get("ReferencedStudySequence", [])
    )
    item.AccessionNumber = ctx.accession_number
    if ctx.sequences.get("IssuerOfAccessionNumberSequence"):
        item.IssuerOfAccessionNumberSequence = _sequence_from_json(
            ctx.sequences["IssuerOfAccessionNumberSequence"]
        )
    # 予約の C-FIND では受け取らないので空（Type 2）
    item.PlacerOrderNumberImagingServiceRequest = ""
    item.FillerOrderNumberImagingServiceRequest = ""
    item.RequestedProcedureID = request.get("RequestedProcedureID", "")
    item.RequestedProcedureDescription = request.get("RequestedProcedureDescription", "")
    item.RequestedProcedureCodeSequence = _sequence_from_json(
        ctx.sequences.get("ProcedureCodeSequence", [])
    )
    if request.get("ReasonForTheRequestedProcedure"):
        item.ReasonForTheRequestedProcedure = request.ReasonForTheRequestedProcedure
    ds.ReferencedRequestSequence = Sequence([item])


def ensure_modality_matches(item: WorklistItem, template_modality: str) -> None:
    """予約のモダリティとテンプレートのモダリティが違えば止める（6.2・10.5）."""
    if item.modality and item.modality != template_modality:
        raise WorklistMappingError(
            f"予約は {item.modality}、テンプレートは {template_modality} です",
            {
                "attribute": "Modality",
                "scheduled_modality": item.modality,
                "template_modality": template_modality,
                "worklist_key": item.key,
            },
        )


def build_carrier_patient(patient: ScheduledPatient, study_date: str) -> Patient:
    """GenerationConfig に入れる仮の Patient を作る（docs/spec/03 のモダリティのモデル）.

    画像の患者の値は apply_scheduled_context で上書きする。生年月日が空なら
    仮の生年月日を検査日にし、性別が空なら O にする。
    """
    return Patient(
        patient_id=patient.patient_id[:CARRIER_PATIENT_ID_LENGTH],
        # 氏名は apply_scheduled_context で写す。ここは ASCII の仮の名前にして、
        # 生成の側の文字コードの確かめに掛からないようにする
        patient_name=PatientName(alphabetic=CARRIER_PATIENT_NAME),
        birth_date=patient.birth_date or study_date,
        sex=patient.sex or CARRIER_SEX,
    )


def _apply_character_set(ds: Dataset, character_set: list[str]) -> None:
    if not character_set:
        if "SpecificCharacterSet" in ds:
            del ds.SpecificCharacterSet
        return
    ds.SpecificCharacterSet = character_set if len(character_set) > 1 else character_set[0]


def _apply_patient(ds: Dataset, ctx: ScheduledContext) -> None:
    patient = ctx.patient
    ds.PatientName = patient.patient_name
    ds.PatientID = patient.patient_id
    if not ctx.scheduled or patient.issuer_of_patient_id:
        ds.IssuerOfPatientID = patient.issuer_of_patient_id
    ds.PatientBirthDate = patient.birth_date
    ds.PatientSex = patient.sex
    if not patient.birth_date and "PatientAge" in ds:
        del ds.PatientAge
    for keyword, value in (("PatientWeight", patient.weight), ("PatientSize", patient.size)):
        if value:
            setattr(ds, keyword, value)
        elif keyword in ds:
            delattr(ds, keyword)


def _check_length(attribute: str, value: str, max_length: int, worklist_key: str) -> None:
    if len(value) > max_length:
        raise WorklistMappingError(
            f"{attribute} が {max_length} 文字を超えています（{len(value)} 文字）",
            {"attribute": attribute, "max_length": max_length, "worklist_key": worklist_key},
        )


def _check_patient_values(birth_date: str, sex: str, worklist_key: str) -> None:
    if birth_date and not (len(birth_date) == _BIRTH_DATE_LENGTH and birth_date.isdigit()):
        raise WorklistMappingError(
            "予約の生年月日が YYYYMMDD ではありません",
            {"attribute": "PatientBirthDate", "worklist_key": worklist_key},
        )
    if sex not in _VALID_SEXES:
        raise WorklistMappingError(
            "予約の性別が M・F・O・空のどれでもありません",
            {"attribute": "PatientSex", "worklist_key": worklist_key},
        )


def _check_decimal_string(attribute: str, value: str, worklist_key: str) -> None:
    """空か DS（PS3.5 の Decimal String。16 字まで）であることを確かめる（6.5）."""
    if not value:
        return
    if len(value) > DS_MAX_LENGTH or not _DECIMAL_STRING.fullmatch(value.strip(" ")):
        raise WorklistMappingError(
            f"予約の {attribute} が DS（10進の数）の形ではありません",
            {"attribute": attribute, "worklist_key": worklist_key},
        )


def _first_item(ds: Dataset, keyword: str) -> Dataset:
    sequence = ds.get(keyword)
    if sequence:
        return sequence[0]
    return Dataset()


def _collect_sequence(
    ds: Dataset, keyword: str, sequences: dict[str, list[dict]], unreadable: list[str]
) -> None:
    """写す Sequence を DICOM JSON にし、中の読めない値を `Seq>Attr` の形で足す（5.4）."""
    sequence = ds.get(keyword)
    if not sequence:
        return
    for item in sequence:
        for path in _unreadable_paths(item, prefix=f"{keyword}>"):
            if path not in unreadable:
                unreadable.append(path)
    sequences[keyword] = [item.to_json_dict() for item in sequence]


def _unreadable_paths(ds: Dataset, prefix: str) -> Iterator[str]:
    """Sequence の項目の中（入れ子を含む）の読めない値の名前.

    文字の値は置き換えの字を含むもの、UID（UI）は UID の形でないもの（5.4）。
    """
    for element in ds:
        name = element.keyword or str(element.tag)
        if element.VR == "SQ":
            for item in element.value or []:
                yield from _unreadable_paths(item, prefix=f"{prefix}{name}>")
            continue
        if element.value is None or element.VR not in TEXT_VRS | {_UID_VR}:
            continue
        values = element.value if isinstance(element.value, MultiValue) else [element.value]
        if element.VR == _UID_VR:
            unreadable = any(str(v) and not is_valid_uid(str(v)) for v in values)
        else:
            unreadable = any(_REPLACEMENT_CHAR in str(v) for v in values)
        if unreadable:
            yield f"{prefix}{name}"


def _sequence_from_json(items: list[dict]) -> Sequence:
    return Sequence([Dataset.from_json(item) for item in items])


def _character_set_terms(ds: Dataset) -> list[str]:
    value = ds.get("SpecificCharacterSet")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(term) for term in value]
