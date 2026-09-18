"""
Diagnosi Chametiger: stampa cosa calcola QUESTO pc, senza toccare lo sfondo
e senza scrivere niente. Va eseguito su entrambe le macchine e confrontato.

    python check.py
"""

import socket
import hashlib
from datetime import datetime

import app  # importa le funzioni senza avviare il tray


def impronta(valori) -> str:
    """Firma breve di una lista: se due pc danno firme diverse, i pool differiscono."""
    return hashlib.md5("|".join(valori).encode("utf-8")).hexdigest()[:8]


def main():
    cfg = app.load_config()
    libreria = cfg.get("image_library", {})

    print("=" * 78)
    print(f"PC:            {socket.gethostname()}")
    print(f"EPOCH:         {app.EPOCH}")
    print(f"Modalita':     {cfg.get('mode')}")
    print(f"Cartella base: {app.resolve_path(cfg, '')}")
    print(f"Libreria:      {len(libreria)} immagini dichiarate in config.json")

    # Quante di quelle immagini esistono davvero su questo pc
    presenti = [
        img
        for img in libreria
        if app.os.path.isfile(app.resolve_path(cfg, img))
    ]
    mancanti = len(libreria) - len(presenti)
    print(f"               {len(presenti)} presenti su disco, {mancanti} mancanti")
    print(f"Impronta libreria presente: {impronta(sorted(presenti))}")
    print("=" * 78)

    oggi = datetime.now()
    print(f"\nGiornata del {oggi:%Y-%m-%d} (l'ora attuale e' {oggi:%H:%M})\n")
    print(f"{'ora':>5}  {'pool':>4}  {'impronta':>8}  {'giro':>5} {'pos':>4}  immagine")
    print("-" * 78)

    for h in range(24):
        t = oggi.replace(hour=h, minute=0, second=0, microsecond=0)

        rule = app._regola_attiva(cfg, t)
        if rule is None:
            continue

        sig = app._rule_signature(rule)
        rotate = app._rotate_of(rule)
        pool = sorted(app.candidates_for_rule(cfg, rule))

        if not pool:
            print(f"{h:02d}:00  {0:>4}  {'-':>8}  {'-':>5} {'-':>4}  NESSUNA CANDIDATA")
            continue

        giro, pos = divmod(app._window_ordinal(rule, t, rotate), len(pool))
        scelta = app._scelta_giornaliera(cfg, t)

        print(
            f"{h:02d}:00  {len(pool):>4}  {impronta(pool):>8}  "
            f"{giro:>5} {pos:>4}  {scelta}"
        )

    print("-" * 78)
    print("\nRipetizioni nella giornata:")
    viste = {}
    for h in range(24):
        t = oggi.replace(hour=h, minute=0, second=0, microsecond=0)
        if app._regola_attiva(cfg, t) is None:
            continue
        s = app._scelta_giornaliera(cfg, t)
        if s:
            viste.setdefault(s, []).append(f"{h:02d}:00")

    doppie = {k: v for k, v in viste.items() if len(v) > 1}
    if doppie:
        for img, ore in doppie.items():
            print(f"  RIPETUTA {img} alle {', '.join(ore)}")
    else:
        print("  nessuna, ogni immagine esce una volta sola")

    print("\nStabilita' dentro la finestra corrente:")
    valori = set()
    for m in range(0, 60, 5):
        t = oggi.replace(minute=m, second=0, microsecond=0)
        if app._regola_attiva(cfg, t) is None:
            continue
        valori.add(app._scelta_giornaliera(cfg, t))
    if len(valori) <= 1:
        print(f"  stabile: {valori or '(nessuna regola attiva)'}")
    else:
        print(f"  INSTABILE, {len(valori)} risultati diversi nella stessa ora:")
        for v in sorted(valori):
            print(f"    {v}")


if __name__ == "__main__":
    main()
