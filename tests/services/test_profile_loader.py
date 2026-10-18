"""装置のプロファイルの読み込みの試験（spec/13 の 6）."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from app.core import (
    DuplicateProfileError,
    ProfileError,
    ProfileNotFoundError,
    ProfileParseError,
)
from app.services.profile_loader import (
    EXAMPLES_DIR,
    PROFILE_DIRS_ENV,
    ProfileLoaderService,
)

ROOT_DIR = Path(__file__).resolve().parents[2]


def _profile(name: str, manufacturer: str = "DTG External") -> dict:
    return {
        "schema_version": 1,
        "name": name,
        "device": {
            "modality": "CT",
            "manufacturer": manufacturer,
            "manufacturers_model_name": "DTG External CT",
        },
        "storage": {
            "sop_classes": ["1.2.840.10008.5.1.4.1.1.2"],
            "transfer_syntaxes": ["1.2.840.10008.1.2"],
        },
    }


def _write(directory: Path, name: str, data: dict | str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.yaml"
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _loader(tmp_path: Path, env_dirs: list[Path] | None = None,
            config_paths: list[str] | None = None) -> ProfileLoaderService:
    config_path = tmp_path / "config" / "app_config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {"profiles": {"search_paths": config_paths or []}}
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    env = {}
    if env_dirs:
        env[PROFILE_DIRS_ENV] = os.pathsep.join(str(p) for p in env_dirs)
    return ProfileLoaderService(config_path=config_path, environ=env)


def test_loads_bundled_example() -> None:
    loader = ProfileLoaderService(environ={})

    profile = loader.load("dtg_synthetic_ct")

    assert profile.device.manufacturer == "DTG Synthetic"


def test_loads_profile_from_env_directory(tmp_path) -> None:
    external = tmp_path / "private_profiles"
    _write(external, "site_ct", _profile("site_ct"))
    loader = _loader(tmp_path, env_dirs=[external])

    profile = loader.load("site_ct")

    assert profile.device.manufacturer == "DTG External"


def test_loads_profile_from_config_relative_path(tmp_path) -> None:
    external = tmp_path / "config" / "my_profiles"
    _write(external, "site_ct", _profile("site_ct"))
    loader = _loader(tmp_path, config_paths=["my_profiles"])

    assert loader.load("site_ct").name == "site_ct"


def test_search_order_env_then_config_then_examples(tmp_path) -> None:
    env_dir = tmp_path / "env"
    config_dir = tmp_path / "cfg"
    env_dir.mkdir()
    config_dir.mkdir()
    loader = _loader(tmp_path, env_dirs=[env_dir], config_paths=[str(config_dir)])

    assert loader.search_paths() == [env_dir, config_dir, EXAMPLES_DIR]


def test_same_name_in_two_places_is_an_error(tmp_path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    _write(first, "site_ct", _profile("site_ct"))
    _write(second, "site_ct", _profile("site_ct"))
    loader = _loader(tmp_path, env_dirs=[first, second])

    with pytest.raises(DuplicateProfileError) as exc_info:
        loader.load("site_ct")

    message = str(exc_info.value)
    assert str(first / "site_ct.yaml") in message
    assert str(second / "site_ct.yaml") in message


def test_same_directory_listed_twice_is_not_a_duplicate(tmp_path) -> None:
    external = tmp_path / "a"
    _write(external, "site_ct", _profile("site_ct"))
    loader = _loader(tmp_path, env_dirs=[external], config_paths=[str(external)])

    assert loader.load("site_ct").name == "site_ct"


def test_shadowing_an_example_is_an_error(tmp_path) -> None:
    external = tmp_path / "a"
    _write(external, "dtg_synthetic_ct", _profile("dtg_synthetic_ct"))
    loader = _loader(tmp_path, env_dirs=[external])

    with pytest.raises(DuplicateProfileError):
        loader.load("dtg_synthetic_ct")


def test_missing_profile_lists_searched_directories(tmp_path) -> None:
    external = tmp_path / "a"
    external.mkdir()
    loader = _loader(tmp_path, env_dirs=[external])

    with pytest.raises(ProfileNotFoundError) as exc_info:
        loader.load("nothing_here")

    assert str(external) in str(exc_info.value)
    assert str(EXAMPLES_DIR) in str(exc_info.value)


def test_missing_search_directory_is_an_error(tmp_path) -> None:
    loader = _loader(tmp_path, env_dirs=[tmp_path / "does_not_exist"])

    with pytest.raises(ProfileError, match="does_not_exist"):
        loader.load("dtg_synthetic_ct")


def test_broken_yaml_is_a_clear_error(tmp_path) -> None:
    external = tmp_path / "a"
    path = _write(external, "broken", "device: [unclosed")
    loader = _loader(tmp_path, env_dirs=[external])

    with pytest.raises(ProfileParseError) as exc_info:
        loader.load("broken")

    assert str(path) in str(exc_info.value)


def test_schema_error_names_the_field(tmp_path) -> None:
    external = tmp_path / "a"
    data = _profile("bad_fields")
    del data["device"]["manufacturer"]
    data["device"]["manufacturer_typo"] = "x"
    _write(external, "bad_fields", data)
    loader = _loader(tmp_path, env_dirs=[external])

    with pytest.raises(ProfileParseError) as exc_info:
        loader.load("bad_fields")

    message = str(exc_info.value)
    assert "device.manufacturer" in message
    assert "device.manufacturer_typo" in message


def test_name_must_match_file_name(tmp_path) -> None:
    external = tmp_path / "a"
    _write(external, "file_name", _profile("other_name"))
    loader = _loader(tmp_path, env_dirs=[external])

    with pytest.raises(ProfileParseError, match="other_name"):
        loader.load("file_name")


def test_invalid_requested_name_is_rejected(tmp_path) -> None:
    loader = _loader(tmp_path)

    with pytest.raises(ProfileNotFoundError):
        loader.load("../escape")


def test_list_profiles_reports_broken_ones_separately(tmp_path) -> None:
    external = tmp_path / "a"
    _write(external, "site_ct", _profile("site_ct"))
    _write(external, "broken", "device: [unclosed")
    loader = _loader(tmp_path, env_dirs=[external])

    entries, errors = loader.list_profiles()

    names = [entry.name for entry in entries]
    assert "site_ct" in names
    assert "dtg_synthetic_ct" in names
    assert len(errors) == 1
    assert isinstance(errors[0], ProfileParseError)


def test_list_profiles_reports_duplicates(tmp_path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    _write(first, "site_ct", _profile("site_ct"))
    _write(second, "site_ct", _profile("site_ct"))
    loader = _loader(tmp_path, env_dirs=[first, second])

    entries, errors = loader.list_profiles()

    assert "site_ct" not in [entry.name for entry in entries]
    assert any(isinstance(error, DuplicateProfileError) for error in errors)


def test_invalid_config_search_paths_is_an_error(tmp_path) -> None:
    config_path = tmp_path / "app_config.yaml"
    config_path.write_text("profiles:\n  search_paths: not-a-list\n", encoding="utf-8")
    loader = ProfileLoaderService(config_path=config_path, environ={})

    with pytest.raises(ProfileError, match="search_paths"):
        loader.search_paths()


def test_missing_config_file_uses_env_and_examples_only(tmp_path) -> None:
    loader = ProfileLoaderService(config_path=tmp_path / "none.yaml", environ={})

    assert loader.search_paths() == [EXAMPLES_DIR]


def test_repository_profiles_contain_only_fictional_examples() -> None:
    """公開のリポジトリの profiles/ には架空の例だけを置く（spec/13 の 6.2）.

    追跡しているファイルと、まだ追跡していないが .gitignore で外れていない
    ファイル（＝commit に入りうるもの）を見る。
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "profiles"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip("git is not available")
    tracked = [line for line in result.stdout.splitlines() if line]

    assert tracked, "profiles/examples should be tracked"
    for path in tracked:
        assert path.startswith("profiles/examples/"), path

    loader = ProfileLoaderService(environ={})
    for path in sorted(EXAMPLES_DIR.glob("*.yaml")):
        profile = loader.load(path.stem)
        assert profile.device.manufacturer.startswith("DTG")
        assert profile.device.manufacturers_model_name.startswith("DTG")
        assert profile.source.url == ""


def test_private_directory_is_ignored_by_git() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "profiles/private/some_device.yaml"],
        cwd=ROOT_DIR,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode == 128:
        pytest.skip("git is not available")

    assert result.returncode == 0
