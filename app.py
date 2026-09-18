"""
Chametiger - Wallpaper scheduler per ora + giorno della settimana
Due modalita':
  - "scheduled": ogni slot ha un'immagine fissa (comportamento storico)
  - "random":    ogni slot pesca a caso tra le immagini che hanno certi tag
Richiede: pystray, Pillow, pywin32
"""

import sys
import os
import json
import random
import ctypes
import threading
import subprocess
import winreg
import socket
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image
except ImportError:
    print("Dipendenze mancanti. Esegui: pip install pystray Pillow pywin32")
    sys.exit(1)

# ── Percorsi ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
APP_NAME = "Chametiger"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOG_FILE = BASE_DIR / "chametiger.log"
MAX_LOG_BYTES = 200_000
HISTORY_FILE = BASE_DIR / "log.json"
DEFAULT_HISTORY_DAYS = 60
# Origine del conteggio delle finestre. NON cambiarla mai dopo il primo avvio:
# spostarla trasla l'intero mazzo e i PC gia' allineati si disallineano.
EPOCH = date(2026, 1, 1)

# log.json e' scritto sia dal thread dello scheduler sia da quello del menu tray
_history_lock = threading.Lock()


def log(msg: str):
    """Scrive a schermo e su file, troncando il log quando diventa grosso."""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
            old = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            LOG_FILE.write_text(old[-MAX_LOG_BYTES // 2 :], encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Costanti giorno ──────────────────────────────────────────────────────────
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

MODE_SCHEDULED = "scheduled"
MODE_RANDOM = "random"


# ═══════════════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════════════


def ensure_defaults(cfg: dict) -> dict:
    """Aggiunge le chiavi nuove se mancano, cosi' i config vecchi restano validi."""
    cfg.setdefault("mode", MODE_SCHEDULED)
    cfg.setdefault("tags", [])
    cfg.setdefault("image_library", {})

    rules = cfg.setdefault("random_rules", {})
    rules.setdefault("weekday", [])
    rules.setdefault("weekend", [])
    rules.setdefault("overrides", {})
    for day in WEEKDAYS:
        rules["overrides"].setdefault(day, [])

    return cfg


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return ensure_defaults(json.load(f))


def is_absolute_path(p: str) -> bool:
    """True per /percorso, C:/percorso e \\\\server/share (non dipende dall'OS)."""
    s = str(p).replace("\\", "/")
    return s.startswith("/") or (len(s) > 1 and s[1] == ":")


def resolve_path(config: dict, filename: str) -> str:
    """
    Risolve il percorso dell'immagine.
    - Percorso relativo -> concatenato alla cartella base del PC corrente
    - Percorso assoluto -> ri-mappato sulla cartella base del PC corrente,
                           se inizia con una delle basi conosciute
    """
    hostname = socket.gethostname()
    path_map = config.get("path_map", {})
    default_base = config.get("base_path", "")
    base_path = path_map.get(hostname, default_base)

    if not is_absolute_path(filename):
        return str(Path(base_path) / filename)

    normalized = filename.replace("\\", "/")
    known_bases = [default_base] + list(path_map.values())
    for kb in known_bases:
        if not kb:
            continue
        kb_norm = kb.replace("\\", "/").rstrip("/") + "/"
        if normalized.lower().startswith(kb_norm.lower()):
            relative = normalized[len(kb_norm) :]
            return str(Path(base_path) / relative)

    return filename


# ═══════════════════════════════════════════════════════════════════════════════
#  Orari
# ═══════════════════════════════════════════════════════════════════════════════


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
        # Fascia a cavallo della mezzanotte (es. 22:00 -> 06:00)
        return now >= start or now <= end


def _first_match(slots, now: datetime) -> dict | None:
    """Ritorna il primo slot che copre l'orario corrente, o None."""
    if not slots:
        return None
    for slot in slots:
        if time_in_slot(now, slot):
            return slot
    return None


def _window(slot: dict) -> str:
    """Fascia oraria dello slot, come appare nel log."""
    return f"{slot.get('from', '?')}-{slot.get('to', '?')}"


def _tags_of(rule: dict) -> str:
    """Tag della regola casuale, in coda alla categoria. Vuoto se non ce ne sono."""
    parts = []
    if rule.get("include"):
        joiner = "/" if rule.get("match", "all") == "any" else "+"
        parts.append(joiner.join(rule["include"]))
    if rule.get("exclude"):
        parts.append("-" + ",-".join(rule["exclude"]))
    return f" [{' '.join(parts)}]" if parts else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Modalita' programmata
# ═══════════════════════════════════════════════════════════════════════════════


def resolve_scheduled(config: dict, now: datetime) -> tuple[str | None, str]:
    """
    Ritorna (percorso, categoria). La categoria e' l'etichetta della regola che
    ha vinto, usata nel log.

    Priorita':
      1. special_days (data esatta)
      2. overrides    (giorno della settimana)
      3. schedules    (weekday / weekend)
      4. fallback     (weekday, se il weekend non copre l'orario)
    """
    today_key = now.strftime("%Y-%m-%d")
    day_name = WEEKDAYS[now.weekday()]
    schedules = config.get("schedules", {})

    slot = _first_match(config.get("special_days", {}).get(today_key), now)
    if slot:
        cat = f"programmata, giorno speciale {today_key} {_window(slot)}"
        return resolve_path(config, slot["image"]), cat

    slot = _first_match(config.get("overrides", {}).get(day_name), now)
    if slot:
        cat = f"programmata, override {day_name} {_window(slot)}"
        return resolve_path(config, slot["image"]), cat

    schedule_key = "weekend" if day_name in WEEKEND else "weekday"
    slot = _first_match(schedules.get(schedule_key, []), now)
    if slot:
        cat = f"programmata, {schedule_key} {_window(slot)}"
        return resolve_path(config, slot["image"]), cat

    if schedule_key == "weekend":
        slot = _first_match(schedules.get("weekday", []), now)
        if slot:
            log("[INFO] Nessuno slot weekend attivo, uso il fallback weekday.")
            cat = f"programmata, fallback weekday {_window(slot)}"
            return resolve_path(config, slot["image"]), cat

    return None, ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Modalita' casuale per tag
# ═══════════════════════════════════════════════════════════════════════════════


def image_matches_rule(image_tags, rule: dict) -> bool:
    """
    include: tag che l'immagine deve avere
    exclude: tag che l'immagine non deve avere
    match:   "all" (default) = deve avere tutti gli include
             "any"           = ne basta uno
    """
    tags = set(image_tags or [])

    for t in rule.get("exclude", []):
        if t in tags:
            return False

    include = rule.get("include", [])
    if not include:
        return True

    if rule.get("match", "all") == "any":
        return any(t in tags for t in include)
    return all(t in tags for t in include)


def candidates_for_rule(config: dict, rule: dict) -> list[str]:
    """Immagini della libreria che soddisfano la regola e che esistono su disco."""
    library = config.get("image_library", {})
    out = []
    for image, tags in library.items():
        if not image_matches_rule(tags, rule):
            continue
        if os.path.isfile(resolve_path(config, image)):
            out.append(image)
    return out


def _rule_signature(rule: dict) -> str:
    return "|".join(
        [
            str(rule.get("from", "")),
            str(rule.get("to", "")),
            ",".join(sorted(rule.get("include", []))),
            ",".join(sorted(rule.get("exclude", []))),
            str(rule.get("match", "all")),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Storico delle estrazioni (log.json)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Lo storico e' scritto solo da questo processo, mai dalla GUI: config.json e'
#  quello che decidi tu, log.json e' quello che e' successo. La "priorita'" di
#  un'immagine non viene salvata da nessuna parte, si ricalcola da qui, cosi'
#  non puo' andare fuori sincrono con la libreria.


def history_days(config: dict) -> int:
    """Per quanti giorni indietro guardare. Sotto 1 giorno non ha senso."""
    try:
        days = int(config.get("history_days", DEFAULT_HISTORY_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_HISTORY_DAYS
    return days if days >= 1 else DEFAULT_HISTORY_DAYS


def load_history() -> list[dict]:
    """Un log.json rovinato non deve impedire all'app di partire."""
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        log(f"[WARN] log.json illeggibile, riparto da zero: {e}")
        return []


def _save_history(entries: list[dict]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1, ensure_ascii=False)
    except OSError as e:
        log(f"[WARN] Impossibile scrivere log.json: {e}")


def _prune_history(entries: list[dict], days: int, now: datetime) -> list[dict]:
    """Butta le voci piu' vecchie della finestra. Le date ISO si ordinano da sole."""
    limit = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    return [e for e in entries if e.get("day", "") >= limit]


def _window_entry(entries: list[dict], day: str, sig: str, bucket: int) -> dict | None:
    """L'estrazione gia' decisa per questa finestra di rotazione, se esiste."""
    for e in entries:
        if e.get("day") == day and e.get("rule") == sig and e.get("bucket") == bucket:
            return e
    return None


def _window_ordinal(rule: dict, now: datetime, rotate: int) -> int:
    """
    Numero progressivo della finestra, contando solo quelle che la regola copre.
    Se contassimo il tempo assoluto, le ore in cui la regola non e' attiva
    farebbero avanzare il mazzo e salterebbero delle immagini.
    """
    sh, sm = parse_time(rule["from"])
    eh, em = parse_time(rule["to"])
    start = sh * 60 + sm
    end = eh * 60 + em
    if end <= start:
        end += 1440  # fascia a cavallo della mezzanotte

    per_giorno = max(1, -(-(end - start) // rotate))

    cur = now.hour * 60 + now.minute
    giorno = now.date()
    if cur < start:  # oltre la mezzanotte: la finestra e' iniziata ieri
        cur += 1440
        giorno -= timedelta(days=1)

    offset = min((cur - start) // rotate, per_giorno - 1)
    return (giorno - EPOCH).days * per_giorno + offset


def _mazzo(pool: list[str], sig: str, giro: int) -> list[str]:
    """
    L'ordine delle immagini per un giro completo. Deterministico: due PC con la
    stessa libreria e la stessa regola ottengono lo stesso mazzo senza parlarsi.
    """
    m = sorted(pool)
    if len(m) <= 2:
        return m  # con una o due immagini l'unica sequenza sensata e' l'alternanza

    random.Random(f"{sig}|{giro}").shuffle(m)

    # Evita che l'ultima carta di un giro e la prima del successivo coincidano.
    # Si scambiano le posizioni 0 e 1 e non 0 e ultima, altrimenti la correzione
    # cambierebbe la carta finale e il controllo diventerebbe ricorsivo.
    prec = sorted(pool)
    random.Random(f"{sig}|{giro - 1}").shuffle(prec)
    if m[0] == prec[-1]:
        m[0], m[1] = m[1], m[0]

    return m


def _rotate_of(rule: dict) -> int:
    """La finestra di rotazione della regola, con i valori assurdi normalizzati."""
    try:
        r = int(rule.get("rotate_minutes", 60))
    except (TypeError, ValueError):
        return 60
    return r if r >= 1 else 60


def _regola_attiva(config: dict, quando: datetime) -> dict | None:
    """
    La regola casuale che copre quell'istante. Rispecchia le priorita' di
    resolve_random: se cambi l'ordine la', va cambiato anche qui.
    """
    day_name = WEEKDAYS[quando.weekday()]
    rules = config.get("random_rules", {})

    rule = _first_match(rules.get("overrides", {}).get(day_name), quando)
    if rule:
        return rule

    key = "weekend" if day_name in WEEKEND else "weekday"
    rule = _first_match(rules.get(key, []), quando)
    if rule:
        return rule

    if day_name in WEEKEND:
        return _first_match(rules.get("weekday", []), quando)

    return None


def _scelta_giornaliera(config: dict, now: datetime) -> str | None:
    """
    Ripercorre le finestre di oggi dalla mezzanotte fino ad adesso e assegna
    un'immagine a ognuna, saltando quelle gia' uscite nelle fasce precedenti.

    Non legge e non scrive nulla: ogni PC ricalcola la stessa sequenza dagli
    stessi ingressi, quindi l'unicita' giornaliera vale su tutte le macchine
    senza che debbano parlarsi.
    """
    if _regola_attiva(config, now) is None:
        return None

    pools: dict[str, list[str]] = {}  # una volta per regola, non per finestra
    usate: set[str] = set()
    scelta = None
    ultima_finestra = None

    mezzanotte = now.replace(hour=0, minute=0, second=0, microsecond=0)

    for m in range(now.hour * 60 + now.minute + 1):
        t = mezzanotte + timedelta(minutes=m)
        rule = _regola_attiva(config, t)
        if rule is None:
            continue

        rotate = _rotate_of(rule)
        sig = _rule_signature(rule)
        finestra = (sig, (t.hour * 60 + t.minute) // rotate)
        if finestra == ultima_finestra:
            continue  # stessa finestra del minuto precedente, gia' assegnata
        ultima_finestra = finestra

        if sig not in pools:
            pools[sig] = sorted(candidates_for_rule(config, rule))
        pool = pools[sig]
        if not pool:
            continue

        n = len(pool)
        giro, pos = divmod(_window_ordinal(rule, t, rotate), n)
        mazzo = _mazzo(pool, sig, giro)

        scelta = mazzo[pos]
        for k in range(n):  # avanza finche' non trovi una non ancora uscita oggi
            carta = mazzo[(pos + k) % n]
            if carta not in usate:
                scelta = carta
                break

        usate.add(scelta)

    return scelta


def pick_from_rule(
    config: dict, rule: dict, now: datetime, force_new: bool = False
) -> str | None:
    """
    Sceglie un'immagine dando la precedenza a quelle uscite meno spesso.

    Estrae solo dal gruppo a conteggio minimo: finche' restano immagini mai viste
    si pesca fra quelle, e solo quando il pool e' esaurito si riparte. A parita'
    di conteggio sorteggia.

    La scelta viene memorizzata in log.json per la finestra di rotazione corrente
    e riusata finche' la finestra non cambia. Senza questa memoria lo sfondo
    cambierebbe a ogni giro dello scheduler: l'immagine appena estratta salirebbe
    di conteggio e uscirebbe subito dal gruppo a priorita' massima.

    force_new=True ignora la memoria ed estrae di nuovo, escludendo la corrente.
    """
    pool = sorted(candidates_for_rule(config, rule))
    if not pool:
        return None

    try:
        rotate = int(rule.get("rotate_minutes", 60))
    except (TypeError, ValueError):
        rotate = 60
    if rotate < 1:
        rotate = 60

    day = now.strftime("%Y-%m-%d")
    sig = _rule_signature(rule)
    bucket = (now.hour * 60 + now.minute) // rotate

    scelta = _scelta_giornaliera(config, now)
    if scelta is None:
        return None

    with _history_lock:
        entries = load_history()
        memo = _window_entry(entries, day, sig, bucket)

        if force_new:
            corrente = memo.get("image") if memo else scelta
            rest = [i for i in pool if i != corrente]
            if rest:
                scelta = random.choice(rest)
            if memo:
                entries.remove(memo)
            forzata = True
        else:
            if memo:
                # un'estrazione manuale vale fino alla fine della sua finestra
                if memo.get("forced") and memo.get("image") in pool:
                    return memo["image"]
                # finestra gia' registrata con la stessa immagine: niente da scrivere
                if memo.get("image") == scelta:
                    return scelta
                entries.remove(memo)
            forzata = False

        entries.append(
            {
                "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
                "day": day,
                "image": scelta,
                "rule": sig,
                "bucket": bucket,
                "forced": forzata,
            }
        )
        _save_history(_prune_history(entries, history_days(config), now))

    return scelta


def resolve_random(config: dict, now: datetime) -> tuple[str | None, str]:
    """
    Ritorna (percorso, categoria), come resolve_scheduled.

    Priorita':
      1. special_days  (immagini fisse: a Natale vuoi quella, non una a caso)
      2. random_rules.overrides[giorno]
      3. random_rules.weekday / weekend
      4. fallback weekday
      5. fallback finale sulla modalita' programmata
    """
    today_key = now.strftime("%Y-%m-%d")
    day_name = WEEKDAYS[now.weekday()]
    rules = config.get("random_rules", {})

    slot = _first_match(config.get("special_days", {}).get(today_key), now)
    if slot:
        cat = f"casuale, giorno speciale {today_key} {_window(slot)}"
        return resolve_path(config, slot["image"]), cat

    rule = _first_match(rules.get("overrides", {}).get(day_name), now)
    if rule:
        image = pick_from_rule(config, rule, now)
        if image:
            cat = f"casuale, override {day_name} {_window(rule)}{_tags_of(rule)}"
            return resolve_path(config, image), cat
        log("[WARN] Regola override senza immagini valide, proseguo.")

    rules_key = "weekend" if day_name in WEEKEND else "weekday"
    rule = _first_match(rules.get(rules_key, []), now)
    if rule:
        image = pick_from_rule(config, rule, now)
        if image:
            cat = f"casuale, {rules_key} {_window(rule)}{_tags_of(rule)}"
            return resolve_path(config, image), cat
        log(f"[WARN] Regola {rules_key} senza immagini valide, proseguo.")

    if rules_key == "weekend":
        rule = _first_match(rules.get("weekday", []), now)
        if rule:
            image = pick_from_rule(config, rule, now)
            if image:
                log("[INFO] Nessuna regola weekend attiva, uso il fallback weekday.")
                cat = f"casuale, fallback weekday {_window(rule)}{_tags_of(rule)}"
                return resolve_path(config, image), cat

    log("[INFO] Nessuna regola casuale attiva, ripiego sulla modalita' programmata.")
    return resolve_scheduled(config, now)


# ═══════════════════════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════════════════════


def resolve_wallpaper(config: dict) -> tuple[str | None, str]:
    """Ritorna (percorso, categoria) della regola attiva adesso."""
    now = datetime.now()
    if config.get("mode", MODE_SCHEDULED) == MODE_RANDOM:
        return resolve_random(config, now)
    return resolve_scheduled(config, now)


# ═══════════════════════════════════════════════════════════════════════════════
#  Cambio sfondo Windows
# ═══════════════════════════════════════════════════════════════════════════════

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

_last_wallpaper: str = ""


def set_wallpaper(path: str, category: str = "") -> bool:
    global _last_wallpaper
    if not path or not os.path.isfile(path):
        log(f"[WARN] Immagine non trovata: {path}")
        return False
    if path == _last_wallpaper:
        return False  # nessun cambiamento necessario
    result = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if result:
        _last_wallpaper = path
        suffix = f" ({category})" if category else ""
        log(f"[OK] Sfondo impostato{suffix}: {path}")
    else:
        log(f"[ERR] Impossibile impostare lo sfondo: {path}")
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
    log("[OK] Avvio automatico abilitato.")


def disable_autostart():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        log("[OK] Avvio automatico disabilitato.")
    except FileNotFoundError:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  System Tray
# ═══════════════════════════════════════════════════════════════════════════════


def make_tray_icon() -> Image.Image:
    return Image.open(BASE_DIR / "icon.ico")


class ChametigerTray:
    def __init__(self):
        self.config = load_config()
        self._stop_event = threading.Event()
        self._icon = None
        self._no_slot_logged = False

    def _report_no_slot(self, always: bool = False):
        """
        Logga l'assenza di slot attivi.

        Lo scheduler passa always=False: la riga compare una volta sola e non si
        ripete a ogni ciclo, finche' non torna attivo uno slot. Le azioni manuali
        passano always=True, perche' un click vuole sempre un riscontro.
        """
        if always or not self._no_slot_logged:
            log("[INFO] Nessuno slot attivo al momento.")
        self._no_slot_logged = True

    # ── Thread principale del polling ────────────────────────────────────────
    def _run_scheduler(self):
        while not self._stop_event.is_set():
            try:
                self.config = load_config()  # rilegge la config ad ogni ciclo
                wallpaper, category = resolve_wallpaper(self.config)
                if wallpaper:
                    self._no_slot_logged = False
                    set_wallpaper(wallpaper, category)
                else:
                    self._report_no_slot()
            except Exception as e:
                log(f"[ERR] Scheduler: {e}")

            interval = self.config.get("check_interval_minutes", 5) * 60
            self._stop_event.wait(interval)

    # ── Azioni menu tray ─────────────────────────────────────────────────────
    def _open_editor(self, icon, item):
        editor_path = BASE_DIR / "gui.py"
        subprocess.Popen([sys.executable, str(editor_path)])

    def _apply_now(self, icon, item):
        try:
            self.config = load_config()
            wallpaper, category = resolve_wallpaper(self.config)
            if wallpaper:
                self._no_slot_logged = False
                set_wallpaper(wallpaper, category)
            else:
                self._report_no_slot(always=True)
        except Exception as e:
            log(f"[ERR] Apply now: {e}")

    def _shuffle_now(self, icon, item):
        """Forza una nuova estrazione ignorando la finestra di rotazione."""
        try:
            self.config = load_config()
            if self.config.get("mode") != MODE_RANDOM:
                log("[INFO] Estrazione disponibile solo in modalita' casuale.")
                return

            now = datetime.now()
            day_name = WEEKDAYS[now.weekday()]
            rules = self.config.get("random_rules", {})

            category = ""
            rule = _first_match(rules.get("overrides", {}).get(day_name), now)
            if rule:
                category = f"override {day_name}"
            if not rule:
                key = "weekend" if day_name in WEEKEND else "weekday"
                rule = _first_match(rules.get(key, []), now)
                if rule:
                    category = key
            if not rule and day_name in WEEKEND:
                rule = _first_match(rules.get("weekday", []), now)
                if rule:
                    category = "fallback weekday"

            if not rule:
                log("[INFO] Nessuna regola casuale attiva adesso.")
                return

            image = pick_from_rule(self.config, rule, now, force_new=True)
            if not image:
                log("[WARN] Nessuna immagine valida per la regola attiva.")
                return

            category = f"estrazione forzata, {category} {_window(rule)}{_tags_of(rule)}"
            set_wallpaper(resolve_path(self.config, image), category)
        except Exception as e:
            log(f"[ERR] Shuffle: {e}")

    def _toggle_mode(self, icon, item):
        """Passa da programmata a casuale e viceversa, salvando nel config."""
        try:
            cfg = load_config()
            cfg["mode"] = (
                MODE_RANDOM if cfg.get("mode") == MODE_SCHEDULED else MODE_SCHEDULED
            )
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self.config = cfg
            log(f"[OK] Modalita': {cfg['mode']}")
            self._apply_now(None, None)
        except Exception as e:
            log(f"[ERR] Cambio modalita': {e}")

    def _toggle_autostart(self, icon, item):
        if is_autostart_enabled():
            disable_autostart()
        else:
            enable_autostart()

    def _quit(self, icon, item):
        self._stop_event.set()
        icon.stop()

    # ── Build menu ───────────────────────────────────────────────────────────
    def _current_mode(self) -> str:
        try:
            return load_config().get("mode", MODE_SCHEDULED)
        except Exception:
            return MODE_SCHEDULED

    def _build_menu(self):
        def mode_label(item):
            if self._current_mode() == MODE_RANDOM:
                return "Modalita': casuale"
            return "Modalita': programmata"

        def autostart_label(item):
            return (
                "* Avvio con Windows"
                if is_autostart_enabled()
                else "  Avvio con Windows"
            )

        return pystray.Menu(
            Item("Chametiger", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Applica adesso", self._apply_now),
            Item("Cambia immagine adesso", self._shuffle_now),
            Item("Apri editor config", self._open_editor),
            pystray.Menu.SEPARATOR,
            Item(mode_label, self._toggle_mode),
            Item(autostart_label, self._toggle_autostart),
            pystray.Menu.SEPARATOR,
            Item("Esci", self._quit),
        )

    # ── Entry point ──────────────────────────────────────────────────────────
    def run(self):
        if not is_autostart_enabled():
            enable_autostart()

        log(f"Avvio Chametiger. Modalita': {self.config.get('mode')}")
        self._apply_now(None, None)

        t = threading.Thread(target=self._run_scheduler, daemon=True)
        t.start()

        self._icon = pystray.Icon(
            APP_NAME, make_tray_icon(), APP_NAME, self._build_menu()
        )
        self._icon.run()


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ChametigerTray()
    app.run()
