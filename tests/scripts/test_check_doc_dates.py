"""ADR の最終更新日の確認（scripts/check_doc_dates.py。docs/decisions/README.md の書き方）のテスト."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_doc_dates.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_doc_dates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_doc_dates = _load_module()


def _git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    if date is not None:
        env["GIT_AUTHOR_DATE"] = f"{date}T12:00:00+09:00"
        env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00+09:00"
    result = subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    return result.stdout


def _doc(updated: str | None, body: str = "本文") -> str:
    lines = ["# 題", ""]
    if updated is not None:
        lines += ["- 作成日：2026-01-01", f"- 最終更新日：{updated}", ""]
    lines.append(body)
    return "\n".join(lines) + "\n"


def _commit(repo: Path, files: dict[str, str], date: str) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "change", date=date)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, {ADR_PATH: _doc("2026-01-01")}, "2026-01-01")
    _git(tmp_path, "tag", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


ADR_PATH = "docs/decisions/0001-x.md"


def test_up_to_date_adr_passes(repo: Path) -> None:
    _commit(repo, {"docs/decisions/0002-y.md": _doc("2026-10-22")}, "2026-10-22")
    assert check_doc_dates.check("base..HEAD") == []


def test_stale_date_is_reported(repo: Path) -> None:
    _commit(repo, {ADR_PATH: _doc("2026-01-01", "直した本文")}, "2026-10-22")
    problems = check_doc_dates.check("base..HEAD")
    assert len(problems) == 1
    assert ADR_PATH in problems[0]
    assert "2026-01-01" in problems[0]


def test_missing_date_line_is_reported(repo: Path) -> None:
    _commit(repo, {"docs/decisions/0003-z.md": _doc(None)}, "2026-10-22")
    problems = check_doc_dates.check("base..HEAD")
    assert len(problems) == 1
    assert "docs/decisions/0003-z.md" in problems[0]


def test_documents_other_than_adr_are_skipped(repo: Path) -> None:
    _commit(
        repo,
        {
            "README.md": _doc(None),
            "docs/README.md": _doc(None),
            "docs/spec/01.md": _doc(None),
            "docs/decisions/README.md": _doc(None),
            "docs/decisions/template.md": _doc(None),
            "AGENTS.md": _doc(None),
            "app/x.py": "x = 1\n",
        },
        "2026-10-22",
    )
    assert check_doc_dates.check("base..HEAD") == []


def test_bad_range_exits_with_2(repo: Path) -> None:
    assert check_doc_dates.main(["no-such-ref..HEAD"]) == 2


def test_wrong_argument_count_exits_with_2() -> None:
    assert check_doc_dates.main([]) == 2
