"""Progress display widget."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class ProgressWidget(QWidget):
    """進捗表示ウィジェット."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("待機中")
        layout.addWidget(self.status_label)

    def update_progress(self, current: int, total: int, filename: str) -> None:
        """進捗を更新する."""
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"生成中: {filename} ({current}/{total})")

    def reset(self) -> None:
        """初期状態にリセットする."""
        self.progress_bar.setValue(0)
        self.status_label.setText("待機中")
