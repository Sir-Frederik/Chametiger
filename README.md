# 🦎 Chametiger

**v4.2** — 1 ottobre 2026
Pasqua: date relative alla festa mobile, ricalcolate ogni anno.


Wallpaper scheduler per Windows — cambia lo sfondo in base all'**ora del giorno**, al **giorno della settimana**, alla **stagione**, agli **eventi** dell'anno e agli **orari reali di alba e tramonto**.

Ogni fascia oraria pesca fra le immagini che hanno certi **tag**, e le fa scorrere tutte prima di ripeterle.

---

## Novità della 4.2

- **Date relative a Pasqua.** Le date di stagioni ed eventi accettano, oltre a `MM-GG`, anche `pasqua`, `pasqua-5`, `pasqua+2`: giorni prima o dopo la domenica di Pasqua, ricalcolata ogni anno (algoritmo di Meeus, in `date_mobili.py`, senza dipendenze). La durata la decidi tu con lo scostamento. Vedi [Feste mobili](#feste-mobili).
- **Evento Pasqua** nel config, da `pasqua-5` a `pasqua+2` (8 giorni: nel 2027 dal 23 al 30 marzo), col tag `pasqua` e niente horror.
- **Il dialogo mostra dove cadono le date mobili** quest'anno e il prossimo; il grafico dell'anno indica l'anno a cui si riferisce.

## Novità della 4.1

- **Vietati sempre (`veto`)**: ogni stagione o evento può vietare dei tag senza appello, accanto al divieto morbido dei tag di stagione. A Natale "no horror" toglie ogni immagine horror, anche quelle taggate `inverno` o `natale`; finito Natale il veto sparisce. Il veto scende lungo la pila (vale anche nelle ore che si torna alla stagione) ma non sale negli eventi annidati sopra. Vedi [Vietati sempre](#vietati-sempre).
- **Nel config**: niente horror a Natale, Capodanno e San Valentino; niente `natale` né `sanValentino` ad Halloween. Capodanno ha il suo veto perché, stando sopra Natale, non eredita quello di Natale.
- **Anteprima e log** mostrano i tag vietati dal periodo come `!horror`; la tabella degli eventi come "natale  no horror".

## Novità della 4.0

- **Stagioni ed eventi al posto dei periodi.** Prima c'era un elenco solo, e vinceva il primo periodo che copriva la data: un evento doveva stare sopra la stagione per vincere, ma vincendo la sostituiva per intero. San Valentino, messo sotto l'Inverno, non usciva mai; Natale, messo sopra, si mangiava l'Inverno dal 1° dicembre al 6 gennaio, e nelle ore senza fasce proprie le regole di base venivano filtrate coi divieti di Natale. Ora sono due livelli: le **stagioni** coprono l'anno, gli **eventi** ci si appoggiano sopra. Vedi [Stagioni ed eventi](#stagioni-ed-eventi).
- **Gli eventi si annidano come matrioske**: Capodanno sopra Natale sopra l'Inverno. Ogni strato ha le sue fasce; nelle ore che non copre si scende allo strato sotto, con i tag ammessi da quello strato.
- **Le transizioni sono sovrapposizioni.** Non servono più le righe `Inv-Prim`, `Prim-Est`…: dove Inverno e Primavera si sovrappongono valgono entrambe.
- **Niente più tag vietati da scrivere a mano.** Ogni stagione ed evento dichiara i *suoi* tag; un tag di stagione o di evento vale solo nei giorni del suo periodo. Prima `sanValentino` non lo vietava nessun periodo, e tre immagini con solo quel tag potevano uscire a luglio.
- **Grafico dell'anno** nella tab *Stagioni ed eventi*: una riga per stagione e per evento, con le sovrapposizioni incolonnate e la linea di oggi.
- **Rimossa la modalità programmata**, con il suo ripiego, i giorni speciali, le impostazioni e le tab. I due giorni speciali ancora utili sono diventati eventi (*Capodanno*, *Compleanno*). Le tab dell'editor ora stanno su una fila sola.
- **Verifica regole conta per strato**: per ogni regola mostra quante immagini pesca in ogni combinazione dell'anno in cui viene davvero letta (*Inverno*, *Inverno/Primavera*, *Inverno > Natale*…). Le regole di base si contano sotto ogni stagione, le fasce di un evento solo nel suo strato.
- **Verifica anno controlla ogni combinazione**: oltre al 15 di ogni mese prende il primo giorno di ogni pila distinta, così anche un evento di un giorno solo e ogni transizione passano il controllo.
- **Anteprima e log dicono da quale strato viene la regola**: `evento Natale weekday`, `stagione Estate weekday`, oppure `weekday [Inverno]` per una regola di base filtrata dalla stagione. Sparisce l'elenco `!tag` delle stagioni vietate, che con tutti i tag di stagione ed evento sarebbe diventato illeggibile.
- **Un nome solo per periodo**: l'editor rifiuta due stagioni o eventi con lo stesso nome, che nel log e nell'anteprima si confonderebbero.

### Aggiornare dalla 3.x

- **La chiave `periods` non viene più letta.** Va divisa in `seasons` ed `events`, e ogni periodo dichiara i suoi `tags` al posto della lista `exclude`. Il `config.json` di questo repository è già convertito; le chiavi `mode`, `schedules`, `overrides` e `special_days` sono state tolte.
- **Riavvia l'app nel tray** dopo l'aggiornamento: un'istanza col codice vecchio, letto il config nuovo, smetterebbe di cambiare lo sfondo.
- **I mazzi si rimescolano una volta**: la firma delle regole contiene il nome dello strato, quindi le sequenze non riprendono da dove erano.
- **Un tag di evento vale solo nell'evento.** Le immagini con solo `horror` ora escono nelle sere di Halloween e basta (in un anno simulato: da 1120 a 125 uscite); prima uscivano anche in primavera, estate e autunno. Per riaverle tutto l'anno basta togliere `horror` dai tag di Halloween.

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
├── sun.py          ← Orari solari: alba, tramonto, crepuscolo, mezzogiorno solare
├── verifica_immagini.py ← Simula un anno e trova le immagini che non escono mai
├── versione.py     ← Numero di versione, mostrato nel tray e nell'editor
├── date_mobili.py  ← Date di stagioni ed eventi, comprese quelle relative a Pasqua
├── config.json     ← Configurazione: regole, stagioni, eventi, tag, libreria
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

  "latitude": 40.8518,
  "longitude": 14.2681,

  "base_path": "G:/Temi",
  "path_map": {
    "NomePC": "C:/Users/Tizio/Pictures/Temi"
  },

  "tags": ["mattino", "lavoro", "notte", "..."],
  "image_library": { "cartella/foto.jpg": ["mattino", "lavoro"] },
  "random_rules": {
    "weekday":   [ ... ],
    "weekend":   [ ... ],
    "overrides": { "monday": [ ... ] }
  },
  "seasons": [
    { "name": "Autunno", "from": "09-15", "to": "11-30", "tags": ["autunno"] }
  ],
  "events": [
    { "name": "Halloween", "from": "10-20", "to": "11-01", "tags": ["horror"],
      "random_rules": { "weekday": [ ... ] } }
  ]
}
```

| Chiave                    | A cosa serve                                                        |
| ------------------------- | ------------------------------------------------------------------- |
| `check_interval_minutes`  | Ogni quanto lo scheduler ricontrolla                                 |
| `history_days`            | Per quanti giorni conservare le righe di `log.json` (default 7). Non è nell'editor: **non** influenza quale immagine esce |
| `latitude` / `longitude`  | Posizione, per calcolare alba e tramonto. Default: Napoli            |
| `base_path` / `path_map`  | Cartella base delle immagini, con override per singolo PC (hostname) |
| `seasons` / `events`      | Stagioni ed eventi, che filtrano i tag (vedi sotto)                  |

### Percorsi multi-PC

`base_path` è la cartella di riferimento; `path_map` la sostituisce sui PC elencati, usando il **nome del computer** come chiave. Nella libreria le immagini si indicano con percorsi **relativi** a quella cartella, così la stessa `config.json` funziona ovunque.

---

## Regole e tag

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

Se nessuna regola copre l'orario, lo sfondo resta quello che c'è.

> I tag **stagionali** (`inverno`, `estate`, `natale`…) non vanno messi nell'`exclude` delle regole: è il lavoro di [stagioni ed eventi](#stagioni-ed-eventi). Ripetuti in ogni regola diventano decine di righe da tenere allineate a mano, e una stagione dimenticata si nota solo sei mesi dopo.

### Come viene scelta l'immagine

Non è un sorteggio. Le immagini che soddisfano la regola vengono disposte in un **mazzo**, mescolato in modo deterministico a partire dalla regola stessa; ogni finestra di rotazione pesca la carta successiva. Finito il mazzo si rimescola con un ordine nuovo, e la prima carta non coincide mai con l'ultima del giro precedente. Così tutta la raccolta scorre prima che qualcosa si ripeta, senza bisogno di tenere conteggi.

Dentro la stessa giornata non ci sono ripetizioni: se la carta che toccherebbe è già uscita oggi, si avanza nel mazzo fino alla prima non ancora vista. Vale anche fra regole diverse — un'immagine vista stamattina non torna nel pomeriggio.

Il calcolo è **deterministico e senza stato**: dipende solo dalla regola, dalla libreria e dalla data. Due PC con la stessa configurazione ottengono la stessa sequenza senza parlarsi, ed è questo che fa funzionare la sincronizzazione multi-PC.

`log.json` **non** partecipa alla scelta: serve a ricordare quale immagine è stata assegnata alla finestra corrente, così lo sfondo resta fermo fra un controllo e l'altro dello scheduler, e a far durare un'estrazione forzata fino alla fine della sua finestra.

### Priorità (dalla più alta)

1. **eventi del giorno**, dal più interno → override del giorno, poi feriali/weekend, poi feriali se il weekend non copre
2. **stagione** (o le due stagioni di una transizione) → idem
3. **regole di base** → idem, filtrate dalla stagione

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

## Stagioni ed eventi

Due livelli di periodi, entrambi intervalli di date che si ripetono ogni anno:

- le **stagioni** coprono l'anno intero; dove due si sovrappongono c'è una **transizione** e valgono entrambe;
- gli **eventi** sono facoltativi e si appoggiano sopra la stagione. Si possono **annidare**: Capodanno dentro Natale dentro l'Inverno.

```json
"seasons": [
  { "name": "Inverno",   "from": "11-16", "to": "04-05", "tags": ["inverno"] },
  { "name": "Primavera", "from": "03-06", "to": "07-06", "tags": ["primavera"] }
],
"events": [
  { "name": "Natale", "from": "12-01", "to": "01-06", "tags": ["natale"],
    "random_rules": {
      "weekday": [
        { "from": "dusk", "to": "02:00", "include": ["natale"],
          "match": "all", "rotate_minutes": 60 }
      ]
    } },
  { "name": "Capodanno", "from": "01-01", "to": "01-01", "tags": ["capodanno"],
    "random_rules": { "weekday": [ ... ] } }
]
```

| Campo          | Effetto                                                                   |
| -------------- | ------------------------------------------------------------------------- |
| `from` / `to`  | `MM-GG`, **senza anno**: il periodo si ripete ogni anno. Se la fine precede l'inizio scavalca il capodanno. Per le feste mobili: `pasqua-5`, `pasqua+2` |
| `tags`         | I tag del periodo: valgono solo nei suoi giorni                            |
| `veto`         | Tag vietati senza appello nei giorni del periodo: basta averne uno e l'immagine è fuori |
| `random_rules` | Fasce proprie, con la stessa forma di `random_rules`. Si editano col pulsante **Fasce** |
| `prefer`       | Tag preferiti: il pool si restringe a quelli solo se ne resta abbastanza   |
| `prefer_min`   | Soglia di `prefer`. Senza, con pochi tag preferiti la fascia resta fissa   |
| `require`      | Tag obbligatori, si sommano all'`include` (in AND). Raro                   |

### Feste mobili

Pasqua cade fra il 22 marzo e il 25 aprile, quindi una data fissa sarebbe giusta un anno su tanti. Nei campi `from` e `to` si può scrivere una data **relativa alla domenica di Pasqua**:

```json
{ "name": "Pasqua", "from": "pasqua-5", "to": "pasqua+2", "tags": ["pasqua"], "veto": ["horror"] }
```

| Scrittura      | Giorno                                   |
| -------------- | ---------------------------------------- |
| `pasqua`       | La domenica di Pasqua                    |
| `pasqua-5`     | Cinque giorni prima (anche `pasqua - 5g`) |
| `pasqua+1`     | Il lunedì dell'Angelo                    |

La data si ricalcola **ogni anno**, così l'evento dura sempre quanto hai deciso: `pasqua-5 → pasqua+2` sono 8 giorni, dal 31 marzo al 7 aprile nel 2026 e dal 23 al 30 marzo nel 2027. Una data fissa e una mobile si possono anche mescolare (`03-01 → pasqua`). Il dialogo dell'evento mostra dove cadono le date quest'anno e il prossimo; il grafico le disegna nell'anno corrente.

### La pila del giorno

Ogni giorno è una pila di **strati**, dall'evento più interno alla stagione. Il 1° gennaio:

```
Capodanno   ammette capodanno, natale, inverno
Natale      ammette natale, inverno
Inverno     ammette inverno            <- qui sotto anche le regole di base
```

Le fasce si leggono dall'alto: prima quelle di Capodanno, poi quelle di Natale, poi quelle dell'Inverno, infine le regole di base. Vince la prima che copre l'ora e ha immagini. **Ogni fascia pesca con i tag ammessi dal suo strato**: nelle ore che Natale non copre si torna all'Inverno, con i divieti dell'Inverno. Così un evento cambia solo le ore che gli interessano, e un evento senza fasce proprie non cambia niente.

Fra due eventi sovrapposti sta sopra **il più corto**, che è il più specifico; a parità di durata, quello che viene prima nell'elenco. In una transizione le fasce proprie delle due stagioni si leggono nell'ordine dell'elenco.

### Un'immagine in più stagioni

I tag stagionali **non sono un divieto per tag, ma per insieme**: un'immagine cade solo se **tutti** i suoi tag di stagione o di evento sono fuori periodo.

```
inverno + primavera   ->  esce in Inverno, in Primavera e nella transizione
solo primavera        ->  resta fuori dall'inverno
primavera + sanValentino -> esce in primavera, e a San Valentino anche d'inverno
nessun tag stagionale ->  esce sempre
```

Quali tag contino come stagione non è una lista fissa nel codice: sono **tutti quelli dichiarati da stagioni ed eventi**. Un tag come `tramonto`, che nessuno dichiara, non rende stagionale l'immagine che lo porta.

L'`exclude` della singola **regola** resta invece un divieto secco per tag: `-smart` toglie l'immagine e basta.

### Vietati sempre

I tag di stagione ed evento sono un divieto **morbido**: un'immagine cade solo se *tutti* i suoi tag di stagione sono fuori periodo. Per dire invece *"in questo periodo, questo tag no, punto"* c'è il **veto**, la lista **Vietati sempre** nel dialogo della stagione o dell'evento:

```json
{ "name": "Natale", "from": "12-01", "to": "01-06", "tags": ["natale"], "veto": ["horror"] }
```

Un'immagine con anche un solo tag vietato è fuori, qualunque altro tag porti: `horror + inverno + natale` a Natale non esce. Finito il periodo, il veto non c'è più.

Il veto **scende** lungo la pila: vale nelle fasce del suo strato e in tutte quelle sotto, quindi il "no horror" di Natale tiene anche nelle ore che si torna all'Inverno e alle regole di base. Uno strato annidato **sopra** non lo eredita e decide per conto suo: un "no horror" sull'Autunno lascia intatte le fasce di Halloween, che gli sta sopra.

```
Halloween   veto: -           <- le sue fasce pescano l'horror
Autunno     veto: horror      <- qui e nelle regole di base, no
```

In **Anteprima** e nel log un tag vietato dal periodo compare come `!horror`.

### Le stagioni devono coprire l'anno intero

Un giorno che **nessuna** stagione copre non applica nessun filtro di stagione: a luglio tornerebbero le immagini invernali. La tab **Stagioni ed eventi** lo segnala in fondo (*"12 giorni senza stagione: …"*), e il pulsante **Verifica anno** controlla ogni combinazione di stagioni ed eventi dell'anno e avvisa sulle fasce rimaste con meno di 5 immagini.

---

## L'editor grafico

| Tab                     | A cosa serve                                                        |
| ----------------------- | ------------------------------------------------------------------- |
| Tag                     | Il vocabolario. Rinominare o cancellare un tag lo aggiorna anche in stagioni ed eventi |
| Libreria                | Assegna i tag alle immagini                                          |
| **Stagioni ed eventi**  | Il grafico dell'anno e le due tabelle. Avvisa sui giorni senza stagione, e ha **Verifica anno** |
| Feriali / Weekend       | Le regole di base. Mostrano l'orario reale di oggi accanto alle ancore solari |
| Override giorno         | Regole di base per un singolo giorno della settimana                 |
| **Anteprima**           | Una data qualsiasi risolta ora per ora, con il motore vero           |

Nel **grafico** ogni stagione ed evento è una riga, coi mesi in colonna: le transizioni e gli eventi annidati si vedono incolonnati, e cliccando una barra si seleziona la riga nella tabella.

**Fasce** apre le fasce orarie proprie della stagione o dell'evento selezionato — feriali, weekend e override di giorno — con lo stesso editor delle regole di base, ancore solari e conteggio immagini compresi. Si aprono anche su un periodo che non ne ha: le liste rimaste vuote vengono tolte alla chiusura, così un periodo senza fasce resta pulito nel `config.json`.

**Anteprima** è lo strumento da usare quando qualcosa non torna: per ogni finestra della giornata mostra la pila del giorno (*Inverno > Natale*), regola vincente, fascia con l'orario solare risolto, tag effettivi, dimensione del pool e immagine scelta. In fondo riporta quante immagini distinte escono e qual è il pool più piccolo.

In **Impostazioni → Posizione** si impostano latitudine e longitudine, con un elenco delle principali città italiane e gli orari solari di oggi come conferma.

---

## Menu tray (tasto destro sull'icona)

| Voce                    | Descrizione                                      |
| ----------------------- | ------------------------------------------------ |
| Applica adesso          | Forza il controllo immediato                     |
| Cambia immagine adesso  | Nuova estrazione subito                          |
| Apri editor config      | Apre la GUI di configurazione                    |
| \* Avvio con Windows    | Toggle avvio automatico                          |
| Esci                    | Chiude l'applicazione                            |

---

## Log

`chametiger.log` registra ogni cambio di sfondo indicando **quale regola** ha vinto:

```
[2026-12-25 15:00:03] Avvio Chametiger 4.2.
[2026-12-25 15:00:03] [OK] Sfondo impostato (weekday [Inverno] 14:00-18:00 [lavoro/pomeriggio -smart]): G:\Temi\...
[2026-12-25 16:00:07] [OK] Sfondo impostato (evento Natale weekday sunset-40m (15:57)-23:30 [natale]): G:\Temi\...
```

Nei tag, `+` significa che servono **tutti** quelli elencati, `/` che ne basta **uno**, `-tag` sono le esclusioni della regola, `!tag` i tag vietati dal periodo e `~tag` i preferiti.

La categoria dice anche **da quale strato** viene la regola. `evento Natale weekday` è una fascia propria dell'evento; `weekday [Inverno]` è una regola di base filtrata dalla stagione. Accanto alle ancore solari c'è l'orario a cui sono cadute davvero.

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
| Esce sempre la stessa                 | La regola ha pochi candidati: usa **Verifica anno** in Stagioni ed eventi |
| Le immagini si ripetono troppo spesso | Il pool è piccolo: il mazzo si riavvolge presto. Taggane altre, o allarga i tag della regola. `history_days` **non** c'entra |
| Su un altro PC non trova le immagini  | Aggiungi il suo hostname in `path_map`                                  |
| Le fasce serali cadono nell'ora sbagliata | Coordinate sbagliate: **Impostazioni → Posizione**                  |
| Un'immagine stagionale non esce mai   | Tutti i suoi tag di stagione o evento sono fuori periodo, ha un tag vietato (`!tag`), oppure è ammessa solo in uno strato le cui fasce non la pescano: guarda **Anteprima** |
| A luglio escono immagini invernali    | Un giorno dell'anno non è coperto da nessuna stagione: la tab Stagioni ed eventi lo segnala |
| Una fascia resta ferma tutto il giorno | Pool troppo piccolo, o `prefer` che stringe troppo: alza `prefer_min`  |
