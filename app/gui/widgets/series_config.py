"""Series configuration widget."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.models import SeriesConfig


class _SeriesRow(QWidget):
    """1シリーズ分の設定行."""

    def __init__(self, series_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.series_number = series_number

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(f"シリーズ{series_number}:"))

        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(1, 10000)
        self.num_images_spin.setValue(20)
        layout.addWidget(QLabel("画像数"))
        layout.addWidget(self.num_images_spin)

        self.slice_thickness_spin = QDoubleSpinBox()
        self.slice_thickness_spin.setRange(0.1, 100.0)
        self.slice_thickness_spin.setValue(5.0)
        self.slice_thickness_spin.setSuffix(" mm")
        layout.addWidget(QLabel("スライス厚"))
        layout.addWidget(self.slice_thickness_spin)

        layout.addStretch()


class SeriesConfigWidget(QWidget):
    """シリーズ設定ウィジェット."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        group = QGroupBox("シリーズ・画像設定")
        group_layout = QVBoxLayout()

        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("シリーズ数:"))
        self.series_count_spin = QSpinBox()
        self.series_count_spin.setRange(1, 10)
        self.series_count_spin.setValue(1)
        count_layout.addWidget(self.series_count_spin)
        count_layout.addStretch()
        group_layout.addLayout(count_layout)

        self._rows_container = QVBoxLayout()
        group_layout.addLayout(self._rows_container)
        group.setLayout(group_layout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)

        self._rows: list[_SeriesRow] = []
        self.series_count_spin.valueChanged.connect(self._on_count_changed)
        self._on_count_changed(1)

    def get_series_list(self) -> list[SeriesConfig]:
        """現在の設定から SeriesConfig リストを返す."""
        return [
            SeriesConfig(
                series_number=row.series_number,
                num_images=row.num_images_spin.value(),
                slice_thickness=row.slice_thickness_spin.value(),
                slice_spacing=row.slice_thickness_spin.value(),
            )
            for row in self._rows
        ]

    def _on_count_changed(self, count: int) -> None:
        while len(self._rows) > count:
            row = self._rows.pop()
            self._rows_container.removeWidget(row)
            row.deleteLater()

        while len(self._rows) < count:
            series_number = len(self._rows) + 1
            row = _SeriesRow(series_number)
            self._rows.append(row)
            self._rows_container.addWidget(row)
