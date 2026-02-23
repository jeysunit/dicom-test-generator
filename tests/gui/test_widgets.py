"""Widget unit tests."""

from app.gui.widgets.template_selector import TemplateSelector


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
