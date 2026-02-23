# ADR-0010: Storage SCP の運用仕様（重複処理・停止・テスト）を固定

## ステータス

**Accepted** - 2026-02-23

## 背景

Phase 1.5 の Storage SCP は概略仕様が存在したが、実装に必要な運用判断が未固定だった。

- 重複SOP Instance UID受信時の既定動作
- UID短縮ディレクトリ衝突時の命名
- `scp start` の停止時挙動
- 最低限必要なテスト範囲

これらが未確定だと、実装差分とレビュー基準がぶれる。

## 決定

1. `duplicate_handling` の既定値は `overwrite`
2. `duplicate_handling=reject` 時は `0xC000` を返す
3. UID短縮名衝突時は `_<sha1先頭8桁>` を付与
4. `scp start` は `Ctrl+C` で正常終了（exit code 0）
5. 最小テストセットを「起動停止」「受信成功」「重複3モード」「設定エラー」に固定
6. 依存は `requirements.txt` に `pynetdicom>=2.0.0` を明示して管理

## 影響

### 良い点

- 実装時の判断コストが下がる
- テスト観点が明確になり、レビューがしやすい
- 運用時の重複データ挙動が予測可能になる

### 悪い点

- `overwrite` 既定のため、誤送信時に既存ファイルが置換される
  - 回避したい運用では `reject` または `rename` 設定を選択する

## 変更対象

- `spec/11_storage_scp.md`

## 関連する決定

- [ADR-0009: Phase 1.5（Storage SCP）の推奨実装順序を明確化](0009-phase-1_5-ordering.md)
