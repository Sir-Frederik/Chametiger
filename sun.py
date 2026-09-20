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


def coords(config: dict) -> tuple[float, float]:
    """Latitudine e longitudine dal config. Default: Napoli."""
    try:
        lat = float(config.get("latitude", 40.8518))
        lon = float(config.get("longitude", 14.2681))
    except (TypeError, ValueError):
        return 40.8518, 14.2681
    return lat, lon


def describe(t, giorno: date, lat: float, lon: float) -> str:
    """
    'sunset-40m' -> 'sunset-40m (19:12)'. Per il log e per la GUI: senza l'orario
    reale accanto, una regola ancorata al sole non si riesce a verificare a occhio.
    """
    parsed = parse_anchor(t) if isinstance(t, str) else None
    if not parsed:
        return str(t)
    minuti = solar_minutes(parsed[0], parsed[1], giorno, lat, lon)
    if minuti is None:
        return f"{t} (n.d.)"
    return f"{t} ({(minuti // 60) % 24:02d}:{minuti % 60:02d})"
