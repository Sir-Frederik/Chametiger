"""
Verifica che ogni immagine con almeno un tag esca davvero, con il config attuale.

Simula un anno a partire da oggi usando le stesse funzioni dello scheduler
(stagioni, eventi, override, fasce solari, divieti stagionali) e fa due
controlli:

  1. eleggibilita': l'immagine sta nel pool di almeno una regola che vince
     davvero in qualche minuto (la prima per priorita' con pool non vuoto)
  2. uscite reali: ricostruisce la sequenza di ogni giorno con il mazzo e il
     vincolo di non ripetere nella stessa giornata, e conta le uscite

Il meteo dell'anno simulato e' asciutto: oltre le previsioni scaricate
meteo.del_giorno da' asciutte tutte le ore, e cosi' le immagini di pioggia e
temporale non uscirebbero mai. Col meteo attivo le uscite si contano quindi in
tre scenari: l'anno com'e', poi con pioggia e con temporale tutto il giorno.
Un'immagine e' "mai uscita" solo se non esce in nessuno dei tre; quelle col tag
del meteo che non escono nemmeno con la pioggia o il temporale si elencano a
parte. Col meteo disattivato resta lo scenario unico.

La usa anche la GUI, dal pulsante "Verifica anno" della tab Stagioni ed eventi.

Uso: python verifica_immagini.py [giorni] [soglia_rare]
     (default: 365 giorni, segnala le immagini uscite <= 12 volte)
"""

import sys
import threading
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, timedelta

import app
import meteo

GIORNI_DEFAULT = 365
SOGLIA_DEFAULT = 12

# Gli scenari forzati, dopo l'anno com'e'. Lo stato e' anche il tag del meteo.
SCENARI_METEO = (meteo.PIOGGIA, meteo.TEMPORALE)


def _nessun_progresso(fase: str, fatto: int, totale: int):
    pass


def eleggibili(config: dict, giorni: list[date], progresso=_nessun_progresso) -> dict[str, set[str]]:
    """Immagine -> periodi (strati) in cui e' nel pool di una regola vincente."""
    out: dict[str, set[str]] = defaultdict(set)
    pools: dict[str, list[str]] = {}
    for n, g in enumerate(giorni):
        progresso("fasce", n, len(giorni))
        regole = app._regole_del_giorno(config, g)
        vinte = set()
        for minuto in range(1440):
            for rule, _origine, start, end in regole:
                if not app._copre(start, end, minuto):
                    continue
                sig = app._rule_signature(rule)
                if sig not in pools:
                    pools[sig] = app.candidates_for_rule(config, rule)
                if pools[sig]:
                    vinte.add((sig, rule.get("_period", "-")))
                    break
        for sig, nome in vinte:
            for img in pools[sig]:
                out[img].add(nome)
    return out


@contextmanager
def tempo_fisso(stato: str):
    """
    Dentro il blocco meteo.del_giorno da' `stato` a tutte le ore di ogni giorno.

    Lo si sostituisce nel modulo, senza toccare meteo.py ne' il motore, ma solo
    per il thread che verifica: la GUI fa girare la verifica in un thread, e
    l'anteprima che intanto chiede il meteo deve vedere quello vero. Col meteo
    disattivato si lascia rispondere l'originale, che da' None.
    """
    originale = meteo.del_giorno
    mio = threading.get_ident()

    def del_giorno(config: dict, giorno: date) -> dict[int, str] | None:
        if threading.get_ident() != mio or not meteo.impostazioni(config)[0]:
            return originale(config, giorno)
        return dict.fromkeys(range(24), stato)

    meteo.del_giorno = del_giorno
    try:
        yield
    finally:
        meteo.del_giorno = originale


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
    mai eleggibili, immagini mai uscite in nessuno scenario, immagini col tag
    del meteo che non escono nemmeno con pioggia o temporale. Le immagini rare
    o legate a un solo periodo sono informative e non contano come problema.
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

    # Lo scenario di oggi, poi quelli forzati: il progresso li conta come
    # un'unica fase, cosi' la barra della GUI non riparte da zero.
    scenari = [None]
    if meteo.impostazioni(config)[0]:
        scenari += SCENARI_METEO
    conte: dict[str | None, Counter] = {}
    for k, stato in enumerate(scenari):
        def prog(fase, fatto, totale, k=k):
            progresso(fase, k * totale + fatto, len(scenari) * totale)

        if stato is None:
            conte[stato] = uscite(config, giorni, prog)
        else:
            with tempo_fisso(stato):
                conte[stato] = uscite(config, giorni, prog)
    conta = conte[None]

    mai_uscite = [i for i in taggate if not any(c[i] for c in conte.values())]
    # Una mai eleggibile e' per forza anche mai uscita: non la si conta due volte
    problemi += len([i for i in mai_uscite if i in elig])
    if len(scenari) == 1:
        righe.append(f"\nUscite totali: {sum(conta.values())}")
        righe.append(f"Mai uscite in {n_giorni} giorni: {len(mai_uscite)}")
    else:
        righe.append(
            "\nUscite totali: "
            + ", ".join(
                f"{sum(c.values())} {stato or 'col meteo previsto'}"
                for stato, c in conte.items()
            )
        )
        righe.append(
            f"Mai uscite in {n_giorni} giorni, in nessuno dei tre scenari: "
            f"{len(mai_uscite)}"
        )
    righe += [f"  {i}: {taggate[i]}" for i in mai_uscite]

    if len(scenari) > 1:
        # Il problema vero: un'immagine di pioggia che non esce nemmeno quando
        # piove tutto l'anno. Quelle gia' contate come mai uscite o mai
        # eleggibili non si contano una seconda volta.
        ferme = [
            i
            for i, tag in taggate.items()
            if set(tag) & set(SCENARI_METEO)
            and not any(conte[s][i] for s in SCENARI_METEO)
        ]
        problemi += len([i for i in ferme if i not in mai_uscite])
        righe.append(
            f"\nCol tag del meteo, mai uscite nemmeno con pioggia o temporale "
            f"tutto il giorno: {len(ferme)}"
        )
        righe += [f"  {i}: {taggate[i]}" for i in ferme]

    titolo = f"\nUscite al massimo {soglia} volte"
    if len(scenari) > 1:
        titolo += " (col meteo previsto)"
    righe.append(titolo + ":")
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
