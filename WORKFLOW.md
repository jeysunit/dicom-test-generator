# WORKFLOW

## 開発フロー

1. `spec/` 配下の仕様書を読む
2. 不明点がある場合は実装せず質問する
3. テストを先に書く（TDD）
4. 実装する
5. レビュー・修正

## レイヤー構造

```text
CLI (app/cli/) → Service Layer (app/services/) → Core Engine (app/core/)
```

上位レイヤーは下位レイヤーのみに依存する。逆方向の依存は禁止。

## 実装順序

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 0 | Core Engine（モデル、UID、ピクセル、DICOM構築） | ✅ 完了 |
| Phase 1 | CLI + Service Layer（テンプレート、患者、生成、CLI） | ✅ 完了 |
| Phase 2 | GUI（PySide6） | 未着手 |
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
```
