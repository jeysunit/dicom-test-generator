"""Main window for DICOM Test Data Generator GUI."""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    AbnormalConfig,
    CharacterSetConfig,
    GenerationConfig,
    PixelSpecCTRealistic,
    StudyConfig,
    TransferSyntaxConfig,
)

from .widgets.output_config import OutputConfigWidget
from .widgets.patient_form import PatientForm
from .widgets.progress_widget import ProgressWidget
from .widgets.series_config import SeriesConfigWidget
from .widgets.template_selector import TemplateSelector
from .worker_thread import GeneratorWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DICOMテストデータ生成ツール v1.1")
        self.resize(900, 1000)
        self._worker: GeneratorWorker | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.template_selector = TemplateSelector()
        layout.addWidget(self.template_selector)

        self.patient_form = PatientForm()
        layout.addWidget(self.patient_form)

        study_group = QGroupBox("検査情報")
        study_form = QFormLayout()
        self.accession_number_edit = QLineEdit()
        self.accession_number_edit.setMaxLength(16)
        self.accession_number_edit.setPlaceholderText("ACC000001")
        study_form.addRow("Accession Number:", self.accession_number_edit)
        study_group.setLayout(study_form)
        layout.addWidget(study_group)

        self.series_config = SeriesConfigWidget()
        layout.addWidget(self.series_config)

        self.output_config = OutputConfigWidget()
        layout.addWidget(self.output_config)

        button_layout = QHBoxLayout()
        self.generate_button = QPushButton("生成開始")
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget)

        layout.addStretch()

        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)

    def _connect_signals(self) -> None:
        self.generate_button.clicked.connect(self._on_generate_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

    @Slot()
    def _on_generate_clicked(self) -> None:
        try:
            config = self._collect_config()
        except Exception as exc:
            QMessageBox.warning(self, "設定エラー", str(exc))
            return

        self._worker = GeneratorWorker(config)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.generation_finished.connect(self._on_generation_finished)
        self._worker.start()

        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_widget.reset()

    @Slot()
    def _on_cancel_clicked(self) -> None:
        if self._worker:
            self._worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("キャンセル中...")

    @Slot(int, int, str)
    def _on_progress_updated(self, current: int, total: int, filename: str) -> None:
        self.progress_widget.update_progress(current, total, filename)

    @Slot(bool, str)
    def _on_generation_finished(self, success: bool, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("キャンセル")

        if self._worker:
            self._worker.wait(5000)
            if self._worker.isRunning():
                logger.warning("Worker thread did not exit in time")
            self._worker = None

        if success:
            QMessageBox.information(self, "完了", message)
        else:
            QMessageBox.warning(self, "エラー", message)

    def _collect_config(self) -> GenerationConfig:
        patient = self.patient_form.get_patient()
        series_list = self.series_config.get_series_list()
        now = datetime.now()

        accession_number = self.accession_number_edit.text().strip()
        if not accession_number:
            raise ValueError("Accession Number を入力してください")

        study = StudyConfig(
            accession_number=accession_number,
            study_date=now.strftime("%Y%m%d"),
            study_time=now.strftime("%H%M%S"),
            num_series=len(series_list),
        )

        modality = self.template_selector.get_modality()
        hospital = self.template_selector.get_hospital()

        return GenerationConfig(
            job_name=f"GUI_{now.strftime('%Y%m%d_%H%M%S')}",
            output_dir=self.output_config.get_output_dir(),
            patient=patient,
            study=study,
            series_list=series_list,
            modality_template=modality,
            hospital_template=hospital,
            pixel_spec=PixelSpecCTRealistic(),
            transfer_syntax=TransferSyntaxConfig(),
            character_set=CharacterSetConfig(),
            abnormal=AbnormalConfig(),
        )
