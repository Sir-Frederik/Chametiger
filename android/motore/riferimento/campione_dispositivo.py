"""
Il campione del riferimento per il test strumentato, quello che gira sul
telefono: sessanta giorni presi dal riferimento gia' generato, scelti per
passare dai casi in cui la runtime di Android potrebbe dare risposte diverse
dalla JVM del desktop (java.time, dati dei fusi, ICU).

  - i due cambi d'ora, col giorno prima e quello dopo
  - Pasqua e i confini dell'evento che ne dipende (pasqua-5 .. pasqua+2)
  - il confine d'anno, all'inizio e alla fine dell'intervallo
  - la settimana con piu' ore di pioggia e temporale
  - i giorni in cui una fascia con min()/max() compare o sparisce
  - i confini delle stagioni e degli altri eventi
  - e giorni sparsi fino a sessanta

Non ricalcola niente col Python: copia le righe del riferimento. Rilancialo
dopo genera_riferimento.py.

Uso, dalla cartella di questo file:  py campione_dispositivo.py
"""

import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

QUI = Path(__file__).parent.resolve()
CHAMETIGER = QUI.parents[2]
SORGENTE = QUI.parent / "src" / "test" / "resources" / "riferimento"
USCITA = QUI.parents[1] / "app" / "src" / "androidTest" / "assets" / "riferimento"

GIORNI = 60
# Lo scenario senza meteo copre marzo e aprile 2027: cambio d'ora e Pasqua
# vanno provati anche li', dove le firme non hanno la parte m:
SENZA_METEO = [date(2027, 3, 27), date(2027, 3, 28), date(2027, 3, 29), date(2027, 3, 30)]

sys.path.insert(0, str(CHAMETIGER))

import app  # noqa: E402
import date_mobili  # noqa: E402
import json  # noqa: E402


def leggi(scenario: str) -> tuple[list[str], dict[date, list[str]]]:
    intestazione, righe = [], {}
    for riga in (SORGENTE / scenario / "riferimento.tsv").read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        if riga.startswith("#"):
            intestazione.append(riga)
            continue
        righe.setdefault(date.fromisoformat(riga.split("\t")[1]), []).append(riga)
    return intestazione, righe


def intorno(g: date, prima: int = 1, dopo: int = 1) -> list[date]:
    return [g + timedelta(days=d) for d in range(-prima, dopo + 1)]


def ultima_domenica(anno: int, mese: int) -> date:
    g = date(anno, mese + 1, 1) - timedelta(days=1)
    return g - timedelta(days=(g.weekday() + 1) % 7)


def settimana_piovosa(righe: dict[date, list[str]]) -> list[date]:
    """I sette giorni consecutivi con piu' ore di pioggia o temporale."""
    bagnate = {}
    for g, rr in righe.items():
        meteo = next(r for r in rr if r.startswith("M\t")).split("\t")[2]
        bagnate[g] = sum(c != "A" for c in meteo)
    giorni = sorted(bagnate)
    inizio = max(range(len(giorni) - 6), key=lambda i: sum(bagnate[g] for g in giorni[i : i + 7]))
    return giorni[inizio : inizio + 7]


def regole_minmax(config: dict) -> list[dict]:
    def da(rr):
        for chiave, v in (rr or {}).items():
            gruppi = v.values() if chiave == "overrides" else [v]
            for regole in gruppi:
                yield from regole or []

    tutte = list(da(config["random_rules"]))
    for p in config["seasons"] + config["events"]:
        tutte += list(da(p.get("random_rules")))
    return [r for r in tutte if app.sun.is_minmax(r.get("from")) or app.sun.is_minmax(r.get("to"))]


def cambi_minmax(config: dict, giorni: list[date]) -> list[date]:
    """I giorni attorno a quelli in cui una fascia min()/max() compare o sparisce."""
    lat, lon = config["position_map"]["Federico"].values()
    out = []
    for r in regole_minmax(config):
        prima = None
        for g in giorni:
            start = app._resolve_minuti(r["from"], g, lat, lon)
            end = app._resolve_minuti(r["to"], g, lat, lon)
            assente = app.sun.fascia_assente(r["from"], r["to"], start, end)
            if prima is not None and assente != prima:
                out += [g - timedelta(days=1), g]
            prima = assente
    return out


def confini_periodi(config: dict, anni: list[int]) -> list[date]:
    out = []
    for p in config["seasons"] + config["events"]:
        for anno in anni:
            for estremo in (p["from"], p["to"]):
                o = date_mobili.ordinale(estremo, anno)
                if o:
                    out.append(date(anno, o // 100, o % 100))
    return out


def scrivi(scenario: str, intestazione: list[str], righe: dict, scelti: list[date], motivi: dict):
    cartella = USCITA / scenario
    cartella.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SORGENTE / scenario / "config.json", cartella / "config.json")
    with open(cartella / "campione.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# Campione di {len(scelti)} giorni da riferimento.tsv, scelto da campione_dispositivo.py. Non modificare.\n")
        for riga in intestazione:
            f.write(riga + "\n")
        for g in scelti:
            f.write(f"# {g} {', '.join(sorted(motivi[g]))}\n")
            for riga in righe[g]:
                f.write(riga + "\n")


def main():
    intestazione, righe = leggi("con_meteo")
    config = json.loads((SORGENTE / "con_meteo" / "config.json").read_text(encoding="utf-8"))
    giorni = sorted(righe)
    anni = sorted({g.year for g in giorni})
    pasqua = date_mobili.pasqua(2027)

    motivi: dict[date, set[str]] = {}

    def aggiungi(lista, motivo):
        for g in lista:
            if g in righe and (g in motivi or len(motivi) < GIORNI - len(SENZA_METEO)):
                motivi.setdefault(g, set()).add(motivo)

    for anno in anni:
        if date(anno, 3, 1) <= giorni[-1]:
            aggiungi(intorno(ultima_domenica(anno, 3)), "ora legale")
        if date(anno, 10, 1) <= giorni[-1]:
            aggiungi(intorno(ultima_domenica(anno, 10)), "ora solare")
    aggiungi(intorno(pasqua), "Pasqua")
    aggiungi([pasqua - timedelta(days=6), pasqua - timedelta(days=5), pasqua + timedelta(days=2), pasqua + timedelta(days=3)], "evento Pasqua")
    for anno in anni[1:]:
        aggiungi(intorno(date(anno, 1, 1), 2, 1), "confine d'anno")
    aggiungi(settimana_piovosa(righe), "settimana di pioggia")
    aggiungi(cambi_minmax(config, giorni), "fascia min/max")
    aggiungi(confini_periodi(config, anni), "confine di stagione o evento")

    # Il resto a intervalli regolari, perche' anche i giorni qualsiasi contino
    restanti = [g for g in giorni if g not in motivi]
    passo = max(1, len(restanti) // max(1, GIORNI - len(SENZA_METEO) - len(motivi)))
    aggiungi(restanti[::passo], "giorno qualsiasi")

    scelti = sorted(motivi)
    scrivi("con_meteo", intestazione, righe, scelti, motivi)

    intestazione_s, righe_s = leggi("senza_meteo")
    motivi_s = {g: {"senza meteo: ora legale e Pasqua"} for g in SENZA_METEO}
    scrivi("senza_meteo", intestazione_s, righe_s, SENZA_METEO, motivi_s)

    print(f"con_meteo: {len(scelti)} giorni, senza_meteo: {len(SENZA_METEO)}")
    for g in scelti:
        print(f"  {g}  {', '.join(sorted(motivi[g]))}")


if __name__ == "__main__":
    main()
