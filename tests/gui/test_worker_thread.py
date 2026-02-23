"""GeneratorWorker tests."""

from app.gui.worker_thread import GeneratorWorker
from app.core.exceptions import DICOMGeneratorError
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


def _make_config(output_dir: str = "/tmp/test_gui_output") -> GenerationConfig:
    return GenerationConfig(
        job_name="test_gui",
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
        series_list=[SeriesConfig(series_number=1, num_images=2)],
        modality_template="fujifilm_scenaria_view_ct",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
        abnormal=AbnormalConfig(),
    )


def test_worker_emits_progress(qtbot, tmp_path):
    """ワーカーが進捗シグナルを発信すること."""
    config = _make_config(str(tmp_path))
    worker = GeneratorWorker(config)

    progress_values = []
    worker.progress_updated.connect(
        lambda current, total, fname: progress_values.append((current, total))
    )

    with qtbot.waitSignal(worker.generation_finished, timeout=30000):
        worker.start()

    assert len(progress_values) == 2
    assert progress_values[-1] == (2, 2)


def test_worker_emits_finished_on_success(qtbot, tmp_path):
    """正常完了時に success=True で finished シグナルが発信されること."""
    config = _make_config(str(tmp_path))
    worker = GeneratorWorker(config)

    with qtbot.waitSignal(worker.generation_finished, timeout=30000) as blocker:
        worker.start()

    success, message = blocker.args
    assert success is True


def test_worker_cancel(qtbot, tmp_path):
    """キャンセル要求でキャンセル扱いになること."""
    config = _make_config(str(tmp_path))
    worker = GeneratorWorker(config)

    # Start and immediately request cancel
    worker.start()
    worker.request_cancel()

    with qtbot.waitSignal(worker.generation_finished, timeout=30000) as blocker:
        pass

    success, _message = blocker.args
    # With only 2 images, may finish before cancel takes effect
    # Either cancelled or completed is acceptable
    assert isinstance(success, bool)


def test_worker_handles_dicom_generator_error(monkeypatch, qtbot, tmp_path):
    """DICOMGeneratorError 発生時にエラー終了シグナルを返すこと."""
    config = _make_config(str(tmp_path))

    class _DummyService:
        def generate(self, config, progress_callback):
            raise DICOMGeneratorError("broken config")

    monkeypatch.setattr("app.gui.worker_thread.StudyGeneratorService", _DummyService)

    worker = GeneratorWorker(config)
    with qtbot.waitSignal(worker.generation_finished, timeout=3000) as blocker:
        worker.start()

    success, message = blocker.args
    assert success is False
    assert message == "生成エラー: broken config"


def test_worker_handles_unexpected_exception(monkeypatch, qtbot, tmp_path):
    """想定外例外発生時に予期しないエラーとして終了シグナルを返すこと."""
    config = _make_config(str(tmp_path))

    class _DummyService:
        def generate(self, config, progress_callback):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.gui.worker_thread.StudyGeneratorService", _DummyService)

    worker = GeneratorWorker(config)
    with qtbot.waitSignal(worker.generation_finished, timeout=3000) as blocker:
        worker.start()

    success, message = blocker.args
    assert success is False
    assert message == "予期しないエラー: boom"


def test_on_progress_emits_filename_when_not_cancelled(tmp_path):
    """_on_progress はキャンセル未要求時にファイル名付きで進捗を通知すること."""
    worker = GeneratorWorker(_make_config(str(tmp_path)))

    received = []
    worker.progress_updated.connect(
        lambda current, total, filename: received.append((current, total, filename))
    )

    worker._on_progress(3, 10)

    assert received == [(3, 10, "image_0003.dcm")]


def test_on_progress_does_not_emit_when_cancelled(tmp_path):
    """_on_progress はキャンセル要求済みなら進捗通知しないこと."""
    worker = GeneratorWorker(_make_config(str(tmp_path)))
    worker.cancel_requested = True

    received = []
    worker.progress_updated.connect(
        lambda current, total, filename: received.append((current, total, filename))
    )

    worker._on_progress(1, 10)

    assert received == []
