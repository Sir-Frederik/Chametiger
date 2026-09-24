# 🦎 Chametiger

**v3.5** — 21 settembre 2026
Un'immagine può appartenere a più stagioni.


Wallpaper scheduler per Windows — cambia lo sfondo in base all'**ora del giorno**, al **giorno della settimana**, al **periodo dell'anno** e agli **orari reali di alba e tramonto**.

Due modalità:

- **programmata** — ogni fascia oraria ha la sua immagine fissa
- **casuale** — ogni fascia oraria pesca fra le immagini che hanno certi **tag**, dando la precedenza a quelle uscite meno di recente

---

## Novità della 3.1

- **Un'immagine può appartenere a più stagioni.** I tag stagionali erano un divieto secco per tag: `autunno + primavera` non voleva dire *"va bene in autunno e in primavera"*, ma *"vietata in autunno"* **e** *"vietata in primavera"*. Più stagioni si assegnavano a un'immagine, meno la si vedeva. In una libreria di 197 immagini ce n'erano **nove** taggate con cura e **mai mostrate in tutto l'anno**. Ora un'immagine cade solo se **tutte** le stagioni che dichiara sono vietate, e il campo delle stagioni è separato dall'`exclude` della regola, che resta un divieto secco (`-smart` toglie e basta). Il cambio **aggiunge soltanto**: verificato su 196 combinazioni periodo × fascia, 410 immagini tornate in circolo, **zero** tolte. Vedi [Un'immagine in più stagioni](#unimmagine-in-più-stagioni).
- **Quali tag siano "stagioni" non è più una lista nel codice**: sono tutti quelli che almeno un periodo vieta. Aggiungere `carnevale` non richiede di toccare niente, e `tramonto`, che nessun periodo vieta, non rende stagionale l'immagine che lo porta.
- **Le fasce proprie dei periodi si modificano dall'editor**, col pulsante **Fasce del periodo** nella tab *Periodi dell'anno*: feriali, weekend e override di giorno, con lo stesso editor delle regole di base — ancore solari e conteggio immagini compresi. Prima erano l'unica parte del config che restava da scrivere a mano. Le liste rimaste vuote vengono tolte alla chiusura, così un periodo senza fasce resta pulito nel `config.json`.
- **Nel log le stagioni vietate dal periodo si distinguono** dalle esclusioni della regola: `!estate,!natale` contro `-smart`.
- **La GUI non conta più per conto suo.** *Verifica regole* costruiva la patch del periodo rifacendo la logica del motore, e dopo questo cambio avrebbe contato col criterio vecchio: ora chiama `patch_rule`, come già facevano *Anteprima giorno* e *Verifica anno*.

## Novità della 3.0

- **Fasce ancorate al sole**: invece di `19:00`, scrivi `sunset-40m`. Il tramonto a Napoli si sposta di **4 ore e 4 minuti** fra giugno e dicembre, e una fascia a orario fisso è corretta per due settimane l'anno. Le ancore seguono il sole ogni giorno, **ora legale compresa**.
- **Periodi dell'anno**: intervalli di date che filtrano i tag senza duplicare le regole. Un periodo stagionale sono tre campi (nome, intervallo, tag vietati); uno festivo (Halloween, Natale) può aggiungere fasce proprie solo per le ore che gli interessano, lasciando intatto il resto della giornata.
- **Tab "Anteprima giorno"**: scegli una data e vedi la giornata risolta — periodo attivo, regola vincente, orari solari reali, quante immagini ci sono in pool e quale uscirebbe. Usa il motore vero, non una sua imitazione.
- **Tab "Periodi dell'anno"** con avviso sui giorni non coperti e **"Verifica anno"**, che passa i mesi in rassegna e segnala le fasce rimaste con poche immagini.
- **Nessuna dipendenza nuova**: gli orari solari sono calcolati in casa (algoritmo NOAA, `sun.py`), e l'ora legale la applica il sistema operativo.

### Correzioni nella 3.0

- **Rinominare un tag non funzionava.** `notify_tags_changed` era definita annidata dentro un altro metodo, quindi non era un metodo della finestra: ogni rinomina, aggiunta o eliminazione di un tag finiva in `AttributeError`.
- **Il mazzo saltava con le fasce a durata variabile.** Il conteggio delle finestre era una moltiplicazione, e il primo giorno in cui il numero di finestre cambiava il mazzo avanzava di centinaia di posizioni invece di una, saltando immagini che non si vedevano mai. Ora è una somma cumulativa (vedi *Le fasce solari e il mazzo*).
- **Ripiego più solido:** se la regola vincente non ha immagini valide si prova la successiva in ordine di priorità, invece di lasciare lo sfondo fermo. Prima l'anteprima della giornata e lo scheduler potevano scegliere regole diverse in questo caso.
- **`resolve_wallpaper` è ~11 volte più veloce** (da 228 ms a 21 ms): i controlli di esistenza dei file sono condivisi per giro di scheduler e i confini delle fasce si risolvono una volta al giorno invece che a ogni minuto.
- **Rimossa l'impostazione "Memoria estrazioni (giorni)".** Prometteva di decidere quali immagini uscivano, contando le uscite degli ultimi `history_days` giorni, ma da quando la scelta viene dal mazzo non fa più niente di tutto questo — verificato: la sequenza di una giornata è **identica** con `history_days` a 1, 7, 60 o 3650. L'unico effetto rimasto era la potatura di `log.json`, che ora è fissata a 7 giorni nel codice. La chiave nel `config.json` viene ancora rispettata se presente, quindi i config esistenti non cambiano comportamento.

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
├── sun.py          ← Orari solari: alba, tramonto, crepuscolo, mezzogiorno vero
├── config.json     ← Configurazione: regole, periodi, tag, libreria immagini
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

  "latitude": 40.8518,
  "longitude": 14.2681,

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
  },
  "periods": [
    { "name": "Autunno", "from": "09-10", "to": "11-30",
      "exclude": ["estate", "inverno", "primavera", "natale"] }
  ]
}
```

| Chiave                    | A cosa serve                                                        |
| ------------------------- | ------------------------------------------------------------------- |
| `mode`                    | `"scheduled"` o `"random"`                                           |
| `check_interval_minutes`  | Ogni quanto lo scheduler ricontrolla                                 |
| `history_days`            | Per quanti giorni conservare le righe di `log.json` (default 7). Non è nell'editor: **non** influenza quale immagine esce |
| `latitude` / `longitude`  | Posizione, per calcolare alba e tramonto. Default: Napoli            |
| `base_path` / `path_map`  | Cartella base delle immagini, con override per singolo PC (hostname) |
| `periods`                 | Periodi dell'anno che filtrano i tag (vedi sotto)                    |

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

I periodi dell'anno riguardano solo la modalità casuale: in quella programmata ogni slot nomina un'immagine precisa, non c'è nulla da filtrare. Le ancore solari invece funzionano anche qui.

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
  "exclude": ["smart"],
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
| `prefer`         | Tag preferiti: restringe il pool a quelli, se ne resta abbastanza |
| `prefer_min`     | Quante immagini devono restare perché `prefer` si applichi (default 1) |

Se nessuna regola copre l'orario, si ripiega sulla modalità programmata.

> I tag **stagionali** (`inverno`, `estate`, `natale`…) non vanno messi nell'`exclude` delle regole: è il lavoro dei [periodi dell'anno](#periodi-dellanno). Ripetuti in ogni regola diventano decine di righe da tenere allineate a mano, e una stagione dimenticata si nota solo sei mesi dopo.

### Come viene scelta l'immagine

Non è un sorteggio. Le immagini che soddisfano la regola vengono disposte in un **mazzo**, mescolato in modo deterministico a partire dalla regola stessa; ogni finestra di rotazione pesca la carta successiva. Finito il mazzo si rimescola con un ordine nuovo, e la prima carta non coincide mai con l'ultima del giro precedente. Così tutta la raccolta scorre prima che qualcosa si ripeta, senza bisogno di tenere conteggi.

Dentro la stessa giornata non ci sono ripetizioni: se la carta che toccherebbe è già uscita oggi, si avanza nel mazzo fino alla prima non ancora vista. Vale anche fra regole diverse — un'immagine vista stamattina non torna nel pomeriggio.

Il calcolo è **deterministico e senza stato**: dipende solo dalla regola, dalla libreria e dalla data. Due PC con la stessa configurazione ottengono la stessa sequenza senza parlarsi, ed è questo che fa funzionare la sincronizzazione multi-PC.

`log.json` **non** partecipa alla scelta: serve a ricordare quale immagine è stata assegnata alla finestra corrente, così lo sfondo resta fermo fra un controllo e l'altro dello scheduler, e a far durare un'estrazione forzata fino alla fine della sua finestra.

### Priorità in modalità casuale (dalla più alta)

1. **special_days** — a immagine fissa: a Natale vuoi *quella*, non una a caso
2. **periodo attivo** → override del giorno, poi feriali/weekend
3. **regole di base** → override del giorno, poi feriali/weekend
4. **fallback weekday**, se il weekend non copre l'orario
5. **modalità programmata**, se non copre nessuno

A ogni livello, se la regola vincente non ha immagini valide si prova la successiva invece di lasciare lo sfondo fermo.

---

## Fasce ancorate al sole

Nei campi `from` e `to` puoi scrivere un'**ancora solare** invece di un orario:

```json
{ "from": "sunset-40m", "to": "dusk+30m", "include": ["tramonto"], "match": "all" }
```

| Ancora    | Momento                                              |
| --------- | ---------------------------------------------------- |
| `dawn`    | Crepuscolo del mattino (sole 6° sotto l'orizzonte)   |
| `sunrise` | Alba                                                 |
| `noon`    | Mezzogiorno **solare vero**, non le 12:00 dell'orologio |
| `sunset`  | Tramonto                                             |
| `dusk`    | Crepuscolo della sera                                |

Lo scostamento si scrive in minuti (`sunset-40m`, oppure `sunset-40`) o in ore (`dusk+1h`).

### Perché

A Napoli il tramonto va dalle **16:34** di inizio dicembre alle **20:38** di fine giugno: **4 ore e 4 minuti** di escursione. Una regola `"from": "19:00", "to": "20:00"` con tag `tramonto` è corretta per circa due settimane l'anno; a dicembre alle 19:00 è notte da due ore.

Vale anche per l'alba, che a Napoli si sposta di **1 ora e 57 minuti** (dalle 05:30 alle 07:27), e per `noon`, che è il mezzogiorno **solare vero**: oscilla fra le **11:46** e le **13:09** fra ora solare e ora legale, e non coincide quasi mai con le 12:00 dell'orologio.

### Ora legale

Gestita automaticamente e **senza dipendenze**. L'orario dell'evento si calcola in UTC (algoritmo NOAA, in `sun.py`) e si converte con `datetime.fromtimestamp()`, che applica le regole del fuso del sistema operativo. Non servono `tzdata`, `zoneinfo` né `astral`. Passando all'ora legale il tramonto salta di un'ora come deve:

```
2026-03-28   tramonto 18:23
2026-03-29   tramonto 19:24     ← ora legale
```

### Mescolare orologio e sole

Va benissimo: le fasce legate al **tuo orario** (lavoro, pranzo) restano a orologio, quelle **astronomiche** vanno al sole. Un solo accorgimento: **le fasce solari vanno prima nella lista**, perché vince la prima che copre l'ora. Così il riempitivo `18:00-21:00` cede il passo quando il tramonto entra nel suo intervallo, senza doverlo spostare per stagione.

> ⚠️ Evita gli estremi misti tipo `"from": "18:00", "to": "sunset-40m"`: d'inverno `sunset-40m` cade *prima* delle 18:00, la fascia si inverte e si mangia tutta la notte. Meglio due estremi solari, o due d'orologio.

### Le fasce solari e il mazzo

Con le fasce ancorate al sole la durata cambia ogni giorno: la fascia `notte` ha **6 finestre a giugno e 8 a dicembre**. La posizione nel mazzo si ricava quindi da una **somma cumulativa** delle finestre effettive dall'origine, non da `giorni × finestre_al_giorno` — che al primo giorno in cui il conteggio cambia farebbe saltare il mazzo di centinaia di posizioni, bruciando immagini mai viste.

Il calcolo resta **deterministico e senza stato**: due PC con la stessa libreria ottengono la stessa sequenza senza parlarsi, che è la proprietà su cui si regge la sincronizzazione multi-PC.

---

## Periodi dell'anno

Un **periodo** è un intervallo di date che modula le regole casuali **senza duplicarle**.

```json
"periods": [
  { "name": "Halloween", "from": "10-20", "to": "11-01",
    "exclude": ["estate", "natale", "primavera"],
    "random_rules": {
      "weekday": [
        { "from": "sunset-40m", "to": "01:00", "include": ["horror"],
          "match": "all", "rotate_minutes": 60 }
      ]
    } },

  { "name": "Autunno", "from": "09-10", "to": "11-30",
    "exclude": ["estate", "inverno", "natale", "primavera"] }
]
```

| Campo          | Effetto                                                                   |
| -------------- | ------------------------------------------------------------------------- |
| `from` / `to`  | `MM-GG`, **senza anno**: il periodo si ripete ogni anno                    |
| `exclude`      | Stagioni vietate. Un'immagine cade solo se **tutte** le stagioni che dichiara sono vietate |
| `prefer`       | Tag preferiti: il pool si restringe a quelli solo se ne resta abbastanza   |
| `prefer_min`   | Soglia di `prefer`. Senza, con pochi tag preferiti la fascia resta fissa   |
| `require`      | Tag obbligatori, si sommano all'`include` (in AND). Raro                   |
| `random_rules` | Fasce proprie del periodo, con la stessa forma di `random_rules`. Si editano col pulsante **Fasce del periodo** |

### Un'immagine in più stagioni

I tag stagionali **non sono un divieto per tag, ma per insieme**: un'immagine cade solo se **ogni** stagione di cui porta il tag è vietata dal periodo attivo.

```
inverno + primavera   ->  esce in Inverno, in Primavera e in Inv-Prim
solo primavera        ->  resta fuori dall'inverno, come prima
nessun tag stagionale ->  esce sempre, in ogni periodo
```

Serve per poter dire "questa va bene in due stagioni" senza doverlo esprimere con un tag per ogni combinazione. Col divieto secco che c'era prima, `autunno + primavera` significava invece *vietata in autunno* **e** *vietata in primavera*: più stagioni si assegnavano a un'immagine, meno si vedeva — fino a sparire dall'anno intero. In una libreria di 197 immagini ce n'erano **nove** in quello stato, taggate con cura e mai mostrate.

Quali tag contino come stagione non è una lista fissa nel codice: sono **tutti quelli che almeno un periodo vieta**. Così chi aggiunge una stagione sua (`carnevale`) non deve toccare niente, e un tag come `tramonto`, che nessun periodo vieta, non rende stagionale l'immagine che lo porta.

L'`exclude` della singola **regola** resta invece un divieto secco per tag: `-smart` toglie l'immagine e basta. Sono due cose diverse e stanno in due campi diversi.

**Le date si ripetono ogni anno** e se la fine precede l'inizio il periodo **scavalca il capodanno**: `"from": "12-01", "to": "01-06"` copre dicembre e la Befana, con lo stesso confronto invertito che gestisce le fasce a cavallo della mezzanotte.

**Vince il primo periodo attivo**, quindi i periodi festivi vanno messi **sopra** quelli stagionali.

**Le `random_rules` del periodo non sostituiscono quelle di base**: vengono consultate prima, e se nessuna copre l'ora corrente si scende alla base, esattamente come fanno gli override di giorno. Per questo il periodo Halloween è una riga sola — prende dal tramonto all'una di notte e lascia tutto il resto della giornata all'autunno.

### Perché non duplicare le regole

Nel `config.json` la libreria immagini pesa il **32%** del file, le regole casuali il **10%**: la parte che si vorrebbe differenziare per stagione è la più piccola. Quattro config stagionali completi duplicherebbero la libreria — e taggare un'immagine diventerebbe quattro modifiche, con le liste di tag che divergono in silenzio — per de-duplicare le regole.

Tutti e sei i periodi insieme pesano **1.188 byte, il 3% del file**, e due di quelli portano anche fasce orarie proprie.

### I periodi devono coprire l'anno intero

Un giorno che **nessun** periodo copre non applica nessun filtro: a luglio tornerebbero le immagini invernali. La tab **Periodi dell'anno** lo segnala in fondo (*"12 giorni senza periodo: …"*), e il pulsante **Verifica anno** passa i mesi in rassegna e avvisa sulle fasce rimaste con meno di 5 immagini — che per una stagione intera resterebbero quasi fisse.

---

## L'editor grafico

Nella sezione **Casuale** dell'editor:

| Tab                     | A cosa serve                                                        |
| ----------------------- | ------------------------------------------------------------------- |
| Tag                     | Il vocabolario. Rinominare o cancellare un tag lo aggiorna anche nei periodi |
| Libreria immagini       | Assegna i tag alle immagini                                          |
| **Periodi dell'anno**   | I periodi, in ordine di priorità. Avvisa sui giorni non coperti, e ha **Verifica anno** e **Fasce del periodo** |
| Regole feriali/weekend  | Le fasce. Mostrano l'orario reale di oggi accanto alle ancore solari  |
| Regole override giorno  | Fasce per un singolo giorno della settimana                          |
| **Anteprima giorno**    | Una data qualsiasi risolta ora per ora, con il motore vero           |

**Fasce del periodo** apre le fasce orarie proprie del periodo selezionato — feriali, weekend e override di giorno — con lo stesso editor delle regole di base, ancore solari e conteggio immagini compresi. Si aprono anche su un periodo che non ne ha: le liste rimaste vuote vengono tolte alla chiusura, così un periodo senza fasce resta pulito nel `config.json`.

**Anteprima giorno** è lo strumento da usare quando qualcosa non torna: per ogni finestra della giornata mostra periodo attivo, regola vincente, fascia con l'orario solare risolto, tag effettivi, dimensione del pool e immagine scelta. In fondo riporta quante immagini distinte escono e qual è il pool più piccolo.

In **Impostazioni → Posizione** si impostano latitudine e longitudine, con un elenco delle principali città italiane e gli orari solari di oggi come conferma.

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
[2026-12-25 15:00:03] Avvio Chametiger. Modalita': random
[2026-12-25 15:00:03] [OK] Sfondo impostato (casuale, weekday [periodo Natale] 14:00-18:00 [lavoro/pomeriggio -autunno,-estate,-primavera,-smart]): G:\Temi\...
[2026-12-25 16:00:07] [OK] Sfondo impostato (casuale, periodo Natale weekday sunset-40m (15:57)-23:30 [natale]): G:\Temi\...
```

Nei tag, `+` significa che servono **tutti** quelli elencati, `/` che ne basta **uno**, `-tag` sono le esclusioni della regola, `!tag` le stagioni vietate dal periodo e `~tag` i preferiti.

La categoria dice anche **quale periodo** era attivo. `periodo Natale weekday` è una fascia propria del periodo; `weekday [periodo Natale]` è una regola di base vista attraverso il periodo. Accanto alle ancore solari c'è l'orario a cui sono cadute davvero.

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
| In casuale esce sempre la stessa      | La regola ha pochi candidati: usa **Verifica anno** nella tab Periodi    |
| Le immagini si ripetono troppo spesso | Il pool è piccolo: il mazzo si riavvolge presto. Taggane altre, o allarga i tag della regola. `history_days` **non** c'entra |
| Su un altro PC non trova le immagini  | Aggiungi il suo hostname in `path_map`                                  |
| Le fasce serali cadono nell'ora sbagliata | Coordinate sbagliate: **Impostazioni → Posizione**                  |
| Un'immagine stagionale non esce mai   | Ogni stagione che dichiara è vietata dal periodo attivo: guarda la colonna Tag in **Anteprima giorno**. Se le stagioni sono più d'una, basta che una sia ammessa |
| A luglio escono immagini invernali    | Un giorno dell'anno non è coperto da nessun periodo: la tab Periodi lo segnala |
| Una fascia resta ferma tutto il giorno | Pool troppo piccolo, o `prefer` che stringe troppo: alza `prefer_min`  |
