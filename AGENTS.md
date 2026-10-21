# エージェント向けの指示

実装の前に、次を順に読んでください。

1. [docs/development.md](docs/development.md)：変更の手順、コーディング規約、テスト
2. [docs/project_charter.md](docs/project_charter.md)：目的、範囲、規格の前提
3. [docs/spec/](docs/spec/)：現在の動作。モダリティエミュレーター（`app/modality/`・
   `app/web/`）は [docs/spec/12](docs/spec/12_modality_emulator.md) と
   [12a](docs/spec/12a_web_screens_and_cli.md) を読む
4. 設計の判断に関わるときは [docs/decisions/](docs/decisions/README.md)
5. 文書を書くときは [docs/README.md](docs/README.md) の「書き方」

## 守ること

- DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。識別子の
  型と長さ・属性の Type・応答のステータス・文字コードは原典（dicom.nema.org・
  hl7.org・IHE）で確認し、出典を spec か ADR に書く。異常のデータの経路だけは
  例外で、扱いは [ADR-0014](docs/decisions/0014-separate-normal-and-abnormal-paths.md)
- spec に無い機能を追加しない
- `requirements.txt` を断りなく変更しない
- 既存のコードを断りなく削除しない
- 例外を握りつぶさない
- 層の構造を守る（[docs/architecture.md](docs/architecture.md) の 2 章）
- PySide6 のデスクトップ画面（`app/gui/`）には機能を追加しない
- 不明な点は推測せず、質問する

## ブランチ

実装を始める前に、現在のブランチを確認する。`main` なら作業を始めず、ブランチを
作成する。`main` に直接 commit・push しない。

```bash
git branch --show-current
git switch -c <type>/<topic>
```
