"""Patient information form widget."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import Patient, PatientName
from app.services.patient_loader import PatientLoaderService

logger = logging.getLogger(__name__)


class PatientForm(QWidget):
    """患者情報入力フォーム."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        group = QGroupBox("患者情報")
        form = QFormLayout()

        self.patient_combo = QComboBox()
        form.addRow("患者選択:", self.patient_combo)

        self.patient_id_edit = QLineEdit()
        self.patient_id_edit.setMaxLength(16)
        form.addRow("Patient ID:", self.patient_id_edit)

        self.patient_name_edit = QLineEdit()
        form.addRow("Patient Name:", self.patient_name_edit)

        self.birth_date_edit = QLineEdit()
        self.birth_date_edit.setPlaceholderText("YYYYMMDD")
        self.birth_date_edit.setMaxLength(8)
        form.addRow("Birth Date:", self.birth_date_edit)

        self.sex_combo = QComboBox()
        self.sex_combo.addItems(["M", "F", "O"])
        form.addRow("Sex:", self.sex_combo)

        group.setLayout(form)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)

        self._patients: list[Patient] = []
        self._load_patients()

        self.patient_combo.currentIndexChanged.connect(self._on_patient_selected)
        if self.patient_combo.count() > 0:
            self._on_patient_selected(0)

    def get_patient(self) -> Patient:
        """フォーム入力から Patient オブジェクトを返す."""
        name_text = self.patient_name_edit.text()
        parts = name_text.split("=", maxsplit=2)
        alphabetic = parts[0] if parts else ""
        ideographic = parts[1] if len(parts) > 1 else None
        phonetic = parts[2] if len(parts) > 2 else None

        return Patient(
            patient_id=self.patient_id_edit.text(),
            patient_name=PatientName(
                alphabetic=alphabetic,
                ideographic=ideographic,
                phonetic=phonetic,
            ),
            birth_date=self.birth_date_edit.text(),
            sex=self.sex_combo.currentText(),
        )

    def _load_patients(self) -> None:
        try:
            self._patients = PatientLoaderService().load_all()
        except Exception:
            logger.warning("Failed to load patient master", exc_info=True)
            self._patients = []

        for patient in self._patients:
            label = f"{patient.patient_id} - {patient.patient_name.alphabetic}"
            self.patient_combo.addItem(label)

    def _on_patient_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._patients):
            return
        patient = self._patients[index]
        self.patient_id_edit.setText(patient.patient_id)

        name_parts = [patient.patient_name.alphabetic]
        if patient.patient_name.ideographic:
            name_parts.append(patient.patient_name.ideographic)
        if patient.patient_name.phonetic:
            name_parts.append(patient.patient_name.phonetic)
        self.patient_name_edit.setText("=".join(name_parts))

        self.birth_date_edit.setText(patient.birth_date)

        sex_index = self.sex_combo.findText(patient.sex)
        if sex_index >= 0:
            self.sex_combo.setCurrentIndex(sex_index)
