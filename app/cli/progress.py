"""Progress display utilities using tqdm."""

from __future__ import annotations

from collections.abc import Callable

from tqdm import tqdm


def create_progress_callback(quiet: bool) -> Callable[[int, int], None] | None:
    """tqdm進捗表示用のコールバックを作成する."""
    if quiet:
        return None

    bar: tqdm | None = None

    def callback(current: int, total: int) -> None:
        nonlocal bar
        if bar is None:
            bar = tqdm(total=total, unit="img", leave=False)

        if current > bar.n:
            bar.update(current - bar.n)

        if current >= total:
            bar.close()
            bar = None

    return callback

