package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import java.io.File
import java.time.LocalDateTime
import java.util.Locale

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
 * `cartella` e' quella condivisa via USB (config.json, immagini, log),
 * `interna` quella privata dell'app (ultimo config buono, forzata).
 */
class Ciclo(
    private val cartella: File,
    private val interna: File,
    private val identita: String,
    private val versione: String,
    private val sfondo: Sfondo,
    private val diario: Diario = DiarioFile(File(cartella, NOME_LOG)),
    private val orologio: () -> LocalDateTime = { LocalDateTime.now(ZONA) },
) {
    private val memoria = MemoriaForzataFile(File(interna, "forzata.txt"))

    /** Cosa si mostrerebbe adesso, per la schermata: non scrive il log e non mette sfondi. */
    fun valuta(): Valutazione {
        if (identita.isBlank()) return Valutazione.Errore("Imposta l'identità del dispositivo, per esempio android-federico.")
        val lettura = ConfigSicuro(File(cartella, NOME_CONFIG), File(interna, "config.ultimo.json")).leggi()
        if (lettura is ConfigSicuro.Lettura.Nessuna) return Valutazione.Errore(lettura.motivo)
        val (config, avviso) = lettura as ConfigSicuro.Lettura.Ok
        val decisore = Decisore(config, identita, ArchivioCartella(config, cartella))
        val adesso = orologio()
        return Valutazione.Pronta(config, decisore, adesso, decisore.decidi(adesso, memoria.leggi()), avviso)
    }

    fun giro(): Valutazione = synchronized(LOCK) {
        val v = valuta()
        if (v !is Valutazione.Pronta) {
            diario.scrivi("[WARN] ${(v as Valutazione.Errore).messaggio} Nessuno sfondo.")
            return v
        }
        v.avvisoConfig?.let { diario.scrivi("[WARN] $it, continuo con l'ultima configurazione letta") }
        info(v)
        // Una forzata che non vale piu' (finestra finita, file sparito) si dimentica
        val d = v.decisione
        if (!(d is Decisione.Mostra && d.motivo == Motivo.FORZATA)) memoria.leggi()?.let { memoria.scrivi(null) }
        mostra(d)
        v
    }

    /** Estrazione forzata: un'altra immagine fino alla fine della finestra corrente. */
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
        }
        mostra(d)
        v.copy(decisione = d)
    }

    private fun mostra(d: Decisione) {
        when (d) {
            is Decisione.Niente -> diario.scrivi("[CICLO] nessuna immagine: ${d.perche}")
            is Decisione.Mostra -> {
                val f = d.finestra
                if (d.motivo == Motivo.RIPIEGO) {
                    diario.scrivi(
                        "[RIPIEGO] Manca ${d.mancante} (finestra ${f.ordinale}, firma ${f.firma}): " +
                            "mostro ${d.immagine} solo adesso, non entra fra le uscite di oggi",
                    )
                }
                if (sfondo.giaMostrata(d.immagine)) {
                    diario.scrivi("[CICLO] invariato: ${d.immagine}")
                    return
                }
                val prefisso = when (d.motivo) {
                    Motivo.CANONICA -> ""
                    Motivo.FORZATA -> "estrazione forzata, "
                    Motivo.RIPIEGO -> "ripiego, "
                }
                try {
                    sfondo.applica(d.file, d.immagine)
                    diario.scrivi(
                        "[OK] Sfondo impostato ($prefisso${d.categoria}): ${d.immagine} | " +
                            "finestra ${f.ordinale} dalle ${hm(f.minuto)}, pool ${f.pool}, firma ${f.firma}",
                    )
                } catch (e: Exception) {
                    diario.scrivi("[ERR] Impossibile impostare lo sfondo: ${d.immagine}: $e")
                }
            }
        }
    }

    /** Chi e' e dove si crede il telefono: una volta al giorno, e quando cambia qualcosa. */
    private fun info(v: Valutazione.Pronta) {
        val (lat, lon) = v.config.coordinate(identita)
        val fonte = if (v.config.inPositionMap(identita)) "position_map" else "latitude/longitude"
        val pila = v.decisore.motore.stratiDelGiorno(v.adesso.toLocalDate()).reversed().joinToString(" > ") { it.nome }
        val riga = "$identita $versione, ${ZONA.id}, " +
            "%.4f,%.4f".format(Locale.ROOT, lat, lon) + " ($fonte), pila $pila"
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
