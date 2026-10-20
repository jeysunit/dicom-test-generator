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
Web (app/web/) ─┐
CLI (app/cli/) ─┤→ Modality (app/modality/) → Service (app/services/)
                │                                   ↓
GUI (app/gui/) ─┴→ Service (app/services/) ──→ Core (app/core/)
```

- `app/modality/`（モダリティのダミーの通信と手順）は Service Layer の
  一部として扱い、`app/services/`・`app/core/` だけを import する
  （`spec/12_modality_emulator.md` 9 章）
- `app/web/`（Phase 3b）は CLI と同じ所から `app/modality/` を呼ぶ

上位レイヤーは下位レイヤーのみに依存する。逆方向の依存は禁止。

## 実装順序

**段（Phase）の状態は、この表が唯一の置き場。** README・spec には
進捗の表を持たない。

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 0 | Core Engine（モデル、UID、ピクセル、DICOM構築） | ✅ 完了 |
| Phase 1 | CLI + Service Layer（テンプレート、患者、生成、CLI） | ✅ 完了 |
| Phase 1.5 | Storage SCP（PyNetDICOM） | 外した（2026-10-20、ADR-0013。受信は PACS の役目で、モダリティの擬態の目的の外） |
| Phase 2a | GUI MVP（PySide6 基本ウィジェット + 生成フロー） | ✅ 完了（`spec/05_gui.md`。凍結） |
| Phase 2b | GUI フル機能（メニュー、ダイアログ、スタイル） | 進めない（PySide6 の画面は凍結。ADR-0011 の案 B） |
| Phase 3a | モダリティのダミー：ワークリスト（C-FIND MWL）・予約からの生成・送信（C-STORE・C-ECHO）を CLI で（`spec/12_modality_emulator.md`） | ✅ 完了（CLI） |
| Phase 3b | モダリティのダミー：ウェブの画面（ワークリスト・撮影・PACS・設定） | ✅ 完了（`python -m app.web`。`spec/12a_web_screens_and_cli.md`） |
| Phase 3c | モダリティのダミー：保管の確認（Storage Commitment）・MPPS（選べる形） | ✅ 完了（CLI の `commit`・`mpps`、画面の状態の表示。決めたことは `spec/12b_decisions_and_limits.md` 18.2。**試験用の Orthanc での手の確かめは未了**） |

## テスト実行

```bash
# 全テスト
pytest

# レイヤー別
pytest tests/core/ -v
pytest tests/services/ -v
pytest tests/cli/ -v
pytest tests/modality/ -v
pytest tests/integration/ -v
pytest tests/gui/ -v
pytest tests/web/ -v

# カバレッジ
pytest --cov=app --cov-report=term-missing

# 表示の無い環境で GUI の試験を流す（CI と同じ）
QT_QPA_PLATFORM=offscreen pytest
```

### CI

`.github/workflows/ci.yml` が、PR と `main` への push で次を流す。

- pytest（Python 3.10・3.12）。GUI の試験は Qt の offscreen の描き先で
  動かす（X のサーバーを立てない）
- markdownlint（`.markdownlint-cli2.yaml` の設定）
- 画面の CSS：`scripts/build_css.sh`（版と sha256 を固定した Tailwind CSS の
  standalone の実行ファイル）で作り直し、commit した `app/web/static/app.css` と
  差が無いことを確かめる
- Docker のイメージ：`Dockerfile` からイメージを作り（push しない）、CLI が
  root 以外のユーザーで動くこと、Web 画面が `0.0.0.0` で起動して HTTP Basic
  認証を求めること、パスワードのファイルが無ければ起動しないことを確かめる

ruff は、設定のファイルが無く、いまのコードに指摘が残っているため、
CI にはまだ入れていない。

## CLI 使用例

```bash
python -m app.cli generate examples/job_minimal.yaml
python -m app.cli generate examples/job_full.yaml -o output/ --verbose
python -m app.cli validate examples/job_minimal.yaml
python -m app.cli quick -p P000001 -m ct_generic -s 3 -i 1,20,20 -o output/
python -m app.cli quick -p P000001 -m ct_generic --profile dtg_synthetic_ct -s 1 -i 3 -o output/
python -m app.cli profiles list
python -m app.cli version

# モダリティのダミー（Phase 3a。試験用の PACS・RIS にだけつなぐ）
python -m app.cli echo --to PACS_TEST
python -m app.cli worklist query --json
python -m app.cli exam --from-worklist <鍵> -s 2 -i 1,20 --send
python -m app.cli exam --emergency --patient-id E0001 --patient-name "KINKYU^TARO"
python -m app.cli queue list --status failed
python -m app.cli queue retry --all

# 保管の確認と MPPS（Phase 3c。設定で選んだときだけ）
python -m app.cli commit --job 3 --wait 60
python -m app.cli mpps list
python -m app.cli mpps retry

# モダリティのダミーのウェブの画面（Phase 3b。既定は http://127.0.0.1:8080/）
python -m app.web

# GUI 起動
python -m app.gui
```
