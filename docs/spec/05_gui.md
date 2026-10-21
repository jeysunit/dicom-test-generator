# 05. PySide6 のデスクトップの画面

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 概要

> **機能を足さない**: この PySide6 の画面は機能を増やさない。直すのは壊れた
> ときだけで、モダリティエミュレーターの画面（ワークリスト・撮影・PACS・設定）は
> Web 画面を使う（[ADR-0011](../decisions/0011-modality-emulator.md) の案 B）。
> Web 画面は [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の 10 章が決める。
> コードは外していない。この文書は、実装済みの範囲だけを書く。

PySide6 の画面は、Job YAML を書かずに、患者・シリーズ・出力先を選んで
DICOM ファイルを生成するための画面である。生成の本体は Service Layer
（`StudyGeneratorService`）が持ち、画面は設定を集めて呼ぶだけにする。
生成は別スレッド（QThread）で動かし、画面を止めない。

**起動**: `python -m app.gui`

**依存**: Core Engine、Service Layer（`app/services/`）

---

## 実装済みの範囲

```text
app/gui/
├── __init__.py
├── __main__.py            # 起動（python -m app.gui）
├── main_window.py         # メインウィンドウ（MainWindow）
├── worker_thread.py       # 生成のワーカー（GeneratorWorker、QThread）
└── widgets/
    ├── template_selector.py   # TemplateSelector
    ├── patient_form.py        # PatientForm
    ├── series_config.py       # SeriesConfigWidget
    ├── output_config.py       # OutputConfigWidget
    └── progress_widget.py     # ProgressWidget
```

### メインウィンドウ

題は「DICOMテストデータ生成ツール v1.1」、大きさは 900 x 1000。
メニューバーは無い。縦に並べたグループを、スクロールできる領域に置く。

```text
┌──────────────────────────────────────────────────┐
│ DICOMテストデータ生成ツール v1.1                 │
├──────────────────────────────────────────────────┤
│ ┌ テンプレート選択 ───────────────────────────┐ │
│ │ モダリティ:  [Ct Generic                ▼] │ │
│ │ 病院設定:    [なし                      ▼] │ │
│ └────────────────────────────────────────────┘ │
│ ┌ 患者情報 ───────────────────────────────────┐ │
│ │ 患者選択:    [P000001 - YAMADA TARO     ▼] │ │
│ │ Patient ID / Patient Name / Birth Date / Sex │ │
│ └────────────────────────────────────────────┘ │
│ ┌ 検査情報 ───────────────────────────────────┐ │
│ │ Accession Number:  [ACC000001            ] │ │
│ └────────────────────────────────────────────┘ │
│ ┌ シリーズ・画像設定 ─────────────────────────┐ │
│ │ シリーズ数:  [1]                            │ │
│ │ シリーズ1: 画像数 [20]  スライス厚 [5.0 mm] │ │
│ └────────────────────────────────────────────┘ │
│ ┌ 出力設定 ───────────────────────────────────┐ │
│ │ 出力先:  [output                  ] [参照]  │ │
│ └────────────────────────────────────────────┘ │
│            [生成開始]     [キャンセル]          │
│ ┌ 進捗 ───────────────────────────────────────┐ │
│ │ ████████░░░░  60%   生成中: ... (24/41)     │ │
│ └────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### ウィジェット

| ウィジェット | 役割 | 取り出す値 |
|-------------|------|-----------|
| `TemplateSelector` | `templates/modality/` と `templates/hospital/` の YAML を一覧にして選ぶ。病院は「なし」を先頭に置く | `get_modality()`・`get_hospital()`（「なし」は `None`） |
| `PatientForm` | `PatientLoaderService` が読む患者マスターから選び、欄に写す。欄は直せる。氏名は `=` で字種を区切る（`YAMADA^TARO=山田^太郎`） | `get_patient()` |
| `SeriesConfigWidget` | シリーズ数（1〜10）と、シリーズごとの画像数（1〜10000、既定 20）・スライス厚（既定 5.0 mm） | `get_series_list()` |
| `OutputConfigWidget` | 出力先のフォルダ。「参照」でフォルダ選択のダイアログを開く | `get_output_dir()` |
| `ProgressWidget` | 進捗バーと状態の文（待機中／生成中） | `update_progress()`・`reset()` |

Accession Number は `MainWindow` の「検査情報」の欄で、空なら設定エラーにする。
検査日と検査時刻は、生成を始めた時刻から決める。
ピクセルは `PixelSpecCTRealistic`、転送構文・文字セット・異常の設定は既定値で固定する。
`device_profile`（spec/13）は画面から選べない。

出力ファイル名の規則は、CLI と同じく Core が決める（[04_cli.md](04_cli.md)）。

### 生成の流れ

1. 「生成開始」で `MainWindow._collect_config()` が各ウィジェットから `GenerationConfig` を作る。
   作れなければ警告のダイアログを出して止める。
2. `GeneratorWorker` を作って開始し、「生成開始」を無効に、「キャンセル」を有効にする。
3. 進捗のシグナルでバーを更新する。
4. 終了のシグナルで、ボタンを元に戻し、成功なら「完了」、失敗なら「エラー」のダイアログを出す。

---

## 非同期処理

生成は数百枚を超えることがあるので、`GeneratorWorker`（`QThread`）で動かす。
この節の決まりは GUI だけに適用する。CLI とWeb 画面は別の仕組みで動く。

**規則**: ウィジェットの操作は UI スレッドだけで行い、ワーカーとの受け渡しはシグナルだけにする。
共有データへのロックは要らない（ワーカーは設定を受け取って独立に動く）。

```text
MainWindow（UI スレッド）
    ↓ start()
GeneratorWorker（ワーカースレッド）
    ↓ progress_updated(current, total, filename)
MainWindow._on_progress_updated → ProgressWidget
    ↓ generation_finished(success, message)
MainWindow._on_generation_finished
```

### GeneratorWorker

| 項目 | 内容 |
|------|------|
| 場所 | `app/gui/worker_thread.py` |
| シグナル | `progress_updated(int, int, str)`（現在・合計・ファイル名）、`generation_finished(bool, str)`（成功か・メッセージ） |
| 実行 | `run()` が `StudyGeneratorService().generate(config, progress_callback=...)` を呼ぶ |
| 進捗 | Service のコールバック `(current, total)` を受けて `progress_updated` を出す。ファイル名は `image_NNNN.dcm` の形の表示用の名前 |
| 失敗 | `DICOMGeneratorError` は「生成エラー: ...」、それ以外は「予期しないエラー: ...」で `generation_finished(False, ...)` を出す。どちらもログに残す |

### キャンセル

| 項目 | 内容 |
|------|------|
| 要求 | 「キャンセル」で `request_cancel()` を呼び、`cancel_requested` を立てる。ボタンは無効になり「キャンセル中...」と出る |
| 効果 | 要求の後は進捗のシグナルを出さない。Service の生成は途中で止めず、`generate()` が戻った後に `cancel_requested` を見て `generation_finished(False, "Cancelled by user")` を出す |
| 生成済みのファイル | 削除せず残す |

つまり、キャンセルは生成を中断せず、完了の通知を「キャンセルされた」に変える。
枚数が多い生成を途中で止める機能は無い。

### 終了の後始末

`_on_generation_finished` はワーカーを最大 5 秒待ち（`wait(5000)`）、
終わらなければ警告をログに出し、参照を捨てる。

---

## テスト

`tests/gui/` に pytest-qt の試験がある。表示の無い環境で動かすため、
`QT_QPA_PLATFORM=offscreen` を指定する（CI も同じ。`.github/workflows/ci.yml`）。

| ファイル | 対象 |
|---------|------|
| `test_main_window.py` | 題・大きさ・ボタンの状態・設定の集め方・生成と取り消しと終了の画面の変化 |
| `test_widgets.py` | 各ウィジェットの値の取り出し |
| `test_worker_thread.py` | 進捗と終了のシグナル、キャンセル、例外の扱い |

```bash
QT_QPA_PLATFORM=offscreen pytest tests/gui/
```

---

## 作らない物

次は実装しておらず、凍結のため実装しない。Web 画面か CLI を使う。

- メニューバー（Job YAML の読み込み・保存を含む）
- シリーズごとの詳細設定のダイアログ
- ログビューア
- スタイルシート（QSS）
- 設定の永続化
- 複数のワーカーによる並列生成
