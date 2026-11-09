import os
import subprocess

from .i18n import tr

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _utf8_env(extra=None):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if extra:
        for key, value in extra.items():
            if key == "PYTHONPATH" and env.get("PYTHONPATH"):
                env[key] = str(value) + os.pathsep + env[key]
            else:
                env[key] = str(value)
    return env


def run_lines(argv, emit, cwd=None, env_extra=None, timeout=None):
    argv = [str(a) for a in argv]
    emit(" ".join(argv), "cmd")
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            env=_utf8_env(env_extra),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        emit(tr("Nie znaleziono polecenia: %s", "Command not found: %s") % argv[0], "err")
        return 127
    except OSError as exc:
        emit(tr("Nie można uruchomić polecenia: %s", "Cannot run the command: %s") % exc, "err")
        return 126
    try:
        for line in proc.stdout:
            text = line.rstrip("\r\n")
            if text:
                emit(text, _classify(text))
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        emit(tr("Przekroczono limit czasu.", "Timed out."), "err")
        return 124
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass


def run_capture(argv, cwd=None, env_extra=None, timeout=60):
    argv = [str(a) for a in argv]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=_utf8_env(env_extra),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "not found: %s" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 126, "", str(exc)


def _classify(line):
    low = line.strip().lower()
    if low.startswith(("error", "failed", "traceback", "exception", "niepowod")):
        return "err"
    if any(k in low for k in ("error:", "failed:", "permission denied", "refused", "nie udalo")):
        return "err"
    if low.startswith(("warning", "warn", "uwaga", "deprecated")):
        return "warn"
    if low.startswith(("done", "success", "gotowe")) or "successfully" in low:
        return "ok"
    return None
