import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from . import config
from .i18n import tr
from .proc import run_capture, run_lines

USER_AGENT = "MGU-Toolkit/%s (+https://github.com/%s)" % (config.VERSION, config.SSH_SLUG)

DETECT_HELPER = '''import json
import sys

result = {"ok": False}
try:
    from mgu7 import discovery
    gateways = discovery.discover(log=lambda *a, **k: None)
    if gateways:
        gw = gateways[0]
        result = {"ok": True, "ip": getattr(gw, "ip", ""), "vin": getattr(gw, "vin", "")}
    else:
        result["error"] = "no gateway"
except Exception as exc:
    result["error"] = str(exc)
print(json.dumps(result))
'''

RESTART_HELPER = '''import json
import sys

host, key = sys.argv[1], sys.argv[2]
try:
    from mgu7 import sshcli
    rc, out, err = sshcli.run(host, key, "sync; reboot", timeout=30)
    text = (out + " " + err).lower()
    closed = any(k in text for k in ("closed", "reset", "broken pipe", "timed out"))
    print(json.dumps({"ok": rc == 0 or closed, "rc": rc, "out": out.strip(), "err": err.strip()}))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
'''

STATUS_HELPER = '''import json
import sys

host, key = sys.argv[1], sys.argv[2]
try:
    from mgu7 import sshcli
    rc, out, err = sshcli.run(host, key, "id", timeout=30)
    print(json.dumps({"ok": rc == 0, "rc": rc, "out": out.strip(), "err": err.strip()}))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
'''


def _safe_extract(archive, target):
    target = Path(target).resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            dest = (target / member.filename).resolve()
            if not str(dest).startswith(str(target) + os.sep) and dest != target:
                raise RuntimeError(tr("Niebezpieczna ścieżka w archiwum: %s", "Unsafe path in archive: %s") % member.filename)
        zf.extractall(target)


def http_download(url, dest, emit):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    emit(tr("Pobieram: %s", "Downloading: %s") % url, "muted")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = time.time()
    with urllib.request.urlopen(request, timeout=90) as response:
        total = response.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else 0
        done = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
        size = done
    emit(tr("Pobrano %.1f KB w %.1fs", "Downloaded %.1f KB in %.1fs") % (size / 1024.0, time.time() - start), "muted")
    if size == 0:
        raise RuntimeError(tr("Pobrany plik jest pusty: %s", "The downloaded file is empty: %s") % url)
    return dest


def ensure_repo(emit, force=False):
    dest = config.SSH_REPO
    marker = dest / "ssh_enable.py"
    if marker.exists() and not force:
        return dest
    emit(tr("Pobieram repozytorium idrive7-8-ssh-root...", "Downloading the idrive7-8-ssh-root repository...")
         if not force else
         tr("Aktualizuję repozytorium SSH...", "Updating the SSH repository..."), "muted")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = config.DOWNLOADS / ("ssh-root-%s.zip" % stamp)
    url = "https://codeload.github.com/%s/zip/refs/heads/main" % config.SSH_SLUG
    http_download(url, archive, emit)
    extract_dir = Path(tempfile.mkdtemp(prefix="mgu-ssh-", dir=str(config.DOWNLOADS)))
    try:
        _safe_extract(archive, extract_dir)
        inner = next((p for p in extract_dir.iterdir() if (p / "ssh_enable.py").exists()), None)
        if inner is None:
            raise RuntimeError(tr("Archiwum nie zawiera ssh_enable.py", "The archive does not contain ssh_enable.py"))
        old_data = None
        if dest.exists():
            data_dir = dest / "data"
            if data_dir.exists():
                old_data = extract_dir / "__data__"
                shutil.move(str(data_dir), str(old_data))
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(inner), str(dest))
        if old_data is not None and old_data.exists():
            target = dest / "data"
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(old_data), str(target))
        emit(tr("Repozytorium gotowe: %s", "Repository ready: %s") % dest, "ok")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        try:
            archive.unlink()
        except OSError:
            pass
    return dest


def ensure_venv(emit):
    py = config.venv_python()
    if py.exists():
        return py
    base = config.base_python_argv()
    if not base:
        raise RuntimeError(tr("Nie znaleziono Pythona 3.9+. Zainstaluj Python 3 z python.org i zaznacz 'Add Python to PATH'.",
                              "Python 3.9+ not found. Install Python 3 from python.org and tick 'Add Python to PATH'."))
    emit(tr("Tworzę środowisko Python w %s", "Creating the Python environment in %s") % config.VENV, "muted")
    rc = run_lines(base + ["-m", "venv", str(config.VENV)], emit)
    if rc != 0 or not py.exists():
        raise RuntimeError(tr("Nie udało się utworzyć środowiska Python (kod %s).",
                              "Could not create the Python environment (code %s).") % rc)
    return py


def install_requirements(py, emit, force=False):
    req = config.SSH_REPO / "requirements.txt"
    if not req.exists():
        raise RuntimeError(tr("Brak pliku requirements.txt w repozytorium.", "requirements.txt is missing from the repository."))
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    marker = config.VENV / "deps.sha256"
    if not force and marker.exists() and marker.read_text(encoding="utf-8").strip() == digest:
        emit(tr("Zależności Python są aktualne.", "Python dependencies are up to date."), "muted")
        return
    emit(tr("Instaluję zależności (cryptography)...", "Installing dependencies (cryptography)..."), "muted")
    run_lines([str(py), "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check"], emit)
    rc = run_lines([str(py), "-m", "pip", "install", "-r", str(req), "--disable-pip-version-check"], emit)
    if rc != 0:
        raise RuntimeError(tr("Instalacja zależności nie powiodła się (kod %s).",
                              "Dependency installation failed (code %s).") % rc)
    marker.write_text(digest, encoding="utf-8")
    emit(tr("Zależności zainstalowane.", "Dependencies installed."), "ok")


def ensure_store_installer(emit):
    name = "mgu-store-install.ps1" if config.IS_WINDOWS else "mgu-store-install.sh"
    dest = config.TOOLS / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    remote = "install.ps1" if config.IS_WINDOWS else "install.sh"
    url = "https://raw.githubusercontent.com/%s/main/deploy/%s" % (config.STORE_SLUG, remote)
    http_download(url, dest, emit)
    text = dest.read_text(encoding="utf-8", errors="replace")
    if "mgu-install" not in text:
        raise RuntimeError(tr("Pobrany instalator MGU Store wygląda na nieprawidłowy.",
                              "The downloaded MGU Store installer looks invalid."))
    emit(tr("Instalator MGU Store gotowy.", "MGU Store installer ready."), "ok")
    return dest


def write_helpers(emit=None):
    config.ensure_dirs()
    files = {
        "detect_vin.py": DETECT_HELPER,
        "restart_unit.py": RESTART_HELPER,
        "probe_login.py": STATUS_HELPER,
    }
    for name, body in files.items():
        path = config.TOOLS / name
        path.write_text(body, encoding="utf-8")
    if emit:
        emit(tr("Narzędzia pomocnicze zapisane.", "Helper tools written."), "muted")


def _helper_env():
    return {"PYTHONPATH": str(config.SSH_REPO)}


def detect_vin(py, emit):
    helper = config.TOOLS / "detect_vin.py"
    rc, out, err = run_capture([str(py), str(helper)], cwd=config.SSH_REPO, env_extra=_helper_env(), timeout=45)
    result = None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "ok" in parsed:
            result = parsed
            break
    if result is None:
        emit(tr("Nie udało się odczytać VIN.", "Could not read the VIN."), "err")
        if err.strip():
            emit(err.strip(), "muted")
        return {"ok": False, "error": err.strip() or "no output"}
    if result.get("ok"):
        emit(tr("Bramka ENET: %s | VIN: %s", "ENET gateway: %s | VIN: %s")
             % (result.get("ip", "?"), result.get("vin") or tr("brak", "none")), "ok")
    else:
        emit(tr("Brak odpowiedzi bramki ENET. Sprawdź kabel, adapter i zapłon.",
                "No ENET gateway responded. Check the cable, adapter and ignition."), "warn")
        if result.get("error"):
            emit(tr("Szczegóły: %s", "Details: %s") % result["error"], "muted")
    return result


def enrollment_root():
    return config.SSH_REPO / "data" / "enrollments"


def identities():
    root = enrollment_root()
    if not root.exists():
        return []
    found = []
    for entry in sorted(root.iterdir()):
        key = entry / "id_rsa"
        if key.exists():
            found.append((entry.name, key))
    return found


def identity_for(vin):
    vin = (vin or "").strip().upper()
    if vin:
        folder = enrollment_root() / vin
        key = folder / "id_rsa"
        if key.exists():
            return folder, key
    found = identities()
    if len(found) == 1:
        return enrollment_root() / found[0][0], found[0][1]
    return None, None


def enrollment_exists(vin):
    folder, key = identity_for(vin)
    return key is not None and (not vin or folder.name == vin.strip().upper())


def connect_host(folder):
    if folder is None:
        return ""
    meta = Path(folder) / "metadata.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            host = data.get("mgu_ip") or data.get("host") or ""
            if host:
                return host
        except (OSError, ValueError):
            pass
    connect = Path(folder) / "connect.txt"
    if connect.exists():
        try:
            text = connect.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"root@([0-9]{1,3}(?:\.[0-9]{1,3}){3})", text)
            if match:
                return match.group(1)
        except OSError:
            pass
    return ""


def latest_preflight():
    root = config.SSH_REPO / "data" / "preflight"
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def restart_unit(py, folder, emit):
    host = connect_host(folder)
    if not host:
        emit(tr("Nie znam adresu IP jednostki (brak metadata.json / connect.txt).",
                "The head unit IP is unknown (no metadata.json / connect.txt)."), "err")
        return 1
    key = Path(folder) / "id_rsa"
    helper = config.TOOLS / "restart_unit.py"
    emit(tr("Restartuję jednostkę MGU pod %s...", "Restarting the MGU head unit at %s...") % host, "muted")
    rc, out, err = run_capture([str(py), str(helper), host, str(key)], cwd=config.SSH_REPO,
                               env_extra=_helper_env(), timeout=60)
    ok = False
    for line in reversed((out or "").splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        ok = bool(data.get("ok"))
        if data.get("err"):
            emit(data["err"], "muted")
        break
    if ok:
        emit(tr("Polecenie restartu wysłane. Jednostka wstanie za chwilę.", "Restart command sent. The unit will come back shortly."), "ok")
        return 0
    emit(tr("Restart przez SSH nie potwierdził się. Zresetuj jednostkę, przytrzymując pokrętło głośności ok. 25 s.",
            "The SSH restart was not confirmed. Reset the unit by holding the volume knob for about 25 s."), "warn")
    return 1


def probe_login(py, folder, emit):
    host = connect_host(folder)
    if not host:
        emit(tr("Brak adresu IP jednostki.", "No head unit IP address."), "err")
        return 1
    key = Path(folder) / "id_rsa"
    helper = config.TOOLS / "probe_login.py"
    rc, out, err = run_capture([str(py), str(helper), host, str(key)], cwd=config.SSH_REPO,
                               env_extra=_helper_env(), timeout=60)
    for line in reversed((out or "").splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if data.get("ok"):
            emit(tr("Logowanie root przez SSH działa: %s", "Root SSH login works: %s") % (data.get("out") or ""), "ok")
            return 0
        emit(tr("Logowanie SSH nie powiodło się: %s", "SSH login failed: %s")
             % (data.get("err") or data.get("error") or tr("brak szczegółów", "no details")), "err")
        return 1
    emit(tr("Brak odpowiedzi testu SSH.", "No response from the SSH test."), "err")
    return 1
