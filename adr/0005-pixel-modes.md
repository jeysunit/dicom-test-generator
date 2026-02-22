# ADR-0005: Pixel Modes

## Status

**Accepted** - 2025-02-21

## Context

ピクセルデータ生成方式を決定する必要がある。

### 要求

- **目的A**: DICOM ViewerでDICOMとして認識・表示できること
- **目的B**: SOP Instance UIDを視覚的に確認できること
- **目的C**: 医療ビューアで実際のCT画像として表示できること

### 選択肢

1. **空ピクセル**: 真っ黒な画像
2. **ランダムノイズ**: ランダム値
3. **テキスト表示**: SOP UID等を描画
4. **医療リアルモード**: HU値対応、Window/Level設定

## Decision

2つのモードをサポートする。

### モード1: Simple Text（簡易確認用）

**目的**: SOP Instance UIDを視覚的に確認

**仕様**:

- 8bit grayscale
- 黒背景に白文字でSOP UIDを表示
- フォントサイズ: 24ポイント
- 画像幅の70%で折り返し

**用途**:

- デバッグ時の視覚確認
- 画像ファイルが正しいUIDを持っているか確認

### モード2: CT Realistic（医療ビューア対応）

**目的**: 実際の医療ビューアで表示可能

**仕様**:

- 16bit signed (2's complement)
- HU値対応（Rescale Intercept: -1024, Slope: 1）
- Window Center/Width設定
- パターン: gradient, circle, noise

**用途**:

- 医療ビューアでの動作確認
- Window/Level調整のテスト
- PACS連携のテスト

## Consequences

### Positive

- ✅ Simple Textで簡易デバッグ可能
- ✅ CT Realisticで実運用に近いテスト可能
- ✅ 用途に応じて選択可能
- ✅ 医療ビューア（Horos, RadiAnt等）で表示できる

### Negative

- ⚠️ 2つのモード実装が必要
  - **軽減策**: Core Engineで分離、実装は比較的簡単
- ⚠️ 本物のCT画像とは異なる
  - **影響**: テストデータ生成が目的なので問題なし

### Tradeoffs

- Simple Textのみ: 医療ビューアで正しく表示されない
- CT Realisticのみ: UIDの視覚確認が難しい
- 両方サポート: 実装コスト増だが柔軟性が高い

## Implementation

### データモデル

```python
class PixelSpecSimple(BaseModel):
    mode: str = "simple_text"
    width: int = 512
    height: int = 512
    background_color: int = 0
    text_color: int = 255
    font_size: int = 24

class PixelSpecCTRealistic(BaseModel):
    mode: str = "ct_realistic"
    width: int = 512
    height: int = 512
    pattern: str = "gradient"  # gradient, circle, noise
    bits_stored: int = 12

PixelSpec = PixelSpecSimple | PixelSpecCTRealistic
```

### Core Engine

```python
class PixelGenerator:
    def generate_simple_text(self, sop_uid, width, height):
        """Simple Textモード"""
        img = Image.new('L', (width, height), color=0)
        draw = ImageDraw.Draw(img)
        # テキスト描画
        return np.array(img, dtype=np.uint8)
    
    def generate_ct_realistic(self, width, height, pattern):
        """CT Realisticモード"""
        pixels = np.zeros((height, width), dtype=np.int16)
        
        if pattern == "gradient":
            # HU値 -1024 → 1024のグラデーション
            for x in range(width):
                hu_value = int(-1024 + (2048 * x / width))
                pixel_value = hu_value - (-1024)
                pixels[:, x] = pixel_value
        
        return pixels
```

### Job YAML

```yaml
# Simple Text
pixel_spec:
  mode: "simple_text"

# CT Realistic
pixel_spec:
  mode: "ct_realistic"
  pattern: "gradient"
  bits_stored: 12
```

## Validation

生成されたDICOMファイルを以下で確認：

### Simple Text

- dcmdump: Pixel Dataが8bit unsigned
- ImageJ: 黒背景に白文字表示

### CT Realistic

- Horos / RadiAnt: Window/Level調整で表示
- dcmdump: Rescale Intercept = -1024, Slope = 1

## Related Decisions

- [ADR-0001: Core Library First](0001-core-library-first.md)
- [ADR-0004: UUID 2.25 UID](0004-uuid-2-25-uid.md)

## References

- [06_dicom_rules.md](../spec/06_dicom_rules.md#pixel-data)
- DICOM Standard Part 3: C.8.2 CT Image Module
- Horos: <https://horosproject.org/>
