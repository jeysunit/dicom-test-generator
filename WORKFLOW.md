# WORKFLOW

## 開発フロー

1. 作業ブランチを作成する（`main` のまま開始しない）
2. `spec/` 配下の仕様書を読む
3. 不明点がある場合は実装せず質問する
4. テストを先に書く（TDD）
5. 実装する
6. レビュー・修正

## Git開始チェック

実装前に必ず実行:

```bash
git branch --show-current
```

- `main` が表示された場合は作業を開始せず、ブランチを作成する
- 例: `git switch -c fix/<topic>`

## レイヤー構造

```text
GUI (app/gui/) ─┐
CLI (app/cli/) ─┤→ Service Layer (app/services/) → Core Engine (app/core/)
SCP (app/scp/) ─┘
```

上位レイヤーは下位レイヤーのみに依存する。逆方向の依存は禁止。

## 実装順序

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 0 | Core Engine（モデル、UID、ピクセル、DICOM構築） | ✅ 完了 |
| Phase 1 | CLI + Service Layer（テンプレート、患者、生成、CLI） | ✅ 完了 |
| Phase 2a | GUI MVP（PySide6 基本ウィジェット + 生成フロー） | ✅ 完了 |
| Phase 2b | GUI フル機能（メニュー、ダイアログ、スタイル） | 未着手 |
| Phase 1.5 | Storage SCP（PyNetDICOM） | ✅ 完了 |

## テスト実行

```bash
# 全テスト
pytest

# レイヤー別
pytest tests/core/ -v
pytest tests/services/ -v
pytest tests/scp/ -v
pytest tests/cli/ -v
pytest tests/gui/ -v

# カバレッジ
pytest --cov=app --cov-report=term-missing
```

## CLI 使用例

```bash
python -m app.cli generate examples/job_minimal.yaml
python -m app.cli generate examples/job_full.yaml -o output/ --verbose
python -m app.cli validate examples/job_minimal.yaml
python -m app.cli quick -p P000001 -m fujifilm_scenaria_view_ct -s 3 -i 1,20,20 -o output/
python -m app.cli version
python -m app.cli scp start
python -m app.cli scp start --config config/app_config.yaml

# GUI 起動
python -m app.gui
```
