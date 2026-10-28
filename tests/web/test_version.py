"""バージョン情報の画面（docs/spec/12a の 10.7a）."""

from __future__ import annotations

from web_helpers import make_client

from app.cli.commands import VERSION


def test_version_page_shows_name_and_version_without_commit(client, monkeypatch) -> None:
    monkeypatch.delenv("BUILD_COMMIT", raising=False)
    response = client.get("/version")
    assert response.status_code == 200
    html = response.text
    assert "<title>バージョン情報 - dicom-test-generator</title>" in html
    assert "<h1>バージョン情報</h1>" in html
    assert f'<dd data-testid="app-version">{VERSION}</dd>' in html
    assert "build-commit" not in html


def test_version_is_not_in_the_top_bar(client) -> None:
    # 上の帯の題はアプリの名前だけ。版は左のナビの「バージョン情報」で見る
    html = client.get("/worklist").text
    header = html[html.index("<header") : html.index("</header>")]
    assert f">{VERSION}<" not in header and 'class="ver"' not in header


def test_build_commit_is_shown_only_when_it_has_a_valid_form(client, monkeypatch) -> None:
    monkeypatch.setenv("BUILD_COMMIT", " A1B2C3D4E5F6 ")
    assert 'data-testid="build-commit">a1b2c3d4e5f6</dd>' in client.get("/version").text
    for bad in ("", "abc12", "g" * 12, "a" * 41, "a1b2c3d; echo"):
        monkeypatch.setenv("BUILD_COMMIT", bad)
        assert "build-commit" not in client.get("/version").text


def test_version_page_needs_the_password_when_one_is_required(
    tmp_path, worklist_scp, storage_scp
) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port, password="s3cret")
    assert client.get("/version").status_code == 401


def test_version_page_has_no_write_route(client) -> None:
    assert client.post("/version").status_code in (403, 405)
