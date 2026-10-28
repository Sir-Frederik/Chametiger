package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.FonteMeteo
import io.github.sirfrederik.chametiger.motore.Finestra
import io.github.sirfrederik.chametiger.motore.Motore
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import kotlin.random.Random

// Lo strato sopra il motore: dalla finestra canonica all'immagine da mostrare.
//
// Il motore calcola la sequenza del giorno dalle chiavi di image_library e non
// riceve niente da qui. Per questo un ripiego o un'estrazione forzata cambiano
// solo cio' che si mostra adesso: alla finestra dopo il motore ricalcola la
// sequenza canonica, come se il file ci fosse sempre stato. Se la sostituta
// entrasse fra le immagini uscite oggi, la deviazione si propagherebbe a
// tutte le finestre successive e il telefono non tornerebbe mai allineato.

enum class Motivo { CANONICA, FORZATA, RIPIEGO }

sealed interface Decisione {
    data class Mostra(
        val immagine: String,
        val file: File,
        val finestra: Finestra,
        val motivo: Motivo,
        /** 'weekday [Autunno] 14:00-sunset (16:07) [pomeriggio]', come nel log del tray. */
        val categoria: String,
        /** RIPIEGO: l'immagine canonica, il cui file manca. */
        val mancante: String? = null,
        /** FORZATA: la canonica che c'era stata da mostrare, se diversa. */
        val canonica: String = finestra.immagine,
    ) : Decisione

    data class Niente(val perche: String, val finestra: Finestra? = null) : Decisione
}

/**
 * Un Decisore per calcolo: crea il suo Motore e lo butta. Nessuno stato
 * condiviso, anche quando anteprima e lavoro periodico capitano insieme.
 */
class Decisore(
    config: Config,
    identita: String,
    private val archivio: Archivio,
    fonteMeteo: FonteMeteo = FonteMeteo.NESSUNA,
) {
    val motore = Motore(config, identita, ZONA, fonteMeteo)

    // La sequenza di un giorno costa qualche decimo di secondo e in un giro
    // serve piu' volte. Dentro l'istanza, come le cache del motore.
    private val giornate = HashMap<LocalDate, List<Finestra>>()

    fun giornata(giorno: LocalDate): List<Finestra> = giornate.getOrPut(giorno) { motore.sequenzaGiornaliera(giorno) }

    /** La finestra dopo quella di adesso, oggi o domani: la sua immagine si scarica in anticipo. */
    fun prossima(adesso: LocalDateTime): Finestra? {
        val minuto = adesso.hour * 60 + adesso.minute
        return giornata(adesso.toLocalDate()).firstOrNull { it.minuto > minuto }
            ?: giornata(adesso.toLocalDate().plusDays(1)).firstOrNull()
    }

    /** Cosa mostrare adesso, tenendo conto di un'eventuale forzata per questa finestra. */
    fun decidi(adesso: LocalDateTime, forzata: Forzata? = null): Decisione {
        val giornata = giornata(adesso.toLocalDate())
        val finestra = motore.sceltaIn(adesso, giornata)
            ?: return Decisione.Niente("Nessuna regola copre questo istante")
        val cat = categoria(motore.sole, finestra, adesso.toLocalDate())

        if (forzata != null && valeQui(forzata, adesso, finestra) && archivio.esiste(forzata.immagine)) {
            return Decisione.Mostra(forzata.immagine, archivio.file(forzata.immagine), finestra, Motivo.FORZATA, cat)
        }
        if (archivio.esiste(finestra.immagine)) {
            return Decisione.Mostra(finestra.immagine, archivio.file(finestra.immagine), finestra, Motivo.CANONICA, cat)
        }

        // Ripiego: il mazzo della stessa finestra, dalla carta dopo quella
        // scelta. Deterministico: due telefoni senza lo stesso file mostrano
        // la stessa sostituta.
        val mazzo = motore.mazzoDi(finestra)
        val i = mazzo.indexOf(finestra.immagine)
        val dopo = (1 until mazzo.size).map { mazzo[(i + it) % mazzo.size] }
        val sostituta = primaLibera(dopo, giornata, adesso) { it.first() }
            ?: return Decisione.Niente(
                "Manca ${finestra.immagine} e nessun'altra immagine del suo pool e' sul telefono",
                finestra,
            )
        return Decisione.Mostra(
            sostituta, archivio.file(sostituta), finestra, Motivo.RIPIEGO, cat, mancante = finestra.immagine,
        )
    }

    /**
     * Un'estrazione forzata, come force_new in pick_from_rule: casuale, fuori
     * dall'immagine che si vede adesso e da quelle che la sequenza del giorno
     * assegna ad altre finestre. Se le esclusioni svuotano il pool si rinuncia
     * prima a quelle future, poi a tutte. Solo fra i file presenti.
     *
     * Ritorna la forzata da ricordare, o il motivo per cui non c'e'.
     */
    fun forza(adesso: LocalDateTime, attuale: Forzata?, caso: Random = Random.Default): Result<Forzata> {
        val giornata = giornata(adesso.toLocalDate())
        val finestra = motore.sceltaIn(adesso, giornata)
            ?: return Result.failure(IllegalStateException("Nessuna regola attiva adesso"))
        val corrente = (decidi(adesso, attuale) as? Decisione.Mostra)?.immagine
        val resto = motore.mazzoDi(finestra).filter { it != corrente }.sorted()
        val scelta = primaLibera(resto, giornata, adesso) { candidate -> candidate.random(caso) }
            ?: return Result.failure(IllegalStateException("Nessun'altra immagine del pool e' sul telefono"))
        return Result.success(Forzata(adesso.toLocalDate(), finestra.firma, finestra.ordinale, scelta))
    }

    /**
     * Fra le immagini presenti, la prima scelta da `scegli` con esclusioni via
     * via piu' larghe: fuori da tutta la giornata, poi solo da quelle gia'
     * uscite, poi nessuna.
     */
    private fun primaLibera(
        immagini: List<String>,
        giornata: List<Finestra>,
        adesso: LocalDateTime,
        scegli: (List<String>) -> String,
    ): String? {
        val minuto = adesso.hour * 60 + adesso.minute
        val presenti = immagini.filter { archivio.esiste(it) }
        val tutte = giornata.mapTo(HashSet()) { it.immagine }
        val passate = giornata.filter { it.minuto <= minuto }.mapTo(HashSet()) { it.immagine }
        for (escluse in listOf(tutte, passate, emptySet())) {
            val libere = presenti.filter { it !in escluse }
            if (libere.isNotEmpty()) return scegli(libere)
        }
        return null
    }

    private fun valeQui(f: Forzata, adesso: LocalDateTime, finestra: Finestra): Boolean =
        f.giorno == adesso.toLocalDate() && f.firma == finestra.firma && f.ordinale == finestra.ordinale &&
            f.immagine in motore.mazzoDi(finestra)
}
