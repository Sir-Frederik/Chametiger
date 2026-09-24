"""
Verifica che ogni immagine con almeno un tag esca davvero, con il config attuale.

Simula un anno a partire da oggi usando le stesse funzioni dello scheduler
(periodi, override, fasce solari, divieti stagionali, special_days) e fa due
controlli:

  1. eleggibilita': l'immagine sta nel pool di almeno una regola che vince
     davvero in qualche minuto (la prima per priorita' con pool non vuoto)
  2. uscite reali: ricostruisce la sequenza di ogni giorno con il mazzo e il
     vincolo di non ripetere nella stessa giornata, e conta le uscite

Uso: python verifica_immagini.py [giorni] [soglia_rare]
     (default: 365 giorni, segnala le immagini uscite <= 12 volte)
"""

import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import app


def eleggibili(config: dict, giorni: list[date]) -> dict[str, set[str]]:
    """Immagine -> periodi in cui e' nel pool di una regola vincente."""
    out: dict[str, set[str]] = defaultdict(set)
    pools: dict[str, list[str]] = {}
    for g in giorni:
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


def uscite(config: dict, giorni: list[date]) -> Counter:
    """Quante volte esce ogni immagine nelle sequenze giornaliere."""
    conta: Counter = Counter()
    for g in giorni:
        for voce in app.sequenza_giornaliera(config, g):
            conta[voce["image"]] += 1
    return conta


def main():
    n_giorni = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    soglia = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    config = app.load_config()
    taggate = {i: t for i, t in config["image_library"].items() if t}
    oggi = date.today()
    giorni = [oggi + timedelta(d) for d in range(n_giorni)]

    print(f"Immagini con tag: {len(taggate)}  -  periodo: {giorni[0]} -> {giorni[-1]}")

    mancanti = [i for i in taggate if not app._esiste(app.resolve_path(config, i))]
    print(f"\nFile mancanti su disco: {len(mancanti)}")
    for i in mancanti:
        print(f"  {i}")

    elig = eleggibili(config, giorni)
    mai_elig = [i for i in taggate if i not in elig]
    print(f"\nMai eleggibili (nessuna fascia vincente le pesca): {len(mai_elig)}")
    for i in mai_elig:
        print(f"  {i}: {taggate[i]}")

    print("\nEleggibili in un solo periodo:")
    for i, periodi in sorted(elig.items()):
        if i in taggate and len(periodi) == 1:
            print(f"  [{next(iter(periodi))}] {i}: {taggate[i]}")

    conta = uscite(config, giorni)
    mai_uscite = [i for i in taggate if conta[i] == 0]
    print(f"\nUscite totali: {sum(conta.values())}")
    print(f"Mai uscite in {n_giorni} giorni: {len(mai_uscite)}")
    for i in mai_uscite:
        print(f"  {i}: {taggate[i]}")

    print(f"\nUscite al massimo {soglia} volte:")
    for i, n in sorted(conta.items(), key=lambda x: x[1]):
        if n > soglia:
            break
        print(f"  {n:>3}x {i}: {taggate.get(i)}")


if __name__ == "__main__":
    main()
