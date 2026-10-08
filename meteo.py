"""
Meteo per la scelta delle immagini: previsioni orarie da Open-Meteo.

Open-Meteo e' gratuito, senza chiave e senza registrazione, e lavora sulle
stesse latitudine e longitudine degli orari solari. Il METAR sarebbe stato
un'osservazione puntuale di un aeroporto: va bene per "piove adesso", non per
programmare le prossime ore fra un download e l'altro.

Il download lo fa curl.exe, incluso in Windows 10/11, in un processo a parte.
Con urllib l'app si sarebbe portata dietro per sempre http e ssl (circa 4 MB
misurati) per una richiesta ogni cinque ore; cosi' il processo del tray non
cresce di niente.

Le previsioni finiscono in meteo.json, una riga per ora: la legge anche la GUI
per l'anteprima, e dopo un riavvio non serve riscaricare.

Ripiego: senza previsioni valide (nessuna connessione, file vecchio, coordinate
cambiate, curl assente) `del_giorno` ritorna None e il motore ignora il meteo e
i tag pioggia/temporale, come prima di questo modulo.
"""

import json
import os
import subprocess
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import sun

METEO_FILE = Path(__file__).parent.resolve() / "meteo.json"

URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
    "&hourly=weather_code&forecast_days=2&timezone=auto&timeformat=unixtime"
)

DEFAULT_ORE = 5  # ogni quante ore riscaricare
ORE_MIN, ORE_MAX = 1, 10  # limiti di aggiorna_ore, gli stessi della GUI
MAX_ETA_ORE = 12  # oltre, le previsioni non si usano piu'
DEFAULT_MINIMO = 2  # immagini sotto cui il meteo non restringe il pool
RIPROVA_MINUTI = 30  # dopo un download fallito, prima di riprovare

# Stati di un'ora. "asciutto" non e' l'assenza di dati: vuol dire che le
# previsioni ci sono e non danno pioggia.
TEMPORALE = "temporale"
PIOGGIA = "pioggia"
ASCIUTTO = "asciutto"


def stato_da_codice(codice: int) -> str:
    """Codice meteo WMO -> stato. Neve e nebbia contano come asciutto."""
    if codice in (95, 96, 99):
        return TEMPORALE
    if 51 <= codice <= 67 or 80 <= codice <= 82:  # pioviggine, pioggia, rovesci
        return PIOGGIA
    return ASCIUTTO


def impostazioni(config: dict) -> tuple[bool, float]:
    """(attivo, ore fra un download e l'altro), con le ore riportate nei limiti."""
    m = config.get("meteo") or {}
    try:
        ore = float(m.get("aggiorna_ore", DEFAULT_ORE))
    except (TypeError, ValueError):
        ore = DEFAULT_ORE
    return bool(m.get("attivo", True)), min(max(ore, ORE_MIN), ORE_MAX)


def minimo(config: dict) -> int:
    """
    Quante immagini devono restare perche' il meteo restringa il pool, come
    `prefer_min`. Con una sola immagine di pioggia la fascia resterebbe ferma
    su quella per tutte le ore di pioggia.
    """
    try:
        n = int((config.get("meteo") or {}).get("minimo", DEFAULT_MINIMO))
    except (TypeError, ValueError):
        return DEFAULT_MINIMO
    return max(1, n)


def _coords(config: dict) -> tuple[float, float]:
    # Arrotondate: le previsioni sono su una griglia di qualche km, e un
    # ritocco alla quarta cifra non deve buttare il file.
    lat, lon = sun.coords(config)
    return round(lat, 2), round(lon, 2)


# Il contenuto di meteo.json, riletto solo quando il file cambia. Lo scheduler
# lo interroga a ogni giro e la GUI a ogni anteprima: un os.stat costa meno di
# un json.load.
_cache: dict = {"mtime": None, "dati": None}


def _carica() -> dict | None:
    try:
        mtime = os.stat(METEO_FILE).st_mtime
    except OSError:
        return None
    if mtime != _cache["mtime"]:
        try:
            with open(METEO_FILE, encoding="utf-8") as f:
                dati = json.load(f)
        except (OSError, json.JSONDecodeError):
            dati = None
        _cache.update(mtime=mtime, dati=dati if isinstance(dati, dict) else None)
    return _cache["dati"]


def _valide(dati: dict | None, config: dict) -> bool:
    """Previsioni recenti e scaricate per la posizione attuale."""
    if not dati or not impostazioni(config)[0]:
        return False
    if [dati.get("lat"), dati.get("lon")] != list(_coords(config)):
        return False
    try:
        eta = time.time() - float(dati.get("scaricato", 0))
    except (TypeError, ValueError):
        return False
    return 0 <= eta <= MAX_ETA_ORE * 3600


def del_giorno(config: dict, giorno: date) -> dict[int, str] | None:
    """
    {ora: stato} per quel giorno, con le sole ore coperte dalle previsioni.
    None se non ci sono previsioni valide: il motore ignora il meteo.
    """
    dati = _carica()
    if not _valide(dati, config):
        return None
    prefisso = giorno.isoformat() + "T"
    return {
        int(chiave[-2:]): stato
        for chiave, stato in (dati.get("ore") or {}).items()
        if chiave.startswith(prefisso)
    }


def ultimo_download() -> datetime | None:
    """Quando sono state scaricate le previsioni in meteo.json, se ci sono."""
    try:
        return datetime.fromtimestamp(float((_carica() or {})["scaricato"]))
    except (KeyError, TypeError, ValueError, OSError):
        return None


# Ultimo tentativo fallito, per non lanciare curl a ogni giro quando si e'
# offline. In memoria: dopo un riavvio si riprova subito, ed e' giusto cosi'.
_ultimo_errore: float = 0.0

# Scheduler e menu del tray possono chiedere un download insieme: uno alla volta.
_download_lock = threading.Lock()


def aggiorna_se_serve(config: dict, log, forza: bool = False) -> bool:
    """
    Riscarica le previsioni se sono piu' vecchie di `aggiorna_ore` o se la
    posizione e' cambiata; con forza=True subito, anche dopo un errore recente.
    True se ha scaricato. Non solleva mai: un errore vuol dire solo niente
    meteo fino al prossimo tentativo.
    """
    with _download_lock:
        return _aggiorna(config, log, forza)


def _aggiorna(config: dict, log, forza: bool) -> bool:
    global _ultimo_errore

    attivo, ore = impostazioni(config)
    if not attivo:
        if forza:
            log('[METEO] Meteo disattivato nel config ("attivo": false).')
        return False
    if not forza:
        dati = _carica()
        if _valide(dati, config) and time.time() - float(dati["scaricato"]) < ore * 3600:
            return False
        if time.time() - _ultimo_errore < RIPROVA_MINUTI * 60:
            return False

    lat, lon = _coords(config)
    try:
        uscita = subprocess.run(
            ["curl.exe", "-s", "-f", "--max-time", "20", URL.format(lat=lat, lon=lon)],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if uscita.returncode != 0:
            raise RuntimeError(f"curl ha risposto {uscita.returncode}")
        risposta = json.loads(uscita.stdout)
        orari = risposta["hourly"]["time"]
        codici = risposta["hourly"]["weather_code"]
    except Exception as e:
        # Lo scheduler lo dice una volta per serie di errori; una richiesta
        # dal menu vuole sempre una risposta.
        if forza or not _ultimo_errore:
            log(f"[METEO] Previsioni non disponibili ({e}): scelgo senza meteo.")
        _ultimo_errore = time.time()
        return False

    # Ora locale del PC, come gli orari solari: fromtimestamp applica il fuso
    # e l'ora legale del sistema.
    ore_previste = {}
    for ts, codice in zip(orari, codici):
        if codice is None:
            continue
        chiave = datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H")
        ore_previste[chiave] = stato_da_codice(int(codice))

    nuovo = {"scaricato": time.time(), "lat": lat, "lon": lon, "ore": ore_previste}
    try:
        with open(METEO_FILE, "w", encoding="utf-8") as f:
            json.dump(nuovo, f, indent=1)
    except OSError as e:
        log(f"[METEO] Impossibile scrivere meteo.json: {e}")
        return False

    _ultimo_errore = 0.0
    log(f"[METEO] Previsioni aggiornate: {riassunto(ore_previste)}.")
    return True


def riassunto(ore: dict[str, str]) -> str:
    """'pioggia 14-17, temporale 20-21' sulle ore a venire, per il log."""
    adesso = datetime.now().strftime("%Y-%m-%dT%H")
    tratti: list[list] = []  # [stato, prima ora, ultima ora, chiave dell'ultima]
    for chiave in sorted(ore):
        if chiave < adesso or ore[chiave] == ASCIUTTO:
            continue
        h = chiave[-2:]
        if tratti and tratti[-1][0] == ore[chiave] and tratti[-1][3] == _precedente(chiave):
            tratti[-1][2], tratti[-1][3] = h, chiave
        else:
            tratti.append([ore[chiave], h, h, chiave])
    if not tratti:
        return "niente pioggia nelle prossime ore"
    return ", ".join(f"{s} {a}-{int(b) + 1:02d}" for s, a, b, _ in tratti)


def _precedente(chiave: str) -> str:
    """La chiave dell'ora prima: '2026-10-08T00' -> '2026-10-07T23'."""
    t = datetime.strptime(chiave, "%Y-%m-%dT%H") - timedelta(hours=1)
    return t.strftime("%Y-%m-%dT%H")
