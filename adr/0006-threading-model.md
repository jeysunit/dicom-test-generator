# ADR-0006: Threading Model

## Status
**Accepted** - 2025-02-21

## Context
GUI での大量DICOM生成時にUIがフリーズしないための非同期処理方式を決定する必要がある。

### 問題
- 100枚のDICOM生成に約10秒かかる
- メインスレッド（UIスレッド）で実行するとGUIがフリーズ
- ユーザーはキャンセルできない
- 進捗表示ができない

### 選択肢
1. **QThread** (PySide6組み込み)
2. **threading.Thread** (Python標準ライブラリ)
3. **asyncio** (Python 3.7+)
4. **multiprocessing** (マルチプロセス)
5. **concurrent.futures** (ThreadPoolExecutor)

### 要求
- GUIフリーズしない
- 進捗表示可能
- キャンセル可能
- PySide6と統合しやすい

## Decision
**QThread を採用する**

### 理由

#### QThread の利点
1. **PySide6ネイティブ**
   - Qt Signal/Slotで簡単に通信
   - UIスレッドとの連携が自然

2. **進捗表示が簡単**
   ```python
   class Worker(QThread):
       progress = Signal(int, int, str)
       
       def run(self):
           for i in range(total):
               # 処理
               self.progress.emit(i, total, filename)
   ```

3. **キャンセルが簡単**
   ```python
   def run(self):
       for i in range(total):
           if self.cancel_requested:
               return
           # 処理
   ```

4. **スレッドセーフ**
   - Qt EventLoopが安全に処理
   - UIウィジェットへのアクセスはUIスレッドのみ

#### threading.Thread を選ばない理由
- PySide6との統合が面倒
- Signal/Slotが使えない
- 手動でロック管理が必要

#### asyncio を選ばない理由
- PySide6との統合が複雑
- Qt EventLoopと競合しうる
- 学習コスト高い

#### multiprocessing を選ばない理由
- オーバーヘッドが大きい
- プロセス間通信が複雑
- 本アプリではI/O boundなのでスレッドで十分

#### concurrent.futures を選ばない理由
- PySide6との統合が面倒
- QThreadの方がQt標準

## Consequences

### Positive
- ✅ GUIフリーズしない
- ✅ リアルタイム進捗表示
- ✅ いつでもキャンセル可能
- ✅ Signal/Slotで安全な通信
- ✅ PySide6のベストプラクティス

### Negative
- ⚠️ **GIL（Global Interpreter Lock）の制約**
  - PythonスレッドはCPUバウンド処理では並列化されない
  - **影響なし**: 本アプリはI/Oバウンド（ファイル書き込み）
- ⚠️ **複数ワーカー未対応（Phase 2）**
  - Phase 3以降で検討

### Tradeoffs
- QThreadはQt依存だが、本アプリはQt前提なので問題なし
- マルチプロセスより遅いが、オーバーヘッドが少ない

## Implementation

### GeneratorWorker

```python
# app/gui/worker_thread.py
from PySide6.QtCore import QThread, Signal

class GeneratorWorker(QThread):
    """DICOM生成ワーカースレッド"""
    
    progress_updated = Signal(int, int, str)
    generation_finished = Signal(bool, str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.cancel_requested = False
    
    def run(self):
        try:
            total = calculate_total(self.config)
            
            for i in range(total):
                if self.cancel_requested:
                    self.generation_finished.emit(False, "Cancelled")
                    return
                
                # 生成処理
                filepath = generate_image(i)
                self.progress_updated.emit(i + 1, total, filepath)
            
            self.generation_finished.emit(True, "Completed")
        
        except Exception as e:
            self.generation_finished.emit(False, str(e))
    
    def request_cancel(self):
        self.cancel_requested = True
```

### MainWindow

```python
# app/gui/main_window.py
class MainWindow(QMainWindow):
    def on_generate_clicked(self):
        self.worker = GeneratorWorker(config)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.generation_finished.connect(self.on_finished)
        self.worker.start()
        
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
    
    def on_cancel_clicked(self):
        if self.worker:
            self.worker.request_cancel()
    
    def update_progress(self, current, total, filename):
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
    
    def on_finished(self, success, message):
        self.generate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "完了", message)
```

### スレッドセーフのルール

**重要**: UIウィジェットの操作はUIスレッドのみ

```python
# ❌ 悪い例（ワーカースレッドからUI操作）
class Worker(QThread):
    def run(self):
        self.progress_bar.setValue(50)  # ❌ NG

# ✅ 良い例（シグナル経由）
class Worker(QThread):
    progress = Signal(int)
    
    def run(self):
        self.progress.emit(50)  # ✅ OK

# UIスレッドで受信
worker.progress.connect(lambda v: progress_bar.setValue(v))
```

## Performance
- **1画像生成**: <100ms
- **100画像生成**: <10秒
- **スレッドオーバーヘッド**: 無視できるレベル

**結論**: 単一スレッドで十分、マルチスレッド化は不要

## Future Extensions (Phase 3)
複数ワーカーで並列生成:

```python
class MainWindow(QMainWindow):
    def start_parallel(self, configs):
        self.workers = []
        for config in configs:
            worker = GeneratorWorker(config)
            worker.start()
            self.workers.append(worker)
```

ただし、Phase 2まではシングルワーカーのみ。

## Related Decisions
- [ADR-0003: PySide6 GUI](0003-pyside6-gui.md)
- [ADR-0001: Core Library First](0001-core-library-first.md)

## References
- [10_async_processing.md](../spec/10_async_processing.md)
- Qt Threading: https://doc.qt.io/qt-6/thread-basics.html
- Python GIL: https://docs.python.org/3/glossary.html#term-global-interpreter-lock
