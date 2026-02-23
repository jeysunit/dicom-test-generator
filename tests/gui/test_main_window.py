"""MainWindow tests."""

from app.gui.main_window import MainWindow


def test_main_window_title(qtbot):
    """メインウィンドウのタイトルが正しいこと."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "DICOMテストデータ生成ツール v1.1"


def test_main_window_initial_size(qtbot):
    """メインウィンドウの初期サイズが設定されていること."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.width() >= 800
    assert window.height() >= 900
