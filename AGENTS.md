# エージェント向けの指示

実装の前に、次を順に読んでください。

1. [docs/development.md](docs/development.md)：開発環境、テスト、確認のコマンド、
   変更の手順、コーディング規約、Git。ここに書いた規則に従う
2. [docs/README.md](docs/README.md) の「書き方」：ドキュメントの書き方
3. [docs/project_charter.md](docs/project_charter.md)：目的、範囲、規格の前提
4. [docs/spec/](docs/spec/)：現在の動作。モダリティエミュレーター（`app/modality/`・
   `app/web/`）は [docs/spec/12](docs/spec/12_modality_emulator.md) と
   [12a](docs/spec/12a_web_screens_and_cli.md) を読む
5. 設計の判断に関わるときは [docs/decisions/](docs/decisions/README.md)

## エージェントに固有の規則

- `requirements.txt` を断りなく変更しない
- 既存のコードを断りなく削除しない
- 不明な点は推測せず、質問する
- 実装を始める前に現在のブランチを確認する。`main` なら作業を始めず、ブランチを
  作成する

```bash
git branch --show-current
git switch -c <type>/<topic>
```
