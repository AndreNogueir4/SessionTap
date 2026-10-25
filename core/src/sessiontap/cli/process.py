import os
import sys
import time
import ctypes
import signal
import subprocess
from typing import Any
from pathlib import Path
from sessiontap import config as cfg

POLL_INTERVAL = 0.1
POLL_ATTEMPTS = 50


class DaemonProcess:
    def __init__(self, pid_file: Path | None = None) -> None:
        self._pid_file = pid_file

    @property
    def pid_file(self) -> Path:
        return self._pid_file or cfg.pid_path()

    @property
    def log_file(self) -> Path:
        return cfg.home_dir() / "daemon.log"

    def running_pid(self) -> int | None:
        try:
            pid = int(self.pid_file.read_text())
        except (FileNotFoundError, ValueError):
            return None
        return pid if self._alive(pid) else None

    def start_detached(self) -> bool:
        cfg.home_dir().mkdir(parents=True, exist_ok=True)
        fd = os.open(self.log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(
                [sys.executable, "-m", "sessiontap.server.daemon"],
                stdin=subprocess.DEVNULL,
                stdout=fd,
                stderr=fd,
                **kwargs,
            )
        finally:
            os.close(fd)
        return self._wait_until(running=True)

    def stop(self) -> bool:
        pid = self.running_pid()
        if pid is None:
            return False
        os.kill(pid, signal.SIGTERM)
        self._wait_until(running=False)
        return True

    def _wait_until(self, running: bool) -> bool:
        for _ in range(POLL_ATTEMPTS):
            if (self.running_pid() is not None) == running:
                return True
            time.sleep(POLL_INTERVAL)
        return False

    @staticmethod
    def _alive(pid: int) -> bool:
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return code.value == 259
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            return True
