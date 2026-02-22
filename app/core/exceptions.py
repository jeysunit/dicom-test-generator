"""Core engine exception hierarchy."""

from __future__ import annotations


class DICOMGeneratorError(Exception):
    """ベース例外クラス"""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class GenerationError(DICOMGeneratorError):
    pass


class ConfigurationError(DICOMGeneratorError):
    pass


class TemplateError(ConfigurationError):
    pass


class TemplateNotFoundError(TemplateError):
    def __init__(self, template_name: str):
        super().__init__(
            f"Template not found: {template_name}",
            {"template_name": template_name},
        )


class TemplateParseError(TemplateError):
    def __init__(self, template_path: str, parse_error: str):
        super().__init__(
            f"Failed to parse template: {template_path}",
            {"template_path": template_path, "error": parse_error},
        )


class PatientDataError(ConfigurationError):
    pass


class PatientNotFoundError(PatientDataError):
    def __init__(self, patient_id: str):
        super().__init__(f"Patient not found: {patient_id}", {"patient_id": patient_id})


class PatientDataInvalidError(PatientDataError):
    pass


class JobSchemaError(ConfigurationError):
    def __init__(self, validation_errors: list):
        super().__init__(
            "Job configuration validation failed",
            {"errors": validation_errors},
        )


class UIDGenerationError(GenerationError):
    def __init__(self, message: str, uid_type: str | None = None):
        super().__init__(message, {"uid_type": uid_type} if uid_type else {})


class PixelGenerationError(GenerationError):
    def __init__(self, message: str, mode: str | None = None):
        super().__init__(message, {"mode": mode} if mode else {})


class FileMetaError(GenerationError):
    pass


class DICOMBuildError(GenerationError):
    def __init__(self, message: str, tag: str | None = None):
        super().__init__(message, {"tag": tag} if tag else {})


class IOError(DICOMGeneratorError):
    pass


class FileWriteError(IOError):
    def __init__(self, filepath: str, reason: str):
        super().__init__(
            f"Failed to write file: {filepath}",
            {"filepath": filepath, "reason": reason},
        )


class FileReadError(IOError):
    def __init__(self, filepath: str, reason: str):
        super().__init__(
            f"Failed to read file: {filepath}",
            {"filepath": filepath, "reason": reason},
        )


class DirectoryCreateError(IOError):
    def __init__(self, dirpath: str, reason: str):
        super().__init__(
            f"Failed to create directory: {dirpath}",
            {"dirpath": dirpath, "reason": reason},
        )


class ValidationError(DICOMGeneratorError):
    pass


class JobValidationError(ValidationError):
    pass


class DICOMValidationError(ValidationError):
    pass
