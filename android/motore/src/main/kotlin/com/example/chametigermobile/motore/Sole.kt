package com.example.chametigermobile.motore

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import kotlin.math.PI
import kotlin.math.floor

/**
 * Gli orari solari e gli orari delle regole, come sun.py.
 *
 * Il fuso e' esplicito, mentre il Python usa quello del sistema operativo: per
 * restare allineati con i PC deve essere lo stesso (Europe/Rome).
 *
 * Le funzioni trigonometriche sono quelle di StrictMath, che danno gli stessi
 * bit su qualunque JVM e dispositivo. Rispetto alla libm del Python possono
 * differire di un ULP, che conta solo se l'orario cade a meno di un
 * microsecondo dal cambio di secondo.
 */
class Sole(val lat: Double, val lon: Double, val zona: ZoneId) {

    private val cacheGiorni = HashMap<LocalDate, Map<String, LocalDateTime?>>()
    private val cacheMinuti = HashMap<Pair<String, LocalDate>, Int>()

    /** L'orario in minuti dalla mezzanotte di quel giorno, come _resolve_minuti di app.py. */
    fun minuti(t: String, giorno: LocalDate): Int = cacheMinuti.getOrPut(t to giorno) {
        if (isMinmax(t)) {
            // 'min(sunset+2m, 18:00)': non scavalca la mezzanotte, vedi fasciaAssente
            return@getOrPut minmaxMinuti(t, giorno) ?: 0
        }
        val ancora = parseAncora(t)
        if (ancora != null) {
            val m = minutiSolari(ancora.first, ancora.second, giorno) ?: return@getOrPut 0
            return@getOrPut Math.floorMod(m, 1440)
        }
        // parse_time: 'HH:MM', con int() che tollera gli spazi
        val pezzi = t.split(":")
        require(pezzi.size == 2) { "Orario non valido: '$t'" }
        val h = pyInt(pezzi[0]) ?: throw IllegalArgumentException("Orario non valido: '$t'")
        val m = pyInt(pezzi[1]) ?: throw IllegalArgumentException("Orario non valido: '$t'")
        Math.floorMod(h * 60 + m, 1440)
    }

    /** Il min/max in minuti [0, 1440), null se uno degli eventi quel giorno manca. */
    fun minmaxMinuti(t: String, giorno: LocalDate): Int? {
        val (funzione, orari) = parseMinmax(t) ?: return null
        val valori = orari.map { o ->
            val ancora = parseAncora(o)
            (if (ancora != null) minutiSolari(ancora.first, ancora.second, giorno) else parseOrologio(o))
                ?: return null
        }
        val v = if (funzione == "min") valori.min() else valori.max()
        return Math.floorMod(v, 1440)
    }

    /**
     * L'ancora in minuti dalla mezzanotte, offset incluso: puo' uscire da
     * [0, 1440). null se quel giorno l'evento non avviene.
     */
    fun minutiSolari(ancora: String, offset: Int, giorno: LocalDate): Int? {
        val evento = orari(giorno)[ancora] ?: return null
        return evento.hour * 60 + evento.minute + offset
    }

    /** Alba, tramonto, crepuscoli e mezzogiorno vero, in ora locale. */
    fun orari(giorno: LocalDate): Map<String, LocalDateTime?> = cacheGiorni.getOrPut(giorno) {
        val alba = evento(giorno, ZENITH_SUN, true)
        val tramonto = evento(giorno, ZENITH_SUN, false)
        // Meta' esatta dell'arco diurno: (tramonto - alba) / 2 sui datetime naive
        val mezzogiorno = if (alba != null && tramonto != null) {
            alba.plusNanos(Duration.between(alba, tramonto).toNanos() / 2)
        } else null
        mapOf(
            "dawn" to evento(giorno, ZENITH_CIVIL, true),
            "sunrise" to alba,
            "noon" to mezzogiorno,
            "sunset" to tramonto,
            "dusk" to evento(giorno, ZENITH_CIVIL, false),
        )
    }

    /** _sun_event: l'algoritmo NOAA, operazione per operazione. */
    private fun evento(giorno: LocalDate, zenith: Double, rising: Boolean): LocalDateTime? {
        val n = giorno.dayOfYear
        val lngHour = lon / 15.0

        val t = n + ((if (rising) 6.0 else 18.0) - lngHour) / 24.0

        val m = 0.9856 * t - 3.289
        val l = pyMod(
            m + 1.916 * StrictMath.sin(rad(m)) + 0.020 * StrictMath.sin(rad(2 * m)) + 282.634,
            360.0,
        )

        var ra = pyMod(deg(StrictMath.atan(0.91764 * StrictMath.tan(rad(l)))), 360.0)
        ra += pyFloorDiv(l, 90.0) * 90 - pyFloorDiv(ra, 90.0) * 90
        ra /= 15.0

        val sinDec = 0.39782 * StrictMath.sin(rad(l))
        val cosDec = StrictMath.cos(StrictMath.asin(sinDec))

        val cosH = (StrictMath.cos(rad(zenith)) - sinDec * StrictMath.sin(rad(lat))) /
            (cosDec * StrictMath.cos(rad(lat)))
        if (!(cosH >= -1.0 && cosH <= 1.0)) return null

        var h = deg(StrictMath.acos(cosH))
        h = if (rising) 360.0 - h else h
        h /= 15.0

        val tempoLocale = h + ra - 0.06571 * t - 6.622
        val ut = pyMod(tempoLocale - lngHour, 24.0)

        val mezzanotteUtc = giorno.toEpochDay() * 86400
        return daTimestamp(mezzanotteUtc.toDouble() + ut * 3600)
    }

    /**
     * datetime.fromtimestamp(ts).replace(microsecond=0): i microsecondi si
     * arrotondano half-even, e un arrotondamento a 1e6 passa al secondo dopo.
     */
    private fun daTimestamp(ts: Double): LocalDateTime {
        var secondi = floor(ts)
        val micro = Math.rint((ts - secondi) * 1e6)
        if (micro >= 1e6) secondi += 1.0
        return LocalDateTime.ofInstant(Instant.ofEpochSecond(secondi.toLong()), zona)
    }

    companion object {
        private const val ZENITH_SUN = 90.833
        private const val ZENITH_CIVIL = 96.0
        private const val DEG_TO_RAD = PI / 180.0
        private const val RAD_TO_DEG = 180.0 / PI

        private val ANCORE = listOf("dawn", "sunrise", "noon", "sunset", "dusk")
        private val ANCORA_RE = Regex(
            "^(" + ANCORE.joinToString("|") + """)\s*(?:([+-])\s*(\d+)\s*([mh]?))?$""",
            RegexOption.IGNORE_CASE,
        )
        private val MINMAX_RE = Regex("""^(min|max)\s*\((.*)\)$""", RegexOption.IGNORE_CASE)
        private val OROLOGIO_RE = Regex("""^(\d{1,2}):(\d{2})$""")

        private fun rad(x: Double) = x * DEG_TO_RAD
        private fun deg(x: Double) = x * RAD_TO_DEG

        fun isSolare(t: String): Boolean = ANCORA_RE.matches(t.trim())

        /** 'sunset-40m' -> ('sunset', -40). Senza unita' sono minuti. */
        fun parseAncora(t: String): Pair<String, Int>? {
            val m = ANCORA_RE.find(t.trim()) ?: return null
            val (ancora, segno, valore, unita) = m.destructured
            var offset = 0
            if (valore.isNotEmpty()) {
                offset = valore.toInt() * (if (unita.lowercase() == "h") 60 else 1)
                if (segno == "-") offset = -offset
            }
            return ancora.lowercase() to offset
        }

        /** '18:00' -> 1080. null se non e' un orario di orologio valido. */
        fun parseOrologio(t: String): Int? {
            val m = OROLOGIO_RE.find(t.trim()) ?: return null
            val h = m.groupValues[1].toInt()
            val mi = m.groupValues[2].toInt()
            return if (h <= 23 && mi <= 59) h * 60 + mi else null
        }

        /** 'min(sunset+2m, 18:00)' -> ('min', ['sunset+2m', '18:00']): almeno due orari validi. */
        fun parseMinmax(t: String): Pair<String, List<String>>? {
            val m = MINMAX_RE.find(t.trim()) ?: return null
            val orari = m.groupValues[2].split(",").map { it.trim() }
            if (orari.size < 2 || !orari.all { isSolare(it) || parseOrologio(it) != null }) return null
            return m.groupValues[1].lowercase() to orari
        }

        fun isMinmax(t: String?): Boolean = t != null && parseMinmax(t) != null

        /**
         * Una fascia con min()/max() non scavalca la mezzanotte: se quel giorno
         * finisce prima di cominciare, o insieme, quel giorno non c'e'.
         */
        fun fasciaAssente(from: String?, to: String?, start: Int, end: Int): Boolean =
            (isMinmax(from) || isMinmax(to)) && end <= start
    }
}
