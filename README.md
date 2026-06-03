# 🦎 Chametiger

Wallpaper scheduler per Windows — cambia lo sfondo in base all'**ora del giorno** e al **giorno della settimana**.

---

## Struttura del progetto

```

├── app.py          ← Applicazione principale (tray + scheduler)
├── gui.py          ← Editor grafico della configurazione
├── config.json     ← Configurazione degli sfondi
├── requirements.txt
└── README.md
```

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
  "check_interval_minutes": 5,
  "schedules": {
    "weekday": [ ... ],   ← lunedì–venerdì (se nessun override attivo)
    "weekend": [ ... ]    ← sabato–domenica
  },
  "overrides": {
    "monday": null,       ← null = usa schedule base
    "friday": [ ... ]     ← lista di slot = override attivo solo quel giorno
  },
  "special_days": {
    "2025-12-25": [ ... ] ← priorità massima: sovrascrive tutto
  }
}
```

### Priorità di risoluzione (dalla più alta)

1. **special_days** — data esatta (es. Natale, Capodanno)
2. **overrides** — override per giorno della settimana (es. venerdì sera)
3. **schedules** — weekday o weekend in base al giorno

### Slot orario

```json
{
  "from": "08:00",
  "to": "12:00",
  "image": "C:/Wallpapers/morning.jpg",
  "label": "Mattina"
}
```

- Le fasce a **cavallo della mezzanotte** sono supportate (es. `"from": "22:00", "to": "06:00"`)
- Se nessuno slot copre l'orario corrente, lo sfondo non viene cambiato

---

## Menu tray (tasto destro sull'icona)

| Voce                | Descrizione                   |
| ------------------- | ----------------------------- |
| Applica adesso      | Forza il controllo immediato  |
| Apri editor config  | Apre la GUI di configurazione |
| ✓ Avvio con Windows | Toggle avvio automatico       |
| Esci                | Chiude l'applicazione         |

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

| Problema              | Soluzione                                 |
| --------------------- | ----------------------------------------- |
| Lo sfondo non cambia  | Verifica che il percorso immagine esista  |
| `ModuleNotFoundError` | Esegui `pip install -r requirements.txt`  |
| Icona tray non appare | Assicurati di avere Pillow installato     |
| `winreg` non trovato  | Solo Windows; non funziona su Linux/macOS |
