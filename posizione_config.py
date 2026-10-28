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

import hashlib
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


# Senza queste un config e' vuoto o tagliato, non "un config con pochi dati".
CHIAVI_ESSENZIALI = ("image_library", "random_rules")

# Quante cifre dello SHA-256 formano l'impronta: le stesse sul telefono.
CIFRE_IMPRONTA = 8


class ConfigIllegibile(Exception):
    """config.json c'e' ma non si puo' usare: troncato, a meta' scrittura, non JSON."""


def impronta(byte: bytes) -> str:
    """
    Le prime cifre dello SHA-256 dei byte del config. Il tray la scrive nel
    log e il telefono la mostra: "stanno sullo stesso config?" diventa il
    confronto di due stringhe.
    """
    return hashlib.sha256(byte).hexdigest()[:CIFRE_IMPRONTA]


def leggi_config(percorso: Path | None = None) -> dict:
    """Il config cosi' com'e' sul disco, senza i default: vedi leggi_config_e_impronta."""
    return leggi_config_e_impronta(percorso)[0]


def leggi_config_e_impronta(percorso: Path | None = None) -> tuple[dict, str]:
    """
    Il config cosi' com'e' sul disco, senza i default, con l'impronta dei
    byte appena letti: una sola lettura, cosi' l'impronta e' proprio quella del
    config usato.

    Su Drive il file puo' trovarsi a meta' di una scrittura o di una
    sincronizzazione. Un file che non e' un config completo solleva
    ConfigIllegibile invece di passare per un config vuoto: ensure_defaults lo
    riempirebbe di liste vuote, e chi lo usa resterebbe senza regole. Il file
    assente o la cartella non montata arrivano come OSError.
    """
    percorso = percorso or percorso_config()
    with open(percorso, "rb") as f:
        byte = f.read()
    try:
        cfg = json.loads(byte.decode("utf-8"))
    except ValueError as e:  # JSONDecodeError e UnicodeDecodeError
        raise ConfigIllegibile(f"{percorso} non e' un JSON valido: {e}") from e
    if not isinstance(cfg, dict):
        raise ConfigIllegibile(f"{percorso} non contiene un oggetto JSON")
    mancanti = [k for k in CHIAVI_ESSENZIALI if not cfg.get(k)]
    if mancanti:
        raise ConfigIllegibile(f"{percorso}: mancano o sono vuote {', '.join(mancanti)}")
    return cfg, impronta(byte)
