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
    def __init__(self, template_name: str, hint: str | None = None):
        details = {"template_name": template_name}
        if hint is not None:
            details["hint"] = hint
        super().__init__(f"Template not found: {template_name}", details)


class TemplateParseError(TemplateError):
    def __init__(self, template_path: str, parse_error: str):
        super().__init__(
            f"Failed to parse template: {template_path}",
            {"template_path": template_path, "error": parse_error},
        )


class ProfileError(ConfigurationError):
    """装置のプロファイルの誤り（spec/13 の 9）."""

    pass


class ProfileNotFoundError(ProfileError):
    def __init__(self, profile_name: str, searched: list[str]):
        super().__init__(
            f"Device profile not found: {profile_name}",
            {"profile_name": profile_name, "searched": ", ".join(searched)},
        )


class ProfileParseError(ProfileError):
    def __init__(self, profile_path: str, reason: str):
        super().__init__(
            f"Invalid device profile: {profile_path}",
            {"profile_path": profile_path, "errors": reason},
        )


class DuplicateProfileError(ProfileError):
    def __init__(self, profile_name: str, paths: list[str]):
        super().__init__(
            f"Device profile '{profile_name}' exists in more than one place",
            {"profile_name": profile_name, "paths": ", ".join(paths)},
        )


class ProfileMismatchError(ProfileError):
    """プロファイルがテンプレート・Job と合わない（spec/13 の 4.3）."""

    pass


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


class SCPError(DICOMGeneratorError):
    """Storage SCP ベース例外."""

    pass


class SCPConfigError(SCPError):
    """SCP 設定エラー."""

    pass


class SCPStoreError(SCPError):
    """C-STORE 処理エラー."""

    def __init__(self, message: str, sop_uid: str | None = None):
        super().__init__(message, {"sop_uid": sop_uid} if sop_uid else {})
