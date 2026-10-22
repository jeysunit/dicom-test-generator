# Claude への指示

@AGENTS.md

実装は小さな単位で行ってください。

## Codex MCP の呼び出し

- `approval-policy` は必ず `"never"` を指定する（MCP 経由では対話で承認できない
  ため）
- `sandbox` は `"workspace-write"` を指定する
- 文書（.md）の編集と整形は Codex に任せない（直接行う）
- 1ファイルで済む変更は Codex に任せない
- Codex に任せるのは、新しいコードの生成が 20 行以上のときと、複数のファイルの
  コードを変えるときに限る
