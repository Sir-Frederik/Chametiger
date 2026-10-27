package io.github.sirfrederik.chametiger.motore

import java.security.MessageDigest
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId

// La logica decisionale di app.py: dati data e ora, il config, la libreria e
// il meteo, quale immagine tocca. Deterministica e senza stato: dispositivi con
// gli stessi ingressi calcolano la stessa sequenza senza parlarsi.
//
// Il pool viene dalle chiavi di image_library e non dal disco: se un file manca
// lo decide chi mostra l'immagine, senza toccare la sequenza.

/** Origine del conteggio delle finestre. NON cambiarla mai: trasla tutti i mazzi. */
val EPOCH: LocalDate = LocalDate.of(2026, 1, 1)

/** I momenti della giornata: nell'exclude valgono per insieme, come le stagioni. */
val TAG_ORARI = setOf("alba", "mattino", "pranzo", "pomeriggio", "tramonto", "crepuscolo", "sera", "notte")

private val TAG_METEO = setOf(StatoMeteo.TEMPORALE.tag, StatoMeteo.PIOGGIA.tag)

/** Il meteo ora per ora, fornito da fuori: il motore non lo va a prendere. */
fun interface FonteMeteo {
    /**
     * Gli stati noti per le ore di quel giorno (0-23). Le ore mancanti valgono
     * asciutto, come senza dati: dati vecchi o di un'altra posizione vanno
     * scartati da chi li fornisce.
     */
    fun ore(giorno: LocalDate): Map<Int, StatoMeteo>

    companion object {
        val NESSUNA = FonteMeteo { emptyMap() }
    }
}

/** Uno strato della pila del giorno, dall'evento piu' interno alla stagione. */
data class Strato(
    val nome: String,
    val tipo: String,
    val periodi: List<Periodo>,
    /** I tag stagionali ammessi: i suoi e quelli degli strati sotto. */
    val ammessi: Set<String>,
    /** I tag vietati: i suoi e quelli degli strati sopra. */
    val veto: Set<String>,
)

/** Una regola del giorno, gia' vista attraverso il suo strato, coi confini risolti. */
data class RegolaDelGiorno(val regola: Regola, val origine: String, val start: Int, val end: Int)

/** Una finestra di rotazione della giornata e l'immagine che le tocca. */
data class Finestra(
    val minuto: Int,
    val regola: Regola,
    val origine: String,
    val firma: String,
    val ordinale: Int,
    val immagine: String,
    val pool: Int,
)

class Motore(
    val config: Config,
    val dispositivo: String,
    zona: ZoneId,
    private val fonteMeteo: FonteMeteo = FonteMeteo.NESSUNA,
) {
    val sole: Sole = config.coordinate(dispositivo).let { (lat, lon) -> Sole(lat, lon, zona) }

    private val vocabolario: Set<String> get() = config.tagStagionali
    private val sha256 = MessageDigest.getInstance("SHA-256")

    // ── Orari ────────────────────────────────────────────────────────────────

    fun confini(regola: Regola, giorno: LocalDate): Pair<Int, Int> =
        sole.minuti(regola.from ?: "00:00", giorno) to sole.minuti(regola.to ?: "00:00", giorno)

    // ── Stagioni ed eventi ───────────────────────────────────────────────────

    fun periodoAttivo(periodo: Periodo, giorno: LocalDate): Boolean {
        val start = DateMobili.ordinale(periodo.from, giorno.year) ?: return false
        val end = DateMobili.ordinale(periodo.to, giorno.year) ?: return false
        val oggi = giorno.monthValue * 100 + giorno.dayOfMonth
        return if (start <= end) oggi in start..end else oggi >= start || oggi <= end
    }

    /** Quanti giorni copre il periodo, contati su un anno bisestile. */
    private fun durataPeriodo(periodo: Periodo, anno: Int): Int {
        val start = DateMobili.ordinale(periodo.from, anno) ?: return 0
        val end = DateMobili.ordinale(periodo.to, anno) ?: return 0
        val a = LocalDate.of(ANNO_BISESTILE, start / 100, start % 100)
        val b = LocalDate.of(ANNO_BISESTILE, end / 100, end % 100)
        return Math.floorMod(b.toEpochDay() - a.toEpochDay(), 366L).toInt() + 1
    }

    /** Gli eventi del giorno, dal piu' interno (il piu' corto); a pari durata, l'ordine dell'elenco. */
    private fun eventiAttivi(giorno: LocalDate): List<Periodo> =
        config.eventi.withIndex()
            .filter { periodoAttivo(it.value, giorno) }
            .sortedWith(compareBy({ durataPeriodo(it.value, giorno.year) }, { it.index }))
            .map { it.value }

    fun stratiDelGiorno(giorno: LocalDate): List<Strato> {
        val stagioni = config.stagioni.filter { periodoAttivo(it, giorno) }
        var ammessi: Set<String>
        val nome: String
        if (stagioni.isNotEmpty()) {
            ammessi = stagioni.flatMapTo(mutableSetOf()) { it.tags }
            nome = stagioni.joinToString("/") { it.nome }
        } else {
            // Un buco nel config: si ammettono tutti i tag di stagione
            ammessi = config.stagioni.flatMapTo(mutableSetOf()) { it.tags }
            nome = "nessuna stagione"
        }

        val strati = mutableListOf<Pair<Triple<String, String, List<Periodo>>, Set<String>>>(
            Triple(nome, "stagione", stagioni) to ammessi,
        )
        for (evento in eventiAttivi(giorno).reversed()) {
            ammessi = ammessi + evento.tags
            strati.add(Triple(evento.nome, "evento", listOf(evento)) to ammessi)
        }
        strati.reverse()

        // Il veto scende: dall'alto verso il basso ogni strato somma il suo a
        // quelli degli strati sopra
        val veto = mutableSetOf<String>()
        return strati.map { (info, amm) ->
            info.third.forEach { veto += it.veto }
            Strato(info.first, info.second, info.third, amm, veto.toSet())
        }
    }

    /** La regola vista attraverso lo strato. Una copia, come patch_rule. */
    fun applicaStrato(regola: Regola, strato: Strato): Regola {
        var r = regola
        val vietate = vocabolario - strato.ammessi
        if (vietate.isNotEmpty()) {
            r = r.copy(seasonExclude = vietate.ordinate(), seasonal = vocabolario.ordinate())
        }
        if (strato.veto.isNotEmpty()) r = r.copy(veto = strato.veto.ordinate())

        val richiesti = strato.periodi.flatMap { it.require }
        val preferiti = regola.prefer + strato.periodi.flatMap { it.prefer }
        val minimo = strato.periodi.maxOfOrNull { it.preferMin }?.coerceAtLeast(0) ?: 0

        if (richiesti.isNotEmpty()) r = r.copy(include = (regola.include + richiesti).toSet().ordinate())
        if (preferiti.isNotEmpty()) {
            r = r.copy(prefer = preferiti.toSet().ordinate())
            if (minimo != 0) r = r.copy(preferMin = minimo)
        }
        return r.copy(periodo = strato.nome)
    }

    // ── Estrazione per tag ───────────────────────────────────────────────────

    /** image_matches_rule: se l'immagine con quei tag entra nella regola. */
    fun ammessa(tagImmagine: List<String>, regola: Regola): Boolean {
        val tags = tagImmagine.toSet()

        val escluse = regola.exclude.toSet()
        if (tags.any { it in escluse && it !in TAG_ORARI }) return false
        val orari = tags intersect TAG_ORARI
        if (orari.isNotEmpty() && escluse.containsAll(orari)) return false
        if (tags.any { it in regola.veto }) return false

        val vietate = regola.seasonExclude.toSet()
        if (vietate.isNotEmpty()) {
            val dichiarate = regola.seasonal.ifEmpty { regola.seasonExclude }.toSet()
            val stagioni = tags intersect dichiarate
            if (stagioni.isNotEmpty() && vietate.containsAll(stagioni)) return false
        }

        val include = regola.include
        if (include.isEmpty()) return true
        if (regola.matchAny) {
            if (include.any { it in tags }) return true
        } else if (include.all { it in tags }) {
            return true
        }

        // Quando piove, un'immagine di pioggia entra anche senza i tag della
        // fascia, purche' abbia uno dei suoi momenti e i tag del tema
        val piove = regola.meteo?.piove == true && tags.any { it in TAG_METEO }
        if (piove && tags.any { it in regola.momenti }) return tags.containsAll(regola.tema)
        return false
    }

    /** candidates_for_rule, senza il controllo sul disco: il pool e' la libreria. */
    fun candidate(regola: Regola): List<String> {
        val libreria = config.libreria
        var out = libreria.filter { (_, tags) -> ammessa(tags, regola) }.keys.toList()

        val prefer = regola.prefer.toSet()
        if (prefer.isNotEmpty()) {
            val minimo = maxOf(1, regola.preferMin ?: 1)
            val scelti = out.filter { img -> libreria[img].orEmpty().any { it in prefer } }
            // Si restringe solo se ne resta abbastanza
            if (scelti.size >= minimo) out = scelti
        }
        return secondoMeteo(out, regola.meteo)
    }

    /** _secondo_meteo: il pool visto attraverso il tempo che fa, sopra prefer. */
    private fun secondoMeteo(pool: List<String>, stato: StatoMeteo?): List<String> {
        stato ?: return pool
        val libreria = config.libreria
        val minimo = config.meteoMinimo
        fun conTag(gruppo: Set<String>) = pool.filter { img -> libreria[img].orEmpty().any { it in gruppo } }

        if (stato == StatoMeteo.ASCIUTTO) {
            val scelti = pool.filter { img -> libreria[img].orEmpty().none { it in TAG_METEO } }
            return if (scelti.size >= minimo) scelti else pool
        }
        val gruppi = if (stato == StatoMeteo.TEMPORALE) {
            listOf(setOf(StatoMeteo.TEMPORALE.tag), TAG_METEO)
        } else {
            listOf(setOf(StatoMeteo.PIOGGIA.tag))
        }
        for (gruppo in gruppi) {
            val scelti = conTag(gruppo)
            if (scelti.size >= minimo) return scelti
        }
        return pool
    }

    /** La regola col tempo dell'ora. Una copia, come _con_meteo. */
    private fun conMeteo(regola: Regola, stato: StatoMeteo?, campi: Pair<List<String>, List<String>>?): Regola {
        stato ?: return regola
        var r = regola.copy(meteo = stato)
        if (campi != null) {
            if (campi.first.isNotEmpty()) r = r.copy(momenti = campi.first)
            if (campi.second.isNotEmpty()) r = r.copy(tema = campi.second)
        }
        return r
    }

    /**
     * _campi_meteo: quando piove, i momenti della fascia (o della prima sotto di
     * lei che ne chiede) e i tag di stagione richiesti in AND. `regole` sono
     * quelle che coprono lo stesso istante, in ordine di priorita'.
     */
    private fun campiMeteo(regole: List<Regola>, pos: Int): Pair<List<String>, List<String>> {
        var momenti: Set<String> = emptySet()
        for (r in regole.subList(pos, regole.size)) {
            momenti = TAG_ORARI intersect r.include.toSet()
            if (momenti.isNotEmpty()) break
        }
        val regola = regole[pos]
        val tema = if (!regola.matchAny) vocabolario intersect regola.include.toSet() else emptySet()
        return momenti.ordinate() to tema.ordinate()
    }

    /** _rule_signature: l'identita' della regola, seme del mazzo. */
    fun firma(regola: Regola): String {
        val parti = mutableListOf(
            regola.from ?: "",
            regola.to ?: "",
            regola.include.ordinate().joinToString(","),
            regola.exclude.ordinate().joinToString(","),
            regola.match,
        )
        if (regola.seasonExclude.isNotEmpty()) parti += "se:" + regola.seasonExclude.ordinate().joinToString(",")
        if (regola.veto.isNotEmpty()) parti += "v:" + regola.veto.ordinate().joinToString(",")
        if (regola.prefer.isNotEmpty()) {
            parti += "p:" + regola.prefer.ordinate().joinToString(",")
            if (regola.preferMin != null && regola.preferMin != 0) parti += "pm:" + regola.preferMin
        }
        if (!regola.periodo.isNullOrEmpty()) parti += "s:" + regola.periodo
        regola.meteo?.let { parti += "m:" + it.tag }
        if (regola.momenti.isNotEmpty()) parti += "mo:" + regola.momenti.joinToString(",")
        return parti.joinToString("|")
    }

    // ── Finestre di rotazione ────────────────────────────────────────────────

    /** Durata della fascia in minuti. Inizio e fine uguali: tutto il giorno. */
    private fun lunghezza(start: Int, end: Int): Int = Math.floorMod(end - start, 1440).let { if (it == 0) 1440 else it }

    /** Quante finestre ha la regola quel giorno: parti uguali di durata vicina a rotate. */
    private fun finestreDelGiorno(regola: Regola, giorno: LocalDate, rotate: Int): Int {
        val (start, end) = confini(regola, giorno)
        if (Sole.fasciaAssente(regola.from, regola.to, start, end)) return 0
        return maxOf(1, (lunghezza(start, end).toDouble() / rotate + 0.5).toInt())
    }

    // Somme cumulative delle finestre da EPOCH, per (from, to, rotate): e' tutto
    // cio' che determina la durata delle finestre. somme[i] = finestre dei
    // giorni da EPOCH a EPOCH + i - 1.
    private val somme = HashMap<Triple<String?, String?, Int>, MutableList<Int>>()

    /** Quante finestre ha avuto la regola da EPOCH al giorno PRECEDENTE a `giorno`. */
    private fun finestreFinoA(regola: Regola, giorno: LocalDate, rotate: Int): Int {
        if (!giorno.isAfter(EPOCH)) return 0
        val giorni = (giorno.toEpochDay() - EPOCH.toEpochDay()).toInt()
        val cum = somme.getOrPut(Triple(regola.from, regola.to, rotate)) { mutableListOf(0) }
        while (cum.size <= giorni) {
            val g = EPOCH.plusDays((cum.size - 1).toLong())
            cum.add(cum.last() + finestreDelGiorno(regola, g, rotate))
        }
        return cum[giorni]
    }

    /** _window_ordinal: numero progressivo della finestra, contando solo quelle che la regola copre. */
    fun ordinale(regola: Regola, adesso: LocalDateTime, rotate: Int): Int {
        var giorno = adesso.toLocalDate()
        var (start, end) = confini(regola, giorno)
        var cur = adesso.hour * 60 + adesso.minute

        if (start >= end && cur < end) {
            // Coda dopo la mezzanotte: la finestra e' iniziata ieri
            giorno = giorno.minusDays(1)
            val ieri = confini(regola, giorno)
            start = ieri.first
            end = ieri.second
            cur += 1440
        } else if (cur < start) {
            cur = start // fuori fascia: si resta sulla prima finestra
        }

        val perGiorno = finestreDelGiorno(regola, giorno, rotate)
        val offset = minOf(Math.floorDiv((cur - start) * perGiorno, lunghezza(start, end)), perGiorno - 1)
        return finestreFinoA(regola, giorno, rotate) + offset
    }

    /** Il pool ordinato per sha256("firma|giro|immagine"), come _ordine. */
    private fun ordinePerHash(pool: List<String>, firma: String, giro: Int): List<String> =
        pool.map { it to sha256.digest("$firma|$giro|$it".toByteArray(Charsets.UTF_8)) }
            .sortedWith { a, b -> confrontaByte(a.second, b.second) }
            .map { it.first }

    /** L'ordine delle immagini per un giro completo, come _mazzo. */
    fun mazzo(pool: List<String>, firma: String, giro: Int): List<String> {
        if (pool.size <= 2) return pool.ordinate() // l'unica sequenza sensata e' l'alternanza

        val m = ordinePerHash(pool, firma, giro).toMutableList()
        // L'ultima carta del giro prima e la prima di questo non coincidono
        val prec = ordinePerHash(pool, firma, giro - 1)
        if (m[0] == prec.last()) {
            m[0] = m[1].also { m[1] = m[0] }
        }
        return m
    }

    // ── Priorita' ────────────────────────────────────────────────────────────

    private val cacheRegole = object : LinkedHashMap<LocalDate, List<RegolaDelGiorno>>() {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<LocalDate, List<RegolaDelGiorno>>?) = size > 4
    }

    /**
     * Le regole del giorno in ordine di priorita', coi confini risolti. Strato
     * per strato, dall'evento piu' interno alla stagione: override del giorno,
     * feriali/weekend, e nel weekend il ripiego sulle feriali. In fondo le
     * regole di base, viste attraverso la stagione.
     */
    fun regoleDelGiorno(giorno: LocalDate): List<RegolaDelGiorno> = cacheRegole.getOrPut(giorno) {
        val nomeGiorno = NOMI_GIORNI.getValue(giorno.dayOfWeek)
        val chiave = if (giorno.dayOfWeek in WEEKEND) "weekend" else "weekday"
        val strati = stratiDelGiorno(giorno)

        fun fontiDi(regole: RegoleCasuali, etichetta: String): List<Pair<List<Regola>?, String>> {
            val fonti = mutableListOf(
                regole.overrides[nomeGiorno] to "${etichetta}override $nomeGiorno",
                (if (chiave == "weekend") regole.weekend else regole.weekday) to "$etichetta$chiave",
            )
            if (chiave == "weekend") fonti += regole.weekday to "${etichetta}fallback weekday"
            return fonti
        }

        val out = mutableListOf<RegolaDelGiorno>()
        fun aggiungi(fonti: List<Pair<List<Regola>?, String>>, strato: Strato, suffisso: String = "") {
            for ((regole, origine) in fonti) {
                for (regola in regole.orEmpty()) {
                    val (start, end) = confini(regola, giorno)
                    if (Sole.fasciaAssente(regola.from, regola.to, start, end)) continue
                    out += RegolaDelGiorno(applicaStrato(regola, strato), origine + suffisso, start, end)
                }
            }
        }

        for (strato in strati) {
            for (periodo in strato.periodi) {
                if (!periodo.regole.vuote) aggiungi(fontiDi(periodo.regole, "${strato.tipo} ${periodo.nome} "), strato)
            }
        }
        val stagione = strati.last()
        aggiungi(fontiDi(config.regole, ""), stagione, " [${stagione.nome}]")
        out
    }

    /** _copre: se la fascia contiene quel minuto. La fine e' esclusa. */
    private fun copre(start: Int, end: Int, minuto: Int): Boolean = when {
        start == end -> true
        start < end -> minuto in start until end
        else -> minuto >= start || minuto < end
    }

    /** {ora: stato} delle 24 ore, o null col meteo disattivato: come meteo.del_giorno. */
    fun meteoDelGiorno(giorno: LocalDate): Map<Int, StatoMeteo>? {
        if (!config.meteoAttivo) return null
        val noti = fonteMeteo.ore(giorno)
        return (0 until 24).associateWith { noti[it] ?: StatoMeteo.ASCIUTTO }
    }

    /** regole_candidate: le regole che coprono quell'istante, in priorita', col meteo dell'ora. */
    fun regoleCandidate(quando: LocalDateTime): List<Pair<Regola, String>> {
        val minuto = quando.hour * 60 + quando.minute
        val stato = meteoDelGiorno(quando.toLocalDate())?.get(quando.hour)
        val coprono = regoleDelGiorno(quando.toLocalDate()).filter { copre(it.start, it.end, minuto) }
        if (stato?.piove != true) return coprono.map { conMeteo(it.regola, stato, null) to it.origine }
        val regole = coprono.map { it.regola }
        return coprono.mapIndexed { i, r -> conMeteo(r.regola, stato, campiMeteo(regole, i)) to r.origine }
    }

    // ── La sequenza del giorno ───────────────────────────────────────────────

    /**
     * Tutte le finestre di rotazione della giornata fino a `finoA` (minuto),
     * con l'immagine assegnata a ognuna: in ogni minuto vince la prima regola
     * che lo copre e ha immagini, e ogni finestra nuova pesca dal mazzo la prima
     * carta non ancora uscita oggi. Non legge e non scrive nulla.
     */
    fun sequenzaGiornaliera(giorno: LocalDate, finoA: Int = 1439): List<Finestra> {
        val regole = regoleDelGiorno(giorno)
        if (regole.isEmpty()) return emptyList()

        val oreMeteo = meteoDelGiorno(giorno).orEmpty()
        val pools = HashMap<String, List<String>>() // una volta per firma, non per finestra
        val usate = HashSet<String>()
        val sequenza = mutableListOf<Finestra>()
        var ultimaFinestra: Pair<String, Int>? = null

        for (minuto in 0..minOf(finoA, 1439)) {
            val t = giorno.atStartOfDay().plusMinutes(minuto.toLong())
            val stato = oreMeteo[minuto / 60]
            val coprono = regole.filter { copre(it.start, it.end, minuto) }

            var scelto: Triple<RegolaDelGiorno, Regola, String>? = null
            var pool: List<String> = emptyList()
            for ((pos, rdg) in coprono.withIndex()) {
                val campi = if (stato?.piove == true) campiMeteo(coprono.map { it.regola }, pos) else null
                val regola = conMeteo(rdg.regola, stato, campi)
                val firma = firma(regola)
                pool = pools.getOrPut(firma) { candidate(regola).ordinate() }
                if (pool.isNotEmpty()) {
                    scelto = Triple(rdg, regola, firma)
                    break
                }
            }
            val (rdg, regola, firma) = scelto ?: continue

            val ordinale = ordinale(regola, t, regola.rotate)
            val finestra = firma to ordinale
            if (finestra == ultimaFinestra) continue // stessa finestra del minuto prima
            ultimaFinestra = finestra

            val n = pool.size
            val giro = Math.floorDiv(ordinale, n)
            val pos = Math.floorMod(ordinale, n)
            val mazzo = mazzo(pool, firma, giro)

            // Avanza fino alla prima carta non ancora uscita oggi
            val scelta = (0 until n).map { mazzo[(pos + it) % n] }.firstOrNull { it !in usate } ?: mazzo[pos]
            usate += scelta

            sequenza += Finestra(minuto, regola, rdg.origine, firma, ordinale, scelta, n)
        }
        return sequenza
    }

    /**
     * La finestra di adesso, con l'immagine che le tocca, o null se nessuna
     * regola copre quell'istante con almeno un'immagine. E' la scelta di
     * resolve_random, senza il memo di log.json: un'estrazione forzata o un
     * file mancante li gestisce chi sta sopra.
     */
    fun scelta(quando: LocalDateTime): Finestra? {
        if (regoleCandidate(quando).none { (regola, _) -> candidate(regola).isNotEmpty() }) return null
        return sequenzaGiornaliera(quando.toLocalDate(), quando.hour * 60 + quando.minute).lastOrNull()
    }

    companion object {
        private const val ANNO_BISESTILE = 2024
        private val WEEKEND = setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)
        private val NOMI_GIORNI = DayOfWeek.values().associateWith { it.name.lowercase() }

        private fun confrontaByte(a: ByteArray, b: ByteArray): Int {
            for (i in 0 until minOf(a.size, b.size)) {
                val c = (a[i].toInt() and 0xFF).compareTo(b[i].toInt() and 0xFF)
                if (c != 0) return c
            }
            return a.size.compareTo(b.size)
        }
    }
}
