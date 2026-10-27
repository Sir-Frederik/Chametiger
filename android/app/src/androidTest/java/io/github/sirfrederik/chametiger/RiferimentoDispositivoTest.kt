package io.github.sirfrederik.chametiger

import android.icu.util.TimeZone
import android.os.Build
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.Motore
import io.github.sirfrederik.chametiger.motore.StatoMeteo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset

/**
 * Il motore contro il Python, ma sulla runtime di Android: i test del modulo
 * motore girano sulla JVM del desktop, e non dicono niente sull'implementazione
 * di java.time, sui dati dei fusi e sull'ICU del telefono.
 *
 * Il campione sono sessanta giorni del riferimento (vedi
 * motore/riferimento/campione_dispositivo.py): cambi d'ora, Pasqua, confine
 * d'anno, pioggia, fasce min/max che spariscono, confini dei periodi.
 */
@RunWith(AndroidJUnit4::class)
class RiferimentoDispositivoTest {

    @Test
    fun minSdkConJavaTimeNativo() {
        // Sotto la 26 java.time richiede il desugaring, con i suoi dati dei fusi
        val minSdk = InstrumentationRegistry.getInstrumentation().targetContext.applicationInfo.minSdkVersion
        assertTrue("minSdk $minSdk: sotto 26 java.time non e' quello del sistema", minSdk >= 26)
    }

    @Test
    fun europaRomaDaiDatiDelTelefono() {
        Log.i(TAG, "tzdata ${TimeZone.getTZDataVersion()}, fuso di sistema ${ZoneId.systemDefault()}, SDK ${Build.VERSION.SDK_INT}")
        val roma = ZoneId.of("Europe/Rome").rules
        // I due cambi d'ora del 2027, all'01:00 UTC dell'ultima domenica di marzo e ottobre
        fun offset(utc: String) = roma.getOffset(LocalDateTime.parse(utc).toInstant(ZoneOffset.UTC))
        assertEquals(ZoneOffset.ofHours(1), offset("2027-03-28T00:59:59"))
        assertEquals(ZoneOffset.ofHours(2), offset("2027-03-28T01:00:00"))
        assertEquals(ZoneOffset.ofHours(2), offset("2027-10-31T00:59:59"))
        assertEquals(ZoneOffset.ofHours(1), offset("2027-10-31T01:00:00"))
        assertEquals(ZoneOffset.ofHours(1), offset("2028-01-01T00:00:00"))
    }

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
        for (riga in risorsa("$scenario/campione.tsv").lines()) {
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
        assertTrue("Campione $scenario vuoto", sequenze.isNotEmpty() && ore.isNotEmpty())

        val motore = Motore(config, DISPOSITIVO, ZONA) { giorno -> meteo[giorno].orEmpty() }
        val differenze = mutableListOf<String>()

        for ((giorno, attese) in sequenze) {
            val ottenute = motore.sequenzaGiornaliera(giorno).map {
                Attesa(it.minuto, it.ordinale, it.immagine, it.firma)
            }
            val i = (0 until maxOf(attese.size, ottenute.size))
                .firstOrNull { attese.getOrNull(it) != ottenute.getOrNull(it) } ?: continue
            differenze += "$giorno finestra $i\n    Python: ${attese.getOrNull(i)}\n    Android: ${ottenute.getOrNull(i)}"
        }

        var oreDiverse = 0
        for ((giorno, ora, attesa) in ore) {
            val ottenuta = motore.scelta(giorno.atTime(ora, 0))?.immagine ?: ""
            if (ottenuta != attesa && oreDiverse++ < 20) {
                differenze += "$giorno ${"%02d".format(ora)}:00  Python: '$attesa'  Android: '$ottenuta'"
            }
        }

        Log.i(TAG, "$scenario: ${sequenze.size} giorni, ${sequenze.values.sumOf { it.size }} finestre, ${ore.size} ore")
        val giorniDiversi = differenze.size - minOf(oreDiverse, 20)
        assertEquals(
            "Scenario $scenario: $giorniDiversi giorni con sequenze diverse, $oreDiverse ore diverse su ${ore.size}\n" +
                differenze.take(40).joinToString("\n"),
            0,
            differenze.size,
        )
    }

    /** Dagli asset dell'APK di test, non di quello dell'app. */
    private fun risorsa(nome: String): String =
        InstrumentationRegistry.getInstrumentation().context.assets
            .open("riferimento/$nome").bufferedReader(Charsets.UTF_8).use { it.readText() }

    companion object {
        private const val TAG = "RiferimentoTest"
        private const val DISPOSITIVO = "Federico"
        private val STATI = mapOf('A' to StatoMeteo.ASCIUTTO, 'P' to StatoMeteo.PIOGGIA, 'T' to StatoMeteo.TEMPORALE)
    }
}
