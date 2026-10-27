package io.github.sirfrederik.chametiger

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.FonteMeteo
import io.github.sirfrederik.chametiger.motore.Motore
import io.github.sirfrederik.chametiger.motore.Regola
import io.github.sirfrederik.chametiger.motore.Sole
import io.github.sirfrederik.chametiger.motore.risolviSu
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

// Cosa uscirebbe adesso: l'equivalente di una riga dell'Anteprima della GUI.
// Non mostra niente e non ricorda niente: ogni calcolo crea il suo Motore,
// con le cache dentro l'istanza.

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
    /** null: nessuna regola copre questo istante con almeno un'immagine. */
    val scelta: Scelta?,
)

data class Scelta(
    val immagine: String,
    val origine: String,
    /** 'sunset-40m (16:12)-dusk+30m (17:34)', come descrivi_fascia della GUI. */
    val fascia: String,
    /** '+mattino,-alba !natale ~jolly @pioggia', come la colonna tag della GUI. */
    val tag: String,
    val pool: Int,
    val ordinale: Int,
    /** Il minuto in cui e' cominciata la finestra, nella sequenza di oggi. */
    val inizio: String,
    val firma: String,
    val file: File,
    val presente: Boolean,
)

fun calcolaAnteprima(config: Config, identita: String, adesso: LocalDateTime, cartella: File): Anteprima {
    // Meteo fisso su asciutto finche' non c'e' il download: allineati coi PC
    // solo nelle ore senza pioggia
    val motore = Motore(config, identita, ZONA, FonteMeteo.NESSUNA)
    val giorno = adesso.toLocalDate()
    val (lat, lon) = config.coordinate(identita)

    val orari = motore.sole.orari(giorno)
    val orariSolari = listOf(
        "dawn" to "dawn", "alba" to "sunrise", "mezzogiorno" to "noon",
        "tramonto" to "sunset", "dusk" to "dusk",
    ).map { (etichetta, chiave) -> etichetta to (orari[chiave]?.format(HM) ?: "n.d.") }

    val scelta = motore.scelta(adesso)?.let { f ->
        val file = File(risolviSu(config, cartella.path, f.immagine))
        Scelta(
            immagine = f.immagine,
            origine = f.origine,
            fascia = descriviFascia(motore.sole, f.regola, giorno),
            tag = descriviTag(f.regola),
            pool = f.pool,
            ordinale = f.ordinale,
            inizio = hm(f.minuto),
            firma = f.firma,
            file = file,
            presente = file.isFile,
        )
    }

    return Anteprima(
        adesso = adesso,
        identita = identita,
        lat = lat,
        lon = lon,
        inPositionMap = config.inPositionMap(identita),
        meteoAttivo = config.meteoAttivo,
        pila = motore.stratiDelGiorno(giorno).reversed().joinToString(" > ") { it.nome },
        orariSolari = orariSolari,
        scelta = scelta,
    )
}

private val HM = DateTimeFormatter.ofPattern("HH:mm")

private fun hm(minuti: Int): String = "%02d:%02d".format(minuti / 60, minuti % 60)

/** sun.describe: 'sunset-40m' -> 'sunset-40m (19:12)'. */
private fun descriviOrario(sole: Sole, t: String?, giorno: LocalDate): String {
    t ?: return "?"
    if (Sole.isMinmax(t)) {
        val m = sole.minmaxMinuti(t, giorno) ?: return "$t (n.d.)"
        return "$t (${hm(m)})"
    }
    val (ancora, offset) = Sole.parseAncora(t) ?: return t
    val m = sole.minutiSolari(ancora, offset, giorno) ?: return "$t (n.d.)"
    return "$t (${hm(Math.floorMod(m, 1440))})"
}

private fun descriviFascia(sole: Sole, regola: Regola, giorno: LocalDate): String =
    "${descriviOrario(sole, regola.from, giorno)}-${descriviOrario(sole, regola.to, giorno)}"

private fun descriviTag(regola: Regola): String {
    val tag = mutableListOf<String>()
    if (regola.include.isNotEmpty()) tag += regola.include.joinToString(if (regola.match == "all") "+" else "/")
    if (regola.exclude.isNotEmpty()) tag += regola.exclude.joinToString(",") { "-$it" }
    if (regola.veto.isNotEmpty()) tag += regola.veto.joinToString(",") { "!$it" }
    if (regola.prefer.isNotEmpty()) tag += regola.prefer.joinToString(",") { "~$it" }
    regola.meteo?.takeIf { it.piove }?.let { tag += "@${it.tag}" }
    return tag.joinToString(" ")
}
