"""GUI entry point: python -m app.gui"""

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DICOMテストデータ生成ツール")
    app.setApplicationVersion("1.1.0")
    app.setOrganizationName("DICOM Generator Project")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
