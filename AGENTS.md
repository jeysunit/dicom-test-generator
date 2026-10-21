# Codex Agent Instructions

実装前に以下を順番に確認してください：

1. AI_DEVELOPMENT_RULES.md
2. WORKFLOW.md
3. spec/

特に以下は禁止事項です：

- 仕様にない機能の追加
- `requirements.txt` の無断変更
- 既存コードの削除（承認者の指示による撤去は除く。例：Storage SCP を外した
  [ADR-0013](adr/0013-remove-storage-scp.md)）
- 例外の握りつぶし

DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。
識別子の型と長さ・属性の Type・応答の状態・文字コードは原典
（dicom.nema.org・hl7.org・IHE）で確かめ、出どころを spec か ADR に書く。

実装前に `spec/` を読むこと。モダリティのダミー（`app/modality/`・
`app/web/`）は `spec/12_modality_emulator.md`（とその 12a・12b）を読む。

実装開始前に必ず現在ブランチを確認し、`main` の場合は作業を開始しないこと。

```bash
git branch --show-current
git switch -c <type>/<topic>
```

`main` 直コミット・`main` 直pushは禁止です。

不明点がある場合は質問してください。
