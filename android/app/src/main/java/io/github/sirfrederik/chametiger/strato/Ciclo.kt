package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import java.io.File
import java.time.LocalDateTime
import java.util.Locale
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** Chi mette davvero lo sfondo: WallpaperManager sul telefono, un finto nei test. */
interface Sfondo {
    /** Se `immagine` e' gia' lo sfondo, e nessuno l'ha cambiato da fuori. */
    fun giaMostrata(immagine: String): Boolean

    /** Imposta lo sfondo. Un'eccezione se non ci riesce. */
    fun applica(file: File, immagine: String)
}

/** Il config letto e la decisione di adesso, senza aver toccato niente. */
sealed interface Valutazione {
    data class Pronta(
        val config: Config,
        val decisore: Decisore,
        val adesso: LocalDateTime,
        val decisione: Decisione,
        /** Non nullo: config.json non si legge, si usa l'ultimo buono. */
        val avvisoConfig: String?,
        /** Le prime cifre dello SHA-256 del config usato, come nel log del tray. */
        val impronta: String,
        /** Lo stato del meteo in una riga. */
        val meteo: String,
        /** Da dove vengono le coordinate: posizione del telefono, position_map o latitude/longitude. */
        val fonteCoordinate: String,
    ) : Valutazione

    data class Errore(val messaggio: String) : Valutazione
}

/**
 * Un giro dello strato: lo fa il lavoro periodico, "Applica ora" e
 * l'estrazione forzata. Idempotente: se l'immagine da mostrare e' gia' lo
 * sfondo non tocca niente, e lo scrive nel log con una riga [CICLO]. Una riga
 * a ogni risveglio anche quando non cambia niente: i buchi fra due righe
 * dicono quando il sistema ha soppresso i risvegli.
 *
 * `cartella` e' quella condivisa via USB (config.json, immagini, log,
 * meteo.json), `interna` quella privata dell'app (ultimo config buono,
 * forzata, ultimo errore del meteo, indice e cache di Drive).
 *
 * Con Drive configurato (`drive` non nullo) il giro prima aggiorna il config
 * da Drive, poi si assicura l'immagine della finestra, la mostra, scarica in
 * anticipo quella della finestra dopo e tiene la cache sotto il tetto.
 */
class Ciclo(
    private val cartella: File,
    private val interna: File,
    private val identita: String,
    private val versione: String,
    private val sfondo: Sfondo,
    private val diario: Diario = DiarioFile(File(cartella, NOME_LOG)),
    private val orologio: () -> LocalDateTime = { LocalDateTime.now(ZONA) },
    private val rete: Rete = ReteHttp,
    /** Come raggiungere Drive, o null se non e' configurato: allora valgono solo i file copiati via USB. */
    private val drive: ((Diario) -> Sincro)? = null,
    /**
     * L'ultima posizione del telefono, o null: allora valgono le coordinate del
     * config. Vale come la voce del telefono in position_map, per il meteo e
     * per alba e tramonto; entro AGGANCIO_M da una posizione del config prende
     * quella (vedi aggancia).
     */
    private val posizione: Pair<Double, Double>? = null,
) {
    private val memoria = MemoriaForzataFile(File(interna, "forzata.txt"))

    /** Il meteo sulle coordinate di `config`, gia' passato da conPosizione se c'e' una posizione del telefono. */
    private fun meteo(config: Config) = Meteo(
        File(cartella, "meteo.json"), File(interna, "meteo_errore.txt"), identita, versione, diario, rete,
        posizione?.let { config.coordinate(identita) },
    )

    /** Il config con la posizione del telefono al posto di quella del dispositivo, e da dove viene. */
    private fun conLaPosizione(letto: Config): Pair<Config, String> {
        val aggancio = posizione?.let { (lat, lon) -> aggancia(lat, lon, letto.posizioniNote()) }
        val config = (aggancio?.second ?: posizione)?.let { (lat, lon) -> letto.conPosizione(identita, lat, lon) } ?: letto
        val fonte = when {
            aggancio != null -> "posizione del telefono, agganciata a ${aggancio.first}"
            posizione != null -> "posizione del telefono"
            letto.inPositionMap(identita) -> "position_map"
            else -> "latitude/longitude"
        }
        return config to fonte
    }

    /**
     * Se il prossimo giro riscaricherebbe il meteo. Il lavoro in background lo
     * chiede prima del giro, per leggere la posizione del telefono solo allora:
     * il GPS una volta ogni aggiorna_ore, non ogni quarto d'ora.
     */
    fun meteoDaAggiornare(): Boolean = synchronized(LOCK) {
        if (identita.isBlank()) return false
        val lettura = ConfigSicuro(File(cartella, NOME_CONFIG), File(interna, "config.ultimo.json")).leggi()
        val letto = (lettura as? ConfigSicuro.Lettura.Ok)?.config ?: return false
        val (config, _) = conLaPosizione(letto)
        meteo(config).daAggiornare(config, orologio())
    }

    /** Cosa si mostrerebbe adesso, per la schermata: non scarica, non scrive il log e non mette sfondi. */
    fun valuta(): Valutazione = valuta(aggiornaMeteo = false)

    private fun valuta(aggiornaMeteo: Boolean): Valutazione {
        if (identita.isBlank()) return Valutazione.Errore("Imposta l'identità del dispositivo, per esempio android-federico.")
        val lettura = ConfigSicuro(File(cartella, NOME_CONFIG), File(interna, "config.ultimo.json")).leggi()
        if (lettura is ConfigSicuro.Lettura.Nessuna) return Valutazione.Errore(lettura.motivo)
        val (letto, avviso, impronta) = lettura as ConfigSicuro.Lettura.Ok
        val (config, fonte) = conLaPosizione(letto)
        val adesso = orologio()
        val meteo = meteo(config)
        // Come il tray: prima il meteo, poi la scelta. Senza dati validi si sceglie come col sereno
        if (aggiornaMeteo) meteo.aggiornaSeServe(config, adesso)
        val decisore = Decisore(config, identita, ArchivioCartella(config, cartella), meteo.fonte(config, adesso))
        return Valutazione.Pronta(
            config, decisore, adesso, decisore.decidi(adesso, memoria.leggi()), avviso, impronta,
            meteo.descrizione(config, adesso), fonte,
        )
    }

    fun giro(): Valutazione = synchronized(LOCK) {
        val sincro = drive?.invoke(diario)
        // Drive comanda: prima il config, poi tutto il resto lo legge da files/ come sempre
        sincro?.aggiornaConfig()
        var v = valuta(aggiornaMeteo = true)
        if (v !is Valutazione.Pronta) {
            diario.scrivi("[WARN] ${(v as Valutazione.Errore).messaggio} Nessuno sfondo.")
            return v
        }
        v.avvisoConfig?.let { diario.scrivi("[WARN] $it, continuo con l'ultima configurazione letta") }
        info(v)
        if (sincro != null) v = conImmagine(v, sincro)
        // Una forzata che non vale piu' (finestra finita, file sparito) si dimentica
        val d = v.decisione
        if (!(d is Decisione.Mostra && d.motivo == Motivo.FORZATA)) memoria.leggi()?.let { memoria.scrivi(null) }
        val riga = mostra(d)
        if (sincro != null) {
            (d as? Decisione.Mostra)?.let { sincro.usata(it.immagine) }
            val prossima = v.decisore.prossima(v.adesso)?.immagine
            prossima?.let { sincro.assicura(it, "Anticipata") }
            val protette = v.decisore.giornata(v.adesso.toLocalDate()).mapTo(HashSet()) { it.immagine } +
                listOfNotNull((d as? Decisione.Mostra)?.immagine, prossima)
            sincro.pulisci(v.config.libreria.keys, protette)
        }
        diario.scrivi(riga + (sincro?.let { " | Drive ${Sincro.kb(it.byteGiro)}" } ?: ""))
        v
    }

    /**
     * Se il file dell'immagine canonica manca, o su Drive e' cambiato, lo
     * scarica. Se prima mancava e adesso c'e' si ridecide, cosi' non scatta il
     * ripiego; se il download fallisce il ripiego sceglie fra i file in cache.
     */
    private fun conImmagine(v: Valutazione.Pronta, sincro: Sincro): Valutazione.Pronta {
        val d = v.decisione
        val canonica = when (d) {
            is Decisione.Mostra -> d.finestra.immagine.takeIf { d.motivo != Motivo.FORZATA }
            is Decisione.Niente -> d.finestra?.immagine
        } ?: return v
        val cera = File(cartella, canonica).isFile
        if (!sincro.assicura(canonica) || cera) return v
        return v.copy(decisione = v.decisore.decidi(v.adesso, memoria.leggi()))
    }

    /**
     * Il pulsante "Ricontrolla le immagini": scarica le versioni nuove delle
     * immagini in cache cambiate su Drive. Se fra queste c'e' lo sfondo di
     * adesso lo rimette subito. Ritorna una riga per la schermata.
     */
    fun ricontrolla(): String = synchronized(LOCK) {
        val sincro = drive?.invoke(diario)
            ?: return "Drive non è configurato: servono la chiave nella build e il link della cartella."
        sincro.aggiornaConfig()
        val v = valuta()
        if (v !is Valutazione.Pronta) return (v as Valutazione.Errore).messaggio
        val esito = sincro.ricontrolla(v.config.libreria.keys)
        val traffico = " | Drive ${Sincro.kb(sincro.byteGiro)}"
        if (esito == null) {
            diario.scrivi("[DRIVE] Ricontrollo non riuscito: Drive non risponde$traffico")
            return "Drive non risponde: riprova più tardi (il motivo è nel log)."
        }
        val riga = "Ricontrollate ${esito.controllate} immagini in cache: ${esito.cambiate.size} cambiate su Drive, " +
            "${esito.riscaricate.size} riscaricate"
        diario.scrivi("[DRIVE] $riga$traffico")
        val d = v.decisione
        if (d is Decisione.Mostra && d.immagine in esito.riscaricate) diario.scrivi(mostra(d, rimetti = true))
        "$riga."
    }

    /**
     * Il pulsante "Carica meteo": riscarica subito le previsioni, anche dopo un
     * errore recente, poi fa un giro col meteo nuovo. Ritorna una riga per la
     * schermata.
     */
    fun caricaMeteo(): String = synchronized(LOCK) {
        val v = valuta()
        if (v !is Valutazione.Pronta) return (v as Valutazione.Errore).messaggio
        val meteo = meteo(v.config)
        diario.scrivi("[METEO] Carica meteo su ${meteo.origine(v.config)}")
        val scaricato = meteo.aggiornaSeServe(v.config, v.adesso, forza = true)
        val descrizione = (giro() as? Valutazione.Pronta)?.meteo ?: v.meteo
        if (scaricato) "Meteo aggiornato: $descrizione." else "Meteo non scaricato (il motivo è nel log): $descrizione."
    }

    /** Estrazione forzata: un'altra immagine fino alla fine della finestra corrente, fra quelle in cache. */
    fun forza(): Valutazione = synchronized(LOCK) {
        val v = valuta()
        if (v !is Valutazione.Pronta) {
            diario.scrivi("[WARN] Estrazione forzata non riuscita: ${(v as Valutazione.Errore).messaggio}")
            return v
        }
        val esito = v.decisore.forza(v.adesso, memoria.leggi())
        val forzata = esito.getOrElse {
            diario.scrivi("[WARN] Estrazione forzata non riuscita: ${it.message}")
            return v
        }
        memoria.scrivi(forzata)
        val d = v.decisore.decidi(v.adesso, forzata)
        if (d is Decisione.Mostra) {
            diario.scrivi("[FORZATA] ${d.immagine} fino a fine finestra ${d.finestra.ordinale} (dalle ${hm(d.finestra.minuto)})")
            drive?.invoke(diario)?.usata(d.immagine)
        }
        diario.scrivi(mostra(d))
        v.copy(decisione = d)
    }

    /**
     * Mette lo sfondo e ritorna la riga del log che lo racconta: il giro la
     * scrive per ultima, col traffico di Drive in coda. Il ripiego lo scrive
     * subito, prima della riga. `rimetti`: anche se e' gia' lo sfondo, perche'
     * il file e' cambiato.
     */
    private fun mostra(d: Decisione, rimetti: Boolean = false): String = when (d) {
        is Decisione.Niente -> "[CICLO] nessuna immagine: ${d.perche}"
        is Decisione.Mostra -> {
            val f = d.finestra
            if (d.motivo == Motivo.RIPIEGO) {
                diario.scrivi(
                    "[RIPIEGO] Manca ${d.mancante} (finestra ${f.ordinale}, firma ${f.firma}): " +
                        "mostro ${d.immagine} solo adesso, non entra fra le uscite di oggi",
                )
            }
            if (!rimetti && sfondo.giaMostrata(d.immagine)) {
                "[CICLO] invariato: ${d.immagine}"
            } else {
                val prefisso = when (d.motivo) {
                    Motivo.CANONICA -> ""
                    Motivo.FORZATA -> "estrazione forzata, "
                    Motivo.RIPIEGO -> "ripiego, "
                }
                try {
                    sfondo.applica(d.file, d.immagine)
                    "[OK] Sfondo impostato ($prefisso${d.categoria}): ${d.immagine} | " +
                        "finestra ${f.ordinale} dalle ${hm(f.minuto)}, pool ${f.pool}, firma ${f.firma}"
                } catch (e: Exception) {
                    "[ERR] Impossibile impostare lo sfondo: ${d.immagine}: $e"
                }
            }
        }
    }

    /** Chi e' e dove si crede il telefono: una volta al giorno, e quando cambia qualcosa. */
    private fun info(v: Valutazione.Pronta) {
        val (lat, lon) = v.config.coordinate(identita)
        val fonte = v.fonteCoordinate
        val pila = v.decisore.motore.stratiDelGiorno(v.adesso.toLocalDate()).reversed().joinToString(" > ") { it.nome }
        val riga = "$identita $versione, ${ZONA.id}, " +
            "%.4f,%.4f".format(Locale.ROOT, lat, lon) + " ($fonte), pila $pila, config ${v.impronta}"
        val file = File(interna, "info.txt")
        val chiave = "${v.adesso.toLocalDate()}\t$riga"
        if (file.exists() && file.readText(Charsets.UTF_8) == chiave) return
        diario.scrivi("[INFO] $riga")
        scriviIntero(file, chiave)
    }

    companion object {
        const val NOME_CONFIG = "config.json"
        const val NOME_LOG = "chametiger.log"

        /** Lavoro periodico e pulsanti girano nello stesso processo: un giro alla volta. */
        private val LOCK = Any()
    }
}

/**
 * Entro questa distanza la posizione del telefono prende le coordinate esatte
 * di una del config. Il numero della finestra somma le finestre di tutti i
 * giorni prima, e con le fasce legate al sole dipende dalle coordinate: a
 * 300 m dal Lenovo il telefono era gia' una finestra avanti. Agganciato, in
 * ufficio fa gli stessi conti del PC anche se il GPS legge ogni volta un po'
 * diverso.
 */
const val AGGANCIO_M = 1000.0

/** La posizione del config piu' vicina entro AGGANCIO_M, col suo nome, o null. */
fun aggancia(lat: Double, lon: Double, note: Map<String, Pair<Double, Double>>): Pair<String, Pair<Double, Double>>? =
    note.entries
        .map { (nome, p) -> Triple(nome, p, metri(lat, lon, p.first, p.second)) }
        .filter { it.third <= AGGANCIO_M }
        .minByOrNull { it.third }
        ?.let { (nome, p) -> nome to p }

/** Distanza sulla sfera, in metri: per un chilometro basta. */
private fun metri(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
    val dLat = Math.toRadians(lat2 - lat1)
    val dLon = Math.toRadians(lon2 - lon1)
    val a = sin(dLat / 2).pow(2) + cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2).pow(2)
    return 2 * 6_371_000.0 * asin(sqrt(a))
}
