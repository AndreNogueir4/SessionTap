import os
import sys
import json
import shlex
import contextlib
from pathlib import Path
from dataclasses import dataclass
from sessiontap import config as cfg

EXTENSION_ID = "filkhmjmjfdnofidimnincdidbabmhhk"
FIREFOX_EXTENSION_ID = "sessiontap@andrenogueir4.github.io"


@dataclass(frozen=True)
class Browser:
    name: str
    firefox: bool
    linux: str | None
    macos: str | None
    windows_key: str | None


BROWSERS = [
    Browser(
        "chrome",
        False,
        ".config/google-chrome",
        "Library/Application Support/Google/Chrome",
        r"Software\Google\Chrome",
    ),
    Browser(
        "chromium",
        False,
        ".config/chromium",
        "Library/Application Support/Chromium",
        r"Software\Chromium",
    ),
    Browser(
        "brave",
        False,
        ".config/BraveSoftware/Brave-Browser",
        "Library/Application Support/BraveSoftware/Brave-Browser",
        r"Software\BraveSoftware\Brave-Browser",
    ),
    Browser(
        "edge",
        False,
        ".config/microsoft-edge",
        "Library/Application Support/Microsoft Edge",
        r"Software\Microsoft\Edge",
    ),
    Browser(
        "firefox", True, ".mozilla", "Library/Application Support/Mozilla", r"Software\Mozilla"
    ),
]
BROWSER_NAMES = [b.name for b in BROWSERS]


def _launcher_path() -> Path:
    return cfg.home_dir() / (
        "sessiontap-host.bat" if sys.platform == "win32" else "sessiontap-host"
    )


def write_launcher() -> Path:
    path = _launcher_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    if sys.platform == "win32":
        path.write_text(f'@echo off\r\n"{python}" -m sessiontap.nativehost %*\r\n')
    else:
        path.write_text(f'#!/bin/sh\nexec {shlex.quote(python)} -m sessiontap.nativehost "$@"\n')
        os.chmod(path, 0o700)
    return path


def manifest(browser: Browser, launcher: Path, extra_ids: list[str]) -> dict[str, object]:
    base: dict[str, object] = {
        "name": cfg.NATIVE_HOST_NAME,
        "description": "SessionTap native host",
        "path": str(launcher),
        "type": "stdio",
    }
    if browser.firefox:
        base["allowed_extensions"] = [FIREFOX_EXTENSION_ID]
    else:
        ids = [EXTENSION_ID, *extra_ids]
        base["allowed_origins"] = [f"chrome-extension://{i}/" for i in dict.fromkeys(ids)]
    return base


def _manifest_dir(browser: Browser) -> Path | None:
    home = Path.home()
    if sys.platform == "darwin":
        root = browser.macos
    else:
        root = browser.linux
    if root is None:
        return None
    sub = (
        "native-messaging-hosts"
        if browser.firefox and sys.platform != "darwin"
        else ("NativeMessagingHosts")
    )
    return home / root / sub


def install(browsers: list[str], extra_ids: list[str]) -> list[str]:
    for ext_id in extra_ids:
        if len(ext_id) != 32 or not all("a" <= ch <= "p" for ch in ext_id):
            raise ValueError(f"not a Chromium extension ID: {ext_id!r}")
    launcher = write_launcher()
    done = []
    for browser in BROWSERS:
        if browser.name not in browsers:
            continue
        data = json.dumps(manifest(browser, launcher, extra_ids), indent=2)
        if sys.platform == "win32":
            target = cfg.home_dir() / f"{cfg.NATIVE_HOST_NAME}.{browser.name}.json"
            target.write_text(data)
            _set_registry(browser, target)
        else:
            directory = _manifest_dir(browser)
            if directory is None:
                continue
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{cfg.NATIVE_HOST_NAME}.json"
            target.write_text(data)
        done.append(f"{browser.name}: {target}")
    return done


def uninstall(browsers: list[str]) -> list[str]:
    removed = []
    for browser in BROWSERS:
        if browser.name not in browsers:
            continue
        if sys.platform == "win32":
            target = cfg.home_dir() / f"{cfg.NATIVE_HOST_NAME}.{browser.name}.json"
            _delete_registry(browser)
        else:
            directory = _manifest_dir(browser)
            if directory is None:
                continue
            target = directory / f"{cfg.NATIVE_HOST_NAME}.json"
        if target.exists():
            target.unlink()
            removed.append(f"{browser.name}: {target}")
    return removed


def _set_registry(browser: Browser, manifest_path: Path) -> None:
    import winreg  # type: ignore[import-not-found,unused-ignore]

    assert browser.windows_key is not None
    key = rf"{browser.windows_key}\NativeMessagingHosts\{cfg.NATIVE_HOST_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:  # type: ignore[attr-defined,unused-ignore]
        winreg.SetValueEx(handle, "", 0, winreg.REG_SZ, str(manifest_path))  # type: ignore[attr-defined,unused-ignore]


def _delete_registry(browser: Browser) -> None:
    import winreg  # type: ignore[import-not-found,unused-ignore]

    assert browser.windows_key is not None
    key = rf"{browser.windows_key}\NativeMessagingHosts\{cfg.NATIVE_HOST_NAME}"
    with contextlib.suppress(FileNotFoundError):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)  # type: ignore[attr-defined,unused-ignore]
