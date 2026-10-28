package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import kotlin.random.Random

/**
 * Lo strato sopra il motore. Il config e' sintetico: 30 immagini e una fascia
 * su tutto il giorno a finestre di un'ora, quindi 24 finestre e 6 immagini che
 * oggi non escono, per vedere ogni livello delle esclusioni.
 */
class StratoTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val immagini = (0 until 30).map { "img%02d.jpg".format(it) }
    private val testo = """
        {
          "image_library": {${immagini.joinToString(",") { "\"$it\": [\"x\"]" }}},
          "random_rules": {
            "weekday": [{"from": "00:00", "to": "00:00", "include": ["x"], "rotate_minutes": 60}],
            "weekend": [{"from": "00:00", "to": "00:00", "include": ["x"], "rotate_minutes": 60}]
          },
          "meteo": {"attivo": false}
        }
    """.trimIndent()
    private val config = Config.leggi(testo)
    private val giorno = LocalDate.of(2027, 3, 10)
    private val dieci = giorno.atTime(10, 30)

    private class ArchivioFinto(val presenti: Set<String>) : Archivio {
        override fun file(chiave: String) = File(chiave)
        override fun esiste(chiave: String) = chiave in presenti
    }

    private fun decisore(presenti: Set<String> = immagini.toSet()) = Decisore(config, "android-prova", ArchivioFinto(presenti))
    private fun canonica(t: LocalDateTime) = decisore().motore.scelta(t)!!.immagine
    private fun giornata(g: LocalDate) = decisore().motore.sequenzaGiornaliera(g).map { it.immagine }

    @Test
    fun conTuttiIFileEsceLaCanonica() {
        for (ora in 0 until 24) {
            val t = giorno.atTime(ora, 15)
            val d = decisore().decidi(t) as Decisione.Mostra
            assertEquals(Motivo.CANONICA, d.motivo)
            assertEquals(canonica(t), d.immagine)
        }
    }

    @Test
    fun ilRipiegoNonSiPropagaAlleAltreFinestre() {
        val mancante = canonica(dieci)
        val presenti = immagini.toSet() - mancante

        val d = decisore(presenti).decidi(dieci) as Decisione.Mostra
        assertEquals(Motivo.RIPIEGO, d.motivo)
        assertEquals(mancante, d.mancante)
        assertTrue(d.immagine in presenti)
        assertFalse("C'erano immagini fuori dalla giornata", d.immagine in giornata(giorno))
        // Deterministico: un altro telefono senza lo stesso file mostra la stessa sostituta
        assertEquals(d.immagine, (decisore(presenti).decidi(dieci) as Decisione.Mostra).immagine)

        // Tutte le altre finestre di oggi e di domani restano quelle canoniche
        for (g in listOf(giorno, giorno.plusDays(1))) {
            for (ora in 0 until 24) {
                val t = g.atTime(ora, 30)
                if (canonica(t) == mancante) continue
                val altra = decisore(presenti).decidi(t) as Decisione.Mostra
                assertEquals("$t", Motivo.CANONICA, altra.motivo)
                assertEquals("$t", canonica(t), altra.immagine)
            }
        }
    }

    @Test
    fun ilRipiegoAllargaLeEsclusioniSoloSeServe() {
        val oggi = decisore().motore.sequenzaGiornaliera(giorno)
        val mancante = canonica(dieci)
        val passate = oggi.filter { it.minuto < 10 * 60 }.map { it.immagine }.toSet()
        val future = oggi.filter { it.minuto > 10 * 60 }.map { it.immagine }.toSet()

        // Solo immagini di finestre future: si rinuncia a escluderle
        val conFuture = decisore(future).decidi(dieci) as Decisione.Mostra
        assertTrue(conFuture.immagine in future)
        // Solo immagini gia' uscite: si rinuncia a tutte le esclusioni
        val conPassate = decisore(passate).decidi(dieci) as Decisione.Mostra
        assertTrue(conPassate.immagine in passate)
        assertNotEquals(mancante, conPassate.immagine)
    }

    @Test
    fun senzaNessunFileNonSiMostraNiente() {
        val d = decisore(emptySet()).decidi(dieci)
        assertTrue(d is Decisione.Niente)
    }

    @Test
    fun laForzataValeSoloNellaSuaFinestra() {
        // Casuale, ma mai l'immagine di adesso ne' una della giornata finche' ce ne sono altre
        for (seme in 0 until 50) {
            val g = decisore().forza(giorno.atTime(10, 5), null, Random(seme)).getOrThrow()
            assertNotEquals(canonica(dieci), g.immagine)
            assertFalse("seme $seme", g.immagine in giornata(giorno))
        }
        val f = decisore().forza(giorno.atTime(10, 5), null, Random(7)).getOrThrow()

        val dentro = decisore().decidi(giorno.atTime(10, 59), f) as Decisione.Mostra
        assertEquals(Motivo.FORZATA, dentro.motivo)
        assertEquals(f.immagine, dentro.immagine)
        assertEquals(canonica(dieci), dentro.canonica)

        val dopo = decisore().decidi(giorno.atTime(11, 0), f) as Decisione.Mostra
        assertEquals(Motivo.CANONICA, dopo.motivo)
        // Il giorno dopo alla stessa ora non vale piu'
        assertEquals(Motivo.CANONICA, (decisore().decidi(dieci.plusDays(1), f) as Decisione.Mostra).motivo)
        // Se il suo file sparisce torna la canonica
        val senzaFile = decisore(immagini.toSet() - f.immagine).decidi(dieci, f) as Decisione.Mostra
        assertEquals(Motivo.CANONICA, senzaFile.motivo)
    }

    @Test
    fun configIllegibileUsaLUltimoBuono() {
        val principale = tmp.newFile("config.json")
        val copia = File(tmp.root, "interna/config.ultimo.json")
        val sicuro = ConfigSicuro(principale, copia)

        principale.writeText(testo)
        val ok = sicuro.leggi() as ConfigSicuro.Lettura.Ok
        assertNull(ok.avviso)
        assertEquals(testo, copia.readText())

        for (rotto in listOf(testo.take(testo.length / 2), "", "{}", """{"image_library": {"a.jpg": []}}""", "[]")) {
            principale.writeText(rotto)
            val l = sicuro.leggi() as ConfigSicuro.Lettura.Ok
            assertTrue("'$rotto'", l.avviso != null)
            assertEquals(config, l.config)
        }
        principale.delete()
        assertTrue((sicuro.leggi() as ConfigSicuro.Lettura.Ok).avviso != null)

        // Mai un config vuoto: senza un buono precedente non c'e' config
        val nuovo = ConfigSicuro(File(tmp.root, "assente.json"), File(tmp.root, "nessuna_copia.json"))
        assertTrue(nuovo.leggi() is ConfigSicuro.Lettura.Nessuna)
    }

    private class SfondoFinto : Sfondo {
        var attuale: String? = null
        val applicate = mutableListOf<String>()
        override fun giaMostrata(immagine: String) = attuale == immagine
        override fun applica(file: File, immagine: String) {
            attuale = immagine
            applicate += immagine
        }
    }

    private class DiarioFinto : Diario {
        val righe = mutableListOf<String>()
        override fun scrivi(messaggio: String) {
            righe += messaggio
        }
    }

    @Test
    fun ilCicloEIdempotenteEScriveIlLog() {
        val cartella = tmp.newFolder("files")
        File(cartella, "config.json").writeText(testo)
        val mancante = canonica(dieci)
        (immagini - mancante).forEach { File(cartella, it).writeText("") }

        val sfondo = SfondoFinto()
        val diario = DiarioFinto()
        var adesso = giorno.atTime(9, 10)
        val ciclo = Ciclo(cartella, tmp.newFolder("interna"), "android-prova", "1.0", sfondo, diario, orologio = { adesso })

        ciclo.giro()
        assertTrue(diario.righe[0], diario.righe[0].startsWith("[INFO] android-prova 1.0, Europe/Rome"))
        assertTrue(diario.righe[1], diario.righe[1].startsWith("[OK] Sfondo impostato (weekday [nessuna stagione] 00:00-00:00 [x]): ${canonica(adesso)} | finestra "))

        diario.righe.clear()
        adesso = giorno.atTime(9, 25)
        ciclo.giro()
        assertEquals(listOf("[CICLO] invariato: ${canonica(adesso)}"), diario.righe)

        diario.righe.clear()
        adesso = dieci
        ciclo.giro()
        assertTrue(diario.righe[0], diario.righe[0].startsWith("[RIPIEGO] Manca $mancante "))
        assertTrue(diario.righe[1], diario.righe[1].startsWith("[OK] Sfondo impostato (ripiego, weekday"))

        diario.righe.clear()
        ciclo.forza()
        assertTrue(diario.righe[0], diario.righe[0].startsWith("[FORZATA] "))
        assertTrue(diario.righe[1], diario.righe[1].startsWith("[OK] Sfondo impostato (estrazione forzata, weekday"))
        val forzata = sfondo.attuale

        diario.righe.clear()
        adesso = giorno.atTime(10, 45)
        ciclo.giro()
        assertEquals(listOf("[CICLO] invariato: $forzata"), diario.righe)

        // Finita la finestra la forzata si dimentica e torna la sequenza
        diario.righe.clear()
        adesso = giorno.atTime(11, 5)
        ciclo.giro()
        assertTrue(diario.righe.last(), diario.righe.last().contains(": ${canonica(adesso)} | finestra "))
        assertFalse(File(tmp.root, "interna/forzata.txt").exists())

        // Il giorno dopo una nuova riga [INFO]
        diario.righe.clear()
        adesso = giorno.plusDays(1).atTime(8, 0)
        ciclo.giro()
        assertTrue(diario.righe[0].startsWith("[INFO] "))
    }

    @Test
    fun ilLogHaIlFormatoDelTrayENonCresceSenzaFine() {
        val file = File(tmp.root, "chametiger.log")
        val diario = DiarioFile(file) { LocalDateTime.of(2026, 10, 27, 14, 46, 3) }
        diario.scrivi("[CICLO] invariato: a.jpg")
        assertEquals("[2026-10-27 14:46:03] [CICLO] invariato: a.jpg\n", file.readText())

        repeat(5000) { diario.scrivi("[CICLO] invariato: " + "x".repeat(40)) }
        assertTrue(file.length() <= DiarioFile.MAX_BYTES + 200)
    }
}
