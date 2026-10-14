"""
Orari solari per Chametiger — alba, tramonto, crepuscolo, mezzogiorno vero.

Nessuna dipendenza esterna: l'algoritmo e' quello del NOAA / Almanacco Nautico,
accurato al minuto alle nostre latitudini.

Sull'ORA LEGALE. Il calcolo produce l'ora UTC dell'evento; la conversione in ora
locale passa da `datetime.fromtimestamp()`, che applica le regole del fuso del
sistema operativo, ora legale compresa. Per questo non serve ne' `tzdata` ne'
`zoneinfo` (che su Windows senza tzdata non funziona) ne' librerie tipo astral:
il sistema operativo sa gia' quando scatta l'ora legale, e i datetime restituiti
sono naive-locali, gli stessi con cui lavora `datetime.now()` in app.py.
"""

import re
import math
import socket
import calendar
from datetime import date, datetime, timedelta
from functools import lru_cache

# Zenit del sole per ogni evento, in gradi.
#   90.833 = disco sull'orizzonte, tenendo conto di rifrazione e raggio apparente
#   96.0   = crepuscolo civile (sole 6 gradi sotto l'orizzonte)
ZENITH_SUN = 90.833
ZENITH_CIVIL = 96.0

# Le ancore utilizzabili nei campi "from" / "to" delle regole.
ANCHORS = ("dawn", "sunrise", "noon", "sunset", "dusk")

ANCHOR_LABELS = {
    "dawn": "crepuscolo del mattino",
    "sunrise": "alba",
    "noon": "mezzogiorno solare",
    "sunset": "tramonto",
    "dusk": "crepuscolo della sera",
}

# "sunset", "sunset-40m", "sunset + 1h", "dawn-20"  (senza unita' = minuti)
_ANCHOR_RE = re.compile(
    r"^(" + "|".join(ANCHORS) + r")\s*(?:([+-])\s*(\d+)\s*([mh]?))?$",
    re.IGNORECASE,
)


def is_solar(t) -> bool:
    """True se la stringa e' un'ancora solare e non un orario di orologio."""
    return isinstance(t, str) and _ANCHOR_RE.match(t.strip()) is not None


def parse_anchor(t: str) -> tuple[str, int] | None:
    """'sunset-40m' -> ('sunset', -40). None se non e' un'ancora valida."""
    m = _ANCHOR_RE.match(str(t).strip())
    if not m:
        return None
    anchor, segno, valore, unita = m.groups()
    offset = 0
    if valore:
        offset = int(valore) * (60 if (unita or "").lower() == "h" else 1)
        if segno == "-":
            offset = -offset
    return anchor.lower(), offset


# "min(sunset+2m, 18:00)", "max(dusk, 16:00)": il primo / l'ultimo degli orari
# elencati, ricalcolato giorno per giorno. Dentro: orologio o ancore solari.
_MINMAX_RE = re.compile(r"^(min|max)\s*\((.*)\)$", re.IGNORECASE)
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_clock(t) -> int | None:
    """'18:00' -> 1080 minuti. None se non e' un orario di orologio valido."""
    m = _CLOCK_RE.match(str(t).strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if h <= 23 and mi <= 59 else None


def parse_minmax(t) -> tuple[str, list[str]] | None:
    """
    'min(sunset+2m, 18:00)' -> ('min', ['sunset+2m', '18:00']). None se non e'
    un min/max valido: almeno due orari, ognuno orologio o ancora solare.
    """
    m = _MINMAX_RE.match(str(t).strip())
    if not m:
        return None
    orari = [o.strip() for o in m.group(2).split(",")]
    if len(orari) < 2 or not all(is_solar(o) or parse_clock(o) is not None for o in orari):
        return None
    return m.group(1).lower(), orari


def is_minmax(t) -> bool:
    """True se l'orario e' un min(...) / max(...)."""
    return isinstance(t, str) and parse_minmax(t) is not None


def minmax_minutes(t, giorno: date, lat: float, lon: float) -> int | None:
    """
    Il min/max in minuti dalla mezzanotte di quel giorno, in [0, 1440).
    None se non e' un min/max o se quel giorno uno degli eventi non avviene.

    Il confronto e' fatto prima di riportare in [0, 1440): 'min(dusk+3h, 23:30)'
    a giugno vale 23:30 anche se dusk+3h cade dopo la mezzanotte.
    """
    parsed = parse_minmax(t)
    if not parsed:
        return None
    funzione, orari = parsed
    valori = []
    for o in orari:
        ancora = parse_anchor(o)
        minuti = solar_minutes(ancora[0], ancora[1], giorno, lat, lon) if ancora else parse_clock(o)
        if minuti is None:
            return None
        valori.append(minuti)
    return (min(valori) if funzione == "min" else max(valori)) % 1440


def minutes(t, giorno: date, lat: float, lon: float) -> int | None:
    """
    Qualunque orario valido in minuti [0, 1440) di quel giorno: orologio,
    ancora o min/max. None se non e' valido o se l'evento quel giorno manca.
    """
    if is_minmax(t):
        return minmax_minutes(t, giorno, lat, lon)
    ancora = parse_anchor(t)
    if ancora:
        minuti = solar_minutes(ancora[0], ancora[1], giorno, lat, lon)
        return None if minuti is None else minuti % 1440
    return parse_clock(t)


def fascia_assente(frm, to, start: int, end: int) -> bool:
    """
    Una fascia con min()/max() non scavalca mai la mezzanotte: se quel giorno
    finisce prima di cominciare, o insieme, quel giorno non esiste.

    E' il motivo per cui min/max servono: 'sunset-58m -> min(sunset+2m, 18:00)'
    a giugno diventa 19:30 -> 18:00, e letta come le altre fasce coprirebbe
    tutto il giorno passando per la mezzanotte. Le fasce senza min/max
    restano come sempre: '23:00 -> dawn-20m' scavalca la mezzanotte.
    """
    return (is_minmax(frm) or is_minmax(to)) and end <= start


def format_anchor(anchor: str, offset: int) -> str:
    """('sunset', -40) -> 'sunset-40m'. L'inverso di parse_anchor."""
    if not offset:
        return anchor
    return f"{anchor}{'+' if offset > 0 else '-'}{abs(offset)}m"


def _sun_event(giorno: date, lat: float, lon: float, zenith: float, rising: bool):
    """
    Istante dell'evento come datetime naive locale, o None se in quel giorno il
    sole non raggiunge quello zenit (alle latitudini polari accade per settimane).
    """
    n = giorno.timetuple().tm_yday
    lng_hour = lon / 15.0

    # Istante approssimato, poi raffinato: alba verso le 6, tramonto verso le 18
    t = n + ((6.0 if rising else 18.0) - lng_hour) / 24.0

    m = 0.9856 * t - 3.289  # anomalia media del Sole
    l = (  # longitudine vera
        m
        + 1.916 * math.sin(math.radians(m))
        + 0.020 * math.sin(math.radians(2 * m))
        + 282.634
    ) % 360

    # Ascensione retta, riportata nello stesso quadrante della longitudine
    ra = math.degrees(math.atan(0.91764 * math.tan(math.radians(l)))) % 360
    ra += (l // 90) * 90 - (ra // 90) * 90
    ra /= 15.0

    sin_dec = 0.39782 * math.sin(math.radians(l))
    cos_dec = math.cos(math.asin(sin_dec))

    cos_h = (
        math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(lat))
    ) / (cos_dec * math.cos(math.radians(lat)))
    if not -1.0 <= cos_h <= 1.0:
        return None  # sole sempre sopra o sempre sotto quello zenit

    h = math.degrees(math.acos(cos_h))
    h = (360.0 - h) if rising else h
    h /= 15.0

    # Tempo locale medio dell'evento, poi riportato a UTC togliendo la
    # longitudine: senza `- lng_hour` l'orario sbaglia di 4 minuti per grado.
    tempo_locale = h + ra - 0.06571 * t - 6.622
    ut = (tempo_locale - lng_hour) % 24  # ora UTC dell'evento

    # UTC -> timestamp -> ora locale. E' fromtimestamp che applica l'ora legale.
    mezzanotte_utc = calendar.timegm(giorno.timetuple())
    return datetime.fromtimestamp(mezzanotte_utc + ut * 3600).replace(microsecond=0)


@lru_cache(maxsize=8192)
def sun_times(giorno: date, lat: float, lon: float) -> dict:
    """
    Gli orari solari del giorno, come datetime naive locali.
    Le chiavi assenti (None) sono gli eventi che quel giorno non avvengono.

    In cache: `_scelta_giornaliera` ricostruisce la giornata minuto per minuto e
    interroga gli stessi orari centinaia di volte.
    """
    alba = _sun_event(giorno, lat, lon, ZENITH_SUN, True)
    tramonto = _sun_event(giorno, lat, lon, ZENITH_SUN, False)

    # Mezzogiorno solare vero: meta' esatta dell'arco diurno.
    mezzogiorno = None
    if alba and tramonto:
        mezzogiorno = alba + (tramonto - alba) / 2

    return {
        "dawn": _sun_event(giorno, lat, lon, ZENITH_CIVIL, True),
        "sunrise": alba,
        "noon": mezzogiorno,
        "sunset": tramonto,
        "dusk": _sun_event(giorno, lat, lon, ZENITH_CIVIL, False),
    }


def solar_minutes(
    anchor: str, offset: int, giorno: date, lat: float, lon: float
) -> int | None:
    """
    L'ancora, in minuti dalla mezzanotte locale di quel giorno, offset incluso.
    None se quel giorno l'evento non esiste: chi chiama ripiega sull'orologio.

    Il risultato puo' uscire da [0, 1440) — 'dusk+3h' a giugno supera la
    mezzanotte — e va bene: chi confronta lavora in minuti, non in datetime.
    """
    evento = sun_times(giorno, lat, lon).get(anchor)
    if evento is None:
        return None
    return evento.hour * 60 + evento.minute + offset


# Il nome del PC non cambia mentre l'app gira: coords lo chiede di continuo.
HOSTNAME = socket.gethostname()


def coords(config: dict) -> tuple[float, float]:
    """
    Latitudine e longitudine di questo PC. Default: Napoli.

    Come la cartella delle immagini (`base_path` + `path_map`): `latitude` e
    `longitude` valgono per tutti, `position_map` le sostituisce sui PC
    elencati, col nome del computer come chiave. Unico posto da cui passano
    orari solari, meteo e GUI, cosi' nessuno legge le coordinate di un altro.
    """
    voce = (config.get("position_map") or {}).get(HOSTNAME) or {}
    try:
        lat = float(voce.get("latitude", config.get("latitude", 40.8518)))
        lon = float(voce.get("longitude", config.get("longitude", 14.2681)))
    except (TypeError, ValueError, AttributeError):
        return 40.8518, 14.2681
    return lat, lon


def describe(t, giorno: date, lat: float, lon: float) -> str:
    """
    'sunset-40m' -> 'sunset-40m (19:12)'. Per il log e per la GUI: senza l'orario
    reale accanto, una regola ancorata al sole non si riesce a verificare a occhio.
    """
    if is_minmax(t):
        minuti = minmax_minutes(t, giorno, lat, lon)
        if minuti is None:
            return f"{t} (n.d.)"
        return f"{t} ({minuti // 60:02d}:{minuti % 60:02d})"
    parsed = parse_anchor(t) if isinstance(t, str) else None
    if not parsed:
        return str(t)
    minuti = solar_minutes(parsed[0], parsed[1], giorno, lat, lon)
    if minuti is None:
        return f"{t} (n.d.)"
    return f"{t} ({(minuti // 60) % 24:02d}:{minuti % 60:02d})"
