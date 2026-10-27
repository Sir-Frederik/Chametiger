"""
Dove sta config.json: nella cartella delle immagini, non accanto a app.py.

Un solo config per tutti i dispositivi. I PC lo leggono dalla cartella base
(su Drive, o nella copia locale che Drive sincronizza), il telefono dalla
stessa cartella attraverso l'API di Drive. Prima ogni PC aveva la sua copia
nel repository e il telefono avrebbe avuto la sua: due config che prima o poi
divergono, e con loro le immagini mostrate.

Il config non puo' dire dove si trova lui stesso, quindi la cartella di ogni
PC sta in cartella_config.json, accanto a app.py e nel repository: la stessa
forma di base_path / path_map, con il nome del computer come chiave.

Senza cartella_config.json si torna al config.json accanto a app.py, com'era
prima.

La usano sia il tray (app.py) sia l'editor (gui.py), che cosi' leggono e
scrivono lo stesso file.
"""

import json
import socket
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
PUNTATORE = BASE_DIR / "cartella_config.json"
NOME_CONFIG = "config.json"


def cartella_config(hostname: str | None = None) -> Path | None:
    """La cartella del config per questo PC, o None se il puntatore non c'e'."""
    if not PUNTATORE.exists():
        return None
    with open(PUNTATORE, encoding="utf-8") as f:
        dati = json.load(f)
    hostname = hostname or socket.gethostname()
    cartella = dati.get("per_pc", {}).get(hostname) or dati.get("cartella", "")
    if not cartella:
        raise ValueError(f"{PUNTATORE.name}: nessuna cartella per {hostname}")
    return Path(cartella)


def percorso_config() -> Path:
    cartella = cartella_config()
    if cartella is None:
        return BASE_DIR / NOME_CONFIG
    return cartella / NOME_CONFIG
