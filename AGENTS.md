# エージェント向けの指示

実装の前に、次を順に読んでください。

1. [docs/development.md](docs/development.md)：変更の進め方、コードの決まり、試験
2. [docs/project_charter.md](docs/project_charter.md)：目的、範囲、規格の前提
3. [docs/spec/](docs/spec/)：今どう動くか。モダリティエミュレーター（`app/modality/`・
   `app/web/`）は [docs/spec/12](docs/spec/12_modality_emulator.md) と
   [12a](docs/spec/12a_web_screens_and_cli.md) を読む
4. 設計の判断に触れるときは [docs/decisions/](docs/decisions/README.md)

## 守ること

- DICOM と HL7（v2・FHIR）の規格に違反しないことを開発の前提とする。識別子の
  型と長さ・属性の Type・応答の状態・文字コードは原典（dicom.nema.org・hl7.org・
  IHE）で確かめ、出典を spec か ADR に書く。異常のデータの経路だけは例外で、
  扱いは [ADR-0014](docs/decisions/0014-separate-normal-and-abnormal-paths.md)
- spec に無い機能を足さない
- `requirements.txt` を断りなく変えない
- 既存のコードを断りなく消さない
- 例外を握りつぶさない
- 層の構造を守る（[docs/architecture.md](docs/architecture.md) の 2 章）
- PySide6 のデスクトップの画面（`app/gui/`）には機能を足さない
- 不明な点は推測せず、質問する

## ブランチ

実装を始める前に、今のブランチを確かめる。`main` なら作業を始めず、ブランチを
作る。`main` に直接 commit・push しない。

```bash
git branch --show-current
git switch -c <type>/<topic>
```
