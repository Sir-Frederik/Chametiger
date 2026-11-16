"""
Meteo per la scelta delle immagini: le prossime 10 ore, ora attuale compresa.



  Met Norway   le previsioni ora per ora (locationforecast). Sostituisce
               Open-Meteo, che l'8/10/2026 dava "coperto" su Napoli mentre a

  Open-Meteo   in alternativa, col modello ICON-2I di ItaliaMeteo/ARPAE
               (2,2 km, 72 ore, solo Italia e dintorni): i millimetri di
               pioggia ora per ora. Si sceglie con "fonte" nel config.

Il download lo fa curl.exe, incluso in Windows 10/11, in un processo a parte.
Con urllib l'app si sarebbe portata dietro per sempre http e ssl (circa 4 MB
misurati) per una richiesta ogni qualche ora; cosi' il processo del tray non
cresce di niente.

Le ore finiscono in meteo.json: la legge anche la GUI per l'anteprima, e dopo
un riavvio non serve riscaricare.

Ripiego: senza dati validi (nessuna connessione, file vecchio, coordinate
cambiate, curl assente) `del_giorno` da' tutte le ore come asciutte, e cosi' le
ore oltre le 10 scaricate: senza un motivo per crederla, la pioggia non si
mostra. Solo col meteo disattivato ritorna None e il motore ignora il meteo:
i tag pioggia/temporale contano come tutti gli altri.
"""

import json
# import math  # serviva solo a _km, per il METAR
import os
import subprocess
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import sun
from versione import VERSIONE

METEO_FILE = Path(__file__).parent.resolve() / "meteo.json"

# "complete" e non "compact": solo lui ha le nubi per strato, che servono al
# nuvoloso (vedi copertura_bassa).
URL_PREVISIONI = (
    "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    "?lat={lat:.2f}&lon={lon:.2f}"
)
# ICON-2I: precipitation sono i mm caduti nell'ora PRIMA dell'orario indicato,
# weather_code serve solo per il temporale, le nubi basse e medie (%) per il
# nuvoloso. Orari in secondi dall'epoca.
URL_OPEN_METEO = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat:.2f}&longitude={lon:.2f}"
    "&hourly=precipitation,weather_code,cloud_cover_low,cloud_cover_mid"
    "&models=italia_meteo_arpae_icon_2i"
    "&forecast_hours={ore}&timeformat=unixtime&timezone=GMT"
)
# URL_METAR = (
#     "https://aviationweather.gov/api/data/metar"
#     "?bbox={sud:.2f},{ovest:.2f},{nord:.2f},{est:.2f}&format=json"
# )
# Met Norway rifiuta (403) le richieste senza un'identita' dell'applicazione.
USER_AGENT = f"Chametiger/{VERSIONE} github.com/Sir-Frederik/Chametiger"

ORE_PREVISTE = 10  # quante ore tenere, quella attuale compresa
DEFAULT_ORE = 5  # ogni quante ore riscaricare
ORE_MIN, ORE_MAX = 1, 10  # limiti di aggiorna_ore, gli stessi della GUI
MAX_ETA_ORE = 12  # oltre, i dati non si usano piu'
DEFAULT_MINIMO = 2  # immagini sotto cui il meteo non restringe il pool
RIPROVA_MINUTI = 30  # dopo un download fallito, prima di riprovare

# Le fonti delle previsioni: chiave nel config -> nome per log e GUI.
MET_NORWAY = "met_norway"
OPEN_METEO = "open_meteo"
FONTI = {MET_NORWAY: "Met Norway", OPEN_METEO: "Open-Meteo ICON-2I"}
# Open-Meteo da' millimetri, non simboli: sotto questa soglia l'ora non e' di
# pioggia ma nuvolosa, come la pioggia leggera di Met Norway.
DEFAULT_SOGLIA_MM = 1
# Sotto la soglia della pioggia, da quanti mm l'ora e' nuvolosa anche se la
# copertura del cielo non lo dice.
PIOGGIA_LEGGERA_MM = 0.1
# Copertura di nubi basse e medie (%) da cui il cielo conta come nuvoloso.
DEFAULT_SOGLIA_NUVOLE = 90
# Nelle prime ore nuvolose di fila, la probabilita' (%) che una finestra peschi
# solo fra le immagini di nuvole: la prima ora, la seconda, la terza. Dopo, il
# pool e' quello misto.
DEFAULT_PRIORITA_NUVOLE = (100, 60, 40)
# METAR_RAGGIO_KM = 30  # stazioni piu' lontane non dicono che tempo fa qui
# METAR_MAX_ETA_MIN = 90  # i METAR escono ogni 30-60 minuti

# Stati di un'ora. Senza dati l'ora vale "asciutto": la pioggia si mostra solo
# quando una fonte la da'.
TEMPORALE = "temporale"
PIOGGIA = "pioggia"
# Cielo coperto o pioggia leggera. Non restringe il pool come la pioggia:
# ammette le immagini col tag TAG_NUVOLE accanto a quelle di sempre.
NUVOLOSO = "nuvoloso"
ASCIUTTO = "asciutto"

# Il tag delle immagini di cielo coperto. Per pioggia e temporale il tag ha lo
# stesso nome dello stato.
TAG_NUVOLE = "nuvole"


def copertura_bassa(basse, medie) -> float | None:
    """
    Quanto cielo coprono le nubi basse e medie insieme (%), come se gli strati
    fossero indipendenti: 60% basse e 80% medie lasciano scoperto il 40% del
    20%, cioe' coprono il 92%. Le nubi alte (cirri, velature) non contano: il
    cielo resta chiaro anche al 100%, e col solo totale ore cosi' passavano
    per nuvolose. None se mancano tutti e due gli strati.
    """
    if basse is None and medie is None:
        return None
    b = 0.0 if basse is None else float(basse)
    m = 0.0 if medie is None else float(medie)
    return 100 - (100 - b) * (100 - m) / 100


def stato_da_simbolo(simbolo: str) -> str:
    """
    Simbolo di Met Norway -> stato: 'heavyrainandthunder' -> temporale,
    'rainshowers_day' -> pioggia. La pioggia leggera ('lightrain',
    'lightrainshowers_day', 'lightsleet') e il coperto ('cloudy') sono
    nuvoloso: la pioggia si mostra solo quando si vede davvero. Neve, nebbia
    e poco nuvoloso restano asciutto. Il tuono vince anche sul leggero.
    Il coperto puo' essere solo un velo di nubi alte: lo corregge _previsioni
    con gli strati.
    """
    s = simbolo.split("_")[0]
    if "thunder" in s:
        return TEMPORALE
    if "rain" in s or "sleet" in s:
        return NUVOLOSO if s.startswith("light") else PIOGGIA
    return NUVOLOSO if s == "cloudy" else ASCIUTTO


# def stato_da_metar(wx: str | None) -> str:
#     """
#     Fenomeni del METAR -> stato: '-TSRA' e 'VCTS' -> temporale, 'SHRA' e
#     '-DZ' -> pioggia, nessun fenomeno -> asciutto. Il temporale vince su tutto.
#     """
#     gruppi = [g.lstrip("+-") for g in (wx or "").split()]
#     if any("TS" in g for g in gruppi):
#         return TEMPORALE
#     if any("RA" in g or "DZ" in g or g in ("SH", "VCSH") for g in gruppi):
#         return PIOGGIA
#     return ASCIUTTO


def impostazioni(config: dict) -> tuple[bool, float]:
    """(attivo, ore fra un download e l'altro), con le ore riportate nei limiti."""
    m = config.get("meteo") or {}
    try:
        ore = float(m.get("aggiorna_ore", DEFAULT_ORE))
    except (TypeError, ValueError):
        ore = DEFAULT_ORE
    return bool(m.get("attivo", True)), min(max(ore, ORE_MIN), ORE_MAX)


def fonte(config: dict) -> str:
    """La fonte scelta nel config; Met Norway se manca o non e' una di FONTI."""
    f = (config.get("meteo") or {}).get("fonte")
    return f if f in FONTI else MET_NORWAY


def soglia_mm(config: dict) -> float:
    """I mm in un'ora da cui Open-Meteo conta come pioggia (`soglia_mm`)."""
    try:
        mm = float((config.get("meteo") or {}).get("soglia_mm", DEFAULT_SOGLIA_MM))
    except (TypeError, ValueError):
        return DEFAULT_SOGLIA_MM
    return mm if mm > 0 else DEFAULT_SOGLIA_MM


def soglia_nuvole(config: dict) -> float:
    """La copertura di nubi basse e medie (%) da cui il cielo conta come nuvoloso (`soglia_nuvole`)."""
    try:
        n = float((config.get("meteo") or {}).get("soglia_nuvole", DEFAULT_SOGLIA_NUVOLE))
    except (TypeError, ValueError):
        return DEFAULT_SOGLIA_NUVOLE
    return n if 0 < n <= 100 else DEFAULT_SOGLIA_NUVOLE


def priorita_nuvole(config: dict) -> list[int]:
    """
    Le percentuali di `nuvole_priorita`, una per ora nuvolosa di fila, intere
    fra 0 e 100. Se non e' una lista di numeri valgono quelle di default; una
    lista vuota toglie la priorita'.
    """
    valore = (config.get("meteo") or {}).get("nuvole_priorita", DEFAULT_PRIORITA_NUVOLE)
    if not isinstance(valore, (list, tuple)):
        return list(DEFAULT_PRIORITA_NUVOLE)
    try:
        return [min(100, max(0, int(float(x)))) for x in valore]
    except (TypeError, ValueError, OverflowError):
        return list(DEFAULT_PRIORITA_NUVOLE)


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
    """Dati recenti, scaricati per la posizione attuale dalla fonte scelta."""
    if not dati or not impostazioni(config)[0]:
        return False
    # I meteo.json di prima non hanno "fonte": erano di Met Norway
    if dati.get("fonte", MET_NORWAY) != fonte(config):
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
    {ora: stato} per tutte le 24 ore di quel giorno. Le ore che i dati non
    coprono, o tutte se i dati mancano o non valgono, sono asciutte: offline
    le immagini di pioggia uscivano a caso come le altre, anche col sole.
    None solo col meteo disattivato: il motore ignora il meteo.
    """
    if not impostazioni(config)[0]:
        return None
    ore = dict.fromkeys(range(24), ASCIUTTO)
    dati = _carica()
    if _valide(dati, config):
        prefisso = giorno.isoformat() + "T"
        ore.update(
            (int(chiave[-2:]), stato)
            for chiave, stato in (dati.get("ore") or {}).items()
            if chiave.startswith(prefisso)
        )
    return ore


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


def _previsioni(lat: float, lon: float, nuvole: float = DEFAULT_SOGLIA_NUVOLE) -> dict[str, str]:
    """
    {ora locale: stato} da Met Norway, dall'ora attuale per ORE_PREVISTE ore.
    Gli orari arrivano in UTC: fromtimestamp applica il fuso e l'ora legale
    del sistema, come per gli orari solari.

    Un 'cloudy' e' nuvoloso solo se le nubi basse e medie coprono almeno
    `nuvole` %; se no e' un velo di nubi alte, e l'ora e' asciutta. Senza gli
    strati (una risposta "compact") resta nuvoloso. La pioggia leggera e'
    nuvoloso sempre.
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
            stato = stato_da_simbolo(simbolo)
            if simbolo.split("_")[0] == "cloudy":
                strati = passo["data"].get("instant", {}).get("details", {})
                coperto = copertura_bassa(
                    strati.get("cloud_area_fraction_low"),
                    strati.get("cloud_area_fraction_medium"),
                )
                if coperto is not None and coperto < nuvole:
                    stato = ASCIUTTO
            ore[chiave] = stato
        if len(ore) == ORE_PREVISTE:
            break
    return ore


def _previsioni_open_meteo(
    lat: float, lon: float, soglia: float, nuvole: float = DEFAULT_SOGLIA_NUVOLE
) -> dict[str, str]:
    """
    {ora locale: stato} da Open-Meteo (ICON-2I), dall'ora attuale per
    ORE_PREVISTE ore. I mm di un orario sono quelli caduti nell'ora prima:
    il valore delle 15:00 e' la pioggia dell'ora 14. Temporale coi codici
    WMO 95-99, pioggia da `soglia` mm in su; sotto, nuvoloso da
    PIOGGIA_LEGGERA_MM o con le nubi basse e medie da `nuvole` % in su
    (copertura_bassa: le nubi alte non contano).
    Fuori dall'area del modello i valori sono null: allora solleva, e si
    sceglie come col sereno.
    """
    # Due ore in piu': la prima risposta e' l'ora attuale, che parla di quella prima
    risposta = _scarica(URL_OPEN_METEO.format(lat=lat, lon=lon, ore=ORE_PREVISTE + 2))
    orari = risposta["hourly"]
    adesso = _chiave(datetime.now())
    ore = {}
    for t, mm, codice, basse, medie in zip(
        orari["time"],
        orari["precipitation"],
        orari["weather_code"],
        orari["cloud_cover_low"],
        orari["cloud_cover_mid"],
    ):
        chiave = _chiave(datetime.fromtimestamp(t) - timedelta(hours=1))
        if chiave < adesso or mm is None:
            continue
        coperto = copertura_bassa(basse, medie)
        if codice is not None and codice >= 95:
            ore[chiave] = TEMPORALE
        elif mm >= soglia:
            ore[chiave] = PIOGGIA
        elif mm >= PIOGGIA_LEGGERA_MM or (coperto is not None and coperto >= nuvole):
            ore[chiave] = NUVOLOSO
        else:
            ore[chiave] = ASCIUTTO
        if len(ore) == ORE_PREVISTE:
            break
    if not ore:
        raise RuntimeError("nessuna ora nella risposta (fuori dall'area di ICON-2I?)")
    return ore


# Ho temporaneamente tolto Metar perchè non è affidabile per i luoghi lontani dagli aereoporti.
# Meglio usare direttamente Met Norway. _km serviva solo a _metar.

# def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
#     """Distanza approssimata: entro qualche decina di km basta e avanza."""
#     x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
#     y = math.radians(lat2 - lat1)
#     return 6371 * math.hypot(x, y)


# def _metar(lat: float, lon: float) -> tuple[str, str] | None:
#     """
#     (descrizione, stato) dell'osservazione piu' vicina e recente, per esempio
#     ('LIRN -TSRA', 'temporale'). None se non c'e' una stazione entro
#     METAR_RAGGIO_KM con un METAR degli ultimi METAR_MAX_ETA_MIN minuti.
#     """
#     zona = URL_METAR.format(
#         sud=lat - 0.5, nord=lat + 0.5, ovest=lon - 0.5, est=lon + 0.5
#     )
#     limite = time.time() - METAR_MAX_ETA_MIN * 60
#     candidati = []
#     for m in _scarica(zona):
#         try:
#             distanza = _km(lat, lon, float(m["lat"]), float(m["lon"]))
#             quando = float(m["obsTime"])
#         except (KeyError, TypeError, ValueError):
#             continue
#         if distanza <= METAR_RAGGIO_KM and quando >= limite:
#             candidati.append((distanza, -quando, m))
#     if not candidati:
#         return None
#     m = min(candidati, key=lambda c: c[:2])[2]
#     wx = m.get("wxString") or ""
#     return f"{m.get('icaoId', '?')} {wx or 'niente fenomeni'}", stato_da_metar(wx)


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
        if (
            _valide(dati, config)
            and time.time() - float(dati["scaricato"]) < ore * 3600
        ):
            return False
        if time.time() - _ultimo_errore < RIPROVA_MINUTI * 60:
            return False

    lat, lon = _coords(config)
    scelta = fonte(config)
    errori = []
    try:
        if scelta == OPEN_METEO:
            ore_meteo = _previsioni_open_meteo(
                lat, lon, soglia_mm(config), soglia_nuvole(config)
            )
        else:
            ore_meteo = _previsioni(lat, lon, soglia_nuvole(config))
    except Exception as e:
        ore_meteo = {}
        errori.append(f"{FONTI[scelta]}: {e}")
        # try:
        #     osservato = _metar(lat, lon)
        # except Exception as e:
        #     osservato = None
        #     errori.append(f"METAR: {e}")

        # # L'osservazione dice che tempo fa davvero adesso: vince sulla previsione.
        # # Senza previsioni resta comunque l'ora attuale.
        # if osservato:
        #     ore_meteo[_chiave(datetime.now())] = osservato[1]

        # if not ore_meteo:
        #     # Lo scheduler lo dice una volta per serie di errori; una richiesta
        #     # dal menu vuole sempre una risposta.
        if forza or not _ultimo_errore:
            motivo = "; ".join(errori) or "nessun dato"
            log(f"[METEO] Meteo non disponibile ({motivo}): scelgo come col sereno.")
        _ultimo_errore = time.time()
        return False

    nuovo = {
        "scaricato": time.time(),
        "lat": lat,
        "lon": lon,
        "fonte": scelta,
        # "osservato": osservato[0] if osservato else None,
        "ore": dict(
            sorted({**passate_di_oggi(_carica(), config), **ore_meteo}.items())
        ),
    }
    try:
        with open(METEO_FILE, "w", encoding="utf-8") as f:
            json.dump(nuovo, f, indent=1)
    except OSError as e:
        log(f"[METEO] Impossibile scrivere meteo.json: {e}")
        return False

    _ultimo_errore = 0.0
    fonti = [FONTI[scelta]]
    # if osservato:
    #     fonti.append(f"adesso METAR {osservato[0]}")
    nota = f" Non disponibile: {'; '.join(errori)}." if errori else ""
    log(f"[METEO] Aggiornato ({', '.join(fonti)}): {riassunto(ore_meteo)}.{nota}")
    return True


def passate_di_oggi(dati: dict | None, config: dict) -> dict[str, str]:
    """
    Le ore di oggi gia' passate nel meteo.json di prima, da tenere nel nuovo.

    Il motore rifa' la sequenza del giorno dalla mezzanotte, ora per ora col
    suo tempo: se un download butta le ore passate, queste tornano asciutte,
    le finestre di stamattina cambiano mazzo e la finestra di adesso puo'
    cambiare immagine anche se il tempo di quest'ora e' lo stesso
    """
    if not _valide(dati, config):
        return {}
    adesso = _chiave(datetime.now())
    oggi = adesso[:10] + "T"
    return {
        chiave: stato
        for chiave, stato in (dati.get("ore") or {}).items()
        if chiave.startswith(oggi) and chiave < adesso
    }


def riassunto(ore: dict[str, str]) -> str:
    """'pioggia 14-17, temporale 20-21' sulle ore a venire, per il log."""
    adesso = _chiave(datetime.now())
    tratti: list[list] = []  # [stato, prima ora, ultima ora, chiave dell'ultima]
    for chiave in sorted(ore):
        if chiave < adesso or ore[chiave] == ASCIUTTO:
            continue
        h = chiave[-2:]
        if (
            tratti
            and tratti[-1][0] == ore[chiave]
            and tratti[-1][3] == _precedente(chiave)
        ):
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
