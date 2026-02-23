# ADR-0009: Phase 1.5（Storage SCP）の推奨実装順序を明確化

## ステータス

**Accepted** - 2026-02-23

## 背景

Phase 1.5（Storage SCP）はオプション機能だが、早期要件があるため
Phase 2（GUI）より前に着手したいケースがある。

一方で、ドキュメント間で以下の読み取り揺れがあった。

1. フェーズ図では `Phase 2` と `Phase 1.5` の順序が逆転している箇所がある
2. 「前倒し実装可」と「後実装でも可」が混在し、優先順が不明確

## 決定

フェーズ順序を次のように定義する。

- 推奨順序: `Phase 0 → Phase 1 → Phase 1.5 → Phase 2`
- `Phase 1.5` はオプションのため、要件がない場合は `Phase 2` 後でも可
- ただし、`scp start` などのCLI統合は Phase 1 完了後を前提とする

## 影響

### 良い点

- Phase 1.5 に早期着手する際の判断基準が明確になる
- 仕様書の順序認識が統一される
- 実装計画（CLI優先・GUI後続）との整合性が高まる

### 悪い点

- オプション機能のため、チームによっては実装時期のばらつきが残る

## 変更対象

- `spec/00_overview.md`
- `spec/01_architecture.md`
- `spec/11_storage_scp.md`

## 関連する決定

- [ADR-0001: Core Library First](0001-core-library-first.md)
- [ADR-0003: PySide6 GUI](0003-pyside6-gui.md)
