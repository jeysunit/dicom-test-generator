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
