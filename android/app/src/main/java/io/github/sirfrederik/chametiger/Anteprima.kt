package io.github.sirfrederik.chametiger

import io.github.sirfrederik.chametiger.strato.Decisione
import io.github.sirfrederik.chametiger.strato.Motivo
import io.github.sirfrederik.chametiger.strato.Valutazione
import io.github.sirfrederik.chametiger.strato.descriviFascia
import io.github.sirfrederik.chametiger.strato.descriviTag
import io.github.sirfrederik.chametiger.strato.hm
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

// Cosa uscirebbe adesso: l'equivalente di una riga dell'Anteprima della GUI.
// Viene dalla stessa decisione del lavoro periodico, ripiego e forzata
// compresi, cosi' lo schermo dice cosa fa davvero il telefono.

data class Anteprima(
    val adesso: LocalDateTime,
    val identita: String,
    val lat: Double,
    val lon: Double,
    /** False: l'identita' non e' in position_map, valgono latitude/longitude. */
    val inPositionMap: Boolean,
    val meteoAttivo: Boolean,
    /** 'Inverno > Natale > Capodanno', dal basso. */
    val pila: String,
    /** dawn, alba, mezzogiorno, tramonto, dusk, in ora locale. */
    val orariSolari: List<Pair<String, String>>,
    /** Non nullo: config.json non si legge e si usa l'ultimo buono. */
    val avvisoConfig: String?,
    val scelta: Scelta?,
    /** Perche' non c'e' una scelta, quando non c'e'. */
    val niente: String?,
)

data class Scelta(
    val immagine: String,
    val motivo: Motivo,
    /** RIPIEGO: la canonica il cui file manca. FORZATA: la canonica sostituita. */
    val canonica: String,
    val origine: String,
    /** 'sunset-40m (16:12)-dusk+30m (17:34)', come descrivi_fascia della GUI. */
    val fascia: String,
    /** 'mattino+lavoro -alba !natale ~jolly @pioggia', come nel log del tray. */
    val tag: String,
    val pool: Int,
    val ordinale: Int,
    /** Il minuto in cui e' cominciata la finestra, nella sequenza di oggi. */
    val inizio: String,
    val firma: String,
    val file: File,
)

fun anteprima(v: Valutazione.Pronta, identita: String): Anteprima {
    val motore = v.decisore.motore
    val giorno = v.adesso.toLocalDate()
    val (lat, lon) = v.config.coordinate(identita)

    val orari = motore.sole.orari(giorno)
    val orariSolari = listOf(
        "dawn" to "dawn", "alba" to "sunrise", "mezzogiorno" to "noon",
        "tramonto" to "sunset", "dusk" to "dusk",
    ).map { (etichetta, chiave) -> etichetta to (orari[chiave]?.format(HM) ?: "n.d.") }

    val d = v.decisione
    val scelta = (d as? Decisione.Mostra)?.let {
        val f = it.finestra
        Scelta(
            immagine = it.immagine,
            motivo = it.motivo,
            canonica = it.mancante ?: it.canonica,
            origine = f.origine,
            fascia = descriviFascia(motore.sole, f.regola, giorno),
            tag = descriviTag(f.regola),
            pool = f.pool,
            ordinale = f.ordinale,
            inizio = hm(f.minuto),
            firma = f.firma,
            file = it.file,
        )
    }

    return Anteprima(
        adesso = v.adesso,
        identita = identita,
        lat = lat,
        lon = lon,
        inPositionMap = v.config.inPositionMap(identita),
        meteoAttivo = v.config.meteoAttivo,
        pila = motore.stratiDelGiorno(giorno).reversed().joinToString(" > ") { it.nome },
        orariSolari = orariSolari,
        avvisoConfig = v.avvisoConfig,
        scelta = scelta,
        niente = (d as? Decisione.Niente)?.perche,
    )
}

private val HM = DateTimeFormatter.ofPattern("HH:mm")
