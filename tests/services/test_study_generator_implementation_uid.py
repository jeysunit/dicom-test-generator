"""Implementation Class UID・Instance Creator UID を固定にする試験（PS3.7 D.3.3.2、PS3.10 7.1）."""

from __future__ import annotations

import pydicom

from app.core.uid_format import is_valid_uid
from app.services.study_generator import (
    IMPLEMENTATION_CLASS_UID,
    INSTANCE_CREATOR_UID,
    StudyGeneratorService,
)
from tests.services.test_study_generator import _make_config


def _first(tmp_path, name: str) -> pydicom.Dataset:
    config = _make_config(tmp_path / name)
    output_dir = StudyGeneratorService().generate(config=config)
    return pydicom.dcmread(next(output_dir.glob("*.dcm")))


def test_fixed_uids_are_valid() -> None:
    assert is_valid_uid(IMPLEMENTATION_CLASS_UID)
    assert is_valid_uid(INSTANCE_CREATOR_UID)


def test_implementation_and_creator_uids_are_same_across_generations(tmp_path) -> None:
    first = _first(tmp_path, "first")
    second = _first(tmp_path, "second")

    for ds in (first, second):
        assert ds.file_meta.ImplementationClassUID == IMPLEMENTATION_CLASS_UID
        assert ds.InstanceCreatorUID == INSTANCE_CREATOR_UID
    assert first.StudyInstanceUID != second.StudyInstanceUID
