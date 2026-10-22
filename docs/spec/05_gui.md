# 05. PySide6 のデスクトップ画面

PySide6 のデスクトップ画面（`python -m app.gui`）の、実装済みの範囲を定める。

## 1. 画面の役割

> **機能を追加しない**: この PySide6 の画面は機能を増やさない。修正するのは
> 壊れたときだけで、モダリティエミュレーターの画面（ワークリスト・撮影・PACS・
> 設定）は Web 画面を使う（[ADR-0011](../decisions/0011-modality-emulator.md) の
> 案 B）。Web 画面は [12a_web_screens_and_cli.md](12a_web_screens_and_cli.md) の
> 10 章で定める。コードは削除していない。

PySide6 の画面は、Job YAML を書かずに、患者・シリーズ・出力先を選んで
DICOM 画像を作成するための画面である。作成の本体は Service レイヤー
（`StudyGeneratorService`）が持ち、画面は設定を集めて呼ぶだけにする。
作成は別スレッド（QThread）で実行し、画面を止めない。

## 2. 構成

### 2.1 ファイル構成

```text
app/gui/
├── __init__.py
├── __main__.py            # 起動（python -m app.gui）
├── main_window.py         # メインウィンドウ（MainWindow）
├── worker_thread.py       # 作成のワーカー（GeneratorWorker、QThread）
└── widgets/
    ├── template_selector.py   # TemplateSelector
    ├── patient_form.py        # PatientForm
    ├── series_config.py       # SeriesConfigWidget
    ├── output_config.py       # OutputConfigWidget
    └── progress_widget.py     # ProgressWidget
```

### 2.2 メインウィンドウ

タイトルは「DICOMテストデータ生成ツール v1.1」、サイズは 900 x 1000。
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
│ │ 患者選択:    [P000001 - YAMADA^TARO     ▼] │ │
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
│ │ [output                         ] [参照...] │ │
│ └────────────────────────────────────────────┘ │
│            [生成開始]     [キャンセル]          │
│ ┌ 進捗 ───────────────────────────────────────┐ │
│ │ ████████░░░░  60%   生成中: ... (24/41)     │ │
│ └────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 2.3 ウィジェット

| ウィジェット | 役割 | 取得する値 |
|-------------|------|-----------|
| `TemplateSelector` | `templates/modality/` と `templates/hospital/` の YAML を一覧にして選択する。病院は「なし」を先頭に置く | `get_modality()`・`get_hospital()`（「なし」は `None`） |
| `PatientForm` | `PatientLoaderService` が読み込む患者マスターから選択し、入力欄に反映する。入力欄（Patient ID・氏名・生年月日・性別）は編集できる。氏名は `=` でコンポーネントグループを区切る（`YAMADA^TARO=山田^太郎`）。患者マスターを読み込めなければ、警告をログに出力して一覧を空にする | `get_patient()` |
| `SeriesConfigWidget` | シリーズ数（1〜10）と、シリーズごとの画像数（1〜10000、既定 20）・スライス厚（0.1〜100.0 mm、既定 5.0 mm）。スライス間隔はスライス厚と同じ値にする | `get_series_list()` |
| `OutputConfigWidget` | 出力先のフォルダ（既定 `output`）。「参照...」でフォルダ選択のダイアログを開く | `get_output_dir()` |
| `ProgressWidget` | 進捗バーと状態の表示（待機中／生成中） | `update_progress()`・`reset()` |

- Accession Number は `MainWindow` の「検査情報」の入力欄（16 文字まで）で、
  空なら設定エラーにする
- 検査日と検査時刻は、作成を開始した時刻から決める
- 体重と身長は画面から入力できない
- ピクセルは `PixelSpecCTRealistic`、Transfer Syntax・文字セット・異常の設定は
  既定値で固定する。`device_profile`
  （[13_device_profiles.md](13_device_profiles.md)）は画面から選択できない
- 出力ファイル名の規則は、CLI と同じく Service レイヤーが決める
  （[03_data_models.md](03_data_models.md) の 5 章）

### 2.4 作成の流れ

1. 「生成開始」で `MainWindow._collect_config()` が各ウィジェットから
   `GenerationConfig` を作成する。作成できなければ「設定エラー」の警告の
   ダイアログを出して停止する
2. `GeneratorWorker` を作成して開始し、「生成開始」を無効に、「キャンセル」を
   有効にする
3. 進捗のシグナルでバーを更新する
4. 終了のシグナルで、ボタンを元に戻し、成功なら「完了」、失敗なら「エラー」の
   ダイアログを出す

## 3. 非同期処理

作成は数百枚を超えることがあるので、`GeneratorWorker`（`QThread`）で実行する。
この章の規則は GUI だけに適用する。CLI と Web 画面は別の仕組みで動作する。

**規則**: ウィジェットの操作は UI スレッドだけで行い、ワーカーとの受け渡しは
シグナルだけにする。共有データへのロックは不要（ワーカーは設定を受け取って独立に
動作する）。

```text
MainWindow（UI スレッド）
    ↓ start()
GeneratorWorker（ワーカースレッド）
    ↓ progress_updated(current, total, filename)
MainWindow._on_progress_updated → ProgressWidget
    ↓ generation_finished(success, message)
MainWindow._on_generation_finished
```

### 3.1 GeneratorWorker

| 項目 | 内容 |
|------|------|
| 場所 | `app/gui/worker_thread.py` |
| シグナル | `progress_updated(int, int, str)`（現在・合計・ファイル名）、`generation_finished(bool, str)`（成功か・メッセージ） |
| 実行 | `run()` が `StudyGeneratorService().generate(config, progress_callback=...)` を呼ぶ |
| 進捗 | Service のコールバック `(current, total)` を受けて `progress_updated` を送出する。ファイル名は `image_NNNN.dcm` の形の表示用の名前 |
| 成功 | `generation_finished(True, "<枚数> 枚の DICOM ファイルを生成しました")` を送出する |
| 失敗 | `DICOMGeneratorError` は「生成エラー: ...」、それ以外は「予期しないエラー: ...」で `generation_finished(False, ...)` を送出する。どちらもログに記録する |

### 3.2 キャンセル

| 項目 | 内容 |
|------|------|
| 要求 | 「キャンセル」で `request_cancel()` を呼び、`cancel_requested` を設定する。ボタンは無効になり「キャンセル中...」と表示される |
| 効果 | 要求の後は進捗のシグナルを送出しない。Service の作成は途中で止めず、`generate()` が戻った後に `cancel_requested` を確認して `generation_finished(False, "Cancelled by user")` を送出する |
| 作成済みのファイル | 削除せず残す |

つまり、キャンセルは作成を中断せず、完了の通知を「キャンセルされた」に変える。
枚数が多い作成を途中で止める機能は無い。

### 3.3 終了時の後処理

`_on_generation_finished` はワーカーを最大 5 秒待ち（`wait(5000)`）、
終了しなければ警告をログに出力し、参照を破棄する。

## 4. テスト

`tests/gui/` に pytest-qt のテストがある。ディスプレイの無い環境で実行するため、
`QT_QPA_PLATFORM=offscreen` を指定する（CI も同じ。`.github/workflows/ci.yml`）。

| ファイル | 対象 |
|---------|------|
| `test_main_window.py` | タイトル・サイズ・ボタンの状態・設定の収集・作成とキャンセルと終了の画面の変化 |
| `test_widgets.py` | 各ウィジェットの値の取得 |
| `test_worker_thread.py` | 進捗と終了のシグナル、キャンセル、例外の扱い |

```bash
QT_QPA_PLATFORM=offscreen pytest tests/gui/
```

## 5. 実装しない機能

次は実装しておらず、機能を追加しない方針のため今後も実装しない。Web 画面か CLI を
使う。

- メニューバー（Job YAML の読み込み・保存を含む）
- シリーズごとの詳細設定のダイアログ
- ログビューア
- スタイルシート（QSS）
- 設定の永続化
- 複数のワーカーによる並列作成
