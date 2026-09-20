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
import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import sun

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
# Per quanti giorni tenere le voci di log.json. Al memo della finestra servono
# solo quelle di oggi, piu' quelle di ieri per una fascia a cavallo della
# mezzanotte: una settimana e' margine abbondante. Non ha effetto su quale
# immagine esce - la scelta viene dal mazzo e non legge lo storico.
DEFAULT_HISTORY_DAYS = 7
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

# Coordinate di default: Napoli. Servono agli orari solari (alba, tramonto,
# crepuscolo); si cambiano dalle impostazioni della GUI.
DEFAULT_LAT = 40.8518
DEFAULT_LON = 14.2681


# ═══════════════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════════════


def ensure_defaults(cfg: dict) -> dict:
    """Aggiunge le chiavi nuove se mancano, cosi' i config vecchi restano validi."""
    cfg.setdefault("mode", MODE_SCHEDULED)
    cfg.setdefault("tags", [])
    cfg.setdefault("image_library", {})
    cfg.setdefault("periods", [])
    cfg.setdefault("latitude", DEFAULT_LAT)
    cfg.setdefault("longitude", DEFAULT_LON)

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
    """Converte 'HH:MM' in (hour, minute). Solo orari di orologio."""
    h, m = t.split(":")
    return int(h), int(m)


@lru_cache(maxsize=16384)
def _resolve_minuti(t: str, giorno: date, lat: float, lon: float) -> int:
    """
    L'orario in minuti dalla mezzanotte di quel giorno.

    Accetta sia l'orologio ('09:00') sia le ancore solari ('sunset-40m'), cosi'
    le fasce astronomiche seguono il sole giorno per giorno invece di restare
    inchiodate a un'ora fissa che e' giusta due settimane l'anno.

    In cache perche' `_scelta_giornaliera` ricostruisce la giornata minuto per
    minuto e rivaluta gli stessi confini centinaia di volte.
    """
    ancora = sun.parse_anchor(t)
    if ancora:
        minuti = sun.solar_minutes(ancora[0], ancora[1], giorno, lat, lon)
        if minuti is not None:
            return minuti % 1440
        return 0  # evento assente (latitudini polari): la fascia parte a mezzanotte
    h, m = parse_time(t)
    return (h * 60 + m) % 1440


def slot_bounds(slot: dict, giorno: date, config: dict) -> tuple[int, int]:
    """
    (inizio, fine) dello slot in minuti dalla mezzanotte, per quel giorno.
    Entrambi normalizzati in [0, 1440): se fine <= inizio la fascia scavalca la
    mezzanotte, come ha sempre fatto "22:00 -> 06:00".
    """
    lat, lon = sun.coords(config)
    return (
        _resolve_minuti(str(slot.get("from", "00:00")), giorno, lat, lon),
        _resolve_minuti(str(slot.get("to", "00:00")), giorno, lat, lon),
    )


def time_in_slot(now: datetime, slot: dict, config: dict) -> bool:
    """Ritorna True se l'orario corrente rientra nello slot."""
    start, end = slot_bounds(slot, now.date(), config)
    cur = now.hour * 60 + now.minute

    if start <= end:
        return start <= cur <= end
    # Fascia a cavallo della mezzanotte (es. 22:00 -> 06:00, o dusk -> dawn)
    return cur >= start or cur <= end


def _first_match(slots, now: datetime, config: dict) -> dict | None:
    """Ritorna il primo slot che copre l'orario corrente, o None."""
    if not slots:
        return None
    for slot in slots:
        if time_in_slot(now, slot, config):
            return slot
    return None


def _window(slot: dict, giorno: date | None = None, config: dict | None = None) -> str:
    """
    Fascia oraria dello slot, come appare nel log. Con giorno e config, le ancore
    solari mostrano anche l'orario reale: 'sunset-40m (16:58)-dusk (17:29)'.
    Senza l'orario accanto una regola solare non e' verificabile a occhio.
    """
    frm, to = slot.get("from", "?"), slot.get("to", "?")
    if giorno is not None and config is not None:
        lat, lon = sun.coords(config)
        frm = sun.describe(frm, giorno, lat, lon)
        to = sun.describe(to, giorno, lat, lon)
    return f"{frm}-{to}"


def _tags_of(rule: dict) -> str:
    """Tag della regola casuale, in coda alla categoria. Vuoto se non ce ne sono."""
    parts = []
    if rule.get("include"):
        joiner = "/" if rule.get("match", "all") == "any" else "+"
        parts.append(joiner.join(rule["include"]))
    if rule.get("exclude"):
        parts.append("-" + ",-".join(rule["exclude"]))
    if rule.get("prefer"):
        parts.append("~" + ",~".join(rule["prefer"]))
    return f" [{' '.join(parts)}]" if parts else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Periodi dell'anno
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Un periodo copre un intervallo di date che si ripete ogni anno ("09-10" ->
#  "10-10") e modula le regole casuali senza duplicarle:
#
#    exclude  tag vietati, si sommano a quelli della regola
#    prefer   tag preferiti: se nel pool ce n'e' almeno uno il pool si restringe
#             a quelli, altrimenti resta intero (per non rimanere a secco)
#    require  tag obbligatori, si sommano all'include (in AND) - raro
#
#  Un periodo puo' anche portarsi regole proprie (`random_rules`), che NON
#  sostituiscono quelle di base: vengono consultate prima, e se nessuna copre
#  l'ora corrente si scende alla base. Stessa catena degli `overrides`, cosi'
#  un periodo festivo puo' cambiare solo le sere e lasciare intatto il resto.


@lru_cache(maxsize=512)
def _md_ordinal(s: str) -> int | None:
    """'10-20' -> 1020. Accetta anche 'AAAA-MM-GG', ignorando l'anno."""
    pezzi = str(s).strip().split("-")
    if len(pezzi) == 3:
        pezzi = pezzi[1:]
    if len(pezzi) != 2:
        return None
    try:
        mese, giorno = int(pezzi[0]), int(pezzi[1])
    except ValueError:
        return None
    if not (1 <= mese <= 12 and 1 <= giorno <= 31):
        return None
    return mese * 100 + giorno


def period_active(period: dict, giorno: date) -> bool:
    """
    True se il periodo copre quella data. Il salto di capodanno ("10-11" ->
    "01-03") si gestisce come le fasce a cavallo della mezzanotte: confronto
    invertito, nessun caso speciale sull'anno.
    """
    start = _md_ordinal(period.get("from", ""))
    end = _md_ordinal(period.get("to", ""))
    if start is None or end is None:
        return False
    oggi = giorno.month * 100 + giorno.day
    if start <= end:
        return start <= oggi <= end
    return oggi >= start or oggi <= end


def periodo_attivo(config: dict, giorno: date) -> dict | None:
    """
    Il primo periodo che copre quella data, o None. L'ordine conta: i periodi
    festivi vanno messi prima di quelli stagionali, come le regole override.
    """
    for period in config.get("periods", []) or []:
        if period_active(period, giorno):
            return period
    return None


def patch_rule(rule: dict, period: dict | None) -> dict:
    """
    La regola vista attraverso il periodo attivo. Ritorna sempre una COPIA:
    `_scelta_giornaliera` ripassa le stesse regole centinaia di volte e un dict
    mutato in place si porterebbe dietro le patch dei giri precedenti.
    """
    if not period:
        return rule

    patched = dict(rule)

    esclusi = list(rule.get("exclude", [])) + list(period.get("exclude", []))
    if esclusi:
        patched["exclude"] = sorted(set(esclusi))

    richiesti = list(period.get("require", []))
    if richiesti:
        patched["include"] = sorted(set(list(rule.get("include", [])) + richiesti))

    preferiti = list(rule.get("prefer", [])) + list(period.get("prefer", []))
    if preferiti:
        patched["prefer"] = sorted(set(preferiti))
        if period.get("prefer_min"):
            patched["prefer_min"] = period["prefer_min"]

    # Marca la provenienza: entra nella firma della regola, cosi' la stessa
    # fascia in due periodi diversi non condivide il memo in log.json.
    nome = period.get("name")
    if nome:
        patched["_period"] = nome

    return patched


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

    giorno = now.date()

    slot = _first_match(config.get("special_days", {}).get(today_key), now, config)
    if slot:
        cat = f"programmata, giorno speciale {today_key} {_window(slot, giorno, config)}"
        return resolve_path(config, slot["image"]), cat

    slot = _first_match(config.get("overrides", {}).get(day_name), now, config)
    if slot:
        cat = f"programmata, override {day_name} {_window(slot, giorno, config)}"
        return resolve_path(config, slot["image"]), cat

    schedule_key = "weekend" if day_name in WEEKEND else "weekday"
    slot = _first_match(schedules.get(schedule_key, []), now, config)
    if slot:
        cat = f"programmata, {schedule_key} {_window(slot, giorno, config)}"
        return resolve_path(config, slot["image"]), cat

    if schedule_key == "weekend":
        slot = _first_match(schedules.get("weekday", []), now, config)
        if slot:
            log("[INFO] Nessuno slot weekend attivo, uso il fallback weekday.")
            cat = f"programmata, fallback weekday {_window(slot, giorno, config)}"
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


# Esistenza dei file, memorizzata per un giro di scheduler. Su una cartella di
# rete o Google Drive ogni isfile costa, e le regole della giornata chiedono le
# stesse immagini decine di volte. Si svuota a ogni giro, cosi' un'immagine
# aggiunta o rimossa viene notata al controllo successivo come prima.
_esiste_cache: dict[str, bool] = {}


def invalida_cache_file():
    """Svuota la cache di esistenza. Da chiamare a ogni giro dello scheduler."""
    _esiste_cache.clear()


def _esiste(percorso: str) -> bool:
    if percorso not in _esiste_cache:
        _esiste_cache[percorso] = os.path.isfile(percorso)
    return _esiste_cache[percorso]


def candidates_for_rule(config: dict, rule: dict) -> list[str]:
    """
    Immagini della libreria che soddisfano la regola e che esistono su disco.

    `prefer` si applica qui e non in `image_matches_rule` perche' e' una scelta
    sul POOL, non un filtro per immagine: se almeno una candidata ha uno dei tag
    preferiti si tengono solo quelle, altrimenti il pool resta intero. E' cosi'
    che "a dicembre voglio il Natale" non lascia fasce vuote alle tre di notte.
    """
    library = config.get("image_library", {})
    out = []
    for image, tags in library.items():
        if not image_matches_rule(tags, rule):
            continue
        if _esiste(resolve_path(config, image)):
            out.append(image)

    prefer = set(rule.get("prefer", []))
    if prefer:
        try:
            minimo = max(1, int(rule.get("prefer_min", 1)))
        except (TypeError, ValueError):
            minimo = 1
        scelti = [i for i in out if prefer & set(library.get(i) or [])]
        # Si restringe solo se ne resta abbastanza: con pochi tag preferiti il
        # pool si ridurrebbe a una o due immagini e la fascia diventerebbe fissa.
        if len(scelti) >= minimo:
            return scelti

    return out


def _rule_signature(rule: dict) -> str:
    """
    Identita' della regola: indicizza i memo in log.json e fa da seme al mazzo.

    `prefer` e il periodo si aggiungono solo se presenti, cosi' le regole che non
    li usano conservano la firma che avevano prima dei periodi e lo storico
    gia' scritto resta valido.
    """
    parti = [
        str(rule.get("from", "")),
        str(rule.get("to", "")),
        ",".join(sorted(rule.get("include", []))),
        ",".join(sorted(rule.get("exclude", []))),
        str(rule.get("match", "all")),
    ]
    if rule.get("prefer"):
        parti.append("p:" + ",".join(sorted(rule["prefer"])))
        if rule.get("prefer_min"):
            parti.append("pm:" + str(rule["prefer_min"]))
    if rule.get("_period"):
        parti.append("s:" + str(rule["_period"]))
    return "|".join(parti)


# ═══════════════════════════════════════════════════════════════════════════════
#  Memoria della finestra corrente (log.json)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Lo storico e' scritto solo da questo processo, mai dalla GUI: config.json e'
#  quello che decidi tu, log.json e' quello che e' successo.
#
#  ATTENZIONE, non e' piu' quello che il nome suggerisce. Una versione precedente
#  scegliva l'immagine contando quante volte era uscita negli ultimi giorni, e
#  log.json era la fonte di quel conteggio. Oggi la scelta viene dal mazzo
#  (_mazzo + ordinale della finestra), che e' deterministico e non guarda lo
#  storico: e' questo che permette a due PC di restare allineati senza parlarsi.
#
#  Cio' che resta a log.json e' solo:
#    1. il memo della finestra corrente, perche' lo sfondo non cambi a ogni giro
#       dello scheduler;
#    2. il ricordo di un'estrazione forzata, valida fino a fine finestra.
#
#  Per entrambe servono le voci di oggi (e quelle di ieri, per una finestra a
#  cavallo della mezzanotte). Tutto il resto e' solo cronologia leggibile.


def history_days(config: dict) -> int:
    """
    Per quanti giorni conservare le voci di log.json prima di potarle.

    NON influenza quale immagine esce: la scelta non legge lo storico. Alzarlo
    conserva solo piu' cronologia sul disco.
    """
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


def _finestre_del_giorno(rule: dict, giorno: date, rotate: int, config: dict) -> int:
    """Quante finestre di rotazione ha la regola in quel giorno."""
    start, end = slot_bounds(rule, giorno, config)
    lunghezza = (end - start) % 1440 or 1440
    return max(1, math.ceil(lunghezza / rotate))


# Somme cumulative delle finestre, per non ripercorrere l'anno a ogni chiamata.
# Chiave: (from, to, rotate, lat, lon) - e' tutto cio' che determina la durata
# delle finestre. Non il periodo: le patch sui tag non cambiano gli orari, cosi'
# un cambio di periodo non invalida la tabella.
_CUM_TOTALI: dict[tuple, dict[date, int]] = {}
_CUM_PASSO = 64  # si tiene un checkpoint ogni 64 giorni, non uno al giorno


def _finestre_fino_a(rule: dict, giorno: date, rotate: int, config: dict) -> int:
    """
    Quante finestre ha avuto la regola da EPOCH al giorno PRECEDENTE a `giorno`.

    Somma cumulativa, non moltiplicazione. Con le fasce ancorate al sole la
    durata cambia ogni giorno - la fascia 'notte' passa da 7 finestre a giugno a
    13 a dicembre - e la vecchia formula `giorni * per_giorno` farebbe saltare il
    mazzo di centinaia di posizioni il primo giorno in cui per_giorno cambia,
    bruciando immagini che non si vedrebbero mai.

    Per le regole a orario fisso per_giorno e' costante e il risultato coincide
    con la vecchia formula: storico e posizione nel mazzo non si spostano.
    """
    if giorno <= EPOCH:
        return 0

    lat, lon = sun.coords(config)
    chiave = (str(rule.get("from", "")), str(rule.get("to", "")), rotate, lat, lon)
    punti = _CUM_TOTALI.setdefault(chiave, {EPOCH: 0})

    # Riparte dal checkpoint piu' recente che non superi il giorno richiesto.
    g = EPOCH + timedelta(days=((giorno - EPOCH).days // _CUM_PASSO) * _CUM_PASSO)
    while g not in punti:
        g -= timedelta(days=_CUM_PASSO)

    totale = punti[g]
    while g < giorno:
        totale += _finestre_del_giorno(rule, g, rotate, config)
        g += timedelta(days=1)
        if (g - EPOCH).days % _CUM_PASSO == 0:
            punti[g] = totale

    return totale


def _window_ordinal(rule: dict, now: datetime, rotate: int, config: dict) -> int:
    """
    Numero progressivo della finestra, contando solo quelle che la regola copre.
    Se contassimo il tempo assoluto, le ore in cui la regola non e' attiva
    farebbero avanzare il mazzo e salterebbero delle immagini.
    """
    giorno = now.date()
    start, end = slot_bounds(rule, giorno, config)
    cur = now.hour * 60 + now.minute

    if start > end and cur <= end:
        # Coda dopo la mezzanotte: la finestra e' iniziata ieri e al conteggio
        # di ieri appartiene.
        giorno -= timedelta(days=1)
        start, _ = slot_bounds(rule, giorno, config)
        cur += 1440
    elif cur < start:
        cur = start  # minuto di confine: si resta sulla prima finestra

    per_giorno = _finestre_del_giorno(rule, giorno, rotate, config)
    offset = min((cur - start) // rotate, per_giorno - 1)
    return _finestre_fino_a(rule, giorno, rotate, config) + offset


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


def _regole_del_giorno(config: dict, giorno: date) -> list[tuple[dict, str, int, int]]:
    """
    Le regole casuali di quel giorno in ordine di priorita', ognuna con i confini
    (inizio, fine) gia' risolti in minuti.

    UNICO posto in cui l'ordine di priorita' e' definito. Prima era ripetuto in
    resolve_random, _regola_attiva e _shuffle_now: tre copie da tenere allineate
    a mano, che col livello dei periodi sarebbero diventate quattro.

    Ordine:
      1. regole del periodo attivo, override del giorno
      2. regole del periodo attivo, feriali / weekend
      3. regole di base, override del giorno
      4. regole di base, feriali / weekend
      5. ripiego su feriali quando il weekend non copre l'orario

    Le regole del periodo non sostituiscono quelle di base: se nessuna copre
    l'ora corrente si scende, come fanno da sempre gli override di giorno. Cosi'
    un periodo festivo puo' cambiare solo le sere e lasciare intatte le mattine.

    I confini si risolvono una volta per giorno e non per minuto: la ricostruzione
    della giornata interroga queste regole 1440 volte, e con le ancore solari
    ricalcolare alba e tramonto ogni volta costava piu' di tutto il resto.
    """
    day_name = WEEKDAYS[giorno.weekday()]
    key = "weekend" if day_name in WEEKEND else "weekday"
    period = periodo_attivo(config, giorno)

    fonti: list[tuple[list | None, str]] = []

    if period:
        proprie = period.get("random_rules", {}) or {}
        etichetta = f"periodo {period.get('name', '?')}"
        fonti.append(
            (proprie.get("overrides", {}).get(day_name), f"{etichetta} override {day_name}")
        )
        fonti.append((proprie.get(key), f"{etichetta} {key}"))
        if key == "weekend":
            fonti.append((proprie.get("weekday"), f"{etichetta} fallback weekday"))

    base = config.get("random_rules", {})
    suffisso = f" [periodo {period.get('name', '?')}]" if period else ""
    fonti.append(
        (base.get("overrides", {}).get(day_name), f"override {day_name}{suffisso}")
    )
    fonti.append((base.get(key), f"{key}{suffisso}"))
    if key == "weekend":
        fonti.append((base.get("weekday"), f"fallback weekday{suffisso}"))

    out = []
    for regole, origine in fonti:
        for rule in regole or []:
            start, end = slot_bounds(rule, giorno, config)
            out.append((patch_rule(rule, period), origine, start, end))
    return out


def _copre(start: int, end: int, minuto: int) -> bool:
    """Se la fascia (in minuti) contiene quel minuto. Gestisce la mezzanotte."""
    if start <= end:
        return start <= minuto <= end
    return minuto >= start or minuto <= end


def regole_candidate(config: dict, quando: datetime) -> list[tuple[dict, str]]:
    """Le regole che coprono quell'istante, in ordine di priorita'."""
    minuto = quando.hour * 60 + quando.minute
    return [
        (rule, origine)
        for rule, origine, start, end in _regole_del_giorno(config, quando.date())
        if _copre(start, end, minuto)
    ]


def _regola_attiva(config: dict, quando: datetime) -> dict | None:
    """La regola casuale a priorita' piu' alta che copre quell'istante."""
    candidate = regole_candidate(config, quando)
    return candidate[0][0] if candidate else None


def sequenza_giornaliera(config: dict, giorno: date, fino_a: int = 1439) -> list[dict]:
    """
    Tutte le finestre di rotazione della giornata, dalla mezzanotte, con
    l'immagine assegnata a ognuna.

    Ripercorre il giorno e assegna un'immagine a ogni finestra saltando quelle
    gia' uscite nelle fasce precedenti, cosi' nella stessa giornata non si
    ripetono.

    Non legge e non scrive nulla: ogni PC ricalcola la stessa sequenza dagli
    stessi ingressi, quindi l'unicita' giornaliera vale su tutte le macchine
    senza che debbano parlarsi. E' questa proprieta' che vieta di memorizzare la
    posizione nel mazzo: va sempre ricalcolata.

    La usa sia lo scheduler (che ne vuole solo l'ultima) sia l'anteprima della
    GUI (che le vuole tutte): una passata sola invece di una per fascia.
    """
    regole = _regole_del_giorno(config, giorno)
    if not regole:
        return []

    pools: dict[str, list[str]] = {}  # una volta per regola, non per finestra
    usate: set[str] = set()
    sequenza: list[dict] = []
    ultima_finestra = None

    for minuto in range(min(fino_a, 1439) + 1):
        t = datetime(giorno.year, giorno.month, giorno.day) + timedelta(minutes=minuto)

        # Prima regola per priorita' che copra il minuto E abbia immagini: lo
        # stesso criterio di resolve_random, cosi' l'anteprima e lo scheduler non
        # possono divergere su una regola dal pool vuoto.
        scelto = None
        for rule, origine, start, end in regole:
            if not _copre(start, end, minuto):
                continue
            sig = _rule_signature(rule)
            if sig not in pools:
                pools[sig] = sorted(candidates_for_rule(config, rule))
            if pools[sig]:
                scelto = (rule, origine, sig, pools[sig])
                break
        if scelto is None:
            continue

        rule, origine, sig, pool = scelto
        rotate = _rotate_of(rule)
        ordinale = _window_ordinal(rule, t, rotate, config)
        finestra = (sig, ordinale)
        if finestra == ultima_finestra:
            continue  # stessa finestra del minuto precedente, gia' assegnata
        ultima_finestra = finestra

        n = len(pool)
        giro, pos = divmod(ordinale, n)
        mazzo = _mazzo(pool, sig, giro)

        scelta = mazzo[pos]
        for k in range(n):  # avanza finche' non trovi una non ancora uscita oggi
            carta = mazzo[(pos + k) % n]
            if carta not in usate:
                scelta = carta
                break
        usate.add(scelta)

        sequenza.append(
            {
                "minuto": minuto,
                "rule": rule,
                "origine": origine,
                "ordinale": ordinale,
                "image": scelta,
                "pool": n,
            }
        )

    return sequenza


def _scelta_giornaliera(config: dict, now: datetime) -> str | None:
    """L'immagine che tocca alla finestra corrente, o None se nessuna regola copre."""
    if not regole_candidate(config, now):
        return None
    sequenza = sequenza_giornaliera(config, now.date(), now.hour * 60 + now.minute)
    return sequenza[-1]["image"] if sequenza else None


def pick_from_rule(
    config: dict, rule: dict, now: datetime, force_new: bool = False
) -> str | None:
    """
    L'immagine che tocca alla finestra di rotazione corrente.

    La sceglie `sequenza_giornaliera`, dal mazzo: qui non si conta nulla e non si
    guarda lo storico. Questa funzione ci mette solo la persistenza intorno.

    La scelta viene registrata in log.json per la finestra corrente, cosi' i giri
    successivi dello scheduler la ritrovano invece di riscrivere lo sfondo. Il
    calcolo e' deterministico e darebbe comunque lo stesso risultato: il memo
    serve a non toccare il desktop per niente, e a far durare un'estrazione
    forzata fino alla fine della sua finestra.

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
    # Chiave del memo: l'ordinale della finestra. Col vecchio bucket d'orologio
    # una fascia solare (che non parte su un multiplo di rotate) poteva cambiare
    # finestra senza cambiare bucket, e lo sfondo restava fermo.
    bucket = _window_ordinal(rule, now, rotate, config)

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
    giorno = now.date()

    slot = _first_match(config.get("special_days", {}).get(today_key), now, config)
    if slot:
        cat = f"casuale, giorno speciale {today_key} {_window(slot, giorno, config)}"
        return resolve_path(config, slot["image"]), cat

    for rule, origine in regole_candidate(config, now):
        image = pick_from_rule(config, rule, now)
        if image:
            cat = f"casuale, {origine} {_window(rule, giorno, config)}{_tags_of(rule)}"
            return resolve_path(config, image), cat
        log(f"[WARN] Regola '{origine}' senza immagini valide, proseguo.")

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


def acquisisci_istanza_unica() -> bool:
    """
    True se siamo la prima istanza, False se un'altra e' gia' in esecuzione.

    Il mutex va tenuto in una variabile globale: se il riferimento viene
    raccolto dal garbage collector, Windows lo rilascia e il blocco sparisce.
    Non serve chiuderlo all'uscita, ci pensa il sistema anche in caso di crash.
    """
    global _mutex

    ERROR_ALREADY_EXISTS = 183
    _mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Chametiger_SingleInstance"
    )

    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return False
    return _mutex != 0


_mutex = None


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
                invalida_cache_file()
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
            invalida_cache_file()
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
            invalida_cache_file()
            if self.config.get("mode") != MODE_RANDOM:
                log("[INFO] Estrazione disponibile solo in modalita' casuale.")
                return

            now = datetime.now()
            candidate = regole_candidate(self.config, now)
            if not candidate:
                log("[INFO] Nessuna regola casuale attiva adesso.")
                return

            for rule, origine in candidate:
                image = pick_from_rule(self.config, rule, now, force_new=True)
                if image:
                    category = (
                        f"estrazione forzata, {origine} "
                        f"{_window(rule, now.date(), self.config)}{_tags_of(rule)}"
                    )
                    set_wallpaper(resolve_path(self.config, image), category)
                    return

            log("[WARN] Nessuna immagine valida per la regola attiva.")
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
        if not acquisisci_istanza_unica():
            log("[INFO] Chametiger e' gia' in esecuzione, questa istanza si chiude.")
            return
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
