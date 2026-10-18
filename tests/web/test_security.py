"""待ち受けと認証・CSRF・応答の見出し（spec/12 の 10.8・10.9）."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from web_helpers import ORIGIN, csrf_token, make_client, post_headers

from app.web.__main__ import main
from app.web.auth import (
    PASSWORD_FILE_ENV,
    USERNAME,
    WebStartupError,
    host_header_is_loopback,
    startup_password,
)
from app.web.templating import TEMPLATES_DIR, create_environment

WEB_DIR = Path(__file__).resolve().parents[2] / "app" / "web"


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
def test_loopback_needs_no_password(host) -> None:
    assert startup_password(host, environ={}) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "::", "example.org"])
def test_outside_loopback_without_password_file_refuses_to_start(host) -> None:
    with pytest.raises(WebStartupError) as exc_info:
        startup_password(host, environ={})
    assert PASSWORD_FILE_ENV in str(exc_info.value)


def test_password_file_must_exist_and_not_be_empty(tmp_path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(WebStartupError):
        startup_password("0.0.0.0", environ={PASSWORD_FILE_ENV: str(missing)})
    empty = tmp_path / "empty"
    empty.write_text(" \n", encoding="utf-8")
    with pytest.raises(WebStartupError):
        startup_password("0.0.0.0", environ={PASSWORD_FILE_ENV: str(empty)})
    good = tmp_path / "pw"
    good.write_text("s3cret\n", encoding="utf-8")
    assert startup_password("0.0.0.0", environ={PASSWORD_FILE_ENV: str(good)}) == "s3cret"
    # 手元でも、ファイルを指していれば認証を付ける
    assert startup_password("127.0.0.1", environ={PASSWORD_FILE_ENV: str(good)}) == "s3cret"


def test_main_refuses_to_start_outside_loopback(tmp_path, monkeypatch, capsys) -> None:
    config = tmp_path / "app_config.yaml"
    config.write_text(
        "modality:\n"
        "  ae_title: DTG_CT01\n"
        "  worklist: {ae_title: RIS_TEST, host: 127.0.0.1, port: 4242}\n"
        "  destinations: [{name: PACS_TEST, ae_title: PACS_TEST, host: 127.0.0.1, port: 4242}]\n"
        "  default_destination: PACS_TEST\n"
        "web:\n"
        "  bind_address: 0.0.0.0\n",
        encoding="utf-8",
    )
    monkeypatch.delenv(PASSWORD_FILE_ENV, raising=False)

    code = main(["--config", str(config)])

    assert code == 2
    assert PASSWORD_FILE_ENV in capsys.readouterr().err


def test_main_bad_config_is_exit_2(tmp_path, capsys) -> None:
    assert main(["--config", str(tmp_path / "missing.yaml")]) == 2
    assert "missing.yaml" in capsys.readouterr().err


def test_basic_auth_is_required_when_password_is_set(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port, password="s3cret")

    response = client.get("/worklist")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic")
    assert client.get("/worklist", headers=_basic(USERNAME, "wrong")).status_code == 401
    assert client.get("/worklist", headers=_basic("other", "s3cret")).status_code == 401
    assert client.get("/static/app.js").status_code == 401
    assert client.get("/worklist", headers=_basic(USERNAME, "s3cret")).status_code == 200


def test_loopback_rejects_foreign_host_header(client) -> None:
    """DNS rebinding：手元で待ち受けるとき、Host が手元の名前でなければ断る（10.9）."""
    assert client.get("/worklist", headers={"Host": "evil.example:8080"}).status_code == 400
    assert client.get("/worklist", headers={"Host": "localhost:8080"}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example@localhost", "localhost/x", "localhost?x", ""])
def test_odd_host_headers_are_not_loopback(host) -> None:
    assert not host_header_is_loopback(host)


@pytest.mark.parametrize("host", ["[", "[::1", "localhost:abc]", "[x]:1"])
def test_unparsable_host_is_400_not_500(client, host) -> None:
    assert not host_header_is_loopback(host)
    assert client.get("/worklist", headers={"Host": host}).status_code == 400


@pytest.mark.parametrize("header", ["Origin", "Referer"])
@pytest.mark.parametrize("value", ["http://[", "http://[::1", "http://127.0.0.1:8080]"])
def test_unparsable_origin_is_403_not_500(client, header, value) -> None:
    token = csrf_token(client)
    response = client.post(
        "/worklist/query",
        data={"day": "today"},
        headers={header: value, "X-CSRF-Token": token},
    )
    assert response.status_code == 403


def test_post_requires_same_origin_and_csrf_token(client) -> None:
    token = csrf_token(client)
    form = {"day": "today"}

    assert client.post("/worklist/query", data=form).status_code == 403
    assert (
        client.post(
            "/worklist/query",
            data=form,
            headers={"Origin": "http://evil.example", "X-CSRF-Token": token},
        ).status_code
        == 403
    )
    assert client.post("/worklist/query", data=form, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            "/worklist/query", data=form, headers={"Origin": ORIGIN, "X-CSRF-Token": "x" * 43}
        ).status_code
        == 403
    )
    # Origin が無いときは Referer の住所で確かめる
    assert (
        client.post(
            "/worklist/query",
            data={**form, "csrf_token": token},
            headers={"Referer": f"{ORIGIN}/worklist"},
        ).status_code
        == 200
    )
    assert client.post("/worklist/query", data=form, headers=post_headers(token)).status_code == 200


def test_security_headers(client) -> None:
    response = client.get("/worklist")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_templates_autoescape_and_never_mark_safe() -> None:
    """相手から来る値はエスケープする。`|safe`・Markup を使わない（10.8）."""
    env = create_environment()
    assert env.autoescape is True
    assert env.from_string("{{ v }}").render(v="<b>&") == "&lt;b&gt;&amp;"
    for path in TEMPLATES_DIR.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "|safe" not in text.replace(" ", ""), path
        assert "autoescape false" not in text, path
    for path in WEB_DIR.rglob("*.py"):
        assert "Markup" not in path.read_text(encoding="utf-8"), path


def test_control_characters_are_made_visible_in_templates() -> None:
    env = create_environment()
    rendered = env.from_string("{{ v }}").render(v="A\x1b[31mB\u202eC")
    assert "\x1b" not in rendered and "\u202e" not in rendered
    assert rendered == "A\\x1b[31mB\\u202eC"
