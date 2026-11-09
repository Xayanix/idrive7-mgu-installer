import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from . import checks, config, repos
from .i18n import language, set_language, tr
from .proc import run_lines

C = {
    "bg": "#0A0C0F",
    "panel": "#11151A",
    "panel2": "#171D24",
    "panel3": "#1E2630",
    "stroke": "#26303B",
    "stroke_soft": "#1B232C",
    "text": "#E8EDF4",
    "muted": "#8A96A6",
    "muted2": "#616D7C",
    "accent": "#4C9BFF",
    "accent_hover": "#6FB2FF",
    "accent_soft": "#12263F",
    "ok": "#37D399",
    "warn": "#F0B429",
    "err": "#F05252",
    "danger": "#B42318",
    "danger_hover": "#D02B1E",
    "danger_soft": "#2A1412",
    "warn_soft": "#241B0C",
}

FONTS = {"ui": "Segoe UI", "mono": "Consolas"}

ARCH = [
    ("iDrive 7 — MGU (ID7)", "id7"),
    ("iDrive 8 — BDC3", "id8-bdc3"),
    ("iDrive 8 — BCP", "id8-bcp"),
]
ARCH_BY_LABEL = {label: value for label, value in ARCH}
ARCH_LABEL = {value: label for label, value in ARCH}


def _pick_fonts(root):
    families = set(tkfont.families(root))
    for name in ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "DejaVu Sans", "Helvetica"):
        if name in families:
            FONTS["ui"] = name
            break
    for name in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"):
        if name in families:
            FONTS["mono"] = name
            break


def _open_path(path):
    path = str(path)
    try:
        if config.IS_WINDOWS:
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


def _elide(text, limit=74):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def make_button(parent, text, command, kind="primary", small=False):
    palette = {
        "primary": (C["accent"], "#06111F", C["accent_hover"], C["accent"]),
        "danger": (C["danger"], "#FFFFFF", C["danger_hover"], C["danger"]),
        "ghost": (C["panel2"], C["text"], C["panel3"], C["stroke"]),
        "quiet": (C["panel"], C["muted"], C["panel2"], C["panel"]),
    }
    bg, fg, hover, ring = palette.get(kind, palette["ghost"])
    padx, pady = (11, 6) if small else (16, 9)
    size = 8 if small else 9
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=fg,
        disabledforeground=C["muted2"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=ring,
        highlightcolor=ring,
        cursor="hand2",
        font=(FONTS["ui"], size, "bold"),
        padx=padx,
        pady=pady,
    )
    button.bind("<Enter>", lambda _e: button["state"] != "disabled" and button.configure(bg=hover))
    button.bind("<Leave>", lambda _e: button["state"] != "disabled" and button.configure(bg=bg))
    return button


def make_link(parent, text, command, bg=None):
    label = tk.Label(parent, text=text, bg=bg or C["panel"], fg=C["accent"], font=(FONTS["ui"], 9), cursor="hand2", anchor="w")
    label.bind("<Button-1>", lambda _e: command())
    label.bind("<Enter>", lambda _e: label.configure(fg=C["accent_hover"]))
    label.bind("<Leave>", lambda _e: label.configure(fg=C["accent"]))
    return label


class Chip(tk.Frame):
    def __init__(self, parent, label):
        super().__init__(parent, bg=C["panel2"], highlightbackground=C["stroke"], highlightthickness=1, bd=0)
        self.dot = tk.Canvas(self, width=8, height=8, bg=C["panel2"], highlightthickness=0)
        self.dot.pack(side="left", padx=(10, 6), pady=7)
        self.label = tk.Label(self, text=label, bg=C["panel2"], fg=C["muted2"], font=(FONTS["ui"], 8, "bold"))
        self.label.pack(side="left", padx=(0, 10))
        self.set("muted")

    def set(self, state):
        color = {"ok": C["ok"], "err": C["err"], "warn": C["warn"], "muted": C["muted2"], "busy": C["accent"]}.get(state, C["muted2"])
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 7, 7, fill=color, outline="")
        self.label.configure(fg=C["text"] if state in ("ok", "err", "warn", "busy") else C["muted2"])


class StepCard(tk.Frame):
    def __init__(self, parent, number, title, desc, accent=None):
        super().__init__(parent, bg=C["panel"], highlightbackground=C["stroke"], highlightthickness=1, bd=0)
        self.accent = accent or C["accent"]
        top = tk.Frame(self, bg=C["panel"])
        top.pack(fill="x", padx=18, pady=(16, 0))
        badge = tk.Label(top, text=str(number), bg=self.accent, fg="#06111F", font=(FONTS["ui"], 10, "bold"), width=3, pady=2)
        badge.pack(side="left")
        tk.Label(top, text=title, bg=C["panel"], fg=C["text"], font=(FONTS["ui"], 13, "bold")).pack(side="left", padx=10)
        self.state = tk.Label(top, text=tr("Oczekuje", "Waiting"), bg=C["panel"], fg=C["muted2"], font=(FONTS["ui"], 9))
        self.state.pack(side="right")
        self.desc = tk.Label(self, text=desc, bg=C["panel"], fg=C["muted"], font=(FONTS["ui"], 9), justify="left", anchor="w")
        self.desc.pack(fill="x", padx=18, pady=(7, 0))
        self.body = tk.Frame(self, bg=C["panel"])
        self.body.pack(fill="x", padx=18, pady=(10, 0))
        self.actions = tk.Frame(self, bg=C["panel"])
        self.actions.pack(fill="x", padx=18, pady=(12, 16))
        self.bind("<Configure>", self._wrap)

    def _wrap(self, event):
        self.desc.configure(wraplength=max(240, event.width - 70))

    def add_button(self, text, command, kind="primary", small=False, side="left", padx=(0, 8)):
        button = make_button(self.actions, text, command, kind, small)
        button.pack(side=side, padx=padx)
        return button

    def set_state(self, text, kind="muted"):
        color = {"ok": C["ok"], "err": C["err"], "warn": C["warn"], "busy": C["accent"], "muted": C["muted2"]}.get(kind, C["muted2"])
        self.state.configure(text=text, fg=color)


class TypedConfirm(tk.Toplevel):
    def __init__(self, parent, title, heading, warning, word, action_label, checks=None, danger=True):
        super().__init__(parent)
        self.result = False
        self.word = word
        self.title(title)
        self.configure(bg=C["panel"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        wrapper = tk.Frame(self, bg=C["panel"], padx=26, pady=22)
        wrapper.pack(fill="both", expand=True)
        tk.Label(wrapper, text=heading, bg=C["panel"], fg=C["err"] if danger else C["text"],
                 font=(FONTS["ui"], 14, "bold"), anchor="w", justify="left").pack(fill="x")
        tk.Label(wrapper, text=warning, bg=C["panel"], fg=C["muted"], font=(FONTS["ui"], 9),
                 justify="left", anchor="w", wraplength=560).pack(fill="x", pady=(10, 12))
        self.check_vars = []
        for label in (checks or []):
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(wrapper, text=label, variable=var, command=self._update,
                           bg=C["panel"], fg=C["text"], activebackground=C["panel"],
                           activeforeground=C["text"], selectcolor=C["panel2"], font=(FONTS["ui"], 9),
                           anchor="w", justify="left", wraplength=540, highlightthickness=0, bd=0).pack(fill="x", pady=1)
            self.check_vars.append(var)
        tk.Label(wrapper, text=tr("Wpisz %s, aby odblokować:", "Type %s to unlock:") % word,
                 bg=C["panel"], fg=C["muted"], font=(FONTS["ui"], 9), anchor="w").pack(fill="x", pady=(14, 4))
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(wrapper, textvariable=self.entry_var, bg=C["panel2"], fg=C["text"],
                              insertbackground=C["text"], relief="flat", highlightthickness=1,
                              highlightbackground=C["stroke"], highlightcolor=C["accent"],
                              font=(FONTS["mono"], 12), width=18)
        self.entry.pack(fill="x", ipady=6)
        self.entry_var.trace_add("write", lambda *_a: self._update())
        row = tk.Frame(wrapper, bg=C["panel"])
        row.pack(fill="x", pady=(18, 0))
        make_button(row, tr("Anuluj", "Cancel"), self._cancel, "ghost").pack(side="right")
        self.action = make_button(row, action_label, self._confirm, "danger" if danger else "primary")
        self.action.pack(side="right", padx=(0, 8))
        self.action.configure(state="disabled")
        self.bind("<Escape>", lambda _e: self._cancel())
        self.after(60, self._center)
        self.wait_window(self)

    def _center(self):
        try:
            self.update_idletasks()
            parent = self.master
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
            self.geometry("+%d+%d" % (max(0, x), max(0, y)))
        except tk.TclError:
            pass

    def _ready(self):
        return all(v.get() for v in self.check_vars) and self.entry_var.get().strip().upper() == self.word

    def _update(self):
        self.action.configure(state="normal" if self._ready() else "disabled")

    def _confirm(self):
        if not self._ready():
            return
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title(tr("Jak to działa", "How it works"))
        self.configure(bg=C["bg"])
        self.geometry("740x660")
        self.transient(parent)
        wrap = tk.Frame(self, bg=C["bg"], padx=24, pady=20)
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text=tr("Instrukcja i zasady bezpieczeństwa", "Guide and safety rules"),
                 bg=C["bg"], fg=C["text"], font=(FONTS["ui"], 16, "bold"), anchor="w").pack(fill="x")
        holder = tk.Frame(wrap, bg=C["bg"])
        holder.pack(fill="both", expand=True, pady=(12, 0))
        text = tk.Text(holder, bg=C["panel"], fg=C["text"], relief="flat", bd=0, wrap="word",
                       padx=18, pady=16, font=(FONTS["ui"], 9), highlightthickness=1,
                       highlightbackground=C["stroke"], insertbackground=C["text"])
        scroll = ttk.Scrollbar(holder, orient="vertical", command=text.yview, style="Dark.Vertical.TScrollbar")
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        body = tr(
            """PRZEBIEG
1. Podłącz kabel ENET do gniazda OBD2 i do laptopa. Włącz zapłon (tryb diagnostyczny: 3 szybkie kliknięcia START/STOP).
2. Przygotuj komponenty — pobierane są oficjalne repozytoria open source.
3. Kliknij Wykryj VIN. Aplikacja wymaga VIN potwierdzonego przez ENET przed flashem.
4. Zrób kopię kodowania. Aplikacja wymaga udanej kopii odczytowej dla tego VIN. Dodatkowo zrób eksport HU_MGU w BimmerCode.
5. Flash + Enable wykonujesz DOKŁADNIE RAZ na jednostkę. Przed nim przechodzisz listę kontrolną bezpieczeństwa.
6. Zainstaluj MGU Store, zrestartuj jednostkę i sprawdź logowanie SSH.

RYZYKO
Flashowanie obrazu debug czyści kodowanie CAFD, usuwa parowanie BMW Digital Key i w najgorszym przypadku może uszkodzić jednostkę. Nie przerywaj flashowania, nie odłączaj ENET ani zasilania. Samochód musi mieć stabilne napięcie — najlepiej podłącz podtrzymanie 12 V.

CZEGO NIE ROBIĆ
Nie klikaj Flash + Enable drugi raz, jeśli SSH już działa. Ponowny flash nic nie naprawia, a znowu czyści kodowanie. Gdy SSH przestanie odpowiadać, użyj Napraw SSH (enable) — bez flashowania.

PO FLASHU
Jeśli ustawienia wrócą do fabrycznych, przywróć kodowanie z kopii (BimmerCode), a w razie problemów zakoduj HU_MGU ponownie przez E-Sys (VO coding). Nie flashuj ponownie.

ŹRÓDŁA
idrive7-8-ssh-root — aktywacja root SSH (Unlicense)
mgu-store — sklep z aplikacjami (GPL-3.0)
idrive-apps — przykładowe aplikacje

Wszystko wykonujesz na własną odpowiedzialność, tylko na własnym pojeździe.""",
            """PROCESS
1. Connect the ENET cable to the OBD2 port and the laptop. Turn on the ignition (diagnostic mode: press START/STOP 3 times quickly).
2. Prepare the components — the official open-source repositories are downloaded.
3. Click Detect VIN. The app requires a VIN verified over ENET before flashing.
4. Make a coding backup. The app requires a successful read-only backup for this VIN. Also export HU_MGU coding with BimmerCode.
5. Run Flash + Enable EXACTLY ONCE per head unit. You must pass a safety checklist first.
6. Install MGU Store, restart the head unit and verify SSH login.

RISK
Flashing the debug image wipes CAFD coding, deletes BMW Digital Key pairings and in the worst case can brick the head unit. Do not interrupt the flash, do not unplug ENET or power. The car must have stable voltage — connect a 12 V maintainer if possible.

WHAT NOT TO DO
Do not press Flash + Enable a second time if SSH already works. Re-flashing fixes nothing and wipes coding again. If SSH stops answering, use Repair SSH (enable) — no flashing.

AFTER THE FLASH
If settings return to factory defaults, restore the coding from your backup (BimmerCode); if problems remain, recode HU_MGU with E-Sys (VO coding). Do not re-flash.

SOURCES
idrive7-8-ssh-root — root SSH activation (Unlicense)
mgu-store — app store (GPL-3.0)
idrive-apps — example apps

Use at your own risk, only on your own vehicle.""",
        )
        text.insert("1.0", body)
        text.configure(state="disabled")
        make_button(wrap, tr("Zamknij", "Close"), self.destroy, "ghost").pack(anchor="e", pady=(12, 0))


class Task:
    def __init__(self, q):
        self.q = q

    def log(self, text, tag=None):
        self.q.put(("line", str(text), tag))

    def status(self, key, text, kind="muted"):
        self.q.put(("status", key, text, kind))

    def chip(self, name, state):
        self.q.put(("chip", name, state))

    def vin(self, vin, ip):
        self.q.put(("vin", vin, ip))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        _pick_fonts(self)
        config.ensure_dirs()
        self.settings = config.load_settings()
        self.lang = self.settings.get("lang", "pl")
        set_language(self.lang)
        self.q = queue.Queue()
        self.busy = False
        self.components_ready = False
        self.backup_ok = False
        self.flash_ok = False
        self.store_ok = bool(self.settings.get("store_installed"))
        self.identity_folder = None
        self.identity_key = None
        self.is_admin = checks.is_admin()
        self.detected_vin = ""
        self.flash_verify_ok = None
        self.ssh_disabled = False
        self.cards = {}
        self.step_rows = {}
        self.step_kinds = {}
        self.chips = {}
        self.chip_states = {"admin": "ok" if self.is_admin else "err"}
        self.step_keys = ["prepare", "vin", "backup", "flash", "store", "manage"]
        self.active_step = "prepare"
        self.session_log_path = config.LOGS / ("session-%s.log" % time.strftime("%Y%m%d-%H%M%S"))
        try:
            self.session_log = open(self.session_log_path, "a", encoding="utf-8")
        except OSError:
            self.session_log = None
        self.title("%s — %s" % (config.APP_NAME, config.APP_TAGLINE))
        self.geometry("1200x940")
        self.minsize(1080, 780)
        self.configure(bg=C["bg"])
        self._styles()
        self._build()
        self._refresh_enrollment()
        self._restore_state()
        self._refresh_buttons()
        self.after(80, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._startup_checks()
        self._append(tr("MGU Toolkit %s — gotowy.", "MGU Toolkit %s — ready.") % config.VERSION, "title")
        self._append(tr("Obszar roboczy: %s", "Workspace: %s") % config.WORK, "muted")
        if self.session_log_path:
            self._append(tr("Log sesji: %s", "Session log: %s") % self.session_log_path, "muted")
        if not self.is_admin:
            self._append(tr("Brak uprawnień administratora — flash i wykrywanie ENET mogą nie działać.",
                            "Administrator rights missing — flash and ENET detection may fail."), "warn")

    def _styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Dark.TCombobox", fieldbackground=C["panel2"], background=C["panel2"],
                        foreground=C["text"], arrowcolor=C["muted"], bordercolor=C["stroke"],
                        lightcolor=C["panel2"], darkcolor=C["panel2"], padding=6, relief="flat")
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", C["panel2"]), ("disabled", C["panel3"])],
                  foreground=[("disabled", C["muted2"])],
                  selectbackground=[("readonly", C["panel2"])],
                  selectforeground=[("readonly", C["text"])])
        style.configure("Dark.Vertical.TScrollbar", background=C["panel3"], troughcolor=C["bg"],
                        bordercolor=C["bg"], arrowcolor=C["muted"], relief="flat", width=10)
        style.map("Dark.Vertical.TScrollbar", background=[("active", C["stroke"])])
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=C["panel2"], background=C["accent"],
                        bordercolor=C["panel2"], lightcolor=C["accent"], darkcolor=C["accent"])
        self.option_add("*TCombobox*Listbox.background", C["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#06111F")

    def _build(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self._build_header()
        self._build_sidebar()
        self._build_content()
        self._build_log()

    def _build_header(self):
        header = tk.Frame(self, bg=C["bg"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=22, pady=(18, 10))
        left = tk.Frame(header, bg=C["bg"])
        left.pack(side="left")
        logo = tk.Canvas(left, width=42, height=42, bg=C["bg"], highlightthickness=0)
        logo.pack(side="left", padx=(0, 12))
        for i, height in enumerate((14, 26, 20, 32)):
            x = 6 + i * 8
            logo.create_rectangle(x, 36 - height, x + 5, 36, fill=C["accent"], outline="")
        titles = tk.Frame(left, bg=C["bg"])
        titles.pack(side="left")
        tk.Label(titles, text="MGU TOOLKIT", bg=C["bg"], fg=C["text"], font=(FONTS["ui"], 16, "bold")).pack(anchor="w")
        tk.Label(titles, text=config.APP_TAGLINE + "   ·   ROOT SSH & MGU STORE", bg=C["bg"], fg=C["muted2"],
                 font=(FONTS["ui"], 8, "bold")).pack(anchor="w")
        right = tk.Frame(header, bg=C["bg"])
        right.pack(side="right")
        lang_box = tk.Frame(right, bg=C["bg"])
        lang_box.pack(side="left", padx=(0, 14))
        for code in ("pl", "en"):
            active = language() == code
            button = tk.Label(lang_box, text=code.upper(),
                              bg=C["accent"] if active else C["panel2"],
                              fg="#06111F" if active else C["muted"],
                              padx=9, pady=5, font=(FONTS["ui"], 8, "bold"), cursor="hand2",
                              highlightthickness=1,
                              highlightbackground=C["accent"] if active else C["stroke"])
            button.pack(side="left", padx=(0, 4))
            button.bind("<Button-1>", lambda _e, c=code: self._switch_language(c))
        for name, label in (("admin", "ADMIN"), ("ssh", "OPENSSH"), ("internet", "INTERNET"),
                            ("components", tr("KOMPONENTY", "COMPONENTS"))):
            chip = Chip(right, label)
            chip.pack(side="left", padx=(8, 0))
            self.chips[name] = chip
        for name, state in self.chip_states.items():
            if name in self.chips:
                self.chips[name].set(state)

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=C["bg"], width=286)
        sidebar.grid(row=1, column=0, sticky="nsw", padx=(22, 0), pady=(0, 10))
        sidebar.grid_propagate(False)
        tk.Label(sidebar, text=tr("PRZEBIEG", "PROGRESS"), bg=C["bg"], fg=C["muted2"],
                 font=(FONTS["ui"], 8, "bold")).pack(anchor="w", pady=(4, 10))
        steps = [
            ("prepare", tr("Przygotowanie", "Setup")),
            ("vin", tr("Połączenie i VIN", "Connection & VIN")),
            ("backup", tr("Kopia kodowania", "Coding backup")),
            ("flash", tr("Aktywacja SSH", "SSH activation")),
            ("store", "MGU Store"),
            ("manage", tr("Zarządzanie", "Management")),
        ]
        for key, title in steps:
            row = tk.Frame(sidebar, bg=C["bg"])
            row.pack(fill="x", pady=5)
            dot = tk.Canvas(row, width=10, height=10, bg=C["bg"], highlightthickness=0)
            dot.pack(side="left", padx=(2, 10))
            dot.create_oval(1, 1, 9, 9, fill=C["muted2"], outline="", tags="dot")
            label = tk.Label(row, text=title, bg=C["bg"], fg=C["muted"], font=(FONTS["ui"], 9), anchor="w")
            label.pack(side="left")
            for widget in (row, dot, label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, k=key: self._show_step(k))
            self.step_rows[key] = (dot, label, row)
        tk.Frame(sidebar, bg=C["bg"], height=18).pack(fill="x")
        warn = tk.Frame(sidebar, bg=C["danger_soft"], highlightbackground="#3A211B", highlightthickness=1)
        warn.pack(fill="x", pady=(8, 14))
        tk.Label(warn, text=tr("ZANIM ZACZNIESZ", "BEFORE YOU START"), bg=C["danger_soft"], fg=C["err"],
                 font=(FONTS["ui"], 8, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        tk.Label(warn, text=tr(
            "Flashowanie czyści kodowanie CAFD i parowanie Digital Key. Zrób kopię w BimmerCode. Ryzyko uszkodzenia jednostki.",
            "Flashing wipes CAFD coding and Digital Key pairings. Make a BimmerCode backup. Risk of bricking the unit."),
            bg=C["danger_soft"], fg="#D7B8B4", font=(FONTS["ui"], 8), justify="left", anchor="w",
            wraplength=236).pack(fill="x", padx=14, pady=(0, 12))
        links = tk.Frame(sidebar, bg=C["bg"])
        links.pack(fill="x")
        for text, url in ((tr("Repozytorium SSH root", "SSH root repository"), config.SSH_URL),
                          ("MGU Store", config.STORE_URL),
                          (tr("Aplikacje iDrive", "iDrive apps"), config.APPS_URL)):
            make_link(links, text, lambda u=url: webbrowser.open(u), bg=C["bg"]).pack(anchor="w", pady=3)
        tk.Frame(links, bg=C["stroke_soft"], height=1).pack(fill="x", pady=10)
        make_link(links, tr("Otwórz folder danych", "Open data folder"), self._open_data, bg=C["bg"]).pack(anchor="w", pady=3)
        make_link(links, tr("Otwórz folder logów", "Open logs folder"), self._open_logs, bg=C["bg"]).pack(anchor="w", pady=3)
        make_link(links, tr("Instrukcja i bezpieczeństwo", "Guide & safety"),
                  lambda: HelpWindow(self), bg=C["bg"]).pack(anchor="w", pady=3)

    def _build_content(self):
        content = tk.Frame(self, bg=C["bg"])
        content.grid(row=1, column=1, sticky="nsew", padx=(18, 22), pady=(0, 10))
        content.grid_rowconfigure(2, weight=1)
        content.grid_columnconfigure(0, weight=1)
        if not self.is_admin:
            banner = tk.Frame(content, bg=C["danger_soft"], highlightbackground="#3A211B", highlightthickness=1)
            banner.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            tk.Label(banner, text=tr("Wymagane uprawnienia administratora", "Administrator rights required"),
                     bg=C["danger_soft"], fg=C["err"], font=(FONTS["ui"], 10, "bold")).pack(side="left", padx=14, pady=10)
            tk.Label(banner, text=tr("Windows musi widzieć adres 169.254.x.x na kablu ENET.",
                                     "Windows must see a 169.254.x.x address on the ENET adapter."),
                     bg=C["danger_soft"], fg="#D7B8B4", font=(FONTS["ui"], 9)).pack(side="left")
            make_button(banner, tr("Uruchom jako administrator", "Relaunch as administrator"),
                        self._elevate, "danger", small=True).pack(side="right", padx=10, pady=6)
        intro = tk.Frame(content, bg=C["bg"])
        intro.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        tk.Label(intro, text=tr("Od zera do MGU Store", "From zero to MGU Store"), bg=C["bg"], fg=C["text"],
                 font=(FONTS["ui"], 18, "bold")).pack(anchor="w")
        tk.Label(intro, text=tr(
            "Podłącz ENET, włącz zapłon i przechodź kroki przyciskami na dole. Konsola pokazuje pełny przebieg.",
            "Connect ENET, switch on the ignition and move through the steps with the buttons below. The console shows everything."),
            bg=C["bg"], fg=C["muted"], font=(FONTS["ui"], 9)).pack(anchor="w")
        self.step_host = tk.Frame(content, bg=C["bg"])
        self.step_host.grid(row=2, column=0, sticky="new")
        self._build_cards(self.step_host)
        tip = tk.Frame(content, bg=C["accent_soft"], highlightbackground="#1E3A5C", highlightthickness=1)
        tip.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        tk.Frame(tip, bg=C["accent"], width=3).pack(side="left", fill="y")
        tk.Label(tip, text=tr("WSKAZÓWKA", "TIP"), bg=C["accent_soft"], fg=C["accent"],
                 font=(FONTS["ui"], 8, "bold")).pack(side="left", padx=(14, 10), pady=12)
        self.tip_label = tk.Label(tip, text="", bg=C["accent_soft"], fg="#B9CBE0", font=(FONTS["ui"], 9),
                                  anchor="w", justify="left")
        self.tip_label.pack(side="left", fill="x", expand=True, padx=(0, 14), pady=12)
        nav = tk.Frame(content, bg=C["bg"])
        nav.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.step_counter = tk.Label(nav, text="", bg=C["bg"], fg=C["muted2"], font=(FONTS["ui"], 8, "bold"))
        self.step_counter.pack(side="left")
        tk.Label(nav, text=tr("  ·  możesz wrócić do każdego kroku z listy po lewej",
                              "  ·  you can return to any step from the list on the left"),
                 bg=C["bg"], fg=C["muted2"], font=(FONTS["ui"], 8)).pack(side="left")
        self.btn_next = make_button(nav, tr("Dalej", "Next"), lambda: self._navigate(1), "ghost", small=True)
        self.btn_next.pack(side="right")
        self.btn_prev = make_button(nav, tr("Wstecz", "Back"), lambda: self._navigate(-1), "ghost", small=True)
        self.btn_prev.pack(side="right", padx=(0, 8))
        self._show_step("prepare")

    def _build_cards(self, host):
        card = StepCard(host, 1, tr("Przygotuj komponenty", "Prepare the components"),
                        tr("Pobiera repozytorium SSH root, tworzy izolowane środowisko Python i pobiera instalator MGU Store. Wymaga internetu.",
                           "Downloads the SSH root repository, creates an isolated Python environment and fetches the MGU Store installer. Requires internet."),
                        C["accent"])
        tk.Label(card.body, text=tr("Obszar roboczy: %s", "Workspace: %s") % _elide(config.WORK, 82),
                 bg=C["panel"], fg=C["muted2"], font=(FONTS["mono"], 8), anchor="w").pack(fill="x")
        self.btn_prepare = card.add_button(tr("Przygotuj komponenty", "Prepare components"), self.do_prepare, "primary")
        self.cards["prepare"] = card

        card = StepCard(host, 2, tr("Połącz auto i wykryj VIN", "Connect the car and detect the VIN"),
                        tr("Podłącz kabel ENET do OBD2 i laptopa, włącz zapłon. VIN jest zapisywany do jednostki, więc musi być potwierdzony przez ENET.",
                           "Connect the ENET cable to OBD2 and the laptop, switch on the ignition. The VIN is written to the unit, so it must be verified over ENET."))
        vin_row = tk.Frame(card.body, bg=C["panel"])
        vin_row.pack(fill="x")
        tk.Label(vin_row, text="VIN", bg=C["panel"], fg=C["muted"], font=(FONTS["ui"], 9, "bold")).pack(side="left")
        self.vin_var = tk.StringVar(value=self.settings.get("vin", ""))
        self.vin_entry = tk.Entry(vin_row, textvariable=self.vin_var, width=22, bg=C["panel2"], fg=C["text"],
                                  insertbackground=C["text"], relief="flat", highlightthickness=1,
                                  highlightbackground=C["stroke"], highlightcolor=C["accent"],
                                  font=(FONTS["mono"], 11), bd=0)
        self.vin_entry.pack(side="left", padx=(8, 10), ipady=6)
        self.btn_detect = make_button(vin_row, tr("Wykryj VIN", "Detect VIN"), self.do_detect, "ghost")
        self.btn_detect.pack(side="left")
        arch_row = tk.Frame(card.body, bg=C["panel"])
        arch_row.pack(fill="x", pady=(10, 0))
        tk.Label(arch_row, text=tr("Architektura", "Architecture"), bg=C["panel"], fg=C["muted"],
                 font=(FONTS["ui"], 9, "bold")).pack(side="left")
        self.arch_var = tk.StringVar(value=ARCH_LABEL.get(self.settings.get("arch", "id7"), ARCH[0][0]))
        self.arch_box = ttk.Combobox(arch_row, textvariable=self.arch_var, values=[label for label, _v in ARCH],
                                     state="readonly", style="Dark.TCombobox", width=26, font=(FONTS["ui"], 9))
        self.arch_box.pack(side="left", padx=(8, 0))
        self.arch_box.bind("<<ComboboxSelected>>", self._on_arch)
        tk.Label(card.body, text=tr("ID7 jest domyślne. ID8 wybierz tylko, jeśli faktycznie masz iDrive 8.",
                                    "ID7 is the default. Select ID8 only if the car really has iDrive 8."),
                 bg=C["panel"], fg=C["muted2"], font=(FONTS["ui"], 8), anchor="w").pack(fill="x", pady=(8, 0))
        self.vin_var.trace_add("write", lambda *_a: self._on_vin_change())
        self.cards["vin"] = card

        card = StepCard(host, 3, tr("Kopia kodowania", "Coding backup"),
                        tr("Zweryfikowany odczyt kodu MGU przez ENET (tylko UDS 0x22, bez zapisu). Ta kopia jest wymagana przed flashem. BimmerCode nadal zalecany.",
                           "Verified read-only MGU coding read over ENET (UDS 0x22 only, no writes). This backup is required before flashing. BimmerCode is still recommended."))
        tk.Label(card.body, text=tr("Wymagane: udana kopia dla aktualnego VIN. Dodatkowo zrób eksport HU_MGU w BimmerCode.",
                                    "Required: a successful backup for the current VIN. Also export HU_MGU coding with BimmerCode."),
                 bg=C["panel"], fg=C["warn"], font=(FONTS["ui"], 9), anchor="w", wraplength=760).pack(fill="x")
        self.btn_backup = card.add_button(tr("Zrób kopię odczytową", "Make read-only backup"), self.do_backup, "ghost")
        card.add_button(tr("Otwórz folder kopii", "Open backup folder"), self._open_backup, "quiet", small=True)
        self.cards["backup"] = card

        card = StepCard(host, 4, tr("Aktywuj root SSH", "Activate root SSH"),
                        tr("Jednorazowy flash obrazu debug, enrollment i trwałe SSH bez DTC B7F8E5. Po sukcesie nie powtarzaj.",
                           "One-time debug image flash, enrollment and persistent SSH without DTC B7F8E5. Do not repeat after success."),
                        C["err"])
        tk.Label(card.body, text=tr("Flash czyści kodowanie CAFD i parowanie BMW Digital Key. Ryzyko uszkodzenia jednostki. Tylko na własnym aucie.",
                                    "The flash wipes CAFD coding and BMW Digital Key pairings. Risk of bricking the unit. Only on your own car."),
                 bg=C["panel"], fg=C["err"], font=(FONTS["ui"], 9), anchor="w", wraplength=760).pack(fill="x")
        tk.Label(card.body, text=tr("Wymaga uprawnień administratora, VIN potwierdzonego przez ENET i kopii kodowania.",
                                    "Requires administrator rights, an ENET-verified VIN and a coding backup."),
                 bg=C["panel"], fg=C["muted2"], font=(FONTS["ui"], 8), anchor="w").pack(fill="x", pady=(6, 0))
        self.flash_ready = tk.Label(card.body, text="", bg=C["panel"], fg=C["warn"],
                                    font=(FONTS["mono"], 8), anchor="w", justify="left")
        self.flash_ready.pack(fill="x", pady=(6, 0))
        self.btn_flash = card.add_button(tr("Flash + Enable (jednorazowo)", "Flash + Enable (one time)"), self.do_flash, "danger")
        self.cards["flash"] = card

        card = StepCard(host, 5, tr("Zainstaluj MGU Store", "Install MGU Store"),
                        tr("Instaluje Store, updater, deploy tool, renderer i uplink przez SSH z kluczem z poprzedniego kroku. Potem aplikacje instalujesz z ekranu auta.",
                           "Installs the Store, updater, deploy tool, renderer and uplink over SSH with the key from the previous step. Then install apps from the car screen."))
        self.key_label = tk.Label(card.body, text=tr("Klucz: —", "Key: —"), bg=C["panel"], fg=C["muted2"],
                                  font=(FONTS["mono"], 8), anchor="w")
        self.key_label.pack(fill="x")
        self.btn_store = card.add_button(tr("Zainstaluj MGU Store", "Install MGU Store"), self.do_store, "primary")
        self.btn_restart = card.add_button(tr("Restart jednostki", "Restart head unit"), self.do_restart, "ghost")
        self.btn_probe = card.add_button(tr("Sprawdź logowanie SSH", "Test SSH login"), self.do_probe, "quiet", small=True)
        card.add_button(tr("Folder klucza", "Key folder"), self._open_identity, "quiet", small=True)
        self.cards["store"] = card

        card = StepCard(host, 6, tr("Zarządzanie i diagnostyka", "Management & diagnostics"),
                        tr("Status jednostki, naprawa SSH bez flashowania, wyłączenie trwałego dostępu. Wyłączenie SSH nie usuwa Store ani aplikacji.",
                           "Unit status, SSH repair without flashing, disable persistent access. Disabling SSH does not remove the Store or apps."),
                        C["muted"])
        self.btn_status = card.add_button(tr("Status jednostki", "Unit status"), self.do_status, "ghost")
        self.btn_enable = card.add_button(tr("Napraw SSH (enable)", "Repair SSH (enable)"), self.do_enable, "ghost")
        self.btn_disable = card.add_button(tr("Wyłącz SSH", "Disable SSH"), self.do_disable, "ghost")
        card.add_button(tr("Otwórz folder danych", "Open data folder"), self._open_data, "quiet", small=True)
        row = tk.Frame(card.body, bg=C["panel"])
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text=tr("Logowanie odrzucone mimo otwartego portu 22?", "Login refused although port 22 is open?"),
                 bg=C["panel"], fg=C["muted2"], font=(FONTS["ui"], 8)).pack(side="left")
        self.btn_fix = make_button(row, tr("Napraw klucz (fix-key)", "Fix key (fix-key)"), self.do_fix, "quiet", small=True)
        self.btn_fix.pack(side="left", padx=(8, 0))
        self.cards["manage"] = card

    def _build_log(self):
        panel = tk.Frame(self, bg=C["panel"], highlightbackground=C["stroke"], highlightthickness=1, bd=0)
        panel.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(0, 18))
        head = tk.Frame(panel, bg=C["panel"])
        head.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(head, text=tr("KONSOLA", "CONSOLE"), bg=C["panel"], fg=C["muted2"],
                 font=(FONTS["ui"], 8, "bold")).pack(side="left")
        self.run_label = tk.Label(head, text=tr("GOTOWE", "READY"), bg=C["panel"], fg=C["muted2"],
                                  font=(FONTS["ui"], 8, "bold"))
        self.run_label.pack(side="left", padx=(12, 8))
        self.progress = ttk.Progressbar(head, mode="indeterminate", style="Accent.Horizontal.TProgressbar", length=120)
        self.progress.pack(side="left")
        make_button(head, tr("Kopiuj", "Copy"), self._copy_log, "quiet", small=True).pack(side="right")
        make_button(head, tr("Folder logów", "Logs folder"), self._open_logs, "quiet", small=True).pack(side="right", padx=(0, 6))
        make_button(head, tr("Wyczyść", "Clear"), self._clear_log, "quiet", small=True).pack(side="right", padx=(0, 6))
        body = tk.Frame(panel, bg="#070A0D")
        body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.log_text = tk.Text(body, height=9, bg="#070A0D", fg="#C7D2E0", insertbackground=C["text"],
                                relief="flat", bd=0, padx=14, pady=10, wrap="word",
                                font=(FONTS["mono"], 9), highlightthickness=0, state="disabled")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.log_text.yview, style="Dark.Vertical.TScrollbar")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.log_text.tag_configure("ok", foreground=C["ok"])
        self.log_text.tag_configure("err", foreground=C["err"])
        self.log_text.tag_configure("warn", foreground=C["warn"])
        self.log_text.tag_configure("muted", foreground=C["muted2"])
        self.log_text.tag_configure("cmd", foreground=C["accent"])
        self.log_text.tag_configure("title", foreground=C["text"], font=(FONTS["mono"], 9, "bold"))

    def _session_write(self, text):
        if self.session_log is None:
            return
        try:
            self.session_log.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), text))
            self.session_log.flush()
        except OSError:
            pass

    def _restore_state(self):
        self.components_ready = checks.components()
        self.chip_states["components"] = "ok" if self.components_ready else "muted"
        self.chips["components"].set(self.chip_states["components"])
        if self.components_ready:
            self.cards["prepare"].set_state(tr("Gotowe", "Ready"), "ok")
            self._set_step_row("prepare", "ok")
        self._on_arch()
        self._on_vin_change(initial=True)
        if self.components_ready and self.flash_ok:
            self._show_step("store")
        elif self.components_ready:
            self._show_step("vin")

    def _startup_checks(self):
        def work():
            ok, _version = checks.ssh_client()
            self.q.put(("chip", "ssh", "ok" if ok else "err"))
            self.q.put(("chip", "internet", "ok" if checks.internet() else "err"))
        threading.Thread(target=work, daemon=True).start()

    def _append(self, text, tag=None):
        self._session_write(text)
        self.log_text.configure(state="normal")
        if self.log_text.index("end-1c") != "1.0":
            self.log_text.insert("end", "\n")
        self.log_text.insert("end", text, tag if tag else ())
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _drain(self):
        try:
            while True:
                event = self.q.get_nowait()
                kind = event[0]
                if kind == "line":
                    self._append(event[1], event[2])
                elif kind == "status":
                    self._set_status(event[1], event[2], event[3])
                elif kind == "chip":
                    self.chip_states[event[1]] = event[2]
                    if event[1] in self.chips:
                        self.chips[event[1]].set(event[2])
                elif kind == "vin":
                    self._apply_vin(event[1], event[2])
                elif kind == "done":
                    self._finish(event[1], event[2])
        except queue.Empty:
            pass
        self.after(70, self._drain)

    def _set_status(self, key, text, kind):
        card = self.cards.get(key)
        if card is not None:
            card.set_state(text, kind)
        self._set_step_row(key, kind)

    def _set_step_row(self, key, kind):
        row = self.step_rows.get(key)
        if row is None:
            return
        self.step_kinds[key] = kind
        dot, label = row[0], row[1]
        color = {"ok": C["ok"], "err": C["err"], "warn": C["warn"], "busy": C["accent"], "muted": C["muted2"]}.get(kind, C["muted2"])
        dot.delete("dot")
        dot.create_oval(1, 1, 9, 9, fill=color, outline="", tags="dot")
        active = key == self.active_step
        label.configure(fg=C["accent"] if active else (C["text"] if kind in ("ok", "err", "warn", "busy") else C["muted"]),
                        font=(FONTS["ui"], 9, "bold" if active else "normal"))

    def _show_step(self, key):
        if key not in self.cards:
            return
        self.active_step = key
        for name, card in self.cards.items():
            if name == key:
                card.pack(fill="x", anchor="n")
            else:
                card.pack_forget()
        for name in self.step_keys:
            self._set_step_row(name, self.step_kinds.get(name, "muted"))
        tips = {
            "prepare": tr("Pierwsze uruchomienie pobiera repozytorium i tworzy środowisko Python (ok. 10–20 MB).",
                          "The first run downloads the repository and creates the Python environment (about 10–20 MB)."),
            "vin": tr("Tryb diagnostyczny: 3 szybkie kliknięcia START/STOP. Na Windows uruchom aplikację jako administrator.",
                      "Diagnostic mode: press START/STOP 3 times quickly. On Windows run the app as administrator."),
            "backup": tr("Odczyt jest bezpieczny: tylko UDS 0x22, bez zapisu. Kopia jest wymagana przed flashem.",
                         "The read is safe: UDS 0x22 only, no writes. The backup is required before flashing."),
            "flash": tr("Nie odłączaj ENET ani zasilania. Flash wykonujesz dokładnie raz na jednostkę.",
                        "Do not unplug ENET or power. Flash exactly once per head unit."),
            "store": tr("Po instalacji zrestartuj MGU. Źródło robertnisipeanu/idrive-apps jest domyślne; jeśli go brak, dodaj w Store → Settings → Add source.",
                        "Restart the head unit after installation. robertnisipeanu/idrive-apps is a default source; if missing, add it in Store → Settings → Add source."),
            "manage": tr("Wyłączenie SSH nie usuwa MGU Store ani aplikacji. Dostęp włączysz ponownie przez Napraw SSH.",
                         "Disabling SSH does not remove MGU Store or apps. Re-enable access with Repair SSH."),
        }
        self.tip_label.configure(text=tips.get(key, ""))
        index = self.step_keys.index(key)
        self.step_counter.configure(text=tr("KROK %d / %d", "STEP %d / %d") % (index + 1, len(self.step_keys)))
        self.btn_prev.configure(state="normal" if index > 0 else "disabled")
        self.btn_next.configure(state="normal" if index < len(self.step_keys) - 1 else "disabled")

    def _navigate(self, delta):
        index = self.step_keys.index(self.active_step)
        index = max(0, min(len(self.step_keys) - 1, index + delta))
        self._show_step(self.step_keys[index])

    def _switch_language(self, code):
        if code == language():
            return
        if self.busy:
            messagebox.showwarning(
                tr("Nie zmieniaj języka", "Language change blocked"),
                tr("Trwa operacja. Zmiana języka będzie możliwa po jej zakończeniu.",
                   "An operation is running. You can change the language when it finishes."),
            )
            return
        try:
            old_log = self.log_text.get("1.0", "end-1c")
        except tk.TclError:
            old_log = ""
        active = self.active_step
        kinds = dict(self.step_kinds)
        self.settings["lang"] = code
        config.save_settings(self.settings)
        set_language(code)
        self.lang = code
        self._rebuild_ui(old_log, active, kinds)

    def _rebuild_ui(self, old_log, active, kinds):
        for widget in self.winfo_children():
            widget.destroy()
        self.cards.clear()
        self.step_rows.clear()
        self.step_kinds.clear()
        self.chips.clear()
        self._styles()
        self._build()
        self._refresh_enrollment()
        self._restore_state()
        self._refresh_buttons()
        if old_log:
            self.log_text.configure(state="normal")
            self.log_text.insert("1.0", old_log)
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        self._append(tr("— język: polski —", "— language: English —"), "muted")
        self._show_step(active if active in self.cards else "prepare")
        for key, kind in kinds.items():
            self._set_step_row(key, kind)

    def _py(self):
        py = config.venv_python()
        return py if py.exists() else None

    def _need_py(self):
        py = self._py()
        if py is None:
            messagebox.showerror("Python", tr(
                "Środowisko Python nie jest gotowe. Uruchom krok 1 (Przygotuj komponenty).",
                "The Python environment is not ready. Run step 1 (Prepare components)."))
        return py

    def _vin(self):
        return self.vin_var.get().strip().upper()

    def _vin_valid(self):
        return re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", self._vin()) is not None

    def _arch(self):
        return ARCH_BY_LABEL.get(self.arch_var.get(), "id7")

    def _log_path(self, label):
        config.ensure_dirs()
        return config.LOGS / ("%s-%s.log" % (time.strftime("%Y%m%d-%H%M%S"), label))

    def _on_arch(self, _event=None):
        self.settings["arch"] = self._arch()
        config.save_settings(self.settings)

    def _apply_vin(self, vin, ip):
        if ip:
            self.settings["gateway"] = ip
        if vin:
            self.detected_vin = vin.strip().upper()
            self.vin_var.set(vin)
        else:
            self.detected_vin = ""
            self._on_vin_change()

    def _refresh_backup_state(self):
        vin = self._vin()
        last = self.settings.get("last_backup") or ""
        bvin = self.settings.get("backup_vin") or ""
        folder = Path(last) if last else None
        complete = bool(folder and folder.exists()
                        and (folder / "SHA256SUMS").exists()
                        and (folder / "coding_MGU.txt").exists())
        self.backup_ok = bool(vin and bvin == vin and complete)

    def _on_vin_change(self, initial=False):
        self.settings["vin"] = self._vin()
        config.save_settings(self.settings)
        vin = self._vin()
        if not vin:
            self.cards["vin"].set_state(tr("Wpisz lub wykryj VIN", "Enter or detect the VIN"), "muted")
        elif not self._vin_valid():
            self.cards["vin"].set_state(tr("VIN: 17 znaków, bez I/O/Q", "VIN: 17 characters, no I/O/Q"), "warn")
        elif vin == self.detected_vin:
            self.cards["vin"].set_state(tr("VIN potwierdzony przez ENET", "VIN verified over ENET"), "ok")
        else:
            self.cards["vin"].set_state(tr("Kliknij Wykryj VIN, aby potwierdzić", "Click Detect VIN to verify"), "warn")
        self._refresh_backup_state()
        if not self._vin_valid():
            self.cards["backup"].set_state(tr("Najpierw potwierdź VIN", "Verify the VIN first"), "muted")
        elif self.backup_ok:
            self.cards["backup"].set_state(tr("Kopia dla tego VIN zapisana", "Backup saved for this VIN"), "ok")
        else:
            self.cards["backup"].set_state(tr("Wymagana kopia dla tego VIN", "Coding backup required for this VIN"), "warn")
        self._refresh_enrollment()
        self._refresh_buttons()

    def _refresh_enrollment(self):
        vin = self._vin()
        folder, key = repos.identity_for(vin)
        matches = key is not None and (not vin or folder.name == vin)
        self.identity_folder = folder if matches else None
        self.identity_key = key if matches else None
        self.flash_ok = self.identity_key is not None
        ever_flashed = bool(vin) and vin in self.settings.get("flashed_vins", [])
        if self.identity_key is not None:
            self.key_label.configure(text=tr("Klucz: %s", "Key: %s") % _elide(self.identity_key, 82))
            if not self.busy:
                self.cards["flash"].set_state(tr("Flash wykonany — klucz zapisany", "Flashed — key saved"), "ok")
                if self.ssh_disabled:
                    self.cards["store"].set_state(tr("SSH wyłączone — użyj Napraw SSH", "SSH disabled — use Repair SSH"), "warn")
                elif self.flash_verify_ok is False:
                    self.cards["flash"].set_state(tr("Flash OK — SSH niezweryfikowane", "Flash OK — SSH not verified"), "warn")
                    self.cards["store"].set_state(tr("Nie instaluj — najpierw fix-key", "Do not install — run fix-key first"), "warn")
                else:
                    self.cards["store"].set_state(tr("Gotowe do instalacji", "Ready to install"), "ok")
        elif ever_flashed:
            self.key_label.configure(text=tr("Klucz: — (ten VIN był już flashowany)", "Key: — (this VIN was already flashed)"))
            if not self.busy:
                if self.flash_verify_ok is False:
                    self.cards["flash"].set_state(tr("Flash OK — SSH niezweryfikowane", "Flash OK — SSH not verified"), "warn")
                    self.cards["store"].set_state(tr("Nie instaluj — najpierw fix-key", "Do not install — run fix-key first"), "warn")
                else:
                    self.cards["flash"].set_state(tr("Ten VIN był już flashowany — użyj Napraw SSH", "This VIN was already flashed — use Repair SSH"), "warn")
                    self.cards["store"].set_state(tr("Brak klucza — użyj Napraw SSH", "No key — use Repair SSH"), "warn")
        else:
            self.key_label.configure(text=tr("Klucz: — (najpierw aktywuj SSH)", "Key: — (activate SSH first)"))
            if not self.busy:
                self.cards["store"].set_state(tr("Czeka na klucz SSH", "Waiting for the SSH key"), "muted")

    def _flash_gates(self):
        vin = self._vin()
        return [
            ("VIN", bool(vin) and self.detected_vin == vin),
            (tr("kopia", "backup"), self.backup_ok),
            ("admin", self.is_admin),
            (tr("komponenty", "components"), self.components_ready),
        ]

    def _flash_gate_reason(self):
        vin = self._vin()
        if self.flash_ok:
            return tr("Root SSH jest już aktywne. Nie flashuj ponownie.", "Root SSH is already active. Do not flash again.")
        if not self.components_ready:
            return tr("Najpierw przygotuj komponenty (krok 1).", "Prepare the components first (step 1).")
        if not self.is_admin:
            return tr("Flash wymaga uprawnień administratora.", "Flashing requires administrator rights.")
        if not self._vin_valid():
            return tr("VIN musi mieć 17 znaków (bez I, O, Q).", "The VIN must be 17 characters (no I, O, Q).")
        if self.detected_vin != vin:
            return tr("Kliknij Wykryj VIN, aby potwierdzić VIN odczytany z auta.",
                      "Click Detect VIN to verify the VIN read from the car.")
        if vin in self.settings.get("flashed_vins", []):
            return tr("Ten VIN był już flashowany. Użyj Napraw SSH (enable).",
                      "This VIN has already been flashed. Use Repair SSH (enable).")
        if not self.backup_ok:
            return tr("Najpierw wykonaj kopię odczytową dla tego VIN (krok 3).",
                      "First make a read-only coding backup for this VIN (step 3).")
        return ""

    def _update_flash_ready(self):
        if not hasattr(self, "flash_ready"):
            return
        if self.flash_ok:
            if self.flash_verify_ok is False:
                self.flash_ready.configure(text=tr("Flash wykonany — brak weryfikacji SSH. Użyj fix-key.",
                                                  "Flashed — SSH not verified. Use fix-key."), fg=C["warn"])
            else:
                self.flash_ready.configure(text=tr("Flash wykonany — nie powtarzaj.", "Flashed — do not repeat."), fg=C["ok"])
            return
        gates = self._flash_gates()
        ready = all(value for _name, value in gates)
        text = tr("Gotowość: ", "Readiness: ") + " · ".join(
            ("%s: OK" % name) if value else ("%s: —" % name) for name, value in gates
        )
        self.flash_ready.configure(text=text, fg=C["ok"] if ready else C["warn"])

    def _refresh_buttons(self):
        busy = self.busy
        vin = self._vin()
        blocked = bool(vin) and vin in self.settings.get("flashed_vins", [])
        can_flash = self._flash_gate_reason() == "" and not busy
        self.btn_prepare.configure(state="disabled" if busy else "normal")
        self.btn_detect.configure(state="disabled" if (busy or not self.components_ready) else "normal")
        self.btn_backup.configure(state="normal" if (not busy and self.components_ready and self.is_admin and self._vin_valid()) else "disabled")
        self.btn_flash.configure(state="normal" if can_flash else "disabled")
        if self.flash_ok:
            self.btn_flash.configure(text=tr("SSH już aktywne — nie flashuj", "SSH already active — do not flash"))
        elif blocked:
            self.btn_flash.configure(text=tr("Ten VIN był już flashowany", "This VIN was already flashed"))
        else:
            self.btn_flash.configure(text=tr("Flash + Enable (jednorazowo)", "Flash + Enable (one time)"))
        has_key = self.identity_key is not None
        store_ready = has_key and not self.ssh_disabled and self.flash_verify_ok is not False
        self.btn_store.configure(state="normal" if (not busy and store_ready) else "disabled")
        self.btn_restart.configure(state="normal" if (not busy and has_key) else "disabled")
        self.btn_probe.configure(state="normal" if (not busy and has_key) else "disabled")
        manage_ready = self.components_ready and self.is_admin and not busy
        self.btn_status.configure(state="normal" if manage_ready else "disabled")
        self.btn_enable.configure(state="normal" if manage_ready else "disabled")
        self.btn_disable.configure(state="normal" if manage_ready else "disabled")
        self.btn_fix.configure(state="normal" if (manage_ready and self._vin_valid()) else "disabled")
        self.vin_entry.configure(state="disabled" if busy else "normal")
        self.arch_box.configure(state="disabled" if busy else "readonly")
        self._update_flash_ready()

    def _set_busy(self, on):
        self.busy = on
        if on:
            self.run_label.configure(text=tr("PRACUJE", "WORKING"), fg=C["accent"])
            self.progress.start(14)
        else:
            self.run_label.configure(text=tr("GOTOWE", "READY"), fg=C["muted2"])
            self.progress.stop()
        self._refresh_buttons()

    def _start(self, key, target):
        if self.busy:
            messagebox.showinfo(tr("Trwa operacja", "Operation in progress"),
                                tr("Poczekaj, aż bieżące zadanie się zakończy.", "Wait for the current task to finish."))
            return
        self._set_busy(True)
        self._set_status(key, tr("Pracuję...", "Working..."), "busy")
        task = Task(self.q)

        def worker():
            code = 1
            try:
                code = target(task) or 0
            except Exception as exc:
                task.log(tr("Błąd: %s", "Error: %s") % exc, "err")
                code = 1
            self.q.put(("done", key, code))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, key, code):
        self._set_busy(False)
        if code == 0:
            self._append(tr("Zadanie zakończone pomyślnie.", "Task completed successfully."), "ok")
            if key == "prepare":
                self.components_ready = True
                self.chip_states["components"] = "ok"
                self.chips["components"].set("ok")
                self.cards["prepare"].set_state(tr("Gotowe — przejdź do kroku 2", "Ready — continue to step 2"), "ok")
            elif key == "backup":
                self._refresh_backup_state()
                if self.backup_ok:
                    self.cards["backup"].set_state(tr("Kopia zapisana — możesz flashować", "Backup saved — ready to flash"), "ok")
                else:
                    self.cards["backup"].set_state(tr("Kopia nie pasuje do VIN", "Backup does not match the VIN"), "warn")
            elif key == "flash":
                self.flash_ok = True
                self.ssh_disabled = False
                vin = self._vin()
                flashed = self.settings.setdefault("flashed_vins", [])
                if vin and vin not in flashed:
                    flashed.append(vin)
                config.save_settings(self.settings)
                self._refresh_enrollment()
                if self.flash_verify_ok is False:
                    self.cards["flash"].set_state(tr("Flash OK — SSH niezweryfikowane", "Flash OK — SSH not verified"), "warn")
                else:
                    self.cards["flash"].set_state(tr("SSH aktywne — przejdź do MGU Store", "SSH active — continue to MGU Store"), "ok")
            elif key == "store":
                self.store_ok = True
                self.settings["store_installed"] = True
                config.save_settings(self.settings)
                self.cards["store"].set_state(tr("Zainstalowany — zrestartuj MGU", "Installed — restart the head unit"), "ok")
            if key == "prepare" and self.active_step == "prepare":
                self.after(350, lambda: self._show_step("vin"))
        else:
            self._append(tr("Zadanie zakończone kodem %s — sprawdź konsolę.", "Task ended with code %s — check the console.") % code, "err")
            if self.step_kinds.get(key) == "busy":
                self.cards[key].set_state(tr("Błąd — sprawdź konsolę", "Error — check the console"), "err")
        if key in ("flash", "manage"):
            self._refresh_enrollment()
        self._refresh_buttons()
        if code == 0 and key == "flash":
            self._flash_success()
        elif code == 0 and key == "store":
            self._store_success()

    def _flash_success(self):
        if self.flash_verify_ok is False:
            messagebox.showwarning(
                tr("Flash OK — brak weryfikacji SSH", "Flash OK — SSH not verified"),
                tr("Jednostka została sflaszowana, ale test logowania SSH nie powiódł się.\n\n"
                   "Nie instaluj MGU Store. Użyj „Napraw klucz (fix-key)” w kroku 6, a potem sprawdź logowanie SSH.\n\n"
                   "Jeśli problem jest tylko z adresem IP, ponownie odczytaj status jednostki.",
                   "The head unit was flashed, but the SSH login test failed.\n\n"
                   "Do not install MGU Store. Use “Fix key (fix-key)” in step 6, then test SSH login again.\n\n"
                   "If only the IP address is stale, read the unit status again."),
            )
            return
        folder = self.identity_folder
        messagebox.showinfo(
            tr("Root SSH aktywne", "Root SSH active"),
            tr("Jednostka została sflaszowana, a root SSH jest aktywne i zweryfikowane.\n\n"
               "Klucz i dane połączenia:\n%s\n\n"
               "Następny krok: zainstaluj MGU Store.\n"
               "Nie powtarzaj flashowania. Jeśli ustawienia wrócą do fabrycznych, przywróć kodowanie z kopii.",
               "The head unit was flashed and root SSH is active and verified.\n\n"
               "Key and connection details:\n%s\n\n"
               "Next step: install MGU Store.\n"
               "Do not flash again. If settings return to factory defaults, restore the coding from your backup.")
            % (folder if folder else "data/enrollments/<VIN>"),
        )
        if self.active_step == "flash":
            self._show_step("store")

    def _store_success(self):
        messagebox.showinfo(
            tr("MGU Store zainstalowany", "MGU Store installed"),
            tr("Instalacja zakończona. Zrestartuj jednostkę, aby kafelek MGU Store pojawił się w menu.\n\n"
               "Użyj przycisku „Restart jednostki” w kroku 5 albo przytrzymaj pokrętło głośności ok. 25 s.\n\n"
               "Potem otwórz MGU Store. Źródło robertnisipeanu/idrive-apps jest domyślne; jeśli go brak, "
               "dodaj je w Settings → Add source.",
               "Installation complete. Restart the head unit so the MGU Store tile appears in the menu.\n\n"
               "Use “Restart head unit” in step 5 or hold the volume knob for about 25 s.\n\n"
               "Then open MGU Store. robertnisipeanu/idrive-apps is a default source; if it is missing, "
               "add it in Settings → Add source."),
        )

    def do_prepare(self):
        if not checks.python_ok():
            messagebox.showerror("Python", tr("Wymagany Python 3.9 lub nowszy.", "Python 3.9 or newer is required."))
            return
        self.cards["prepare"].set_state(tr("Pracuję...", "Working..."), "busy")

        def task(t):
            repos.ensure_repo(t.log)
            py = repos.ensure_venv(t.log)
            repos.install_requirements(py, t.log)
            repos.ensure_store_installer(t.log)
            repos.write_helpers(t.log)
            t.chip("components", "ok")
            t.status("prepare", tr("Komponenty gotowe", "Components ready"), "ok")
            return 0

        self._start("prepare", task)

    def do_detect(self):
        if not self.components_ready:
            messagebox.showinfo(tr("Najpierw komponenty", "Components first"),
                                tr("Kliknij „Przygotuj komponenty”.", "Click “Prepare components”."))
            return
        py = self._need_py()
        if py is None:
            return

        def task(t):
            t.status("vin", tr("Skanuję ENET...", "Scanning ENET..."), "busy")
            result = repos.detect_vin(py, t.log)
            if result.get("ok"):
                t.vin(result.get("vin", ""), result.get("ip", ""))
                if result.get("vin"):
                    t.status("vin", tr("VIN wykryty", "VIN detected"), "ok")
                else:
                    t.status("vin", tr("Bramka wykryta, brak VIN", "Gateway found, no VIN"), "warn")
                return 0
            t.status("vin", tr("Brak bramki ENET", "No ENET gateway"), "err")
            return 1

        self._start("vin", task)

    def do_backup(self):
        if not self.components_ready:
            messagebox.showinfo(tr("Najpierw komponenty", "Components first"),
                                tr("Kliknij „Przygotuj komponenty”.", "Click “Prepare components”."))
            return
        if not self.is_admin:
            messagebox.showwarning("Administrator", tr("Uruchom aplikację jako administrator.", "Run the app as administrator."))
            return
        if not self._vin_valid():
            messagebox.showerror(tr("VIN", "VIN"),
                                 tr("Najpierw wykryj lub wpisz poprawny VIN (krok 2).", "Detect or enter a valid VIN first (step 2)."))
            return
        py = self._need_py()
        if py is None:
            return
        vin = self._vin()

        def task(t):
            t.status("backup", tr("Odczytuję kodowanie...", "Reading coding..."), "busy")
            argv = [py, "ssh_enable.py", "preflight", "--vin", vin, "--log", str(self._log_path("preflight"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            if code == 0:
                folder = repos.latest_preflight()
                if folder is not None:
                    self.settings["last_backup"] = str(folder)
                    self.settings["backup_vin"] = vin
                    config.save_settings(self.settings)
                    t.log(tr("Kopia: %s", "Backup: %s") % folder, "ok")
                t.status("backup", tr("Kopia zapisana", "Backup saved"), "ok")
            else:
                t.status("backup", tr("Niepowodzenie", "Failed"), "err")
            return code

        self._start("backup", task)

    def _safety_checks(self, arch):
        items = [
            tr("Samochód zaparkowany, zapłon włączony, jednostka MGU wybudzona.",
               "Car parked, ignition on, MGU head unit awake."),
            tr("Akumulator ma stabilne napięcie; podłączone podtrzymanie 12 V.",
               "Battery voltage is stable; a 12 V maintainer is connected."),
            tr("Mam pełną kopię kodowania HU_MGU (BimmerCode / E-Sys).",
               "I have a full HU_MGU coding backup (BimmerCode / E-Sys)."),
            tr("Kabel ENET jest podłączony pewnie i nie odłączę go podczas operacji.",
               "The ENET cable is firmly connected and will not be unplugged."),
            tr("Rozumiem, że flash czyści CAFD i Digital Key i może uszkodzić jednostkę.",
               "I understand the flash wipes CAFD and Digital Key and can brick the unit."),
        ]
        if arch != "id7":
            items.append(tr("Wybrana architektura ID8 jest poprawna dla tego auta.",
                            "The selected ID8 architecture is correct for this car."))
        return items

    def do_flash(self):
        reason = self._flash_gate_reason()
        if reason:
            messagebox.showwarning(tr("Nie można flashować", "Cannot flash"), reason)
            return
        py = self._need_py()
        if py is None:
            return
        vin = self._vin()
        arch = self._arch()
        arch_label = self.arch_var.get()
        arch_warning = ""
        if arch != "id7":
            arch_warning = tr("\nUWAGA: wybrano %s. Flash niewłaściwą architekturą może uszkodzić jednostkę.\n",
                              "\nWARNING: %s selected. Flashing the wrong architecture can brick the unit.\n") % arch_label
        word = "FLASH" if arch == "id7" else "FLASH-ID8"
        warning = tr(
            "Architektura: %s.%s\n\n"
            "Flash + Enable zapisuje VIN %s do jednostki MGU, przełącza ją w tryb programowania i restartuje.\n\n"
            "• Kodowanie CAFD zostanie wyczyszczone.\n"
            "• Parowanie BMW Digital Key zostanie usunięte.\n"
            "• W najgorszym przypadku jednostka może zostać uszkodzona.\n"
            "• Operacja trwa zwykle 20–30 minut. Nie odłączaj ENET ani zasilania.\n\n"
            "Wykonaj to tylko raz. Klucz zostanie zapisany w data/enrollments/%s.",
            "Architecture: %s.%s\n\n"
            "Flash + Enable writes VIN %s to the MGU head unit, switches it into programming mode and reboots it.\n\n"
            "• CAFD coding will be wiped.\n"
            "• BMW Digital Key pairings will be deleted.\n"
            "• In the worst case the head unit can be bricked.\n"
            "• The operation usually takes 20–30 minutes. Do not unplug ENET or power.\n\n"
            "Do this only once. The key will be saved in data/enrollments/%s.",
        ) % (arch_label, arch_warning, vin, vin)
        dialog = TypedConfirm(self, tr("Potwierdź flashowanie", "Confirm flashing"),
                              "Flash + Enable", warning, word,
                              tr("Flash + Enable", "Flash + Enable"),
                              checks=self._safety_checks(arch))
        if not dialog.result:
            self._session_write(tr("Flash anulowany przez użytkownika.", "Flash cancelled by the user."))
            return
        self._session_write(tr("Flash zatwierdzony: VIN=%s arch=%s", "Flash approved: VIN=%s arch=%s") % (vin, arch))

        def task(t):
            t.status("flash", tr("Flashowanie...", "Flashing..."), "busy")
            argv = [py, "ssh_enable.py", "flash", "--vin", vin, "--persist", "--yes",
                    "--arch", arch, "--log", str(self._log_path("flash"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            if code == 0:
                self.settings["vin"] = vin
                config.save_settings(self.settings)
                folder, key = repos.identity_for(vin)
                self.flash_verify_ok = False
                if key is not None:
                    t.log(tr("Weryfikuję logowanie SSH nowym kluczem...", "Verifying SSH login with the new key..."), "muted")
                    self.flash_verify_ok = repos.probe_login(py, folder, t.log) == 0
                if self.flash_verify_ok:
                    t.status("flash", tr("SSH aktywne i zweryfikowane", "SSH active and verified"), "ok")
                else:
                    t.log(tr("UWAGA: flash OK, ale logowanie SSH nie zostało potwierdzone. Użyj fix-key.",
                             "WARNING: flash OK, but SSH login was not verified. Use fix-key."), "warn")
                    t.status("flash", tr("Flash OK — SSH niezweryfikowane", "Flash OK — SSH not verified"), "warn")
            else:
                t.status("flash", tr("Flash nieudany", "Flash failed"), "err")
            return code

        self._start("flash", task)

    def do_store(self):
        folder, key = repos.identity_for(self._vin())
        if key is None:
            messagebox.showerror(tr("Brak klucza", "No key"),
                                 tr("Najpierw aktywuj root SSH (krok 4).", "Activate root SSH first (step 4)."))
            return
        if self.ssh_disabled:
            messagebox.showwarning(tr("SSH wyłączone", "SSH disabled"),
                                   tr("SSH jest wyłączone. Użyj Napraw SSH (enable), a potem sprawdź logowanie przed instalacją.",
                                      "SSH is disabled. Use Repair SSH (enable), then test the login before installing."))
            return
        if self.flash_verify_ok is False:
            messagebox.showwarning(tr("SSH niezweryfikowane", "SSH not verified"),
                                   tr("Logowanie SSH nie zostało potwierdzone. Użyj fix-key i sprawdź logowanie przed instalacją.",
                                      "SSH login was not verified. Use fix-key and test the login before installing."))
            return
        py = self._need_py()
        if py is None:
            return
        if not messagebox.askyesno(tr("MGU Store", "MGU Store"),
                                   tr("Zainstalować MGU Store przez SSH?\n\nAuto musi być włączone, a jednostka osiągalna. Nie odłączaj zasilania.",
                                      "Install MGU Store over SSH?\n\nThe car must be on and the unit reachable. Do not disconnect power.")):
            return

        def task(t):
            t.status("store", tr("Instaluję MGU Store...", "Installing MGU Store..."), "busy")
            installer = repos.ensure_store_installer(t.log)
            if config.IS_WINDOWS:
                argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer),
                        "first-install", "--identity", str(key), "--no-restart-prompt"]
            else:
                argv = ["sh", str(installer), "first-install", "--identity", str(key), "--no-restart-prompt"]
            code = run_lines(argv, t.log)
            if code == 0:
                t.status("store", tr("Zainstalowany", "Installed"), "ok")
            else:
                t.status("store", tr("Instalacja nieudana", "Installation failed"), "err")
            return code

        self._start("store", task)

    def do_restart(self):
        folder, key = repos.identity_for(self._vin())
        if key is None:
            messagebox.showerror(tr("Brak klucza", "No key"), tr("Najpierw aktywuj root SSH.", "Activate root SSH first."))
            return
        py = self._need_py()
        if py is None:
            return
        if not messagebox.askyesno(tr("Restart jednostki", "Restart head unit"),
                                   tr("Zrestartować jednostkę MGU teraz?\n\nEkran iDrive zgaśnie na chwilę. Auto musi być włączone.",
                                      "Restart the MGU head unit now?\n\nThe iDrive screen will go dark briefly. The car must be on.")):
            return

        def task(t):
            t.status("store", tr("Restartuję...", "Restarting..."), "busy")
            code = repos.restart_unit(py, folder, t.log)
            if code == 0:
                t.status("store", tr("Restart wysłany", "Restart sent"), "ok")
            else:
                t.status("store", tr("Restart niepotwierdzony", "Restart not confirmed"), "warn")
            return code

        self._start("store", task)

    def do_probe(self):
        folder, key = repos.identity_for(self._vin())
        if key is None:
            messagebox.showerror(tr("Brak klucza", "No key"), tr("Najpierw aktywuj root SSH.", "Activate root SSH first."))
            return
        py = self._need_py()
        if py is None:
            return

        def task(t):
            t.status("store", tr("Testuję SSH...", "Testing SSH..."), "busy")
            code = repos.probe_login(py, folder, t.log)
            t.status("store", tr("SSH działa", "SSH works") if code == 0 else tr("SSH nie odpowiada", "SSH not responding"),
                     "ok" if code == 0 else "err")
            self.flash_verify_ok = code == 0
            self.ssh_disabled = code != 0
            return code

        self._start("store", task)

    def do_status(self):
        py = self._need_py()
        if py is None:
            return

        def task(t):
            t.status("manage", tr("Odczytuję status...", "Reading status..."), "busy")
            argv = [py, "ssh_enable.py", "status", "--log", str(self._log_path("status"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            t.status("manage", tr("Status odczytany", "Status read") if code == 0 else tr("Status nieudany", "Status read failed"),
                     "ok" if code == 0 else "err")
            return code

        self._start("manage", task)

    def do_enable(self):
        py = self._need_py()
        if py is None:
            return
        if not messagebox.askyesno(tr("Napraw SSH", "Repair SSH"),
                                   tr("Naprawić SSH bez flashowania?\n\nTo nie czyści kodowania. Użyj, gdy SSH przestało odpowiadać.",
                                      "Repair SSH without flashing?\n\nThis does not wipe coding. Use it when SSH stopped answering.")):
            return
        vin = self._vin() if self._vin_valid() else ""

        def task(t):
            t.status("manage", tr("Naprawiam SSH...", "Repairing SSH..."), "busy")
            argv = [py, "ssh_enable.py", "enable", "--persist", "--yes"]
            if vin:
                argv += ["--vin", vin]
            argv += ["--log", str(self._log_path("enable"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            t.status("manage", tr("SSH naprawione", "SSH repaired") if code == 0 else tr("Naprawa nieudana", "Repair failed"),
                     "ok" if code == 0 else "err")
            if code == 0:
                self.flash_ok = True
                self.flash_verify_ok = True
                self.ssh_disabled = False
            return code

        self._start("manage", task)

    def do_disable(self):
        py = self._need_py()
        if py is None:
            return
        if not messagebox.askyesno(tr("Wyłącz SSH", "Disable SSH"),
                                   tr("Wyłączyć trwały dostęp SSH?\n\nMGU Store i aplikacje pozostaną zainstalowane. Nie będzie można logować się przez SSH, dopóki nie uruchomisz enable ponownie.",
                                      "Disable persistent SSH access?\n\nMGU Store and apps stay installed. You will not be able to log in over SSH until you run enable again.")):
            return

        def task(t):
            t.status("manage", tr("Wyłączam SSH...", "Disabling SSH..."), "busy")
            argv = [py, "ssh_enable.py", "disable", "--yes", "--log", str(self._log_path("disable"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            t.status("manage", tr("SSH wyłączone", "SSH disabled") if code == 0 else tr("Wyłączanie nieudane", "Disable failed"),
                     "ok" if code == 0 else "err")
            if code == 0:
                self.ssh_disabled = True
            return code

        self._start("manage", task)

    def do_fix(self):
        if not self._vin_valid():
            messagebox.showerror("VIN", tr("Podaj poprawny VIN.", "Enter a valid VIN."))
            return
        vin = self._vin()
        if not self.components_ready or not self.is_admin:
            messagebox.showwarning(tr("Nie można naprawić klucza", "Cannot fix the key"),
                                   tr("Wymagane są komponenty i uprawnienia administratora.",
                                      "Components and administrator rights are required."))
            return
        if self.detected_vin != vin:
            messagebox.showwarning(tr("Nie można naprawić klucza", "Cannot fix the key"),
                                   tr("Kliknij Wykryj VIN, aby potwierdzić VIN odczytany z auta.",
                                      "Click Detect VIN to verify the VIN read from the car."))
            return
        if not self.backup_ok:
            messagebox.showwarning(tr("Nie można naprawić klucza", "Cannot fix the key"),
                                   tr("Najpierw wykonaj kopię odczytową dla tego VIN (krok 3).",
                                      "First make a read-only coding backup for this VIN (step 3)."))
            return
        py = self._need_py()
        if py is None:
            return
        warning = tr(
            "Fix-key ponownie flashuje obraz debug, tym razem z naszym kluczem w niepodpisanym regionie.\n\n"
            "• To jest flash — czyści kodowanie CAFD i usuwa Digital Key.\n"
            "• Użyj tylko, gdy port 22 jest otwarty, ale logowanie root jest odrzucane.\n"
            "• Operacja zapisuje VIN %s i restartuje jednostkę.",
            "Fix-key re-flashes the debug image with our key in the unsigned region.\n\n"
            "• This is a flash — it wipes CAFD coding and removes Digital Key.\n"
            "• Use it only when port 22 is open but root login is refused.\n"
            "• The operation writes VIN %s and reboots the unit.",
        ) % vin
        dialog = TypedConfirm(self, tr("Potwierdź fix-key", "Confirm fix-key"),
                              tr("Napraw klucz (fix-key)", "Fix key (fix-key)"), warning, "FIX",
                              tr("Napraw klucz", "Fix key"), checks=self._safety_checks(self._arch()))
        if not dialog.result:
            return

        def task(t):
            t.status("manage", tr("Naprawiam klucz...", "Fixing the key..."), "busy")
            argv = [py, "ssh_enable.py", "fix-key", "--vin", vin, "--yes",
                    "--log", str(self._log_path("fix-key"))]
            code = run_lines(argv, t.log, cwd=config.SSH_REPO)
            if code == 0:
                self.flash_ok = True
                self.ssh_disabled = False
                flashed = self.settings.setdefault("flashed_vins", [])
                if vin not in flashed:
                    flashed.append(vin)
                config.save_settings(self.settings)
                folder, key = repos.identity_for(vin)
                self.flash_verify_ok = False
                if key is not None:
                    self.flash_verify_ok = repos.probe_login(py, folder, t.log) == 0
                t.status("manage", tr("Klucz naprawiony", "Key fixed") if self.flash_verify_ok else
                         tr("Fix-key OK — SSH niezweryfikowane", "Fix-key OK — SSH not verified"),
                         "ok" if self.flash_verify_ok else "warn")
            else:
                t.status("manage", tr("Fix-key nieudany", "Fix-key failed"), "err")
            return code

        self._start("manage", task)

    def _open_data(self):
        path = config.SSH_REPO / "data"
        if path.exists():
            _open_path(path)
        else:
            _open_path(config.WORK)

    def _open_logs(self):
        _open_path(config.LOGS)

    def _open_backup(self):
        folder = repos.latest_preflight()
        if folder is None:
            messagebox.showinfo(tr("Brak kopii", "No backup"),
                                tr("Nie znaleziono kopii. Kliknij „Zrób kopię odczytową”.",
                                   "No backup found. Click “Make read-only backup”."))
            return
        _open_path(folder)

    def _open_identity(self):
        folder = self.identity_folder
        if folder is None:
            folder, _key = repos.identity_for(self._vin())
        if folder is None:
            messagebox.showinfo(tr("Brak klucza", "No key"),
                                tr("Nie znaleziono klucza SSH. Najpierw aktywuj dostęp.",
                                   "No SSH key found. Activate access first."))
            return
        _open_path(folder)

    def _copy_log(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.log_text.get("1.0", "end-1c"))
        except tk.TclError:
            pass

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _elevate(self):
        if not config.IS_WINDOWS:
            messagebox.showinfo("Administrator", tr("Na tym systemie uruchom aplikację z uprawnieniami root.",
                                                    "Run the app with root privileges on this system."))
            return
        try:
            import ctypes
            params = "" if getattr(sys, "frozen", False) else '"%s"' % Path(sys.argv[0]).resolve()
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, str(config.ROOT), 1)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Administrator", tr("Nie udało się uruchomić jako administrator: %s",
                                                     "Could not relaunch as administrator: %s") % exc)

    def _on_close(self):
        if self.busy:
            messagebox.showwarning(tr("Nie zamykaj", "Do not close"),
                                   tr("Trwa operacja. Przerwanie flashowania może uszkodzić jednostkę.\n\nPoczekaj na zakończenie.",
                                      "An operation is running. Interrupting the flash can brick the unit.\n\nWait for it to finish."))
            return
        try:
            if self.session_log is not None:
                self.session_log.close()
        except OSError:
            pass
        self.destroy()


def main():
    config.bootstrap()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
