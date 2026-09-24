"""
Verifica che ogni immagine con almeno un tag esca davvero, con il config attuale.

Simula un anno a partire da oggi usando le stesse funzioni dello scheduler
(periodi, override, fasce solari, divieti stagionali, special_days) e fa due
controlli:

  1. eleggibilita': l'immagine sta nel pool di almeno una regola che vince
     davvero in qualche minuto (la prima per priorita' con pool non vuoto)
  2. uscite reali: ricostruisce la sequenza di ogni giorno con il mazzo e il
     vincolo di non ripetere nella stessa giornata, e conta le uscite

La usa anche la GUI, dal pulsante "Verifica anno" della tab Periodi.

Uso: python verifica_immagini.py [giorni] [soglia_rare]
     (default: 365 giorni, segnala le immagini uscite <= 12 volte)
"""

import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import app

GIORNI_DEFAULT = 365
SOGLIA_DEFAULT = 12


def _nessun_progresso(fase: str, fatto: int, totale: int):
    pass


def eleggibili(config: dict, giorni: list[date], progresso=_nessun_progresso) -> dict[str, set[str]]:
    """Immagine -> periodi in cui e' nel pool di una regola vincente."""
    out: dict[str, set[str]] = defaultdict(set)
    pools: dict[str, list[str]] = {}
    for n, g in enumerate(giorni):
        progresso("fasce", n, len(giorni))
        regole = app._regole_del_giorno(config, g)
        speciali = config.get("special_days", {}).get(g.strftime("%Y-%m-%d")) or []
        periodo = app.periodo_attivo(config, g)
        nome = periodo.get("name", "?") if periodo else "-"
        vinte = set()
        for minuto in range(1440):
            if speciali:
                t = datetime(g.year, g.month, g.day) + timedelta(minutes=minuto)
                if app._first_match(speciali, t, config):
                    continue  # coperto da un giorno speciale, le regole non contano
            for rule, _origine, start, end in regole:
                if not app._copre(start, end, minuto):
                    continue
                sig = app._rule_signature(rule)
                if sig not in pools:
                    pools[sig] = app.candidates_for_rule(config, rule)
                if pools[sig]:
                    vinte.add(sig)
                    break
        for sig in vinte:
            for img in pools[sig]:
                out[img].add(nome)
    return out


def uscite(config: dict, giorni: list[date], progresso=_nessun_progresso) -> Counter:
    """Quante volte esce ogni immagine nelle sequenze giornaliere."""
    conta: Counter = Counter()
    for n, g in enumerate(giorni):
        progresso("uscite", n, len(giorni))
        for voce in app.sequenza_giornaliera(config, g):
            conta[voce["image"]] += 1
    return conta


def rapporto(
    config: dict,
    n_giorni: int = GIORNI_DEFAULT,
    soglia: int = SOGLIA_DEFAULT,
    progresso=_nessun_progresso,
) -> tuple[list[str], int]:
    """
    Le righe del rapporto e il numero di problemi veri: file mancanti, immagini
    mai eleggibili, immagini mai uscite. Le immagini rare o legate a un solo
    periodo sono informative e non contano come problema.
    """
    app.invalida_cache_file()
    taggate = {i: t for i, t in config.get("image_library", {}).items() if t}
    oggi = date.today()
    giorni = [oggi + timedelta(d) for d in range(n_giorni)]
    righe = [f"Immagini con tag: {len(taggate)}  -  periodo: {giorni[0]} -> {giorni[-1]}"]
    problemi = 0

    mancanti = [i for i in taggate if not app._esiste(app.resolve_path(config, i))]
    problemi += len(mancanti)
    righe.append(f"\nFile mancanti su disco: {len(mancanti)}")
    righe += [f"  {i}" for i in mancanti]

    elig = eleggibili(config, giorni, progresso)
    mai_elig = [i for i in taggate if i not in elig]
    problemi += len(mai_elig)
    righe.append(f"\nMai eleggibili (nessuna fascia vincente le pesca): {len(mai_elig)}")
    righe += [f"  {i}: {taggate[i]}" for i in mai_elig]

    righe.append("\nEleggibili in un solo periodo:")
    for i, periodi in sorted(elig.items()):
        if i in taggate and len(periodi) == 1:
            righe.append(f"  [{next(iter(periodi))}] {i}: {taggate[i]}")

    conta = uscite(config, giorni, progresso)
    mai_uscite = [i for i in taggate if conta[i] == 0]
    # Una mai eleggibile e' per forza anche mai uscita: non la si conta due volte
    problemi += len([i for i in mai_uscite if i in elig])
    righe.append(f"\nUscite totali: {sum(conta.values())}")
    righe.append(f"Mai uscite in {n_giorni} giorni: {len(mai_uscite)}")
    righe += [f"  {i}: {taggate[i]}" for i in mai_uscite]

    righe.append(f"\nUscite al massimo {soglia} volte:")
    for i, n in sorted(conta.items(), key=lambda x: x[1]):
        if n > soglia:
            break
        righe.append(f"  {n:>3}x {i}: {taggate.get(i)}")

    return righe, problemi


def main():
    n_giorni = int(sys.argv[1]) if len(sys.argv) > 1 else GIORNI_DEFAULT
    soglia = int(sys.argv[2]) if len(sys.argv) > 2 else SOGLIA_DEFAULT
    righe, _ = rapporto(app.load_config(), n_giorni, soglia)
    print("\n".join(righe))


if __name__ == "__main__":
    main()
