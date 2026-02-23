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


def test_main_window_has_generate_button(qtbot):
    """生成ボタンが存在し有効であること."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.generate_button.isEnabled()
    assert window.generate_button.text() == "生成開始"


def test_main_window_has_cancel_button_disabled(qtbot):
    """キャンセルボタンが初期状態で無効であること."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.cancel_button.isEnabled()


def test_main_window_has_all_widgets(qtbot):
    """全ウィジェットが配置されていること."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.template_selector is not None
    assert window.patient_form is not None
    assert window.series_config is not None
    assert window.output_config is not None
    assert window.progress_widget is not None
