"""
Meteo per la scelta delle immagini: le prossime 10 ore, ora attuale compresa.

Due fonti, gratuite e senza chiave, sulle stesse coordinate degli orari solari:

  Met Norway   le previsioni ora per ora (locationforecast). Sostituisce
               Open-Meteo, che l'8/10/2026 dava "coperto" su Napoli mentre a
               Capodichino c'era il temporale, e lo spostava di due ore dopo
  METAR        l'ora attuale, dalla stazione meteo piu' vicina entro 30 km
               (a Napoli Capodichino, LIRN). E' un'osservazione, non una
               previsione: quando c'e' vince lei. Se manca o e' vecchia
               resta la previsione

Il download lo fa curl.exe, incluso in Windows 10/11, in un processo a parte.
Con urllib l'app si sarebbe portata dietro per sempre http e ssl (circa 4 MB
misurati) per una richiesta ogni qualche ora; cosi' il processo del tray non
cresce di niente.

Le ore finiscono in meteo.json: la legge anche la GUI per l'anteprima, e dopo
un riavvio non serve riscaricare.

Ripiego: senza dati validi (nessuna connessione, file vecchio, coordinate
cambiate, curl assente) `del_giorno` ritorna None e il motore ignora il meteo e
i tag pioggia/temporale. Anche le ore oltre le 10 scaricate restano senza meteo.
"""

import json
import math
import os
import subprocess
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import sun
from versione import VERSIONE

METEO_FILE = Path(__file__).parent.resolve() / "meteo.json"

URL_PREVISIONI = (
    "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    "?lat={lat:.2f}&lon={lon:.2f}"
)
URL_METAR = (
    "https://aviationweather.gov/api/data/metar"
    "?bbox={sud:.2f},{ovest:.2f},{nord:.2f},{est:.2f}&format=json"
)
# Met Norway rifiuta (403) le richieste senza un'identita' dell'applicazione.
USER_AGENT = f"Chametiger/{VERSIONE} github.com/Sir-Frederik/Chametiger"

ORE_PREVISTE = 10  # quante ore tenere, quella attuale compresa
DEFAULT_ORE = 5  # ogni quante ore riscaricare
ORE_MIN, ORE_MAX = 1, 10  # limiti di aggiorna_ore, gli stessi della GUI
MAX_ETA_ORE = 12  # oltre, i dati non si usano piu'
DEFAULT_MINIMO = 2  # immagini sotto cui il meteo non restringe il pool
RIPROVA_MINUTI = 30  # dopo un download fallito, prima di riprovare
METAR_RAGGIO_KM = 30  # stazioni piu' lontane non dicono che tempo fa qui
METAR_MAX_ETA_MIN = 90  # i METAR escono ogni 30-60 minuti

# Stati di un'ora. "asciutto" non e' l'assenza di dati: vuol dire che i dati
# ci sono e non danno pioggia.
TEMPORALE = "temporale"
PIOGGIA = "pioggia"
ASCIUTTO = "asciutto"


def stato_da_simbolo(simbolo: str) -> str:
    """
    Simbolo di Met Norway -> stato: 'heavyrainandthunder' -> temporale,
    'lightrainshowers_day' -> pioggia. Neve e nebbia contano come asciutto.
    """
    s = simbolo.split("_")[0]
    if "thunder" in s:
        return TEMPORALE
    if "rain" in s or "sleet" in s:
        return PIOGGIA
    return ASCIUTTO


def stato_da_metar(wx: str | None) -> str:
    """
    Fenomeni del METAR -> stato: '-TSRA' e 'VCTS' -> temporale, 'SHRA' e
    '-DZ' -> pioggia, nessun fenomeno -> asciutto. Il temporale vince su tutto.
    """
    gruppi = [g.lstrip("+-") for g in (wx or "").split()]
    if any("TS" in g for g in gruppi):
        return TEMPORALE
    if any("RA" in g or "DZ" in g or g in ("SH", "VCSH") for g in gruppi):
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
    """Dati recenti e scaricati per la posizione attuale."""
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
    {ora: stato} per quel giorno, con le sole ore coperte dai dati.
    None se non ci sono dati validi: il motore ignora il meteo.
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
    """Quando sono stati scaricati i dati in meteo.json, se ci sono."""
    try:
        return datetime.fromtimestamp(float((_carica() or {})["scaricato"]))
    except (KeyError, TypeError, ValueError, OSError):
        return None


# ── Download ────────────────────────────────────────────────────────────────


def _scarica(url: str):
    """JSON da un URL, via curl. Solleva se qualcosa va storto."""
    uscita = subprocess.run(
        ["curl.exe", "-s", "-f", "--max-time", "20", "-A", USER_AGENT, url],
        capture_output=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if uscita.returncode != 0:
        raise RuntimeError(f"curl ha risposto {uscita.returncode}")
    return json.loads(uscita.stdout)


def _chiave(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H")


def _previsioni(lat: float, lon: float) -> dict[str, str]:
    """
    {ora locale: stato} da Met Norway, dall'ora attuale per ORE_PREVISTE ore.
    Gli orari arrivano in UTC: fromtimestamp applica il fuso e l'ora legale
    del sistema, come per gli orari solari.
    """
    risposta = _scarica(URL_PREVISIONI.format(lat=lat, lon=lon))
    adesso = _chiave(datetime.now())
    ore = {}
    for passo in risposta["properties"]["timeseries"]:
        simbolo = (
            passo["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code")
        )
        if not simbolo:
            continue  # oltre le prime ~60 ore Met Norway passa a passi di 6 ore
        utc = datetime.fromisoformat(passo["time"].replace("Z", "+00:00"))
        chiave = _chiave(datetime.fromtimestamp(utc.timestamp()))
        if chiave >= adesso:
            ore[chiave] = stato_da_simbolo(simbolo)
        if len(ore) == ORE_PREVISTE:
            break
    return ore


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza approssimata: entro qualche decina di km basta e avanza."""
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371 * math.hypot(x, y)


def _metar(lat: float, lon: float) -> tuple[str, str] | None:
    """
    (descrizione, stato) dell'osservazione piu' vicina e recente, per esempio
    ('LIRN -TSRA', 'temporale'). None se non c'e' una stazione entro
    METAR_RAGGIO_KM con un METAR degli ultimi METAR_MAX_ETA_MIN minuti.
    """
    zona = URL_METAR.format(sud=lat - 0.5, nord=lat + 0.5, ovest=lon - 0.5, est=lon + 0.5)
    limite = time.time() - METAR_MAX_ETA_MIN * 60
    candidati = []
    for m in _scarica(zona):
        try:
            distanza = _km(lat, lon, float(m["lat"]), float(m["lon"]))
            quando = float(m["obsTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if distanza <= METAR_RAGGIO_KM and quando >= limite:
            candidati.append((distanza, -quando, m))
    if not candidati:
        return None
    m = min(candidati, key=lambda c: c[:2])[2]
    wx = m.get("wxString") or ""
    return f"{m.get('icaoId', '?')} {wx or 'niente fenomeni'}", stato_da_metar(wx)


# Ultimo tentativo fallito, per non lanciare curl a ogni giro quando si e'
# offline. In memoria: dopo un riavvio si riprova subito, ed e' giusto cosi'.
_ultimo_errore: float = 0.0

# Scheduler e menu del tray possono chiedere un download insieme: uno alla volta.
_download_lock = threading.Lock()


def aggiorna_se_serve(config: dict, log, forza: bool = False) -> bool:
    """
    Riscarica il meteo se e' piu' vecchio di `aggiorna_ore` o se la posizione
    e' cambiata; con forza=True subito, anche dopo un errore recente.
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
    errori = []
    try:
        ore_meteo = _previsioni(lat, lon)
    except Exception as e:
        ore_meteo = {}
        errori.append(f"Met Norway: {e}")
    try:
        osservato = _metar(lat, lon)
    except Exception as e:
        osservato = None
        errori.append(f"METAR: {e}")

    # L'osservazione dice che tempo fa davvero adesso: vince sulla previsione.
    # Senza previsioni resta comunque l'ora attuale.
    if osservato:
        ore_meteo[_chiave(datetime.now())] = osservato[1]

    if not ore_meteo:
        # Lo scheduler lo dice una volta per serie di errori; una richiesta
        # dal menu vuole sempre una risposta.
        if forza or not _ultimo_errore:
            motivo = "; ".join(errori) or "nessun dato"
            log(f"[METEO] Meteo non disponibile ({motivo}): scelgo senza meteo.")
        _ultimo_errore = time.time()
        return False

    nuovo = {
        "scaricato": time.time(),
        "lat": lat,
        "lon": lon,
        "osservato": osservato[0] if osservato else None,
        "ore": dict(sorted(ore_meteo.items())),
    }
    try:
        with open(METEO_FILE, "w", encoding="utf-8") as f:
            json.dump(nuovo, f, indent=1)
    except OSError as e:
        log(f"[METEO] Impossibile scrivere meteo.json: {e}")
        return False

    _ultimo_errore = 0.0
    fonti = [] if any(e.startswith("Met Norway") for e in errori) else ["Met Norway"]
    if osservato:
        fonti.append(f"adesso METAR {osservato[0]}")
    nota = f" Non disponibile: {'; '.join(errori)}." if errori else ""
    log(f"[METEO] Aggiornato ({', '.join(fonti)}): {riassunto(ore_meteo)}.{nota}")
    return True


def riassunto(ore: dict[str, str]) -> str:
    """'pioggia 14-17, temporale 20-21' sulle ore a venire, per il log."""
    adesso = _chiave(datetime.now())
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
        return f"niente pioggia nelle prossime {ORE_PREVISTE} ore"
    return ", ".join(f"{s} {a}-{int(b) + 1:02d}" for s, a, b, _ in tratti)


def _precedente(chiave: str) -> str:
    """La chiave dell'ora prima: '2026-10-08T00' -> '2026-10-07T23'."""
    t = datetime.strptime(chiave, "%Y-%m-%dT%H") - timedelta(hours=1)
    return t.strftime("%Y-%m-%dT%H")
