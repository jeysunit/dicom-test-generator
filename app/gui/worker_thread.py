"""Generator worker thread for async DICOM generation."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.core.exceptions import DICOMGeneratorError
from app.core.models import GenerationConfig
from app.services.study_generator import StudyGeneratorService

logger = logging.getLogger(__name__)


class GeneratorWorker(QThread):
    """DICOM 生成ワーカースレッド."""

    progress_updated = Signal(int, int, str)
    generation_finished = Signal(bool, str)

    def __init__(self, config: GenerationConfig) -> None:
        super().__init__()
        self.config = config
        self.cancel_requested = False

    def run(self) -> None:
        try:
            service = StudyGeneratorService()
            service.generate(
                config=self.config,
                progress_callback=self._on_progress,
            )
            if self.cancel_requested:
                self.generation_finished.emit(False, "Cancelled by user")
            else:
                total = sum(s.num_images for s in self.config.series_list)
                self.generation_finished.emit(
                    True, f"{total} 枚の DICOM ファイルを生成しました"
                )
        except DICOMGeneratorError as exc:
            logger.error("Generation error: %s", exc, exc_info=True)
            self.generation_finished.emit(False, f"生成エラー: {exc}")
        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            self.generation_finished.emit(False, f"予期しないエラー: {exc}")

    def request_cancel(self) -> None:
        """キャンセルを要求する."""
        self.cancel_requested = True
        logger.info("Cancel requested")

    def _on_progress(self, current: int, total: int) -> None:
        if self.cancel_requested:
            return
        filename = f"image_{current:04d}.dcm"
        self.progress_updated.emit(current, total, filename)
