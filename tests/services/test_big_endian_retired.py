"""廃止の転送の形 Explicit VR Big Endian を作らない試験（PS3.5 A.3、違反 6）."""

from __future__ import annotations

import numpy as np
import pytest

from app.core import (
    AbnormalConfig,
    DeviceProfile,
    DICOMValidationError,
    ProfileMismatchError,
    TransferSyntaxConfig,
)
from app.core.dicom_writer import FileMetaBuilder, SpatialCalculator
from app.core.exceptions import DICOMBuildError
from app.core.generator import DICOMBuilder
from app.core.models import InstanceConfig, UIDContext
from app.services.profile_loader import profile_transfer_syntax
from app.services.study_generator import StudyGeneratorService
from tests.core.test_ct_image_conformance import _profile
from tests.services.test_study_generator import _make_config

BIG_ENDIAN = TransferSyntaxConfig(
    uid="1.2.840.10008.1.2.2",
    name="Explicit VR Big Endian",
    is_implicit_vr=False,
    is_little_endian=False,
)


def test_big_endian_is_rejected_before_writing(tmp_path) -> None:
    # ふつうの経路。異常のデータのレベルの試験は test_study_generator_abnormal.py
    config = _make_config(tmp_path=tmp_path).model_copy(
        update={"transfer_syntax": BIG_ENDIAN, "abnormal": AbnormalConfig(level="none")}
    )

    with pytest.raises(DICOMValidationError, match="retired"):
        StudyGeneratorService().generate(config=config)
    assert not (tmp_path / "output").exists()


def test_builder_rejects_big_endian(tmp_path) -> None:
    config = _make_config(tmp_path=tmp_path)
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.100",
        transfer_syntax_uid=BIG_ENDIAN.uid,
        implementation_class_uid="2.25.3",
        implementation_version_name="DICOM_GEN_1.1",
    )

    with pytest.raises(DICOMBuildError, match="1.2.840.10008.1.2.2"):
        DICOMBuilder().build_ct_image(
            patient=config.patient,
            study_config=config.study,
            series_config=config.series_list[0],
            instance_config=InstanceConfig(instance_number=1),
            uid_context=UIDContext(
                study_instance_uid="2.25.1",
                frame_of_reference_uid="2.25.2",
                implementation_class_uid="2.25.3",
                instance_creator_uid="2.25.4",
            ),
            spatial=SpatialCalculator(slice_thickness=5.0, slice_spacing=5.0).calculate(0),
            pixel_data=np.zeros((2, 2), dtype=np.int16),
            file_meta=file_meta,
            sop_instance_uid="2.25.100",
            series_instance_uid="2.25.200",
            bits_stored=12,
        )


def test_profile_preferring_big_endian_cannot_be_generated() -> None:
    data = _profile({})
    data["storage"]["transfer_syntaxes"] = ["1.2.840.10008.1.2.2", "1.2.840.10008.1.2"]
    profile = DeviceProfile.model_validate(data)

    with pytest.raises(ProfileMismatchError, match="1.2.840.10008.1.2.2"):
        profile_transfer_syntax(profile)
