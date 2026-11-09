import os
import shutil
import socket
import subprocess
import sys

from . import config
from .proc import CREATE_NO_WINDOW


def is_admin():
    if config.IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def python_ok():
    return sys.version_info >= (3, 9)


def ssh_client():
    exe = shutil.which("ssh")
    if not exe:
        return False, "brak w PATH"
    try:
        proc = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=8,
                              creationflags=CREATE_NO_WINDOW)
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return True, text[0] if text else "OpenSSH"
    except (OSError, subprocess.SubprocessError):
        return False, "blad"


def internet():
    try:
        with socket.create_connection(("github.com", 443), timeout=6):
            return True
    except OSError:
        return False


def components():
    py = config.venv_python()
    has_py = py.exists()
    has_repo = (config.SSH_REPO / "ssh_enable.py").exists()
    has_installer = (config.TOOLS / ("mgu-store-install.ps1" if config.IS_WINDOWS else "mgu-store-install.sh")).exists()
    deps = (config.VENV / "deps.sha256").exists()
    return has_py and has_repo and has_installer and deps


def enet_link():
    if not config.IS_WINDOWS:
        return []
    command = ("Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
               "Where-Object { $_.IPAddress -like '169.254.*' } | "
               "Select-Object -ExpandProperty IPAddress")
    try:
        proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                              capture_output=True, text=True, timeout=10,
                              creationflags=CREATE_NO_WINDOW)
        return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []
