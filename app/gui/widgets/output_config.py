"""Output directory configuration widget."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OutputConfigWidget(QWidget):
    """出力先設定ウィジェット."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        group = QGroupBox("出力設定")
        h_layout = QHBoxLayout()

        self.path_edit = QLineEdit("output")
        h_layout.addWidget(self.path_edit)

        browse_button = QPushButton("参照...")
        browse_button.clicked.connect(self._on_browse)
        h_layout.addWidget(browse_button)

        group.setLayout(h_layout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(group)

    def get_output_dir(self) -> str:
        """出力先ディレクトリパスを返す."""
        return self.path_edit.text()

    def _on_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "出力先を選択", self.path_edit.text()
        )
        if directory:
            self.path_edit.setText(directory)
