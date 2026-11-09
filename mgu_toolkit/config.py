import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "MGU Toolkit"
APP_TAGLINE = "iDrive 7 / 8  ·  ENET"
VERSION = "1.0.0"
IS_WINDOWS = os.name == "nt"

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "mgu-workspace"
REPOS = WORK / "repos"
TOOLS = WORK / "tools"
LOGS = WORK / "logs"
DOWNLOADS = WORK / "downloads"
VENV = WORK / ".venv"
CONFIG_FILE = WORK / "config.json"

SSH_SLUG = "cauliflowermossgrape/idrive7-8-ssh-root"
SSH_REPO = REPOS / "idrive7-8-ssh-root"
STORE_SLUG = "robertnisipeanu/mgu-store"
APPS_SLUG = "robertnisipeanu/idrive-apps"
SSH_URL = "https://github.com/" + SSH_SLUG
STORE_URL = "https://github.com/" + STORE_SLUG
APPS_URL = "https://github.com/" + APPS_SLUG

DEFAULTS = {
    "vin": "",
    "arch": "id7",
    "gateway": "",
    "last_backup": "",
    "backup_vin": "",
    "store_installed": False,
    "flashed_vins": [],
    "lang": "pl",
}


def ensure_dirs():
    for d in (WORK, REPOS, TOOLS, LOGS, DOWNLOADS):
        d.mkdir(parents=True, exist_ok=True)


def load_settings():
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            for key in DEFAULTS:
                if key not in loaded:
                    continue
                if key == "flashed_vins" and not isinstance(loaded[key], list):
                    continue
                if key == "lang" and loaded[key] not in ("pl", "en"):
                    continue
                data[key] = loaded[key]
    except (OSError, ValueError):
        pass
    return data


def save_settings(data):
    ensure_dirs()
    payload = {key: data.get(key, DEFAULTS[key]) for key in DEFAULTS}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except OSError:
        pass


def venv_python():
    if IS_WINDOWS:
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def base_python_argv():
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    for name in ("py", "python3", "python"):
        found = shutil.which(name)
        if found:
            return [found]
    return []


def bootstrap():
    ensure_dirs()
    return venv_python()
