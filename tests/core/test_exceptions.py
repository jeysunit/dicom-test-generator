from __future__ import annotations

from app.core.exceptions import (
    DICOMBuildError,
    DICOMGeneratorError,
    FileWriteError,
    GenerationError,
    JobSchemaError,
    PixelGenerationError,
    TemplateNotFoundError,
    UIDGenerationError,
)


def test_base_exception_str_with_details() -> None:
    exc = DICOMGeneratorError("base error", details={"key": "value"})

    assert str(exc) == "base error (key=value)"


def test_base_exception_str_without_details() -> None:
    exc = DICOMGeneratorError("base error")

    assert str(exc) == "base error"


def test_base_exception_to_dict() -> None:
    exc = DICOMGeneratorError("base error", details={"code": 123})

    data = exc.to_dict()

    assert data["error_type"] == "DICOMGeneratorError"
    assert data["message"] == "base error"
    assert data["details"] == {"code": 123}


def test_uid_generation_error_with_uid_type() -> None:
    exc = UIDGenerationError("uid error", uid_type="sop")

    assert exc.details["uid_type"] == "sop"


def test_pixel_generation_error_with_mode() -> None:
    exc = PixelGenerationError("pixel error", mode="ct_realistic")

    assert exc.details["mode"] == "ct_realistic"


def test_dicom_build_error_with_tag() -> None:
    exc = DICOMBuildError("build error", tag="(0010,0010)")

    assert exc.details["tag"] == "(0010,0010)"


def test_template_not_found_error() -> None:
    exc = TemplateNotFoundError("ct_default")

    assert "ct_default" in str(exc)
    assert exc.details["template_name"] == "ct_default"


def test_file_write_error() -> None:
    exc = FileWriteError("/tmp/test.dcm", "permission denied")

    assert "/tmp/test.dcm" in str(exc)
    assert "permission denied" in str(exc)
    assert exc.details["filepath"] == "/tmp/test.dcm"
    assert exc.details["reason"] == "permission denied"


def test_exception_hierarchy() -> None:
    uid_exc = UIDGenerationError("uid error")

    assert isinstance(uid_exc, UIDGenerationError)
    assert isinstance(uid_exc, GenerationError)
    assert isinstance(uid_exc, DICOMGeneratorError)


def test_job_schema_error() -> None:
    errors = [{"field": "study_date", "message": "invalid"}]
    exc = JobSchemaError(errors)

    assert exc.details["errors"] == errors
