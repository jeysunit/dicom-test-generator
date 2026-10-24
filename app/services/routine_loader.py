"""撮影のルーチン（templates/routine/ の YAML）を読む（ADR-0025）."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import TemplateNotFoundError, TemplateParseError
from app.core.routine import SERIES_MODELS, Routine, check_routine_set

from .template_loader import TEMPLATE_NAME_PATTERN


class RoutineLoaderService:
    """ルーチンを読む。読めないファイルが1つでもあれば、どれも返さずに止める.

    ルーチンは既定の撮影に使うので、読めないルーチンを黙って飛ばすと、予約に当たる
    はずのルーチンが無いまま標準のルーチンで撮れてしまう。
    """

    def __init__(self, routine_dir: Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self._dir = routine_dir or project_root / "templates" / "routine"
        self._cache: list[Routine] | None = None

    def list_routines(self) -> list[Routine]:
        if self._cache is None:
            routines = [self._load(path) for path in sorted(self._dir.glob("*.yaml"))]
            try:
                check_routine_set(routines)
            except ValueError as exc:
                raise TemplateParseError(str(self._dir), str(exc)) from exc
            self._cache = routines
        return list(self._cache)

    def get(self, name: str) -> Routine:
        if not TEMPLATE_NAME_PATTERN.fullmatch(name):
            raise TemplateNotFoundError(name)
        for routine in self.list_routines():
            if routine.name == name:
                return routine
        raise TemplateNotFoundError(name)

    @staticmethod
    def _load(path: Path) -> Routine:
        try:
            with path.open("r", encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp)
        except (yaml.YAMLError, OSError) as exc:
            raise TemplateParseError(str(path), str(exc)) from exc
        if not isinstance(loaded, dict):
            raise TemplateParseError(str(path), "Routine root must be a mapping")
        model = SERIES_MODELS.get(str(loaded.get("modality")))
        raw_series = loaded.get("series")
        if model is not None and isinstance(raw_series, list):
            # シリーズはモダリティの形で1つずつ読み、誤りの位置（何番目か）を残す
            series = []
            for index, item in enumerate(raw_series):
                try:
                    series.append(model.model_validate(item))
                except PydanticValidationError as exc:
                    raise TemplateParseError(
                        str(path), f"series.{index}.{_first_error(exc)}"
                    ) from exc
            loaded = {**loaded, "series": series}
        try:
            routine = Routine.model_validate(loaded)
        except PydanticValidationError as exc:
            raise TemplateParseError(str(path), _first_error(exc)) from exc
        if routine.name != path.stem:
            raise TemplateParseError(
                str(path), f"name {routine.name!r} must be the file name {path.stem!r}"
            )
        return routine


def _first_error(exc: PydanticValidationError) -> str:
    """どのシリーズのどの値かを、位置（series.2.images など）つきで1行にする."""
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else str(error["msg"])
