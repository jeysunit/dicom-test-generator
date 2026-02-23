"""MainWindow tests."""

from datetime import datetime
from unittest.mock import Mock

from app.core.models import (
    AbnormalConfig,
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.gui.main_window import MainWindow


def _make_generation_config(output_dir: str = "output") -> GenerationConfig:
    return GenerationConfig(
        job_name="gui_test_job",
        output_dir=output_dir,
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^TARO"),
            birth_date="19800101",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20260101",
            study_time="120000",
            num_series=1,
        ),
        series_list=[SeriesConfig(series_number=1, num_images=3)],
        modality_template="fujifilm_scenaria_view_ct",
        hospital_template="hospital_a",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
        abnormal=AbnormalConfig(),
    )


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


def test_collect_config_builds_generation_config(monkeypatch, qtbot, tmp_path):
    """_collect_config が UI 入力から GenerationConfig を構築すること."""
    import app.gui.main_window as main_window_module

    fixed_now = datetime(2026, 2, 3, 4, 5, 6)
    captured_generation_kwargs = {}

    class _FakeDatetime:
        @classmethod
        def now(cls):
            return fixed_now

    class _FakeStudyConfig:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _FakeGenerationConfig:
        def __init__(self, **kwargs):
            captured_generation_kwargs.update(kwargs)
            for key, value in kwargs.items():
                setattr(self, key, value)

    monkeypatch.setattr(main_window_module, "datetime", _FakeDatetime)
    monkeypatch.setattr(main_window_module, "StudyConfig", _FakeStudyConfig)
    monkeypatch.setattr(main_window_module, "GenerationConfig", _FakeGenerationConfig)

    window = MainWindow()
    qtbot.addWidget(window)

    patient = Patient(
        patient_id="P123456",
        patient_name=PatientName(alphabetic="YAMADA^TARO"),
        birth_date="19800101",
        sex="M",
    )
    series_list = [
        SeriesConfig(series_number=1, num_images=2),
        SeriesConfig(series_number=2, num_images=3),
    ]

    monkeypatch.setattr(window.patient_form, "get_patient", lambda: patient)
    monkeypatch.setattr(window.series_config, "get_series_list", lambda: series_list)
    monkeypatch.setattr(window.output_config, "get_output_dir", lambda: str(tmp_path))
    monkeypatch.setattr(window.template_selector, "get_modality", lambda: "ct_modality")
    monkeypatch.setattr(window.template_selector, "get_hospital", lambda: "hospital_a")

    config = window._collect_config()

    assert config.job_name == "GUI_20260203_040506"
    assert config.output_dir == str(tmp_path)
    assert config.patient == patient
    assert config.series_list == series_list
    assert config.modality_template == "ct_modality"
    assert config.hospital_template == "hospital_a"
    assert config.study.accession_number == "ACC20260203040506"
    assert config.study.study_date == "20260203"
    assert config.study.study_time == "040506"
    assert config.study.num_series == 2
    assert isinstance(captured_generation_kwargs["pixel_spec"], main_window_module.PixelSpecCTRealistic)
    assert isinstance(
        captured_generation_kwargs["transfer_syntax"],
        main_window_module.TransferSyntaxConfig,
    )
    assert isinstance(
        captured_generation_kwargs["character_set"],
        main_window_module.CharacterSetConfig,
    )
    assert isinstance(captured_generation_kwargs["abnormal"], main_window_module.AbnormalConfig)


def test_on_generate_clicked_sets_worker_and_ui_state(monkeypatch, qtbot):
    """_on_generate_clicked 成功時にワーカー起動とUI更新を行うこと."""
    import app.gui.main_window as main_window_module

    config = _make_generation_config()

    class _DummySignal:
        def __init__(self):
            self._connected = []

        def connect(self, callback):
            self._connected.append(callback)

    class _DummyWorker:
        def __init__(self, cfg):
            self.config = cfg
            self.progress_updated = _DummySignal()
            self.generation_finished = _DummySignal()
            self.start_called = False

        def start(self):
            self.start_called = True

    monkeypatch.setattr(main_window_module, "GeneratorWorker", _DummyWorker)

    window = MainWindow()
    qtbot.addWidget(window)

    reset_mock = Mock()
    monkeypatch.setattr(window.progress_widget, "reset", reset_mock)
    monkeypatch.setattr(window, "_collect_config", lambda: config)

    window._on_generate_clicked()

    assert isinstance(window._worker, _DummyWorker)
    assert window._worker.config == config
    assert window._worker.start_called is True
    assert window.generate_button.isEnabled() is False
    assert window.cancel_button.isEnabled() is True
    reset_mock.assert_called_once_with()


def test_on_generate_clicked_shows_warning_on_collect_error(monkeypatch, qtbot):
    """_collect_config が失敗した場合は警告ダイアログを表示して中断すること."""
    import app.gui.main_window as main_window_module

    window = MainWindow()
    qtbot.addWidget(window)

    warning_mock = Mock()
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", warning_mock)

    def _raise_error():
        raise RuntimeError("invalid config")

    monkeypatch.setattr(window, "_collect_config", _raise_error)

    window._on_generate_clicked()

    warning_mock.assert_called_once_with(window, "設定エラー", "invalid config")
    assert window._worker is None
    assert window.generate_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False


def test_on_cancel_clicked_requests_cancel_and_updates_button(monkeypatch, qtbot):
    """_on_cancel_clicked でワーカーキャンセル要求とボタン状態更新が行われること."""
    window = MainWindow()
    qtbot.addWidget(window)

    dummy_worker = Mock()
    window._worker = dummy_worker
    window.cancel_button.setEnabled(True)

    window._on_cancel_clicked()

    dummy_worker.request_cancel.assert_called_once_with()
    assert window.cancel_button.isEnabled() is False
    assert window.cancel_button.text() == "キャンセル中..."


def test_on_progress_updated_delegates_to_progress_widget(monkeypatch, qtbot):
    """_on_progress_updated が ProgressWidget に委譲すること."""
    window = MainWindow()
    qtbot.addWidget(window)

    update_mock = Mock()
    monkeypatch.setattr(window.progress_widget, "update_progress", update_mock)

    window._on_progress_updated(2, 10, "image_0002.dcm")

    update_mock.assert_called_once_with(2, 10, "image_0002.dcm")


def test_on_generation_finished_success_restores_ui_and_shows_info(monkeypatch, qtbot):
    """_on_generation_finished 成功時にUI復帰し完了ダイアログを表示すること."""
    import app.gui.main_window as main_window_module

    window = MainWindow()
    qtbot.addWidget(window)

    info_mock = Mock()
    warning_mock = Mock()
    monkeypatch.setattr(main_window_module.QMessageBox, "information", info_mock)
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", warning_mock)

    worker = Mock()
    window._worker = worker
    window.generate_button.setEnabled(False)
    window.cancel_button.setEnabled(True)
    window.cancel_button.setText("キャンセル中...")

    window._on_generation_finished(True, "done")

    worker.wait.assert_called_once_with()
    assert window._worker is None
    assert window.generate_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.cancel_button.text() == "キャンセル"
    info_mock.assert_called_once_with(window, "完了", "done")
    warning_mock.assert_not_called()


def test_on_generation_finished_error_restores_ui_and_shows_warning(monkeypatch, qtbot):
    """_on_generation_finished 失敗時にUI復帰しエラーダイアログを表示すること."""
    import app.gui.main_window as main_window_module

    window = MainWindow()
    qtbot.addWidget(window)

    info_mock = Mock()
    warning_mock = Mock()
    monkeypatch.setattr(main_window_module.QMessageBox, "information", info_mock)
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", warning_mock)

    worker = Mock()
    window._worker = worker

    window._on_generation_finished(False, "failed")

    worker.wait.assert_called_once_with()
    assert window._worker is None
    assert window.generate_button.isEnabled() is True
    assert window.cancel_button.isEnabled() is False
    assert window.cancel_button.text() == "キャンセル"
    warning_mock.assert_called_once_with(window, "エラー", "failed")
    info_mock.assert_not_called()
