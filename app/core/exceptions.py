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
    """装置のプロファイルの誤り（docs/spec/13 の 9）."""

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
    """プロファイルがテンプレート・Job と合わない（docs/spec/13 の 4.3）."""

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


class ModalityError(DICOMGeneratorError):
    """モダリティのダミーの例外の基底（docs/spec/12_modality_emulator.md 9.5）."""


class ModalityConfigError(ModalityError):
    """modality: の節の設定の誤り."""


class AssociationError(ModalityError):
    """Association を張れない・断られた・切れた."""


class WorklistQueryError(ModalityError):
    """C-FIND（MWL）の失敗・時間切れ."""


class WorklistRefreshTimeoutError(WorklistQueryError):
    """予約を再検索する C-FIND が、時間の上限で途中までになった."""


class WorklistItemNotFoundError(ModalityError):
    """最後に取得した一覧に、その予約の鍵が無い."""


class WorklistItemGoneError(ModalityError):
    """再検索した応答に、その予約がもう無い."""


class WorklistMappingError(ModalityError):
    """予約の値を画像に写せない（文字・長さ・モダリティ）."""


class StoreError(ModalityError):
    """C-STORE の失敗."""


class StorageCommitmentError(ModalityError):
    """保管の確認の失敗・時間切れ（Phase 3c）."""


class MPPSError(ModalityError):
    """N-CREATE・N-SET の失敗（Phase 3c）."""
