package io.github.sirfrederik.chametiger

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.sirfrederik.chametiger.strato.Archivio
import io.github.sirfrederik.chametiger.strato.ConfigSicuro
import io.github.sirfrederik.chametiger.strato.Decisione
import io.github.sirfrederik.chametiger.strato.Decisore
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDateTime

/**
 * Quanto costa una decisione sul telefono, partendo da zero come il lavoro
 * periodico: config letto e validato, Motore nuovo, sequenza del giorno. Non
 * verifica le scelte (lo fa RiferimentoDispositivoTest), solo i tempi, che
 * finiscono nel logcat sotto il tag TempiDecisione.
 */
@RunWith(AndroidJUnit4::class)
class TempiDecisioneTest {

    private object TuttiPresenti : Archivio {
        override fun file(chiave: String) = File(chiave)
        override fun esiste(chiave: String) = true
    }

    @Test
    fun unaDecisioneDaZero() {
        val testo = InstrumentationRegistry.getInstrumentation().context.assets
            .open("riferimento/con_meteo/config.json").bufferedReader().use { it.readText() }
        // Ore sparse in giorni diversi: ognuna parte senza cache, come un risveglio
        val istanti = (0 until 12).map { LocalDateTime.of(2027, 1 + it, 10 + it, (7 + it * 3) % 24, 30) }

        val tempi = istanti.map { adesso ->
            val inizio = System.nanoTime()
            val config = ConfigSicuro.valida(testo)
            val lettura = System.nanoTime()
            val d = Decisore(config, "android-federico", TuttiPresenti).decidi(adesso)
            val fine = System.nanoTime()
            assertTrue(d is Decisione.Mostra || d is Decisione.Niente)
            Log.i(TAG, "$adesso: config ${(lettura - inizio) / 1_000_000} ms, decisione ${(fine - lettura) / 1_000_000} ms")
            (fine - inizio) / 1_000_000
        }.sorted()
        Log.i(TAG, "totale per decisione: minimo ${tempi.first()} ms, mediana ${tempi[tempi.size / 2]} ms, massimo ${tempi.last()} ms")
        // Il lavoro periodico ha dieci minuti a disposizione: qui basta che non esploda
        assertTrue("Una decisione oltre i 30 secondi: ${tempi.last()} ms", tempi.last() < 30_000)
    }

    companion object {
        private const val TAG = "TempiDecisione"
    }
}
