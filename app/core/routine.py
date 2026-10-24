"""撮影のルーチン（部位ごとのシリーズの並びと画像数）と、予約への当て方（ADR-0025）.

ルーチンの形はモダリティごとに違う（docs/spec/03）。CT はシリーズの種類と再構成、
MR はシーケンス、CR・DX は撮影の方向、US は静止画と動画の数を持つ。どのシリーズも
既定の画像数を持つ。通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .exceptions import ValidationError
from .models import CTSeriesKind, LocalizerView, SeriesConfig

RoutineModality = Literal["CT", "MR", "CR", "DX", "US"]
# 画面と CLI の1シリーズの画像数の上限（docs/spec/12a の 10.5）と同じ
MAX_ROUTINE_IMAGES_PER_SERIES = 1000
# View Position (0018,5101) の定義の語（PS3.3 C.8.1.1 の Table C.8-1。人の検査の語）
ProjectionView = Literal["AP", "PA", "LL", "RL", "RLD", "LLD", "RLO", "LLO"]


class _RoutineSeries(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    description: str = Field(..., min_length=1, max_length=64)
    images: int = Field(..., ge=1, le=MAX_ROUTINE_IMAGES_PER_SERIES)
    # 書けばその番号にする（999・501 など）。書かなければ続きの番号
    series_number: int | None = Field(None, ge=1)


class CTRoutineSeries(_RoutineSeries):
    kind: CTSeriesKind
    slice_thickness: float = Field(5.0, gt=0)
    views: list[LocalizerView] | None = None
    contrast: bool = False

    @model_validator(mode="after")
    def _views_match_images(self) -> CTRoutineSeries:
        if self.views is not None:
            if self.kind != "localizer":
                raise ValueError("views is only for a localizer series")
            if len(self.views) != self.images:
                raise ValueError(
                    f"views has {len(self.views)} entries but images is {self.images}"
                )
        return self


class MRRoutineSeries(_RoutineSeries):
    kind: Literal["localizer", "acquisition", "derived"]
    plane: Literal["axial", "sagittal", "coronal", "three_plane"]
    slice_thickness: float = Field(..., gt=0)
    spacing: float = Field(0.0, ge=0)


class ProjectionRoutineSeries(_RoutineSeries):
    """CR・DX の1シリーズ。`views` は撮影の方向（画像1枚に1方向）."""

    views: list[ProjectionView] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _one_image_per_view(self) -> ProjectionRoutineSeries:
        if len(self.views) != self.images:
            raise ValueError(f"views has {len(self.views)} entries but images is {self.images}")
        return self


class USRoutineSeries(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    description: str = Field(..., min_length=1, max_length=64)
    still_images: int = Field(..., ge=0, le=MAX_ROUTINE_IMAGES_PER_SERIES)
    clips: int = Field(0, ge=0)
    frames_per_clip: int = Field(1, ge=1)
    series_number: int | None = Field(None, ge=1)

    @property
    def images(self) -> int:
        return self.still_images + self.clips


RoutineSeries = CTRoutineSeries | MRRoutineSeries | ProjectionRoutineSeries | USRoutineSeries
SERIES_MODELS: dict[str, type[BaseModel]] = {
    "CT": CTRoutineSeries,
    "MR": MRRoutineSeries,
    "CR": ProjectionRoutineSeries,
    "DX": ProjectionRoutineSeries,
    "US": USRoutineSeries,
}


class Routine(BaseModel):
    """1つのルーチン（templates/routine/ の YAML の1つ）."""

    model_config = {"frozen": True, "extra": "forbid"}

    name: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    label: str = Field(..., min_length=1)
    modality: RoutineModality
    protocol_name: str = Field(..., min_length=1, max_length=64)
    default: bool = False
    keywords: list[str] = Field(default_factory=list)
    series: list[RoutineSeries] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _series_of_the_modality(cls, data: object) -> object:
        """`series` を `modality` の形で読む（形の違うシリーズを取り違えない）."""
        if not isinstance(data, dict):
            return data
        model = SERIES_MODELS.get(str(data.get("modality")))
        raw = data.get("series")
        if model is None or not isinstance(raw, list):
            return data
        return {**data, "series": [model.model_validate(item) for item in raw]}

    @model_validator(mode="after")
    def _cr_one_view_per_series(self) -> Routine:
        if self.modality == "CR":
            for series in self.series:
                if isinstance(series, ProjectionRoutineSeries) and len(series.views) != 1:
                    raise ValueError(
                        "a CR series has exactly one view (View Position is a series value)"
                    )
        return self

    @property
    def total_images(self) -> int:
        return sum(series.images for series in self.series)


def normalize(text: str) -> str:
    """比べる前の形：NFKC で正規化し、大文字と小文字を区別しない形にする."""
    return unicodedata.normalize("NFKC", text).casefold()


def check_routine_set(routines: Iterable[Routine]) -> None:
    """モダリティごとに既定が1つで、同じ語が2つのルーチンに無いことを確かめる.

    違えば ValueError（読む側が置き場のファイルの名前を足して知らせる）。
    """
    by_modality: dict[str, list[Routine]] = {}
    for routine in routines:
        by_modality.setdefault(routine.modality, []).append(routine)
    for modality, group in by_modality.items():
        defaults = [routine.name for routine in group if routine.default]
        if len(defaults) != 1:
            raise ValueError(
                f"{modality} needs exactly one default routine (default: true), found "
                f"{len(defaults)}: {', '.join(defaults) or 'none'}"
            )
        seen: dict[str, str] = {}
        for routine in group:
            for keyword in routine.keywords:
                key = normalize(keyword)
                other = seen.get(key)
                if other is not None and other != routine.name:
                    raise ValueError(
                        f"keyword {keyword!r} is in both {other} and {routine.name} ({modality})"
                    )
                seen[key] = routine.name


def match_routine(
    routines: Iterable[Routine], modality: str, fields: Iterable[str]
) -> Routine:
    """予約の欄に見出しの言葉（`keywords`）が含まれるルーチンを当てる.

    `fields` は先の欄から順に（Requested Procedure Description、Scheduled Procedure
    Step Description、Body Part Examined）。先の欄で当たれば後の欄は見ない。1つの欄で
    いくつかの語が当たれば長い語、同じ長さなら欄の中で前に出てくる語のルーチン。
    どの欄でも当たらなければ、そのモダリティの既定のルーチン。
    """
    candidates = [routine for routine in routines if routine.modality == modality]
    if not candidates:
        raise ValidationError(f"{modality} のルーチンがありません")
    for field in fields:
        text = normalize(field or "")
        if not text:
            continue
        best: tuple[int, int, Routine] | None = None
        for routine in candidates:
            for keyword in routine.keywords:
                key = normalize(keyword)
                position = text.find(key) if key else -1
                if position < 0:
                    continue
                score = (-len(key), position)
                if best is None or score < best[:2]:
                    best = (score[0], score[1], routine)
        if best is not None:
            return best[2]
    return next(routine for routine in candidates if routine.default)


def assign_series_numbers(
    wanted: list[int | None], used: list[tuple[int, bool]]
) -> list[int]:
    """シリーズ番号を決める。`wanted` は各シリーズの書いた番号（無ければ None）.

    `used` は予約で使った番号と、書いた番号か（True）自動か（False）。自動の番号は
    自動で付けた番号の最大の次で、使った番号に当たれば空いている番号まで進める。書いた
    番号が使った番号か、同じ撮影のほかのシリーズの番号と同じなら ValidationError。
    """
    taken = {number for number, _explicit in used}
    explicit_now = [number for number in wanted if number is not None]
    for number in explicit_now:
        if number in taken or explicit_now.count(number) > 1:
            raise ValidationError(
                f"シリーズ番号 {number} は既にあります。ルーチンのシリーズ番号を変えてください"
            )
    taken.update(explicit_now)
    next_auto = 1 + max((number for number, explicit in used if not explicit), default=0)
    numbers: list[int] = []
    for number in wanted:
        if number is not None:
            numbers.append(number)
            continue
        while next_auto in taken:
            next_auto += 1
        numbers.append(next_auto)
        taken.add(next_auto)
        next_auto += 1
    return numbers


def ct_series_configs(
    routine: Routine, numbers: list[int], keep: list[int], images: list[int]
) -> list[SeriesConfig]:
    """CT のルーチンの `keep` の位置のシリーズを、`images` の画像数で SeriesConfig にする."""
    configs = []
    for number, index, count in zip(numbers, keep, images, strict=True):
        series = routine.series[index]
        if not isinstance(series, CTRoutineSeries):
            raise ValidationError(f"{routine.modality} の画像はまだ作れません")
        configs.append(
            SeriesConfig(
                series_number=number,
                series_description=series.description,
                num_images=count,
                protocol_name=routine.protocol_name,
                slice_thickness=series.slice_thickness,
                slice_spacing=series.slice_thickness,
                kind=series.kind,
                views=series.views or ["frontal"],
                contrast=series.contrast,
            )
        )
    return configs
