"""Main window for DICOM Test Data Generator GUI."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QScrollArea


class MainWindow(QMainWindow):
    """メインウィンドウ."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DICOMテストデータ生成ツール v1.1")
        self.resize(900, 1000)
        self._setup_ui()

    def _setup_ui(self) -> None:
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(15)

        scroll_area.setWidget(container)
        self.setCentralWidget(scroll_area)
