# ADR-0001: Core Library First

## Status

**Accepted** - 2025-02-21

## Context

DICOM生成ツールの開発順序を決定する必要がある。以下の選択肢があった：

1. **GUI-First**: GUIから実装し、後でCLIを追加
2. **CLI-First**: CLIから実装し、後でGUIを追加
3. **Core-First**: Core Engineを先に実装し、後でUI（CLI/GUI）を追加

### 要求

- テストデータ生成が主目的（プログラム開発ではない）
- 生成AIによる実装を前提
- 段階的開発が可能
- 単体テストが容易

### 制約

- 個人開発（小規模チーム）
- 最短実装を優先
- 保守性が必要

## Decision

Phase 0: Core Engine を最優先で実装する。

開発順序：

```text
Phase 0: Core Engine (UI非依存)
   ↓
Phase 1: CLI
   ↓
Phase 2: GUI
```

### 理由

#### Core-First の利点

1. **UI非依存で単体テスト可能**
   - Core Engineは純粋なPython関数
   - PyTestで完全にテスト可能
   - GUIなしで動作確認できる

2. **生成AIによる実装成功率が高い**
   - 入出力が明確な関数
   - UI状態管理が不要
   - 複雑な依存関係がない

3. **CLI/GUIで同じロジックを再利用**
   - Core Engineを共通基盤として使用
   - 重複コードなし
   - バグ修正が一箇所で済む

4. **段階的検証が可能**
   - Core Engine完成 → DICOM生成可能
   - CLI追加 → バッチ処理可能
   - GUI追加 → UX向上

#### GUI-First/CLI-First を選ばない理由

- **GUI-First**: UI実装が複雑、テストが困難、生成AIには不向き
- **CLI-First**: UIとロジックが密結合しがち

## Consequences

### Positive

- ✅ Core Engineが独立したライブラリとして使用可能
- ✅ Jupyter NotebookやスクリプトからCore APIを直接呼び出し可能
- ✅ 単体テストが容易
- ✅ Phase 0完了時点でDICOM生成機能が動作
- ✅ 将来的にWeb API化も容易

### Negative

- ⚠️ 初期段階でGUIがない（テストデータ生成には問題なし）
- ⚠️ Phase 0完了まではCLIもない（開発者向けなので許容）

### Risks

- ⚠️ Core API設計ミスの影響が大きい
  - **軽減策**: 仕様書で事前にAPI設計を固める（本ドキュメント）

## Implementation

- `app/core/` パッケージを最初に実装
- CLI/GUIは `app/core` をimportして使用
- Core Engineは一切のUI依存を持たない

## Related Decisions

- [ADR-0002: YAML Job Configuration](0002-yaml-job-configuration.md)
- [ADR-0006: Threading Model](0006-threading-model.md)

## References

- [02_core_engine.md](../spec/02_core_engine.md)
- [01_architecture.md](../spec/01_architecture.md)
