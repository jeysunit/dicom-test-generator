# 09. ログ

- 作成日：2026-02-22
- 最終更新日：2026-10-22

## 概要

ログは Python 標準の `logging` で出力する。**Core はログを出力しない**。
ログを出力するのは Service Layer（`app/services/`・`app/modality/`）と、CLI・Web 画面の
エントリポイントである。ログの設定は設定ファイルではなく、エントリポイントのコードに
固定してある。CLI は `app/cli/main.py` の `setup_logging`、Web 画面は
`app/web/__main__.py` が設定する。

---

## ログレベル

| Level | 用途 | 出力先（CLI） |
|-------|------|--------|
| DEBUG | 詳細デバッグ情報 | ファイルのみ（`--verbose` ならコンソールにも） |
| INFO | 通常の動作情報 | ファイル + コンソール |
| WARNING | 警告（処理は継続） | ファイル + コンソール |
| ERROR | エラー（処理は中断） | ファイル + コンソール |

コンソールの下限は、既定が INFO、`--verbose` が DEBUG、`--quiet` が ERROR。
ファイルには常に DEBUG 以上を記録する。

---

## CLI のログ設定

`setup_logging(verbose, quiet, log_file)` が、サブコマンドの実行の前に root logger を設定する。

| 項目 | 内容 |
|------|------|
| ファイルの場所 | `--log-file`（既定 `logs/dicom_generator.log`）。親のフォルダが無ければ作成する |
| ファイルのハンドラ | `RotatingFileHandler`（UTF-8、10MB、5世代）。レベルは DEBUG |
| コンソールのハンドラ | `StreamHandler`（標準エラー出力）。レベルは上の表のとおり |
| 書式 | `[%(levelname)s] %(asctime)s - %(message)s` |
| 端末への出力 | `TerminalSafeFormatter`（`app/cli/terminal.py`）を経由する。相手から来た値に含まれる制御文字を可視化（`\x1b` など）し、端末の表示やタイトルを書き換えられないようにする |

`--log-file` と `--verbose` は、`generate` のほか、モダリティエミュレーターのコマンドにもある。
`--quiet` は `generate` だけが持つ。
`--verbose` のとき、pynetdicom のログも DEBUG にする。既定は WARNING 以上だけを出力する。

### Web 画面

`python -m app.web` は `logging.basicConfig` で INFO を標準エラー出力に出す
（書式は `時刻 レベル 名前 メッセージ`）。ファイルには書き込まない。

### ログローテーション

```text
logs/
├── dicom_generator.log       # 現在のログ
├── dicom_generator.log.1     # 1世代前（最新）
├── dicom_generator.log.2     # 2世代前
├── dicom_generator.log.3     # 3世代前
├── dicom_generator.log.4     # 4世代前
└── dicom_generator.log.5     # 5世代前（最古）
```

- **サイズ**: 10MB超過時
- **保持数**: 最大5世代

---

## 出力するログ

logger の名前は、各モジュールの `logging.getLogger(__name__)` である。

### 生成（`StudyGeneratorService`）

| 時点 | レベル | 内容 |
|------|--------|------|
| 開始 | INFO | `Generation started: job_name=... patient_id=... total_images=... output_dir=...` |
| 装置プロファイルを使うとき | INFO | `Device profile: <名前>` |
| 完了 | INFO | `Generation completed: patient_id=... generated=... output_dir=...` |
| 失敗 | ERROR | `Generation failed: ...`（Traceback つき） |

### モダリティエミュレーター（`app/modality/`）

通信の開始・終了・相手の Status の値・件数を INFO で記録する（C-ECHO・C-FIND・C-STORE・
保管確認・MPPS・送信キュー）。相手の応答が不正なとき、再送や拒否のときは WARNING。
詳細は [12_modality_emulator.md](12_modality_emulator.md) の 13 章で定める。

### 出力しない値

患者の氏名・生年月日はログに出力しない（[development.md](../development.md) の 3.4）。
出力するのは、患者ID・予約のキー・受付番号・SOP Instance UID まで。

---

## 実装の規則

### Core はログを出力しない

```python
# app/core/uid_generator.py

class UIDGenerator:
    """Core はログ出力しない。例外を投げ、記録は呼ぶ側が決める"""

    def generate_study_uid(self) -> str:
        return self._generate()
```

Core は例外を送出する。捕捉した Service Layer が、必要なら記録して再 raise する
（[08_error_handling.md](08_error_handling.md)）。

### 遅延評価

```python
# 悪い例（DEBUGレベルでなくても文字列結合が実行される）
logger.debug("Generated: " + str(large_object))

# 良い例（DEBUGレベルの場合のみ評価）
logger.debug("Generated: %s", large_object)
```

### 大量ログの抑制

画像1枚ごとに INFO を出力しない。画像ごとの記録は DEBUG にとどめる。

---

## ログ検索

```bash
# エラーのみ抽出
grep '\[ERROR\]' logs/dicom_generator.log

# 特定患者のログ抽出
grep 'P000001' logs/dicom_generator.log

# 完了の数
grep -c 'Generation completed' logs/dicom_generator.log
```

---

## テスト

ログは `caplog` で確認する。

```python
def test_generation_logs_info(caplog):
    with caplog.at_level(logging.INFO):
        StudyGeneratorService().generate(config)

    assert "Generation started" in caplog.text
    assert "Generation completed" in caplog.text
```

端末への出力の処理は `tests/cli/test_terminal.py` が確認する。
