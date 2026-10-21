"""MPPS の規格への適合の試験（PS3.4 F.7.2、IHE RAD TF-2x A.1.3・A.2.2）."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pydicom
import pytest
from modality_peers import MppsRecorder
from pydicom.errors import InvalidDicomError

from app.core.exceptions import GenerationError
from app.core.worklist_mapping import MPPS_SOP_CLASS_UID
from app.modality.mpps_scu import STATE_COMPLETED, STATE_DISCONTINUED, build_n_set
from tests.modality.test_mpps_scu import _scheduled_exam, _service


def test_images_reference_the_mpps_instance(tmp_path, worklist_scp, mpps_scp: MppsRecorder) -> None:
    # MPPS を使うモダリティは、画像に Referenced PPS Sequence を入れる（IHE-A.1.3・A.2.2）
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _scheduled_exam(service, images_per_series=[1, 2])

    uid = result.mpps.sop_instance_uid
    for path in result.files:
        ds = pydicom.dcmread(path)
        (reference,) = ds.ReferencedPerformedProcedureStepSequence
        assert reference.ReferencedSOPClassUID == MPPS_SOP_CLASS_UID
        assert reference.ReferencedSOPInstanceUID == uid


def test_images_have_no_mpps_reference_without_mpps(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, None, use_mpps=False)

    result = _scheduled_exam(service)

    for path in result.files:
        assert "ReferencedPerformedProcedureStepSequence" not in pydicom.dcmread(path)


def test_discontinued_reports_images_written_before_the_stop(
    tmp_path, worklist_scp, mpps_scp: MppsRecorder, monkeypatch
) -> None:
    # 途中まで書いた画像も DISCONTINUED の N-SET で知らせる（PS3.4 F.7.2.2.2）
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)
    original = service._generator.generate

    def stop_after_writing(*args, **kwargs):
        output_dir = original(*args, **kwargs)
        raise GenerationError(f"synthetic stop after writing {output_dir}")

    monkeypatch.setattr(service._generator, "generate", stop_after_writing)

    with pytest.raises(GenerationError):
        _scheduled_exam(service, images_per_series=[2])

    (_uid, modification), = mpps_scp.sets
    assert modification.PerformedProcedureStepStatus == STATE_DISCONTINUED
    (series,) = modification.PerformedSeriesSequence
    assert len(series.ReferencedImageSequence) == 2
    assert series.ProtocolName


@pytest.mark.parametrize("state", [STATE_COMPLETED, STATE_DISCONTINUED])
def test_n_set_without_images_still_has_one_series(state: str) -> None:
    # Performed Series Sequence は COMPLETED・DISCONTINUED で空にしない
    # （PS3.4 F.7.2 の表 F.7.2-1 の Note 2）
    modification = build_n_set(state, [], datetime(2026, 10, 21, 10, 0, 0), [])

    (series,) = modification.PerformedSeriesSequence
    assert series.SeriesInstanceUID
    assert series.ProtocolName  # Type 1
    assert list(series.ReferencedImageSequence) == []


def test_discontinued_skips_unreadable_images(tmp_path: Path) -> None:
    broken = tmp_path / "broken.dcm"
    broken.write_bytes(b"not a dicom file")

    modification = build_n_set(
        STATE_DISCONTINUED, [str(broken)], datetime(2026, 10, 21, 10, 0, 0), []
    )

    (series,) = modification.PerformedSeriesSequence
    assert list(series.ReferencedImageSequence) == []


def test_discontinued_reports_readable_images_among_broken_ones(tmp_path: Path) -> None:
    good = tmp_path / "good.dcm"
    ds = pydicom.Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.SOPInstanceUID = "2.25.11"
    ds.SeriesInstanceUID = "2.25.12"
    ds.SeriesDescription = "AXIAL"
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
    pydicom.dcmwrite(good, ds, enforce_file_format=True)
    no_series = tmp_path / "no_series.dcm"
    del ds.SeriesInstanceUID
    ds.SOPInstanceUID = "2.25.13"
    pydicom.dcmwrite(no_series, ds, enforce_file_format=True)
    garbage = tmp_path / "garbage.dcm"
    garbage.write_bytes(b"\x00" * 10)

    modification = build_n_set(
        STATE_DISCONTINUED,
        [str(garbage), str(good), str(no_series)],
        datetime(2026, 10, 21, 10, 0, 0),
        [],
    )

    (series,) = modification.PerformedSeriesSequence
    assert series.SeriesInstanceUID == "2.25.12"
    assert [r.ReferencedSOPInstanceUID for r in series.ReferencedImageSequence] == ["2.25.11"]


class _BrokenDescription(pydicom.Dataset):
    """Series Description を読むと pydicom の変換の誤りを上げる画像."""

    def get(self, key, default=None):
        if key in ("SeriesDescription", "ProtocolName"):
            raise ValueError("cannot convert the value")
        return super().get(key, default)


def test_discontinued_skips_image_whose_values_fail_to_convert(monkeypatch) -> None:
    image = _BrokenDescription()
    image.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    image.SOPInstanceUID = "2.25.21"
    image.SeriesInstanceUID = "2.25.22"
    monkeypatch.setattr("app.modality.mpps_scu.dcmread", lambda *_a, **_k: image)

    modification = build_n_set(
        STATE_DISCONTINUED, ["broken.dcm"], datetime(2026, 10, 21, 10, 0, 0), []
    )

    (series,) = modification.PerformedSeriesSequence
    assert series.SeriesInstanceUID != "2.25.22"
    assert list(series.ReferencedImageSequence) == []


def test_completed_with_unreadable_image_raises(tmp_path: Path) -> None:
    broken = tmp_path / "broken.dcm"
    broken.write_bytes(b"not a dicom file")

    with pytest.raises(InvalidDicomError):
        build_n_set(STATE_COMPLETED, [str(broken)], datetime(2026, 10, 21, 10, 0, 0), [])
