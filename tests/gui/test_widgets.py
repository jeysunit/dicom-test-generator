"""Widget unit tests."""

from app.gui.widgets.output_config import OutputConfigWidget
from app.gui.widgets.patient_form import PatientForm
from app.gui.widgets.progress_widget import ProgressWidget
from app.gui.widgets.series_config import SeriesConfigWidget
from app.gui.widgets.template_selector import TemplateSelector

from app.core.models import Patient, PatientName, SeriesConfig


class TestTemplateSelector:
    def test_initial_state(self, qtbot):
        """初期状態でコンボボックスが存在すること."""
        widget = TemplateSelector()
        qtbot.addWidget(widget)
        assert widget.modality_combo.count() > 0
        assert widget.hospital_combo.count() > 0
        assert widget.hospital_combo.itemText(0) == "なし"

    def test_get_modality(self, qtbot):
        """モダリティ名を取得できること."""
        widget = TemplateSelector()
        qtbot.addWidget(widget)
        modality = widget.get_modality()
        assert isinstance(modality, str)
        assert len(modality) > 0

    def test_get_hospital_none(self, qtbot):
        """病院 'なし' 選択時に None を返すこと."""
        widget = TemplateSelector()
        qtbot.addWidget(widget)
        widget.hospital_combo.setCurrentIndex(0)
        assert widget.get_hospital() is None


class TestPatientForm:
    def test_initial_state(self, qtbot):
        """初期状態で患者コンボボックスが存在すること."""
        widget = PatientForm()
        qtbot.addWidget(widget)
        assert widget.patient_combo.count() > 0

    def test_get_patient_returns_patient(self, qtbot):
        """選択した患者情報を取得できること."""
        widget = PatientForm()
        qtbot.addWidget(widget)
        patient = widget.get_patient()
        assert isinstance(patient, Patient)
        assert len(patient.patient_id) > 0

    def test_patient_selection_updates_fields(self, qtbot):
        """患者選択でフィールドが更新されること."""
        widget = PatientForm()
        qtbot.addWidget(widget)
        widget.patient_combo.setCurrentIndex(0)
        assert widget.patient_id_edit.text() != ""


class TestSeriesConfigWidget:
    def test_initial_state(self, qtbot):
        """初期状態でシリーズ数1であること."""
        widget = SeriesConfigWidget()
        qtbot.addWidget(widget)
        assert widget.series_count_spin.value() == 1
        assert len(widget.get_series_list()) == 1

    def test_change_series_count(self, qtbot):
        """シリーズ数を変更するとウィジェットが増えること."""
        widget = SeriesConfigWidget()
        qtbot.addWidget(widget)
        widget.series_count_spin.setValue(3)
        assert len(widget.get_series_list()) == 3

    def test_get_series_list_returns_valid_configs(self, qtbot):
        """SeriesConfig のリストが正しく返ること."""
        widget = SeriesConfigWidget()
        qtbot.addWidget(widget)
        widget.series_count_spin.setValue(2)
        series_list = widget.get_series_list()
        assert len(series_list) == 2
        for i, series in enumerate(series_list):
            assert isinstance(series, SeriesConfig)
            assert series.series_number == i + 1


class TestOutputConfigWidget:
    def test_initial_state(self, qtbot):
        """初期状態でデフォルト出力先が設定されていること."""
        widget = OutputConfigWidget()
        qtbot.addWidget(widget)
        assert widget.get_output_dir() == "output"

    def test_set_output_dir(self, qtbot):
        """出力先を手動で変更できること."""
        widget = OutputConfigWidget()
        qtbot.addWidget(widget)
        widget.path_edit.setText("/tmp/test_output")
        assert widget.get_output_dir() == "/tmp/test_output"


class TestProgressWidget:
    def test_initial_state(self, qtbot):
        """初期状態でプログレスバーが0%であること."""
        widget = ProgressWidget()
        qtbot.addWidget(widget)
        assert widget.progress_bar.value() == 0
        assert widget.status_label.text() == "待機中"

    def test_update_progress(self, qtbot):
        """進捗更新が正しく反映されること."""
        widget = ProgressWidget()
        qtbot.addWidget(widget)
        widget.update_progress(50, 100, "test_0050.dcm")
        assert widget.progress_bar.value() == 50
        assert "test_0050.dcm" in widget.status_label.text()

    def test_reset(self, qtbot):
        """リセットで初期状態に戻ること."""
        widget = ProgressWidget()
        qtbot.addWidget(widget)
        widget.update_progress(50, 100, "test.dcm")
        widget.reset()
        assert widget.progress_bar.value() == 0
        assert widget.status_label.text() == "待機中"
