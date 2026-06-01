"""
ChamerTiger — Wallpaper scheduler per ora + giorno della settimana
Richiede: pystray, Pillow, pywin32
"""

import sys
import os
import json
import time
import ctypes
import threading
import subprocess
import winreg
from datetime import datetime
from pathlib import Path

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
except ImportError:
    print("Dipendenze mancanti. Esegui: pip install pystray Pillow pywin32")
    sys.exit(1)

# ── Percorsi ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
APP_NAME = "ChamerTiger"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ── Costanti giorno ───────────────────────────────────────────────────────────
WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
WEEKEND = {"saturday", "sunday"}


# ═══════════════════════════════════════════════════════════════════════════════
#  Logica di scheduling
# ═══════════════════════════════════════════════════════════════════════════════


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def parse_time(t: str) -> tuple[int, int]:
    """Converte 'HH:MM' in (hour, minute)."""
    h, m = t.split(":")
    return int(h), int(m)


def time_in_slot(now: datetime, slot: dict) -> bool:
    """Ritorna True se l'orario corrente rientra nello slot."""
    sh, sm = parse_time(slot["from"])
    eh, em = parse_time(slot["to"])
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=59, microsecond=999999)

    if start <= end:
        return start <= now <= end
    else:
        # Fascia a cavallo della mezzanotte (es. 22:00 → 06:00)
        return now >= start or now <= end


def resolve_wallpaper(config: dict) -> str | None:
    """
    Determina il percorso dell'immagine da usare adesso.
    Priorità: special_days > override giorno > schedule weekday/weekend
    """
    now = datetime.now()
    today_key = now.strftime("%Y-%m-%d")  # es. "2026-06-01"
    day_name = WEEKDAYS[now.weekday()]  # es. "monday"

    # 1. Giorno speciale (data esatta)
    special = config.get("special_days", {}).get(today_key)
    if special:
        for slot in special:
            if time_in_slot(now, slot):
                return slot["image"]

    # 2. Override per giorno della settimana
    override = config.get("overrides", {}).get(day_name)
    if override:
        for slot in override:
            if time_in_slot(now, slot):
                return slot["image"]

    # 3. Schedule base weekday / weekend
    schedule_key = "weekend" if day_name in WEEKEND else "weekday"
    schedule = config.get("schedules", {}).get(schedule_key, [])
    for slot in schedule:
        if time_in_slot(now, slot):
            return slot["image"]

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Cambio sfondo Windows
# ═══════════════════════════════════════════════════════════════════════════════

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

_last_wallpaper: str = ""


def set_wallpaper(path: str) -> bool:
    global _last_wallpaper
    if not path or not os.path.isfile(path):
        print(f"[WARN] Immagine non trovata: {path}")
        return False
    if path == _last_wallpaper:
        return False  # nessun cambiamento necessario
    result = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if result:
        _last_wallpaper = path
        print(f"[OK] Sfondo impostato: {path}")
    else:
        print(f"[ERR] Impossibile impostare lo sfondo: {path}")
    return bool(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  Avvio automatico con Windows
# ═══════════════════════════════════════════════════════════════════════════════


def get_exe_path() -> str:
    """Percorso dell'eseguibile (o dello script Python)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def is_autostart_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def enable_autostart():
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_exe_path())
    winreg.CloseKey(key)
    print("[OK] Avvio automatico abilitato.")


def disable_autostart():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("[OK] Avvio automatico disabilitato.")
    except FileNotFoundError:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  System Tray
# ═══════════════════════════════════════════════════════════════════════════════
def make_tray_icon() -> Image.Image:
    return Image.open(BASE_DIR / "icon.ico")


class ChamerTigerTray:
    def __init__(self):
        self.config = load_config()
        self._stop_event = threading.Event()
        self._icon = None

    # ── Thread principale del polling ─────────────────────────────────────────
    def _run_scheduler(self):
        while not self._stop_event.is_set():
            try:
                self.config = load_config()  # rilegge la config ad ogni ciclo
                wallpaper = resolve_wallpaper(self.config)
                if wallpaper:
                    set_wallpaper(wallpaper)
                else:
                    print("[INFO] Nessuno slot attivo al momento.")
            except Exception as e:
                print(f"[ERR] Scheduler: {e}")

            interval = self.config.get("check_interval_minutes", 5) * 60
            self._stop_event.wait(interval)

    # ── Azioni menu tray ──────────────────────────────────────────────────────
    def _open_editor(self, icon, item):
        editor_path = BASE_DIR / "gui.py"
        subprocess.Popen([sys.executable, str(editor_path)])

    def _apply_now(self, icon, item):
        try:
            self.config = load_config()
            wallpaper = resolve_wallpaper(self.config)
            if wallpaper:
                set_wallpaper(wallpaper)
        except Exception as e:
            print(f"[ERR] Apply now: {e}")

    def _toggle_autostart(self, icon, item):
        if is_autostart_enabled():
            disable_autostart()
        else:
            enable_autostart()

    def _quit(self, icon, item):
        self._stop_event.set()
        icon.stop()

    # ── Build menu ────────────────────────────────────────────────────────────
    def _build_menu(self):
        autostart_label = lambda item: (
            "✓ Avvio con Windows" if is_autostart_enabled() else "  Avvio con Windows"
        )
        return pystray.Menu(
            Item("ChamerTiger", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Applica adesso", self._apply_now),
            Item("Apri editor config", self._open_editor),
            pystray.Menu.SEPARATOR,
            Item(autostart_label, self._toggle_autostart),
            pystray.Menu.SEPARATOR,
            Item("Esci", self._quit),
        )

    # ── Entry point ───────────────────────────────────────────────────────────
    def run(self):
        # Abilita autostart di default al primo avvio
        if not is_autostart_enabled():
            enable_autostart()

        # Avvia il thread scheduler
        t = threading.Thread(target=self._run_scheduler, daemon=True)
        t.start()

        # Applica subito
        self._apply_now(None, None)

        # Avvia il tray
        self._icon = pystray.Icon(
            APP_NAME, make_tray_icon(), APP_NAME, self._build_menu()
        )
        self._icon.run()


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ChamerTigerTray()
    app.run()
