# 05. GUI仕様

## 概要

PySide6を使用したデスクトップGUIアプリケーション。

**Phase**: Phase 2

**依存**: Phase 0 (Core Engine), Phase 1 (Service Layer)

---

## メインウィンドウ

### レイアウト

```text
┌──────────────────────────────────────────────────────────────┐
│ DICOMテストデータ生成ツール v1.1                             │
├──────────────────────────────────────────────────────────────┤
│ [ファイル] [編集] [表示] [ヘルプ]                           │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ テンプレート選択                                      │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ モダリティ:  [FUJIFILM SCENARIA View CT     ▼]      │    │
│ │ 病院設定:    [A病院（日本語使用）           ▼]      │    │
│ │              ├ なし（モダリティ標準）                │    │
│ │              ├ A病院（日本語使用）                   │    │
│ │              └ B病院（ローマ字のみ）                 │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ 患者情報                                              │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ 患者選択:    [P000001 - YAMADA TARO         ▼]      │    │
│ │                                                       │    │
│ │ Patient ID:          [P000001              ] □異常   │    │
│ │ Patient Name:        [YAMADA^TARO=山田^太郎]         │    │
│ │                      (病院設定に応じて表示)          │    │
│ │ Birth Date:          [19800115             ] □異常   │    │
│ │ Sex:                 [M ▼]                   □異常   │    │
│ │ Age:                 [044Y                 ]         │    │
│ │ Weight (kg):         [65.5                 ]         │    │
│ │ Size (m):            [1.70                 ]         │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ 検査情報                                              │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ Accession Number:    [ACC000001            ] □異常   │    │
│ │ Study Date:          [2024/01/15           ] □異常   │    │
│ │ Study Time:          [14:30:00             ]         │    │
│ │ Study Description:   [CT CHEST             ]         │    │
│ │ Referring Physician: [TANAKA^JIRO=田中^次郎]         │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ 詳細設定                                              │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ Pixel Data Mode:     [CT Realistic ▼]               │    │
│ │ Transfer Syntax:     [Implicit VR Little Endian ▼]  │    │
│ │ 異常生成レベル:      [なし ▼]                       │    │
│ │ ☑ SOP Instance UIDに0始まり不正を含める(10%)        │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ シリーズ・画像設定                                    │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ シリーズ数:          [3  ]                           │    │
│ │                                                       │    │
│ │ シリーズ1:           [1  ]枚  Slice Thickness [5.0mm]│    │
│ │                      [詳細設定...]                    │    │
│ │ シリーズ2:           [20 ]枚  Slice Spacing   [5.0mm]│    │
│ │                      [詳細設定...]                    │    │
│ │ シリーズ3:           [20 ]枚  Start Z         [0.0mm]│    │
│ │                      [詳細設定...]                    │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ 出力設定                                              │    │
│ ├──────────────────────────────────────────────────────┤    │
│ │ 出力先:              [output/ACC000001     ] [参照]  │    │
│ │ ファイル名形式:      患者ID_検査日_モダリティ_連番   │    │
│ │ 例:                  P000001_20240115_CT_001.dcm     │    │
│ └──────────────────────────────────────────────────────┘    │
│                                                               │
│              [生成開始]           [キャンセル]               │
│                                                               │
│ ┌──────────────────────────────────────────────────────┐    │
│ │ 進捗状況                                              │    │
│ │ ████████████████░░░░░░░░░░░░  60% (24/41)           │    │
│ │ 生成中: P000001_20240115_CT_024.dcm                  │    │
│ └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## ウィジェット仕様

### テンプレート選択

```python
class TemplateSelector(QWidget):
    """テンプレート選択ウィジェット"""
    
    template_changed = Signal(str, str)  # (modality, hospital)
    
    def __init__(self):
        self.modality_combo = QComboBox()
        self.hospital_combo = QComboBox()
        
    def load_templates(self):
        """テンプレート一覧を読み込み"""
        modalities = scan_modality_templates()
        self.modality_combo.addItems(modalities)
        
        hospitals = ["なし"] + scan_hospital_templates()
        self.hospital_combo.addItems(hospitals)
```

### 患者選択

```python
class PatientSelector(QWidget):
    """患者選択・編集ウィジェット"""
    
    patient_changed = Signal(Patient)
    
    def __init__(self):
        self.patient_combo = QComboBox()
        self.patient_id_edit = QLineEdit()
        self.patient_name_edit = QLineEdit()
        # ...
        
    def load_patient_master(self, filepath):
        """患者マスター読み込み"""
        patients = load_patients(filepath)
        for p in patients:
            self.patient_combo.addItem(
                f"{p.patient_id} - {p.patient_name.alphabetic}",
                userData=p
            )
    
    def on_patient_selected(self, index):
        """患者選択時"""
        patient = self.patient_combo.itemData(index)
        self.populate_fields(patient)
```

### シリーズ設定

```python
class SeriesConfigWidget(QWidget):
    """シリーズ設定ウィジェット"""
    
    def __init__(self, series_number: int):
        self.series_number = series_number
        self.num_images_spin = QSpinBox()
        self.slice_thickness_spin = QDoubleSpinBox()
        self.detail_button = QPushButton("詳細設定...")
        
    def get_config(self) -> SeriesConfig:
        """設定取得"""
        return SeriesConfig(
            series_number=self.series_number,
            num_images=self.num_images_spin.value(),
            slice_thickness=self.slice_thickness_spin.value(),
            # ...
        )
```

### 進捗表示

```python
class ProgressWidget(QWidget):
    """進捗表示ウィジェット"""
    
    def __init__(self):
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("待機中")
        
    def update_progress(self, current: int, total: int, filename: str):
        """進捗更新"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"生成中: {filename}")
```

---

## メインウィンドウクラス

```python
# app/gui/main_window.py
from PySide6.QtWidgets import QMainWindow, QMessageBox
from PySide6.QtCore import Slot
from .worker_thread import GeneratorWorker

class MainWindow(QMainWindow):
    """メインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOMテストデータ生成ツール v1.1")
        self.resize(900, 1000)
        
        self.worker = None
        self.setup_ui()
        self.connect_signals()
        
    def setup_ui(self):
        """UI構築"""
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        
        # テンプレート選択
        self.template_selector = TemplateSelector()
        layout.addWidget(self.template_selector)
        
        # 患者情報
        self.patient_selector = PatientSelector()
        layout.addWidget(self.patient_selector)
        
        # 検査情報
        self.study_widget = StudyWidget()
        layout.addWidget(self.study_widget)
        
        # 詳細設定
        self.detail_widget = DetailWidget()
        layout.addWidget(self.detail_widget)
        
        # シリーズ設定
        self.series_widget = SeriesListWidget()
        layout.addWidget(self.series_widget)
        
        # 出力設定
        self.output_widget = OutputWidget()
        layout.addWidget(self.output_widget)
        
        # ボタン
        button_layout = QHBoxLayout()
        self.generate_button = QPushButton("生成開始")
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        # 進捗
        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget)
        
        self.setCentralWidget(central_widget)
        
    def connect_signals(self):
        """シグナル接続"""
        self.generate_button.clicked.connect(self.on_generate_clicked)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        
    @Slot()
    def on_generate_clicked(self):
        """生成開始ボタン"""
        # 設定収集
        config = self.collect_config()
        
        # バリデーション
        if not self.validate_config(config):
            return
        
        # ワーカースレッド起動
        self.worker = GeneratorWorker(config)
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.generation_finished.connect(self.on_generation_finished)
        self.worker.start()
        
        # ボタン状態変更
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        
    @Slot()
    def on_cancel_clicked(self):
        """キャンセルボタン"""
        if self.worker:
            self.worker.request_cancel()
            
    @Slot(int, int, str)
    def on_progress_updated(self, current: int, total: int, filename: str):
        """進捗更新"""
        self.progress_widget.update_progress(current, total, filename)
        
    @Slot(bool, str)
    def on_generation_finished(self, success: bool, message: str):
        """生成完了"""
        # ボタン状態復帰
        self.generate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "完了", message)
        else:
            QMessageBox.warning(self, "エラー", message)
    
    def collect_config(self) -> GenerationConfig:
        """GUI設定を収集"""
        return GenerationConfig(
            job_name=f"GUI_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            output_dir=self.output_widget.get_output_dir(),
            patient=self.patient_selector.get_patient(),
            study=self.study_widget.get_study_config(),
            series_list=self.series_widget.get_series_list(),
            # ...
        )
    
    def validate_config(self, config: GenerationConfig) -> bool:
        """設定検証"""
        try:
            config.model_validate(config)
            return True
        except ValidationError as e:
            QMessageBox.warning(self, "検証エラー", str(e))
            return False
```

---

## メニューバー

### ファイルメニュー

| 項目 | ショートカット | 動作 |
|------|--------------|------|
| Job設定を開く... | Ctrl+O | Job YAMLを読み込み |
| Job設定を保存... | Ctrl+S | Job YAMLとして保存 |
| 終了 | Ctrl+Q | アプリ終了 |

### 編集メニュー

| 項目 | 動作 |
|------|------|
| 設定をリセット | デフォルト値に戻す |
| 患者マスター再読み込み | 患者マスター再スキャン |

### 表示メニュー

| 項目 | 動作 |
|------|------|
| ログウィンドウ | ログ表示ダイアログ |

### ヘルプメニュー

| 項目 | 動作 |
|------|------|
| ドキュメント | ブラウザでドキュメント表示 |
| バージョン情報 | バージョンダイアログ |

---

## ダイアログ

### シリーズ詳細設定ダイアログ

```python
class SeriesDetailDialog(QDialog):
    """シリーズ詳細設定ダイアログ"""
    
    def __init__(self, series_config: SeriesConfig):
        super().__init__()
        self.setWindowTitle(f"シリーズ{series_config.series_number} 詳細設定")
        
        layout = QFormLayout()
        
        self.series_desc_edit = QLineEdit(series_config.series_description)
        layout.addRow("Series Description:", self.series_desc_edit)
        
        self.protocol_edit = QLineEdit(series_config.protocol_name)
        layout.addRow("Protocol Name:", self.protocol_edit)
        
        self.slice_thickness_spin = QDoubleSpinBox()
        self.slice_thickness_spin.setValue(series_config.slice_thickness)
        layout.addRow("Slice Thickness (mm):", self.slice_thickness_spin)
        
        # OK/Cancelボタン
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
        
        self.setLayout(layout)
```

### ログビューアダイアログ

```python
class LogViewerDialog(QDialog):
    """ログビューアダイアログ"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ログビューア")
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text)
        
        # 更新ボタン
        refresh_button = QPushButton("更新")
        refresh_button.clicked.connect(self.load_log)
        layout.addWidget(refresh_button)
        
        self.setLayout(layout)
        self.load_log()
        
    def load_log(self):
        """ログファイル読み込み"""
        try:
            with open("logs/dicom_generator.log") as f:
                content = f.read()
                self.log_text.setPlainText(content)
                # 最後までスクロール
                self.log_text.moveCursor(QTextCursor.End)
        except FileNotFoundError:
            self.log_text.setPlainText("ログファイルが見つかりません")
```

---

## 設定の永続化

### Job YAMLの読み込み・保存

```python
class MainWindow(QMainWindow):
    
    def load_job_file(self):
        """Job YAML読み込み"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Job設定を開く",
            "",
            "YAML Files (*.yaml *.yml)"
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath) as f:
                job_dict = yaml.safe_load(f)
            
            config = GenerationConfig(**job_dict)
            self.populate_from_config(config)
            
            QMessageBox.information(self, "成功", "Job設定を読み込みました")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"読み込み失敗: {e}")
    
    def save_job_file(self):
        """Job YAML保存"""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Job設定を保存",
            "",
            "YAML Files (*.yaml)"
        )
        
        if not filepath:
            return
        
        try:
            config = self.collect_config()
            config_dict = config.model_dump()
            
            with open(filepath, 'w') as f:
                yaml.safe_dump(config_dict, f, allow_unicode=True)
            
            QMessageBox.information(self, "成功", "Job設定を保存しました")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"保存失敗: {e}")
```

---

## スタイル

### QSSスタイルシート

```python
# app/gui/styles.py

MAIN_STYLE = """
QGroupBox {
    font-weight: bold;
    border: 1px solid #CCCCCC;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
}

QPushButton#generate_button {
    background-color: #4CAF50;
    color: white;
    font-weight: bold;
    padding: 10px;
    border-radius: 5px;
}

QPushButton#generate_button:hover {
    background-color: #45a049;
}

QPushButton#generate_button:disabled {
    background-color: #CCCCCC;
}

QPushButton#cancel_button {
    background-color: #f44336;
    color: white;
    padding: 10px;
    border-radius: 5px;
}
"""

# 適用
app.setStyleSheet(MAIN_STYLE)
```

---

## 実装ガイドライン

### ファイル構成

```text
app/gui/
├── __init__.py
├── main_window.py        # メインウィンドウ
├── worker_thread.py      # QThreadワーカー
├── widgets/
│   ├── __init__.py
│   ├── template_selector.py
│   ├── patient_selector.py
│   ├── series_widget.py
│   └── progress_widget.py
├── dialogs/
│   ├── __init__.py
│   ├── series_detail_dialog.py
│   └── log_viewer_dialog.py
└── styles.py             # QSSスタイル
```

### エントリポイント

```python
# app/gui/__main__.py
import sys
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # アプリケーション情報設定
    app.setApplicationName("DICOMテストデータ生成ツール")
    app.setApplicationVersion("1.1.0")
    app.setOrganizationName("DICOM Generator Project")
    
    # メインウィンドウ表示
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
```

### 起動方法

```bash
python -m app.gui
```

---

## テスト

### UIテスト（pytest-qt）

```python
# tests/gui/test_main_window.py
import pytest
from pytestqt.qtbot import QtBot
from app.gui.main_window import MainWindow

def test_main_window_creation(qtbot):
    """メインウィンドウ作成テスト"""
    window = MainWindow()
    qtbot.addWidget(window)
    
    assert window.windowTitle() == "DICOMテストデータ生成ツール v1.1"

def test_generate_button_click(qtbot):
    """生成ボタンクリックテスト"""
    window = MainWindow()
    qtbot.addWidget(window)
    
    # 初期状態
    assert window.generate_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    
    # TODO: 設定入力してクリック
```

---

## 次のステップ

1. [10_async_processing.md](10_async_processing.md) で非同期処理を確認
2. GUI実装
3. UIテスト作成
