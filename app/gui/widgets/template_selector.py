"""Template selector widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)


class TemplateSelector(QWidget):
    """モダリティ・病院テンプレート選択ウィジェット."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_root = Path(__file__).resolve().parents[3]

        group = QGroupBox("テンプレート選択")
        form = QFormLayout()

        self.modality_combo = QComboBox()
        self.hospital_combo = QComboBox()

        form.addRow("モダリティ:", self.modality_combo)
        form.addRow("病院設定:", self.hospital_combo)
        group.setLayout(form)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)

        self._load_modalities()
        self._load_hospitals()

    def get_modality(self) -> str:
        """選択中のモダリティテンプレート名を返す."""
        return self.modality_combo.currentData() or self.modality_combo.currentText()

    def get_hospital(self) -> str | None:
        """選択中の病院テンプレート名を返す。'なし' なら None."""
        if self.hospital_combo.currentIndex() == 0:
            return None
        return self.hospital_combo.currentData() or self.hospital_combo.currentText()

    def _load_modalities(self) -> None:
        modality_dir = self._project_root / "templates" / "modality"
        if not modality_dir.exists():
            return
        for path in sorted(modality_dir.glob("*.yaml")):
            display_name = path.stem.replace("_", " ").title()
            self.modality_combo.addItem(display_name, path.stem)

    def _load_hospitals(self) -> None:
        self.hospital_combo.addItem("なし", None)
        hospital_dir = self._project_root / "templates" / "hospital"
        if not hospital_dir.exists():
            return
        for path in sorted(hospital_dir.glob("*.yaml")):
            display_name = path.stem.replace("_", " ").title()
            self.hospital_combo.addItem(display_name, path.stem)
