package io.github.sirfrederik.chametiger.motore

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

/**
 * Il motore Kotlin contro il Python, che e' la specifica. Il riferimento lo
 * genera motore/riferimento/genera_riferimento.py: per ogni giorno la sequenza
 * completa delle finestre e la scelta a ogni ora piena. Devono coincidere tutte.
 */
class RiferimentoTest {

    @Test
    fun conMeteo() = confronta("con_meteo")

    @Test
    fun senzaMeteo() = confronta("senza_meteo")

    private data class Attesa(val minuto: Int, val ordinale: Int, val immagine: String, val firma: String)

    private fun confronta(scenario: String) {
        val config = Config.leggi(risorsa("$scenario/config.json"))

        val meteo = HashMap<LocalDate, Map<Int, StatoMeteo>>()
        val sequenze = LinkedHashMap<LocalDate, MutableList<Attesa>>()
        val ore = mutableListOf<Triple<LocalDate, Int, String>>()
        for (riga in risorsa("$scenario/riferimento.tsv").lines()) {
            if (riga.isBlank() || riga.startsWith("#")) continue
            val c = riga.split("\t")
            val giorno = LocalDate.parse(c[1])
            when (c[0]) {
                "M" -> meteo[giorno] = c[2].withIndex().associate { (h, lettera) -> h to STATI.getValue(lettera) }
                "S" -> sequenze.getOrPut(giorno) { mutableListOf() } += Attesa(c[2].toInt(), c[3].toInt(), c[4], c[5])
                "H" -> ore += Triple(giorno, c[2].toInt(), c[3])
                else -> error("Riga sconosciuta: $riga")
            }
        }
        assertTrue("Riferimento $scenario troppo piccolo", sequenze.size > 50 && ore.size > 1000)

        val motore = Motore(config, DISPOSITIVO, ZONA) { giorno -> meteo[giorno].orEmpty() }
        val differenze = mutableListOf<String>()

        // Le sequenze: per giorno basta la prima finestra diversa, le altre ne
        // discendono quasi sempre
        for ((giorno, attese) in sequenze) {
            val ottenute = motore.sequenzaGiornaliera(giorno).map {
                Attesa(it.minuto, it.ordinale, it.immagine, it.firma)
            }
            val i = (0 until maxOf(attese.size, ottenute.size))
                .firstOrNull { attese.getOrNull(it) != ottenute.getOrNull(it) } ?: continue
            differenze += "$giorno finestra $i\n    Python: ${attese.getOrNull(i)}\n    Kotlin: ${ottenute.getOrNull(i)}"
        }

        var oreDiverse = 0
        for ((giorno, ora, attesa) in ore) {
            val ottenuta = motore.scelta(giorno.atTime(ora, 0))?.immagine ?: ""
            if (ottenuta != attesa) {
                if (oreDiverse++ < 20) differenze += "$giorno ${"%02d".format(ora)}:00  Python: '$attesa'  Kotlin: '$ottenuta'"
            }
        }

        val giorniDiversi = differenze.size - minOf(oreDiverse, 20)
        assertEquals(
            "Scenario $scenario: $giorniDiversi giorni con sequenze diverse, $oreDiverse ore diverse su ${ore.size}\n" +
                differenze.take(40).joinToString("\n"),
            0,
            differenze.size,
        )
    }

    private fun risorsa(nome: String): String =
        requireNotNull(javaClass.getResource("/riferimento/$nome")) { "Manca il riferimento $nome" }
            .readText(Charsets.UTF_8)

    companion object {
        private const val DISPOSITIVO = "Federico"
        private val ZONA = ZoneId.of("Europe/Rome")
        private val STATI = mapOf('A' to StatoMeteo.ASCIUTTO, 'P' to StatoMeteo.PIOGGIA, 'T' to StatoMeteo.TEMPORALE)
    }
}
