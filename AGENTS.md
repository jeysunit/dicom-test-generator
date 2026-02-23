# Codex Agent Instructions

実装前に以下を順番に確認してください：

1. AI_DEVELOPMENT_RULES.md
2. WORKFLOW.md
3. spec/

特に以下は禁止事項です：

- 仕様にない機能の追加
- `requirements.txt` の無断変更
- 既存コードの削除
- 例外の握りつぶし

実装前に `spec/` を読むこと。

実装開始前に必ず現在ブランチを確認し、`main` の場合は作業を開始しないこと。

```bash
git branch --show-current
git switch -c <type>/<topic>
```

`main` 直コミット・`main` 直pushは禁止です。

不明点がある場合は質問してください。
