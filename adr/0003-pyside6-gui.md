# ADR-0003: PySide6 GUI

## ステータス

**Accepted** - 2025-02-21

## 背景

デスクトップGUIフレームワークを選択する必要がある。

### 選択肢

1. **PySide6** (Qt for Python, LGPL/Commercial)
2. **PyQt6** (Qt for Python, GPL/Commercial)
3. **Tkinter** (標準ライブラリ)
4. **wxPython**
5. **Kivy**

### 要求

- クロスプラットフォーム（Windows / macOS / Linux）
- 商用利用可能
- プロフェッショナルな見た目
- 非同期処理（スレッド）サポート
- ファイルダイアログ等の標準UI

## 決定

PySide6を採用する。

### 理由

#### PySide6 の利点

1. **ライセンス: LGPL**
   - **商用利用可能**（動的リンクなら）
   - PyQt6はGPLまたは高額な商用ライセンスが必要

2. **Qt 6ベース**
   - モダンなUI
   - 高DPI対応
   - ダークモード対応

3. **公式サポート**
   - The Qt Companyが開発
   - 長期サポート保証

4. **機能が豊富**
   - QThread（非同期処理）
   - QProgressBar（進捗表示）
   - QFileDialog、QMessageBox等

5. **ドキュメントが充実**
   - 公式ドキュメント
   - Qt C++ドキュメントも参考になる

#### Tkinter を選ばない理由

- 見た目が古い
- 機能が限定的
- 非同期処理が面倒

#### wxPython を選ばない理由

- Qtほどモダンではない
- ドキュメントがQtより少ない

#### Kivy を選ばない理由

- モバイル向け
- デスクトップUIとしては過剰

## 影響

### 良い点

- ✅ 商用利用可能（LGPL）
- ✅ クロスプラットフォーム
- ✅ QThreadで非同期処理が簡単
- ✅ プロフェッショナルなUI
- ✅ 豊富なウィジェット

### 悪い点

- ⚠️ **サイズが大きい**: PySide6は約200MB
  - **影響**: インストールに時間がかかる
  - **軽減策**: 必要な人だけインストール（`pip install dicom-generator[gui]`）
- ⚠️ **学習曲線**: Tkinterよりやや複雑
  - **軽減策**: Phase 0, 1でCore/CLIを完成させてから着手

### トレードオフ

- Tkinterより重いが、機能・見た目は圧倒的に上
- PyQt6の方が資料多いが、LGPLライセンスの価値が高い

## 実装

### インストール

```bash
# Core + CLI のみ
pip install dicom-generator

# GUI付き
pip install dicom-generator[gui]
# => PySide6==6.7.0 を追加インストール
```

### requirements.txt

```text
# requirements-gui.txt（オプション依存）
PySide6>=6.7.0
```

### 基本構造

```python
# app/gui/main.py
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication([])
window = QMainWindow()
window.show()
app.exec()
```

### QThread使用例

```python
from PySide6.QtCore import QThread, Signal

class Worker(QThread):
    progress = Signal(int)
    
    def run(self):
        for i in range(100):
            self.progress.emit(i)
            time.sleep(0.1)

worker = Worker()
worker.progress.connect(lambda i: print(i))
worker.start()
```

## 関連する決定

- [ADR-0006: Threading Model](0006-threading-model.md)
- [ADR-0001: Core Library First](0001-core-library-first.md)

## 参考資料

- [05_gui.md](../spec/05_gui.md)
- PySide6: <https://doc.qt.io/qtforpython-6/>
- Qt Documentation: <https://doc.qt.io/qt-6/>
- LGPL License: <https://www.gnu.org/licenses/lgpl-3.0.html>
