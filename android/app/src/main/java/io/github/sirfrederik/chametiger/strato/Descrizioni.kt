package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Finestra
import io.github.sirfrederik.chametiger.motore.Regola
import io.github.sirfrederik.chametiger.motore.Sole
import java.time.LocalDate
import java.time.ZoneId

// Le regole e le fasce scritte come le scrive il tray nel suo log, cosi' una
// riga del telefono si confronta a occhio con chametiger.log dei PC.

/**
 * Il fuso dei PC. L'ora "adesso" e gli orari solari si calcolano qui anche se
 * il telefono e' altrove: come le coordinate, un fuso locale diverso
 * sposterebbe i confini delle fasce e romperebbe l'allineamento.
 */
val ZONA: ZoneId = ZoneId.of("Europe/Rome")

fun hm(minuti: Int): String = "%02d:%02d".format(minuti / 60, minuti % 60)

/** sun.describe: 'sunset-40m' -> 'sunset-40m (19:12)'. */
fun descriviOrario(sole: Sole, t: String?, giorno: LocalDate): String {
    t ?: return "?"
    if (Sole.isMinmax(t)) {
        val m = sole.minmaxMinuti(t, giorno) ?: return "$t (n.d.)"
        return "$t (${hm(m)})"
    }
    val (ancora, offset) = Sole.parseAncora(t) ?: return t
    val m = sole.minutiSolari(ancora, offset, giorno) ?: return "$t (n.d.)"
    return "$t (${hm(Math.floorMod(m, 1440))})"
}

/** _window: 'sunset-40m (16:58)-dusk (17:29)'. */
fun descriviFascia(sole: Sole, regola: Regola, giorno: LocalDate): String =
    "${descriviOrario(sole, regola.from, giorno)}-${descriviOrario(sole, regola.to, giorno)}"

/** _tags_of senza le parentesi: 'mattino+lavoro -alba !natale ~jolly @pioggia'. */
fun descriviTag(regola: Regola): String {
    val tag = mutableListOf<String>()
    if (regola.include.isNotEmpty()) tag += regola.include.joinToString(if (regola.matchAny) "/" else "+")
    if (regola.exclude.isNotEmpty()) tag += regola.exclude.joinToString(",") { "-$it" }
    if (regola.veto.isNotEmpty()) tag += regola.veto.joinToString(",") { "!$it" }
    if (regola.prefer.isNotEmpty()) tag += regola.prefer.joinToString(",") { "~$it" }
    regola.meteo?.takeIf { it.piove }?.let { tag += "@${it.tag}" }
    return tag.joinToString(" ")
}

/** La categoria di resolve_random: 'weekday [Autunno] 14:00-sunset (16:07) [pomeriggio/lavoro]'. */
fun categoria(sole: Sole, finestra: Finestra, giorno: LocalDate): String {
    val tag = descriviTag(finestra.regola)
    return "${finestra.origine} ${descriviFascia(sole, finestra.regola, giorno)}" + if (tag.isEmpty()) "" else " [$tag]"
}
