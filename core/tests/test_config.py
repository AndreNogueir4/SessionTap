import pytest
from pathlib import Path
from sessiontap import config as cfg
from sessiontap.domains import cookie_applies, InvalidDomain, match_any, normalize_domain


def test_defaults() -> None:
    c = cfg.load_config()
    assert c.port == cfg.DEFAULT_PORT
    assert "example.block.com" in c.blocklist


def test_file_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[server]\nport = 9000\n[capture]\nblocklist = ["Bank.Example."]\n')
    c = cfg.load_config(path)
    assert c.port == 9000
    assert c.blocklist == ("bank.example",)
    monkeypatch.setenv("SESSIONTAP_PORT", "9100")
    assert cfg.load_config(path).port == 9100


@pytest.mark.parametrize(
    "toml",
    [
        "[server]\nport = 80\n",
        '[vault]\nkey_backend = "plaintext"\n',
        "server = 1\n",
        '[capture]\nhtml = "yes"\n',
        "[capture]\nlocked = 1\n",
    ],
)
def test_invalid_config(tmp_path: Path, toml: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSIONTAP_KEY_BACKEND")
    path = tmp_path / "config.toml"
    path.write_text(toml)
    with pytest.raises(ValueError):
        cfg.load_config(path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Example.COM.", "example.com"),
        ("www.example.com", "example.com"),
        ("bücher.de", "xn--bcher-kva.de"),
        ("api.example.co.uk", "api.example.co.uk"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "com", "*.example.com", "example.com/path", "http://example.com", "a..b", "-a.com"]
)
def test_normalize_rejects(raw: str) -> None:
    with pytest.raises(InvalidDomain):
        normalize_domain(raw)


def test_matching() -> None:
    assert match_any("api.example.com", ["example.com", "api.example.com"]) == "api.example.com"
    assert match_any("badexample.com", ["example.com"]) is None
    assert cookie_applies(".example.com", "www.example.com")
    assert not cookie_applies("www.example.com", "example.com")
