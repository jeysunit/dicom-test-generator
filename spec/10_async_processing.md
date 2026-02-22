# 10. 非同期処理仕様

## 概要

GUIでの非同期処理（QThread）を定義する。

**Phase**: Phase 2 (GUI)

**目的**: 大量のDICOMファイル生成時にGUIがフリーズしないようにする。

---

## アーキテクチャ

```text
MainWindow (UI Thread)
    ↓ start()
GeneratorWorker (Worker Thread)
    ↓ progress_updated Signal
MainWindow.update_progress()
    ↓ generation_finished Signal
MainWindow.on_finished()
```

---

## GeneratorWorker

### クラス定義

```python
# app/gui/worker_thread.py
from PySide6.QtCore import QThread, Signal
from app.core.models import GenerationConfig, GenerationResult
from app.services.study_generator import StudyGeneratorService
import logging

logger = logging.getLogger("dicom_generator.worker")

class GeneratorWorker(QThread):
    """DICOM生成ワーカースレッド"""
    
    # シグナル定義
    progress_updated = Signal(int, int, str)  # (current, total, message)
    generation_finished = Signal(bool, str)   # (success, message)
    
    def __init__(self, config: GenerationConfig):
        super().__init__()
        self.config = config
        self.cancel_requested = False
        self.service = StudyGeneratorService()
    
    def run(self):
        """ワーカースレッド実行"""
        try:
            # 合計画像数計算
            total_images = sum(s.num_images for s in self.config.series_list)
            current = 0
            
            # シリーズごとに生成
            for series_config in self.config.series_list:
                if self.cancel_requested:
                    self.generation_finished.emit(
                        False,
                        f"Cancelled by user. Generated {current}/{total_images} images"
                    )
                    return
                
                # 画像生成
                for img_idx in range(series_config.num_images):
                    if self.cancel_requested:
                        self.generation_finished.emit(
                            False,
                            f"Cancelled. Generated {current}/{total_images} images"
                        )
                        return
                    
                    # 1画像生成
                    filepath = self._generate_image(series_config, img_idx)
                    
                    # 進捗更新
                    current += 1
                    filename = os.path.basename(filepath)
                    self.progress_updated.emit(current, total_images, filename)
            
            # 完了
            self.generation_finished.emit(
                True,
                f"Successfully generated {current} images"
            )
        
        except Exception as e:
            logger.error(f"Worker thread error: {e}", exc_info=True)
            self.generation_finished.emit(False, str(e))
    
    def request_cancel(self):
        """キャンセル要求"""
        self.cancel_requested = True
        logger.info("Cancel requested")
    
    def _generate_image(self, series_config, img_idx):
        """1画像生成（実装例）"""
        # Core Engineを呼び出し
        # ...
        return filepath
```

---

## MainWindowでの使用

### シグナル接続

```python
# app/gui/main_window.py
from PySide6.QtCore import Slot
from .worker_thread import GeneratorWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.setup_ui()
    
    @Slot()
    def on_generate_clicked(self):
        """生成開始ボタン"""
        # 設定収集
        config = self.collect_config()
        
        # バリデーション
        if not self.validate_config(config):
            return
        
        # ワーカースレッド作成
        self.worker = GeneratorWorker(config)
        
        # シグナル接続
        self.worker.progress_updated.connect(self.on_progress_updated)
        self.worker.generation_finished.connect(self.on_generation_finished)
        
        # スレッド開始
        self.worker.start()
        
        # ボタン状態変更
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_widget.setVisible(True)
    
    @Slot()
    def on_cancel_clicked(self):
        """キャンセルボタン"""
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("キャンセル中...")
    
    @Slot(int, int, str)
    def on_progress_updated(self, current: int, total: int, filename: str):
        """進捗更新（UIスレッドで実行）"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"生成中: {filename}")
        self.statusBar().showMessage(f"{current}/{total} 画像生成済み")
    
    @Slot(bool, str)
    def on_generation_finished(self, success: bool, message: str):
        """生成完了（UIスレッドで実行）"""
        # ボタン状態復帰
        self.generate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("キャンセル")
        
        # ワーカースレッド解放
        if self.worker:
            self.worker.wait()  # スレッド終了を待つ
            self.worker = None
        
        # 結果表示
        if success:
            QMessageBox.information(self, "完了", message)
            self.statusBar().showMessage("生成完了")
        else:
            QMessageBox.warning(self, "エラー", message)
            self.statusBar().showMessage("生成失敗")
```

---

## キャンセル処理

### キャンセル時の挙動

| 項目 | 仕様 |
|------|------|
| **中断単位** | 画像単位（1ファイル生成後に中断） |
| **途中生成ファイル** | 削除せず残す（部分的なデータとして利用可能） |
| **ログ** | "Generation cancelled. XX/YY files generated." と記録 |
| **進捗表示** | "キャンセル中..."と表示、完了までボタン無効 |

### 実装例

```python
class GeneratorWorker(QThread):
    def run(self):
        for i in range(total):
            # キャンセルチェック
            if self.cancel_requested:
                logger.info(f"Cancelled. Generated {i}/{total} images")
                self.generation_finished.emit(False, "Cancelled by user")
                return
            
            # 画像生成
            generate_image(i)
        
        # 正常完了
        self.generation_finished.emit(True, "Completed")
```

---

## エラーハンドリング

### ワーカースレッド内でのエラー

```python
class GeneratorWorker(QThread):
    def run(self):
        try:
            # 生成処理
            for i in range(total):
                if self.cancel_requested:
                    return
                
                generate_image(i)
            
            self.generation_finished.emit(True, "Success")
        
        except ConfigurationError as e:
            logger.error(f"Configuration error: {e}")
            self.generation_finished.emit(False, f"設定エラー: {e}")
        
        except GenerationError as e:
            logger.error(f"Generation error: {e}")
            self.generation_finished.emit(False, f"生成エラー: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            self.generation_finished.emit(False, f"予期しないエラー: {e}")
```

### UIスレッドでのエラー表示

```python
@Slot(bool, str)
def on_generation_finished(self, success: bool, message: str):
    if success:
        QMessageBox.information(self, "完了", message)
    else:
        # エラーメッセージをダイアログ表示
        QMessageBox.critical(self, "エラー", message)
```

---

## 進捗表示

### プログレスバー

```python
# app/gui/widgets/progress_widget.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel

class ProgressWidget(QWidget):
    """進捗表示ウィジェット"""
    
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("待機中")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
    
    def update_progress(self, current: int, total: int, filename: str):
        """進捗更新"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"生成中: {filename} ({current}/{total})")
    
    def reset(self):
        """リセット"""
        self.progress_bar.setValue(0)
        self.status_label.setText("待機中")
```

---

## スレッドセーフ

### 重要な注意点

UIウィジェットの操作はUIスレッドのみで行うこと。

```python
# ❌ 悪い例（ワーカースレッドからUI操作）
class GeneratorWorker(QThread):
    def run(self):
        for i in range(total):
            # ❌ ワーカースレッドからUI操作してはいけない
            self.main_window.progress_bar.setValue(i)

# ✅ 良い例（シグナル経由）
class GeneratorWorker(QThread):
    progress_updated = Signal(int)
    
    def run(self):
        for i in range(total):
            # ✅ シグナルを発信
            self.progress_updated.emit(i)

# MainWindow（UIスレッド）でシグナル受信
worker.progress_updated.connect(lambda i: progress_bar.setValue(i))
```

### 共有データへのアクセス

```python
# データ共有が必要な場合はロック
from PySide6.QtCore import QMutex

class SharedData:
    def __init__(self):
        self.mutex = QMutex()
        self.counter = 0
    
    def increment(self):
        self.mutex.lock()
        try:
            self.counter += 1
        finally:
            self.mutex.unlock()
```

**ただし**: 本アプリではデータ共有は不要（ワーカーは独立して動作）

---

## 複数ワーカー（将来拡張）

Phase 2では単一ワーカーのみ。Phase 3以降で複数ワーカー対応検討。

```python
# 将来的な拡張例
class MainWindow(QMainWindow):
    def __init__(self):
        self.workers = []
    
    def start_parallel_generation(self, configs):
        """複数ワーカーで並列生成"""
        for config in configs:
            worker = GeneratorWorker(config)
            worker.generation_finished.connect(self.on_worker_finished)
            worker.start()
            self.workers.append(worker)
```

---

## テスト

### ワーカースレッドのテスト

```python
# tests/gui/test_worker_thread.py
import pytest
from pytestqt.qtbot import QtBot
from app.gui.worker_thread import GeneratorWorker

def test_worker_emits_progress(qtbot):
    """ワーカーが進捗シグナルを発信するか"""
    config = GenerationConfig(...)
    worker = GeneratorWorker(config)
    
    with qtbot.waitSignal(worker.progress_updated, timeout=10000):
        worker.start()

def test_worker_cancel(qtbot):
    """キャンセルが正しく動作するか"""
    config = GenerationConfig(...)
    worker = GeneratorWorker(config)
    
    worker.start()
    worker.request_cancel()
    
    with qtbot.waitSignal(worker.generation_finished, timeout=5000) as blocker:
        pass
    
    success, message = blocker.args
    assert not success
    assert "Cancelled" in message
```

---

## パフォーマンス考慮

### 進捗更新頻度

```python
# 画像1枚ごとに更新（通常）
for i in range(total):
    generate_image(i)
    self.progress_updated.emit(i, total, filename)

# 大量生成時は10枚ごとに更新
for i in range(total):
    generate_image(i)
    if i % 10 == 0:
        self.progress_updated.emit(i, total, filename)
```

### メモリ管理

```python
class GeneratorWorker(QThread):
    def run(self):
        # 大きなオブジェクトは適宜解放
        for i in range(total):
            pixels = generate_pixels()
            save_dicom(pixels)
            del pixels  # 明示的に解放
```

---

## 次のステップ

1. [11_storage_scp.md](11_storage_scp.md) でStorage SCP仕様を確認（Phase 1.5）
2. ワーカースレッド実装（`app/gui/worker_thread.py`）
3. MainWindowへの統合
