"""Widget unit tests."""

from app.gui.widgets.patient_form import PatientForm
from app.gui.widgets.template_selector import TemplateSelector

from app.core.models import Patient, PatientName


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
