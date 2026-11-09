# MGU Toolkit

**One-click, safety-first installer for root SSH and MGU Store on BMW iDrive 7 / 8 (MGU) over ENET.**

[Polski](#polski) · [English](#english)

> **Warning:** this is an unofficial tool, not affiliated with BMW AG. Flashing can brick the head unit, wipe CAFD coding and delete BMW Digital Key pairings. Use it only on your own car, at your own risk.

| Polski | English |
| --- | --- |
| ![MGU Toolkit PL](docs/screenshots/main-pl.png) | ![MGU Toolkit EN](docs/screenshots/main-en.png) |

---

## Polski

### Co to jest?

MGU Toolkit to graficzna nakładka w Pythonie/Tkinter na dwa oficjalne projekty open source:

- [idrive7-8-ssh-root](https://github.com/cauliflowermossgrape/idrive7-8-ssh-root) — aktywacja root SSH na jednostce MGU przez ENET: flash obrazu debug, enrollment i trwałe SSH bez DTC B7F8E5.
- [mgu-store](https://github.com/robertnisipeanu/mgu-store) — sklep z aplikacjami dla iDrive 7/8: Store, updater, deploy tool, renderer i uplink.

To narzędzie **nie reimplementuje flashowania**. Uruchamia oficjalne skrypty, pilnuje kolejności, sprawdza warunki wejścia i egzekwuje bramki bezpieczeństwa. Dzięki temu proces jest krótszy i trudniejszy do zepsucia przez literówkę.

### Dla kogo?

- Dla właścicieli BMW z iDrive 7 (MGU) lub iDrive 8 (BDC3 / BCP), którzy chcą sami wgrać root SSH i MGU Store.
- Dla osób, które chcą Waze lub Google Maps na zegarach, odczyt parametrów silnika, pomiary 0–100 km/h i inne aplikacje z [idrive-apps](https://github.com/robertnisipeanu/idrive-apps).
- Dla ludzi, którzy rozumieją ryzyko i mają kabel ENET, laptopa z Windows/macOS/Linux, Pythona 3.9+ oraz BimmerCode/E-Sys do kopii kodowania.

**Nie** jest to narzędzie dla iDrive 6 i starszych (NBT/EVO) — upstream tego nie obsługuje. To także nie jest zamiennik BimmerCode/E-Sys: kodowanie i tak trzeba zabezpieczyć i ewentualnie przywrócić.

### Co potrafi?

- Przygotowanie komponentów jednym kliknięciem: pobiera repozytorium, tworzy izolowane `.venv`, instaluje `cryptography` i pobiera instalator MGU Store.
- Wykrywanie VIN przez ENET (UDP discovery).
- **Wymusza VIN potwierdzony przez ENET** — samo wpisanie VIN nie wystarcza.
- **Wymusza udaną, zweryfikowaną kopię odczytową kodowania** (`UDS 0x22`, bez zapisu) i wiąże ją z VIN.
- 5-punktowa lista kontrolna przed flashem + wpisanie `FLASH` (`FLASH-ID8` dla ID8).
- Jednorazowy `Flash + Enable` z `--persist` (SSH trwałe, bez DTC B7F8E5).
- Blokada drugiego flasha (po kluczu lub historii VIN).
- Po flashu automatyczny test logowania SSH; MGU Store jest zablokowany, jeśli SSH niezweryfikowane lub wyłączone.
- `enable` (naprawa bez flasha), `disable`, `fix-key` (z tymi samymi bramkami), restart MGU, test SSH, status.
- Przełącznik języka PL/EN na żywo; wybór jest zapisywany.
- Log sesji na dysku i kolorowana konsola.
- Blokada zamknięcia okna podczas operacji.

### Zrzuty ekranu

| Ekran główny (PL) | Potwierdzenie flashowania |
| --- | --- |
| ![PL](docs/screenshots/main-pl.png) | ![Confirm](docs/screenshots/confirm-en.png) |

### Wymagania

- Windows 10/11 (główny cel; macOS/Linux da się uruchomić ręcznie).
- Python 3.9+ z Tkinterem — instalator z python.org na Windows ma go w komplecie.
- Klient OpenSSH (`ssh -V`).
- Kabel ENET; jeśli laptop nie ma Ethernetu — adapter USB-C/USB na Ethernet.
- Internet przy pierwszym przygotowaniu i przy instalacji MGU Store.
- Uprawnienia administratora/root.
- Auto zaparkowane, zapłon włączony, stabilne napięcie 12 V (najlepiej podtrzymanie).
- BimmerCode lub E-Sys do kopii i przywrócenia kodowania HU_MGU.

### Szybki start

```powershell
git clone https://github.com/Xayanix/idrive7-mgu-installer.git
cd idrive7-mgu-installer
```

1. Uruchom `Start MGU Toolkit (Admin).bat` (UAC) albo `py run.py`.
2. Krok 1: **Przygotuj komponenty**.
3. Krok 2: Podłącz ENET, włącz zapłon, kliknij **Wykryj VIN** i sprawdź VIN.
4. Krok 3: Zrób **kopię odczytową** oraz eksport HU_MGU w BimmerCode.
5. Krok 4: **Flash + Enable** — dokładnie raz.
6. Krok 5: **Zainstaluj MGU Store**, potem zrestartuj jednostkę.
7. Krok 6: Status, naprawa SSH lub wyłączenie dostępu.

### Jak to działa

- `mgu_toolkit/app.py` — GUI, bramki bezpieczeństwa, wątki, konsola.
- `mgu_toolkit/repos.py` — pobieranie repozytoriów, venv, zależności, wykrywanie VIN, restart, test SSH.
- `mgu_toolkit/proc.py` — strumieniowanie procesów bez zamrażania UI.
- `mgu_toolkit/checks.py` — administrator, OpenSSH, internet, komponenty.
- `mgu_toolkit/config.py` — ścieżki i ustawienia.
- `mgu_toolkit/i18n.py` — tłumaczenia PL/EN.
- `run.py` — punkt wejścia.
- `Start MGU Toolkit (Admin).bat` — uruchomienie z podniesieniem UAC.
- `mgu-workspace/` — katalog generowany: repozytoria, `.venv`, logi, config, klucze i kopie. Jest w `.gitignore`; nie trafia do repo.

Nic wrażliwego nie jest wysyłane do repozytorium: klucze SSH, VIN, kopie kodowania i logi zostają lokalnie.

### Model bezpieczeństwa

Aplikacja wymusza następujące warunki:

1. **VIN z ENET** — VIN musi zostać odczytany z bramki samochodu w tej sesji i zgadzać się z wpisanym VIN.
2. **Kopia kodowania** — flash jest zablokowany bez udanej kopii odczytowej dla tego VIN. Kopia musi zawierać `SHA256SUMS` i `coding_MGU.txt`.
3. **Lista kontrolna** — przed flashem trzeba potwierdzić: auto zaparkowane i wybudzone, stabilne 12 V, pełna kopia HU_MGU, pewnie podłączony ENET, świadomość ryzyka.
4. **Świadome potwierdzenie** — trzeba wpisać `FLASH` (`FLASH-ID8` dla iDrive 8).
5. **Jeden flash** — aplikacja blokuje ponowny flash po zapisanym kluczu lub historii VIN.
6. **Weryfikacja po flashu** — automatyczny test logowania SSH; MGU Store nie zostanie uruchomiony, jeśli SSH nie działa.
7. **`fix-key` też jest flashowaniem** — wymaga VIN z ENET, kopii kodowania, listy kontrolnej i wpisania `FIX`.
8. **Log sesji** — każda operacja i odpowiedź narzędzi trafia do `mgu-workspace/logs/session-*.log`.
9. **Blokada zamknięcia** — nie można zamknąć okna w trakcie operacji.
10. **Guardy środowiska** — brak Pythona, venv, admina lub komponentów blokuje akcje zamiast uruchamiać `None`.

Czego aplikacja nie może zagwarantować: zaniku zasilania, luźnego kabla, złej architektury, pominięcia kopii BimmerCode ani stanu jednostki przed rozpoczęciem. Ryzyko sprzętowe pozostaje po stronie użytkownika.

### Po flashu

- Ekran iDrive może zgasnąć, zrobić się niebieski lub jednostka może się zrestartować. To normalne.
- Jeśli ustawienia wrócą do fabrycznych: przywróć kodowanie z kopii (BimmerCode), a w razie problemów zakoduj HU_MGU ponownie przez E-Sys (VO coding). **Nie flashuj ponownie.**
- BMW Digital Key trzeba sparować od nowa.
- Jeśli SSH przestanie odpowiadać: **Napraw SSH (enable)**.
- Jeśli port 22 jest otwarty, ale login jest odrzucany: **Napraw klucz (fix-key)**.

### Rozwiązywanie problemów

**Brak bramki ENET** — sprawdź kabel i adapter, uruchom aplikację jako administrator, włącz zapłon i wybudź MGU (3 szybkie kliknięcia START/STOP). Upewnij się, że Windows widzi adres `169.254.x.x` na adapterze ENET.

**VIN nie jest raportowany** — aplikacja celowo odmawia flashowania bez VIN potwierdzonego przez ENET. Jeśli bramka nie podaje VIN, użyj oficjalnego CLI tylko wtedy, gdy wiesz, co robisz.

**SSH nie działa po udanym flashu** — użyj `fix-key` (to naprawa dla jednostek, które flashują się poprawnie, ale odrzucają login). Potem sprawdź logowanie SSH.

**Store nie pojawia się w menu** — zrestartuj jednostkę przyciskiem w kroku 5 albo przytrzymaj pokrętło głośności ok. 25 s.

**Python nie jest znaleziony** — zainstaluj Python 3.9+ z python.org i zaznacz `Add Python to PATH`. Sprawdź `py -3 --version`.

**Antywirus blokuje PowerShell** — instalator MGU Store jest pobierany z oficjalnego repo i weryfikowany przez `SHA256SUMS`. Możesz podejrzeć skrypt w `mgu-workspace/tools/` przed uruchomieniem.

### FAQ

**Czy działa z iDrive 8?** Upstream obsługuje ID8-BDC3 i ID8-BCP, ale MGU Store jest testowany na ID8 głównie w emulatorze. Traktuj to jako funkcję eksperymentalną.

**Czy działa z iDrive 6 / NBT / EVO?** Nie. Narzędzie odmówi.

**Czy flash czyści kodowanie?** Tak, CAFD zostanie wyczyszczone. Dlatego kopia jest wymagana.

**Czy usuwa Digital Key?** Tak, parowanie zostanie usunięte i trzeba je odtworzyć.

**Czy da się cofnąć?** `disable` wyłącza SSH, ale nie usuwa Store ani aplikacji. Store można odinstalować instalatorem `mgu-store` (`uninstall`), a kodowanie przywrócić z BimmerCode/E-Sys.

**Czy to jest darmowe?** Tak. Ten projekt jest na licencji MIT, a narzędzia upstream mają własne licencje.

**Czy to jest oficjalne BMW?** Nie. BMW, iDrive i Digital Key są znakami towarowymi BMW AG. Projekt jest nieoficjalny.

### Współpraca

Issues i pull requesty są mile widziane. Testy na realnych jednostkach są szczególnie cenne. **Nigdy nie commituj** kluczy SSH, kopii kodowania, VIN-ów ani katalogu `mgu-workspace/`.

### Licencja i kredyty

- Ten projekt: MIT — patrz [LICENSE](LICENSE).
- [idrive7-8-ssh-root](https://github.com/cauliflowermossgrape/idrive7-8-ssh-root): Unlicense.
- [mgu-store](https://github.com/robertnisipeanu/mgu-store): GPL-3.0.
- [idrive-apps](https://github.com/robertnisipeanu/idrive-apps): sprawdź licencję w repozytorium.

Projekt nie jest powiązany z BMW AG ani z autorami narzędzi upstream.

---

## English

### What is it?

MGU Toolkit is a Python/Tkinter GUI that wraps two official open-source projects:

- [idrive7-8-ssh-root](https://github.com/cauliflowermossgrape/idrive7-8-ssh-root) — enables root SSH on BMW MGU head units over ENET (debug image flash, enrollment, persistent SSH without DTC B7F8E5).
- [mgu-store](https://github.com/robertnisipeanu/mgu-store) — the app store for iDrive 7/8 (Store, updater, deploy tool, renderer, uplink).

It does **not** reimplement flashing. It runs the official tools, keeps the order, checks preconditions and enforces safety gates.

### Who is it for?

BMW owners with iDrive 7 (MGU) or iDrive 8 (BDC3/BCP) who want root SSH and MGU Store, including Waze/Google Maps on the cluster, engine data, 0–100 km/h timers and other [idrive-apps](https://github.com/robertnisipeanu/idrive-apps). It is **not** for iDrive 6 / NBT / EVO, and it does not replace BimmerCode or E-Sys for coding backups and restores.

### Features

- One-click component setup: repo download, isolated `.venv`, `cryptography`, MGU Store installer.
- ENET VIN detection.
- **VIN must be verified over ENET** — typing it is not enough.
- **A verified read-only coding backup is mandatory** (`UDS 0x22`, no writes) and is bound to the VIN.
- Five-point safety checklist plus typed `FLASH` (`FLASH-ID8` for ID8).
- One-time `Flash + Enable` with `--persist` (persistent SSH, no B7F8E5 DTC).
- Re-flash blocked by key or VIN history.
- Automatic post-flash SSH login test; MGU Store is blocked if SSH is unverified or disabled.
- Repair tools: `enable`, `disable`, `fix-key` (same safety gates), restart MGU, SSH test, status.
- Live PL/EN switch, persisted.
- Session log on disk and a coloured console.
- The window cannot be closed during an operation.

### Requirements

- Windows 10/11 (primary); macOS/Linux can be run manually.
- Python 3.9+ with Tkinter (the python.org Windows installer includes it).
- OpenSSH client (`ssh -V`).
- ENET cable (plus a USB-C/USB Ethernet adapter if needed).
- Internet for the first setup and the Store install.
- Administrator/root rights.
- Car parked, ignition on, stable 12 V (a maintainer is recommended).
- BimmerCode or E-Sys for the HU_MGU coding backup/restore.

### Quick start

```powershell
git clone https://github.com/Xayanix/idrive7-mgu-installer.git
cd idrive7-mgu-installer
```

1. Run `Start MGU Toolkit (Admin).bat` (UAC) or `py run.py`.
2. Step 1: **Prepare components**.
3. Step 2: Connect ENET, ignition on, click **Detect VIN** and check it.
4. Step 3: **Read-only backup** plus a BimmerCode HU_MGU export.
5. Step 4: **Flash + Enable** — exactly once.
6. Step 5: **Install MGU Store**, then restart the head unit.
7. Step 6: Status, repair SSH, or disable access.

### Safety model

1. VIN must be read from the car's ENET gateway in the current session and match the entered VIN.
2. Flashing is blocked without a successful read-only backup for that VIN (`SHA256SUMS` and `coding_MGU.txt` present).
3. A five-point checklist must be confirmed: parked/awake car, stable 12 V, full HU_MGU backup, firm ENET connection, risk understood.
4. The user must type `FLASH` (`FLASH-ID8` for iDrive 8).
5. Re-flashing is blocked by a saved key or VIN history.
6. After the flash, SSH login is verified automatically; MGU Store is blocked if SSH is not working.
7. `fix-key` is treated as a flash: ENET-verified VIN, coding backup, checklist and typed `FIX`.
8. Every operation and tool output is written to `mgu-workspace/logs/session-*.log`.
9. The window cannot be closed during an operation.
10. Missing Python, venv, admin rights or components block actions instead of running with invalid state.

The tool cannot protect against power loss, a loose cable, the wrong architecture, skipping the BimmerCode backup, or a unit that was already in a bad state.

### After the flash

- The iDrive screen may go dark, turn blue, or the unit may reboot. This is normal.
- If settings return to factory defaults, restore coding with BimmerCode or recode HU_MGU with E-Sys (VO coding). **Do not re-flash.**
- Re-pair BMW Digital Key.
- If SSH stops answering, use **Repair SSH (enable)**.
- If port 22 is open but login is refused, use **Fix key (fix-key)**.

### Troubleshooting

**No ENET gateway** — check the cable/adapter, run as administrator, switch on the ignition and wake the MGU (3 quick START/STOP presses). Confirm Windows sees a `169.254.x.x` address on the ENET adapter.

**VIN is not reported** — the app intentionally refuses to flash without an ENET-verified VIN. If the gateway does not report one, use the official CLI only if you understand the risk.

**SSH does not work after a successful flash** — use `fix-key`, then test SSH login again.

**Store tile is missing** — restart the head unit from step 5 or hold the volume knob for about 25 s.

**Python not found** — install Python 3.9+ from python.org with `Add Python to PATH`, then check `py -3 --version`.

### Project structure

```
run.py
Start MGU Toolkit (Admin).bat
mgu_toolkit/
  app.py
  i18n.py
  repos.py
  proc.py
  checks.py
  config.py
docs/screenshots/
mgu-workspace/        generated, git-ignored
```

### License and credits

- This project: MIT — see [LICENSE](LICENSE).
- idrive7-8-ssh-root: Unlicense.
- mgu-store: GPL-3.0.
- idrive-apps: check the license in that repository.

This project is not affiliated with BMW AG or with the upstream tool authors. BMW, iDrive and Digital Key are trademarks of BMW AG.

### Disclaimer

Use at your own risk, only on your own vehicle. Flashing can wipe CAFD coding, delete BMW Digital Key pairings and brick the head unit. The authors take no responsibility for any damage. The upstream projects are the authoritative source for the flashing behaviour; read their documentation before starting.

---

**Status:** the GUI, downloads, virtual environment, CLI integration, language switch and safety gates have been tested. Real-car flashing has not been tested in this repository environment; community testing is welcome.
