"""
Il riferimento per la conversione del meteo sul telefono: cosa ricava meteo.py
(la specifica) da una risposta di Met Norway, per confrontarlo col Kotlin.

Basta un simbolo classificato in modo diverso perche' telefono e PC, con la
stessa previsione, scelgano da mazzi diversi: la firma della regola contiene
lo stato del meteo. Per questo si confrontano le due implementazioni sulle
stesse risposte, non su una tabella scritta a mano.

Le risposte, nella cartella di uscita:
  reale.json         una risposta vera per Portici, scaricata col tray
  simboli.json       tutti i simboli di Met Norway, uno per ora, piu' qualche
                     stringa insolita
  ora_legale.json    attorno al 28/3/2027, con passi senza next_1_hours
  ora_solare.json    attorno al 31/10/2027: due ore UTC finiscono nella
                     stessa ora locale
  rotta.json         senza timeseries: meteo.py solleva, e il telefono deve
                     fallire allo stesso modo

Il fuso e' quello del sistema operativo, come in meteo.py: va generato su un
PC in ora italiana, e il test Kotlin usa Europe/Rome.

Formato di atteso.tsv (UTF-8):
  S  simbolo  stato                                ogni simbolo di simboli.json
  P  risposta  adesso  ore  riassunto              ore = "chiave=stato,..." nell'ordine di meteo.py,
                                                   riassunto = la riga del log di meteo.riassunto
  E  risposta  adesso                              meteo.py solleva

Uso, dalla cartella di questo file:  py genera_riferimento_meteo.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

QUI = Path(__file__).parent.resolve()
CHAMETIGER = QUI.parents[2]
USCITA = QUI.parents[1] / "app" / "src" / "test" / "resources" / "meteo"

sys.path.insert(0, str(CHAMETIGER))

import meteo  # noqa: E402

# L'elenco dei simboli di Met Norway (weathericon), refusi compresi: e' quello
# che arriva davvero nelle risposte. I simboli con _day/_night/_polartwilight
# sono le varianti col sole o la luna.
BASE = """
clearsky cloudy fair fog heavyrain heavyrainandthunder heavyrainshowers
heavyrainshowersandthunder heavysleet heavysleetandthunder heavysleetshowers
heavysleetshowersandthunder heavysnow heavysnowandthunder heavysnowshowers
heavysnowshowersandthunder lightrain lightrainandthunder lightrainshowers
lightrainshowersandthunder lightsleet lightsleetandthunder lightsleetshowers
lightsnow lightsnowandthunder lightsnowshowers lightssleetshowersandthunder
lightssnowshowersandthunder partlycloudy rain rainandthunder rainshowers
rainshowersandthunder sleet sleetandthunder sleetshowers sleetshowersandthunder
snow snowandthunder snowshowers snowshowersandthunder
""".split()
CON_SOLE = {"clearsky", "fair", "partlycloudy"} | {b for b in BASE if "showers" in b}
INSOLITI = ["Rain", "rain_and_thunder", "thunder", "_day", "x_rain", "pioggia", "sleet_night", "drizzle"]


def simboli() -> list[str]:
    out = []
    for b in BASE:
        out.append(b)
        if b in CON_SOLE:
            out += [f"{b}_day", f"{b}_night", f"{b}_polartwilight"]
    return out + INSOLITI


def risposta(passi: list[tuple[datetime, str | None]]) -> dict:
    """Una risposta di locationforecast coi passi dati; None = solo next_6_hours."""
    serie = []
    for t, simbolo in passi:
        dati = {"instant": {"details": {"air_temperature": 15.0}}}
        if simbolo is None:
            dati["next_6_hours"] = {"summary": {"symbol_code": "cloudy"}}
        else:
            dati["next_1_hours"] = {"summary": {"symbol_code": simbolo}, "details": {}}
        serie.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "data": dati})
    return {"type": "Feature", "properties": {"meta": {}, "timeseries": serie}}


def ore_utc(da: datetime, n: int) -> list[datetime]:
    return [da + timedelta(hours=i) for i in range(n)]


def prepara() -> dict[str, dict]:
    risposte = {"reale.json": json.loads((USCITA / "reale.json").read_text(encoding="utf-8"))}

    s = simboli()
    risposte["simboli.json"] = risposta(list(zip(ore_utc(datetime(2027, 5, 1, tzinfo=timezone.utc), len(s)), s)))

    giro = ["rain", "clearsky_day", "lightrainandthunder", "sleet", "fog", "heavysnow"]
    # Ora legale: alle 01:00 UTC del 28/3/2027 le 02:00 locali non esistono
    passi = []
    for i, t in enumerate(ore_utc(datetime(2027, 3, 27, 18, tzinfo=timezone.utc), 18)):
        passi.append((t, None if i in (4, 9) else ("" if i == 6 else giro[i % len(giro)])))
    risposte["ora_legale.json"] = risposta(passi)
    # Ora solare: 00:00 e 01:00 UTC del 31/10/2027 sono entrambe le 02 locali
    passi = [(t, giro[i % len(giro)]) for i, t in enumerate(ore_utc(datetime(2027, 10, 30, 20, tzinfo=timezone.utc), 16))]
    risposte["ora_solare.json"] = risposta(passi)

    risposte["rotta.json"] = {"type": "Feature", "properties": {"meta": {}}}
    return risposte


def previsioni(risposta: dict, adesso: datetime) -> tuple[dict[str, str], str]:
    """meteo._previsioni e meteo.riassunto con la risposta data e l'orologio fermo su `adesso`."""

    class Orologio(datetime):
        @classmethod
        def now(cls, tz=None):
            return adesso

    vecchio_scarica, vecchio_datetime = meteo._scarica, meteo.datetime
    meteo._scarica = lambda url: risposta
    meteo.datetime = Orologio
    try:
        ore = meteo._previsioni(40.82, 14.34)
        return ore, meteo.riassunto(ore)
    finally:
        meteo._scarica, meteo.datetime = vecchio_scarica, vecchio_datetime


def istanti(nome: str, risposta: dict) -> list[datetime]:
    """Prima della serie, al suo inizio, nel mezzo e verso la fine, in ora locale."""
    serie = (risposta.get("properties") or {}).get("timeseries") or []
    if not serie:
        return [datetime(2027, 1, 1, 12)]
    tempi = [datetime.fromisoformat(p["time"].replace("Z", "+00:00")).timestamp() for p in serie]
    locali = [datetime.fromtimestamp(t) for t in tempi]
    scelti = {locali[0] - timedelta(hours=3), locali[0], locali[len(locali) // 3], locali[-4], locali[-1]}
    if nome == "ora_solare.json":
        scelti |= {datetime(2027, 10, 31, 1, 30), datetime(2027, 10, 31, 2, 30)}
    if nome == "ora_legale.json":
        scelti |= {datetime(2027, 3, 28, 1, 59), datetime(2027, 3, 28, 3, 0)}
    return sorted(t.replace(minute=0, second=0) if nome == "reale.json" else t for t in scelti)


def main():
    risposte = prepara()
    righe = []
    for s in simboli():
        righe.append(f"S\t{s}\t{meteo.stato_da_simbolo(s)}")
    for nome, r in risposte.items():
        if nome != "reale.json":
            (USCITA / nome).write_text(json.dumps(r, indent=1), encoding="utf-8", newline="\n")
        for adesso in istanti(nome, r):
            quando = adesso.strftime("%Y-%m-%dT%H:%M")
            try:
                ore, riassunto = previsioni(r, adesso)
            except Exception:
                righe.append(f"E\t{nome}\t{quando}")
                continue
            righe.append(f"P\t{nome}\t{quando}\t" + ",".join(f"{k}={v}" for k, v in ore.items()) + f"\t{riassunto}")

    with open(USCITA / "atteso.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("# Riferimento della conversione meteo: meteo.py di Chametiger. Generato da genera_riferimento_meteo.py, non modificare.\n")
        f.write("\n".join(righe) + "\n")
    print(f"{sum(r.startswith('S') for r in righe)} simboli, {sum(r.startswith('P') for r in righe)} previsioni, "
          f"{sum(r.startswith('E') for r in righe)} errori")


if __name__ == "__main__":
    main()
