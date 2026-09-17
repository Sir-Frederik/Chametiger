# 🦎 Chametiger

**v2.0**

Wallpaper scheduler per Windows — cambia lo sfondo in base all'**ora del giorno** e al **giorno della settimana**.

Due modalità:

- **programmata** — ogni fascia oraria ha la sua immagine fissa
- **casuale** — ogni fascia oraria pesca fra le immagini che hanno certi **tag**, dando la precedenza a quelle uscite meno di recente

---

## Novità della 2.0

- **Modalità casuale con tag**: invece di assegnare un'immagine a ogni fascia, descrivi che *tipo* di immagine vuoi (`mattino` + `lavoro`, senza `inverno`) e Chametiger sceglie.
- **Memoria delle estrazioni**: un file `log.json` tiene traccia di cosa è già uscito. Il sorteggio pesca sempre e solo fra le immagini viste meno volte, così scorre tutta la raccolta prima di ripetersi.
- **Log leggibile**: ogni cambio di sfondo scrive anche *quale regola* ha vinto, con fascia oraria e tag.
- **"Cambia immagine adesso"** dal menu tray, per forzare una nuova estrazione senza aspettare il cambio di fascia.
- **Libreria immagini e percorsi multi-PC** (`base_path` + `path_map`): la stessa configurazione funziona su computer diversi.

---

## Struttura del progetto

```
├── app.py          ← Applicazione principale (tray + scheduler)
├── gui.py          ← Editor grafico della configurazione
├── config.json     ← Configurazione: regole, tag, libreria immagini
├── log.json        ← Storico delle estrazioni casuali (generato)
├── chametiger.log  ← Log testuale (generato)
├── requirements.txt
└── README.md
```

I due file generati si creano da soli al primo avvio: non vanno preparati né versionati.

---

## Installazione

### 1. Requisiti

- Python 3.11 o superiore
- Windows 10/11

### 2. Dipendenze

```bash
py -m pip install -r requirements.txt
```

> `tkcalendar` è opzionale: se non installato, la selezione data nei giorni speciali
> avviene tramite campo testo anziché calendario grafico.

---

## Avvio

### Avviare l'applicazione

```bash
python app.py
```

L'app si avvia in **system tray** (icona in basso a destra nella taskbar).
Al primo avvio aggiunge automaticamente se stessa all'avvio di Windows (registro HKCU).

### Aprire l'editor

```bash
python gui.py
```

Oppure: click destro sull'icona tray → **Apri editor config**

---

## Configurazione

### Struttura `config.json`

```json
{
  "mode": "random",
  "check_interval_minutes": 5,
  "history_days": 60,

  "base_path": "G:/Temi",
  "path_map": {
    "NomePC": "C:/Users/Tizio/Pictures/Temi"
  },

  "schedules":    { "weekday": [ ... ], "weekend": [ ... ] },
  "overrides":    { "monday": null, "friday": [ ... ] },
  "special_days": { "2026-12-25": [ ... ] },

  "tags": ["mattino", "lavoro", "notte", "..."],
  "image_library": { "cartella/foto.jpg": ["mattino", "lavoro"] },
  "random_rules": {
    "weekday":   [ ... ],
    "weekend":   [ ... ],
    "overrides": { "monday": [ ... ] }
  }
}
```

| Chiave                   | A cosa serve                                                        |
| ------------------------ | ------------------------------------------------------------------- |
| `mode`                   | `"scheduled"` o `"random"`                                           |
| `check_interval_minutes` | Ogni quanto lo scheduler ricontrolla                                 |
| `history_days`           | Per quanti giorni ricordare le immagini già uscite (solo casuale)    |
| `base_path` / `path_map` | Cartella base delle immagini, con override per singolo PC (hostname) |

### Percorsi multi-PC

`base_path` è la cartella di riferimento; `path_map` la sostituisce sui PC elencati, usando il **nome del computer** come chiave. Nella libreria le immagini si indicano con percorsi **relativi** a quella cartella, così la stessa `config.json` funziona ovunque.

---

## Modalità programmata

Ogni fascia oraria punta a un'immagine precisa.

```json
{
  "from": "08:00",
  "to": "12:00",
  "image": "mattina/alba.jpg",
  "label": "Mattina"
}
```

### Priorità di risoluzione (dalla più alta)

1. **special_days** — data esatta (es. Natale, Capodanno)
2. **overrides** — override per giorno della settimana (es. venerdì sera)
3. **schedules** — weekday o weekend in base al giorno
4. **fallback** — se il weekend non copre l'orario, si ripiega su weekday

- Le fasce a **cavallo della mezzanotte** sono supportate (es. `"from": "22:00", "to": "06:00"`)
- Se nessuno slot copre l'orario corrente, lo sfondo non viene cambiato

---

## Modalità casuale

Invece di scegliere l'immagine, descrivi che tipo di immagine vuoi. Serve una **libreria taggata**:

```json
"image_library": {
  "looney/speedy_deserto.png": ["pomeriggio", "svago"],
  "paesaggi/alba_mare.jpg":    ["mattino", "alba"]
}
```

e delle **regole**:

```json
{
  "from": "09:00",
  "to": "13:00",
  "include": ["lavoro", "mattino"],
  "exclude": ["inverno", "smart"],
  "match": "all",
  "rotate_minutes": 60
}
```

| Campo            | Significato                                                  |
| ---------------- | ------------------------------------------------------------ |
| `include`        | Tag che l'immagine deve avere                                 |
| `exclude`        | Tag che l'immagine non deve avere                             |
| `match`          | `"all"` = tutti gli include, `"any"` = ne basta uno           |
| `rotate_minutes` | Ogni quanto cambiare immagine dentro la fascia                |

Le priorità sono le stesse della modalità programmata (i giorni speciali restano a immagine fissa: a Natale vuoi *quella*, non una a caso). Se nessuna regola copre l'orario, si ripiega sulla modalità programmata.

### Come viene scelta l'immagine

Non è un sorteggio puro. Chametiger conta quante volte ogni immagine è uscita negli ultimi `history_days` giorni, tiene solo quelle a conteggio minimo e sorteggia fra quelle. In pratica scorre tutta la raccolta prima di ripetersi, come un mazzo che si rimescola solo quando è finito.

Il conteggio è **globale**: un'immagine vista stamattina non torna nel pomeriggio, anche se una regola diversa la ammetterebbe.

La scelta viene memorizzata in `log.json` per la fascia corrente e riusata finché la fascia non cambia — è questo che tiene lo sfondo fermo fra un controllo e l'altro.

> **Nota sul valore di `history_days`.** Più la raccolta è grande, più la memoria deve essere lunga per avere effetto. Con 40 immagini e una sola estrazione al giorno, una settimana di storico non basta a distinguerle. Il default di 60 giorni è tarato per funzionare anche sulle raccolte ampie.

---

## Menu tray (tasto destro sull'icona)

| Voce                    | Descrizione                                      |
| ----------------------- | ------------------------------------------------ |
| Applica adesso          | Forza il controllo immediato                     |
| Cambia immagine adesso  | Nuova estrazione subito (solo modalità casuale)  |
| Apri editor config      | Apre la GUI di configurazione                    |
| Modalità: …             | Passa da programmata a casuale e viceversa       |
| \* Avvio con Windows    | Toggle avvio automatico                          |
| Esci                    | Chiude l'applicazione                            |

---

## Log

`chametiger.log` registra ogni cambio di sfondo indicando **quale regola** ha vinto:

```
[2026-09-17 14:00:03] Avvio Chametiger. Modalita': random
[2026-09-17 14:00:03] [OK] Sfondo impostato (casuale, weekday 14:00-18:00 [pomeriggio -inverno]): G:\Temi\...
[2026-09-17 15:00:07] [OK] Sfondo impostato (casuale, weekday 14:00-18:00 [pomeriggio -inverno]): G:\Temi\...
```

Nei tag, `+` significa che servono **tutti** quelli elencati, `/` che ne basta **uno**, `-tag` sono le esclusioni.

Lo si apre dalla GUI con **Mostra log**, in fondo alla finestra.

---

## Compilare in .exe (opzionale)

Per un eseguibile standalone senza Python installato:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --icon=icon.ico app.py
```

L'eseguibile comparirà in `dist/app.exe`.

---

## Troubleshooting

| Problema                              | Soluzione                                                              |
| ------------------------------------- | ---------------------------------------------------------------------- |
| Lo sfondo non cambia                  | Verifica che il percorso immagine esista                                |
| `ModuleNotFoundError`                 | Esegui `pip install -r requirements.txt`                                |
| Icona tray non appare                 | Assicurati di avere Pillow installato                                   |
| `winreg` non trovato                  | Solo Windows; non funziona su Linux/macOS                               |
| In casuale esce sempre la stessa      | La regola ha pochi candidati: controlla i tag nel log                   |
| Le immagini si ripetono troppo spesso | Alza `history_days` nelle impostazioni della GUI                        |
| Su un altro PC non trova le immagini  | Aggiungi il suo hostname in `path_map`                                  |
