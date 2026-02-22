# Claude Instructions

このプロジェクトでは AI_DEVELOPMENT_RULES.md を必ず遵守してください。

実装前に以下を順番に確認してください：

1. AI_DEVELOPMENT_RULES.md
2. WORKFLOW.md
3. spec/ 配下の仕様書

重要ルール：

- レイヤー構造を厳守する
- Core Engine を優先実装する
- 不明点は推測せず質問する
- requirements.txt を勝手に変更しない
- 仕様にない機能は実装しない
- GUIは Phase 2 まで実装しない

実装は小さな単位で行ってください。

## Codex MCP 呼び出しルール

- `approval-policy` は必ず `"never"` を指定する
  （MCP経由ではインタラクティブ承認が不可能なため）
- `sandbox` は `"workspace-write"` を指定する
- ドキュメント（.md）の編集・整形は Codex に委譲しない（直接実行する）
- 1ファイルで完結する変更は Codex に委譲しない
- Codex への委譲は「新規コード生成20行以上」「複数ファイルのコード変更」に限定する
