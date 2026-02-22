# AI Development Rules

生成AIによる実装品質を安定化するための最小ルール。
`MUST` は必須、`SHOULD` は推奨、`MUST NOT` は禁止を示す。

## 1. アーキテクチャルール

- `MUST` レイヤー構造を厳守: `UI Layer -> Service Layer -> Core Engine`
- `MUST` UI から Core Engine を直接呼ばない
- `MUST` Core Engine は UI・ログ・設定ファイルに依存しない（Pure ロジック）
- `MUST` フェーズ順に実装: Phase 0 (Core) -> Phase 1 (CLI) -> Phase 2 (GUI)
- `MUST` 仕様変更を伴う設計判断は ADR を追加または更新する
- `SHOULD` 1PR 1目的を維持する

```text
app/
├── core/       # Phase 0: Pure ロジック（外部依存なし）
├── services/   # Service Layer: Core の組み合わせ + ログ
├── cli/        # Phase 1: argparse CLI
├── gui/        # Phase 2: PySide6 GUI
└── scp/        # Phase 1.5: Storage SCP
```

## 2. Pythonコーディング規約

- `MUST` Python 3.10+ 対応、型ヒント必須
- `MUST` PEP 8 準拠。フォーマッタ/リンタ: ruff
- `MUST` データモデル: Pydantic v2
- `MUST` 命名: snake_case（関数・変数）、PascalCase（クラス）、UPPER_CASE（定数）
- `MUST` マジックナンバー禁止（定数として定義する）
- `SHOULD` 1ファイル 800行以下、1関数 50行以下
- `SHOULD` イミュータブルを優先（既存オブジェクトを変更しない）

## 3. 依存関係管理

- `MUST` requirements.txt で管理し、暗黙依存を追加しない
- `MUST` 新規パッケージ追加時は requirements.txt を更新する
- `MUST` 標準ライブラリで済むなら外部パッケージを追加しない
- `SHOULD` Phase 別のオプション依存を意識する（PySide6 は Phase 2 のみ等）

## 4. 例外処理

`spec/08_error_handling.md` の例外階層に従う。

- `MUST` ベース例外: `DICOMGeneratorError`。汎用の `Exception` や `ValueError` を直接 raise しない
- `MUST` Core Engine は例外を raise する（ログは出さない）
- `MUST` Service Layer は例外を catch してログ出力し、必要なら re-raise
- `MUST` UI Layer は例外を catch してユーザーに表示
- `MUST` `except Exception:` の握りつぶし禁止
- `MUST` エラーメッセージに原因と文脈（入力ID、処理段階）を含める

## 5. ログ

`spec/09_logging.md` に従う。

- `MUST` `print()` ではなく `logging` を使う
- `MUST` Core Engine はログを出力しない（Pure 関数）
- `MUST` Service Layer 以上でログを出力する
- `MUST` ロガー名: `logging.getLogger(__name__)`
- `MUST` 機微情報（PHI/個人情報/秘密情報）をログ出力しない
- `SHOULD` DEBUG ログは遅延評価: `logger.debug("msg: %s", obj)`

## 6. Git運用

### 基本ルール

- `MUST` main ブランチへ直接コミットしない
- `MUST` 作業前に必ずブランチを作成する
- `MUST` 1コミット1論理変更とする
- `MUST` Conventional Commits 形式を使用する
- `MUST` シークレット（APIキー、パスワード等）をコミットしない
- `SHOULD` PR には「目的・変更点・確認方法・影響範囲」を記載する

### ブランチ戦略

ブランチ命名規則：

```text
feature/<機能名>
fix/<修正内容>
refactor/<対象>
docs/<対象>
test/<対象>
```

例：

- `feature/core-uid-generator`
- `fix/pixel-spacing-bug`
- `docs/readme-update`

### コミットメッセージ

形式：

```text
<type>: <概要>
```

type 一覧：

- `feat:` 新機能
- `fix:` バグ修正
- `refactor:` リファクタリング
- `test:` テスト追加・修正
- `docs:` ドキュメント変更
- `chore:` その他

説明文は日本語で記述してよい。

コミット例：

- `feat: UID生成機能を追加`
- `fix: PixelSpacing計算のバグを修正`
- `test: UID生成のユニットテストを追加`
- `docs: READMEを更新`

### 禁止事項

- `MUST NOT` main ブランチへ直接コミットする
- `MUST NOT` 仕様変更を含む変更を無断で行う
- `MUST NOT` 大規模変更を単一コミットで行う

## 7. Markdownルール（markdownlint準拠）

- `MUST` コードブロックには言語を指定する（`python`, `bash`, `yaml`, `text` 等）
- `MUST` 見出しレベルを飛ばさない（h1 -> h3 は NG）
- `MUST` 行末スペースを残さない
- `MUST` ファイル末尾に空行を1つ入れる
- `MUST` リスト記号は統一する

## 8. CLIルール

`spec/04_cli.md` に従う。

- `MUST` エントリポイント: `python -m app.cli`
- `MUST` 終了コード: 0=成功, 1=一般エラー, 2=設定エラー, 3=I/Oエラー, 4=バリデーションエラー
- `MUST` 結果は stdout、エラーは stderr に出力する
- `MUST` `--help` を実装し、必須引数と使用例を示す

## 9. テストルール

- `MUST` フレームワーク: pytest
- `MUST` 新機能には正常系・異常系のテストを追加する
- `MUST` バグ修正には再発防止テストを先に書く（TDD）
- `MUST` Core Engine のテストに外部リソース（ファイルI/O、ネットワーク）を使わない
- `SHOULD` カバレッジ 80% 以上を目標とする
- `SHOULD` テスト配置: `tests/` 以下に `core/`, `services/`, `integration/`, `e2e/`

## 10. AIへの禁止事項

- `MUST NOT` DICOM 医療仕様（`spec/06_dicom_rules.md`）を勝手に変更しない
- `MUST NOT` `spec/` 配下のファイルを指示なく編集しない
- `MUST NOT` 仕様書にない機能を勝手に追加しない
- `MUST NOT` 仕様不明点を推測で埋めて実装しない（確認する）
- `MUST NOT` テスト未実施のまま「動作確認済み」と記載しない
- `MUST NOT` 既存コードを無断で大規模リライトしない
- `MUST NOT` 既存テストを通すために仕様を変えない（実装を直す）
- `MUST NOT` エラーを隠蔽して成功扱いにしない
