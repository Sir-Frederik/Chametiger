"""
Le date di stagioni ed eventi: fisse ('12-25') o relative a Pasqua.

Una data fissa si scrive 'MM-GG' e vale ogni anno uguale. Una relativa si
scrive 'pasqua', 'pasqua-5', 'pasqua+2' (la 'g' finale e gli spazi sono
ammessi: 'pasqua - 5g'), e si ricalcola anno per anno: Pasqua cade fra il 22
marzo e il 25 aprile, e un evento a data fissa sarebbe giusto un anno su tanti.

Il confronto resta quello di sempre, sugli ordinali MMGG (1225): una data
relativa si risolve nell'ordinale dell'anno richiesto, e da li' in poi e'
indistinguibile da una fissa.

La usano sia il motore (app.py) sia l'editor (gui.py), che cosi' non deve
importare il tray per sapere quando cade Pasqua.
"""

import re
from datetime import date, timedelta
from functools import lru_cache

GIORNI_MESE = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

_PASQUA = re.compile(r"^pasqua\s*(?:([+-])\s*(\d{1,3})\s*g?)?$", re.IGNORECASE)


@lru_cache(maxsize=256)
def pasqua(anno: int) -> date:
    """La domenica di Pasqua (calendario gregoriano, algoritmo di Meeus)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def scostamento_pasqua(s: str) -> int | None:
    """'pasqua-5' -> -5, 'pasqua' -> 0; None se la data non e' relativa a Pasqua."""
    trovato = _PASQUA.match(str(s).strip())
    if not trovato:
        return None
    segno, giorni = trovato.groups()
    if not giorni:
        return 0
    return -int(giorni) if segno == "-" else int(giorni)


def e_mobile(s: str) -> bool:
    return scostamento_pasqua(s) is not None


def _fissa(s: str) -> tuple[int, int] | None:
    """'10-20' -> (10, 20). Accetta anche 'AAAA-MM-GG', ignorando l'anno."""
    pezzi = str(s).strip().split("-")
    if len(pezzi) == 3:
        pezzi = pezzi[1:]
    if len(pezzi) != 2:
        return None
    try:
        mese, giorno = int(pezzi[0]), int(pezzi[1])
    except ValueError:
        return None
    if not (1 <= mese <= 12 and 1 <= giorno <= GIORNI_MESE[mese - 1]):
        return None
    return mese, giorno


def valida(s: str) -> bool:
    """Data fissa valida (il 29 febbraio si accetta) o relativa a Pasqua."""
    return e_mobile(s) or _fissa(s) is not None


@lru_cache(maxsize=4096)
def ordinale(s: str, anno: int) -> int | None:
    """La data come ordinale MMGG in quell'anno: '10-20' -> 1020, 'pasqua' -> 405 nel 2026."""
    delta = scostamento_pasqua(s)
    if delta is not None:
        g = pasqua(anno) + timedelta(days=delta)
        return g.month * 100 + g.day
    fissa = _fissa(s)
    if fissa is None:
        return None
    return fissa[0] * 100 + fissa[1]


def in_data(s: str, anno: int) -> date | None:
    """La data vera in quell'anno, per mostrarla. None per il 29/2 di un anno non bisestile."""
    o = ordinale(s, anno)
    if o is None:
        return None
    try:
        return date(anno, o // 100, o % 100)
    except ValueError:
        return None
