"""
Genera il riferimento per i test del motore Kotlin: cosa sceglie il Python
(app.py, che e' la specifica) per ogni finestra e ogni ora di un intervallo
di giorni.

Non tocca i file di Chametiger: li importa e sostituisce da fuori tre cose.

  esistenza dei file  sempre vera: il pool viene dalle chiavi di image_library,
                      come sul telefono, e non dal disco di questo PC
  posizione           quella di DISPOSITIVO in position_map, invece del nome
                      del PC su cui gira lo script
  meteo               un calendario sintetico, scritto nel riferimento insieme
                      ai risultati, cosi' il test Kotlin lo legge invece di
                      doverlo rigenerare

Il fuso e' quello del sistema operativo, come in app.py: va generato su un PC
in ora italiana, e il test Kotlin usa Europe/Rome.

Due scenari, ognuno con la sua copia del config:
  con_meteo    il config com'e', col meteo sintetico
  senza_meteo  lo stesso config con "attivo": false, su un intervallo piu'
               corto: le firme perdono la parte m:, e i tag pioggia/temporale
               contano come gli altri

Formato (TSV, UTF-8), una riga per voce:
  M  giorno  24 lettere, una per ora: A asciutto, P pioggia, T temporale
  S  giorno  minuto  ordinale  immagine  firma     una per finestra della giornata
  H  giorno  ora  immagine                         la scelta alle hh:00, vuota se nessuna

Uso, dalla cartella di questo file:  py genera_riferimento.py
"""

import copy
import json
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

QUI = Path(__file__).parent.resolve()
CHAMETIGER = QUI.parents[2]
USCITA = QUI.parent / "src" / "test" / "resources" / "riferimento"

DISPOSITIVO = "Federico"

SCENARI = {
    "con_meteo": (date(2026, 12, 20), date(2028, 1, 10), True),
    "senza_meteo": (date(2027, 3, 1), date(2027, 4, 30), False),
}

sys.path.insert(0, str(CHAMETIGER))

import app  # noqa: E402
import meteo  # noqa: E402
import sun  # noqa: E402

LETTERE = {meteo.ASCIUTTO: "A", meteo.PIOGGIA: "P", meteo.TEMPORALE: "T"}


def meteo_sintetico(giorno: date) -> dict[int, str]:
    """
    Pioggia e temporale a giorni e ore fissi, per passare dai rami del meteo:
    mattine di pioggia, pomeriggi di temporale seguiti da pioggia, giornate
    intere di pioggia. Il resto asciutto, come senza dati.
    """
    ore = dict.fromkeys(range(24), meteo.ASCIUTTO)
    n = giorno.toordinal()
    if n % 5 == 0:
        ore.update(dict.fromkeys(range(7, 13), meteo.PIOGGIA))
    if n % 7 == 3:
        ore.update(dict.fromkeys(range(15, 21), meteo.TEMPORALE))
        ore.update(dict.fromkeys(range(21, 24), meteo.PIOGGIA))
    if n % 11 == 6:
        ore.update(dict.fromkeys(range(24), meteo.PIOGGIA))
    return ore


def del_giorno(config: dict, giorno: date) -> dict[int, str] | None:
    """Come meteo.del_giorno, ma dal calendario sintetico invece che da meteo.json."""
    if not meteo.impostazioni(config)[0]:
        return None
    return meteo_sintetico(giorno)


def prepara():
    app._esiste = lambda percorso: True
    app.resolve_path = lambda config, filename: filename  # la chiave, non il percorso
    app.log = lambda msg: None
    sun.HOSTNAME = DISPOSITIVO
    meteo.del_giorno = del_giorno
    # pick_from_rule scrive il memo della finestra: lontano dal log.json vero
    app.HISTORY_FILE = Path(tempfile.mkdtemp()) / "log.json"


def giorni(dal: date, al: date):
    g = dal
    while g <= al:
        yield g
        g += timedelta(days=1)


def genera(nome: str, config: dict, dal: date, al: date):
    cartella = USCITA / nome
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    righe = [
        f"# Riferimento {nome}: app.py {app.VERSIONE}, dispositivo {DISPOSITIVO},"
        f" dal {dal} al {al}. Generato da genera_riferimento.py, non modificare."
    ]
    for g in giorni(dal, al):
        ore = meteo.del_giorno(config, g)
        if ore is not None:
            righe.append(f"M\t{g}\t{''.join(LETTERE[ore[h]] for h in range(24))}")
        for voce in app.sequenza_giornaliera(config, g):
            firma = app._rule_signature(voce["rule"])
            righe.append(
                f"S\t{g}\t{voce['minuto']}\t{voce['ordinale']}\t{voce['image']}\t{firma}"
            )
        for h in range(24):
            immagine, _ = app.resolve_random(config, datetime(g.year, g.month, g.day, h))
            righe.append(f"H\t{g}\t{h}\t{immagine or ''}")
        print(f"\r{nome} {g}", end="", flush=True)
    print()

    with open(cartella / "riferimento.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(righe) + "\n")


def main():
    prepara()
    with open(CHAMETIGER / "config.json", encoding="utf-8") as f:
        base = app.ensure_defaults(json.load(f))
    for nome, (dal, al, attivo) in SCENARI.items():
        config = copy.deepcopy(base)
        config["meteo"]["attivo"] = attivo
        genera(nome, config, dal, al)


if __name__ == "__main__":
    main()
