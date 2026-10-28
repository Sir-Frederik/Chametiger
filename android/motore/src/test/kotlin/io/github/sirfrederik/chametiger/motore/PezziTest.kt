package io.github.sirfrederik.chametiger.motore

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

/** I pezzi che il riferimento copre solo di riflesso, o non copre affatto. */
class PezziTest {

    @Test
    fun moduloEDivisioneComeInPython() {
        assertEquals(350.0, pyMod(-10.0, 360.0), 0.0)
        assertEquals(-350.0, pyMod(10.0, -360.0), 0.0)
        assertEquals(10.0, pyMod(370.0, 360.0), 0.0)
        assertEquals(-1.0, pyFloorDiv(-0.5, 90.0), 0.0)
        assertEquals(3.0, pyFloorDiv(359.9, 90.0), 0.0)
    }

    @Test
    fun ordinePerCodePoint() {
        // U+1F600 (fuori dal piano base) viene dopo U+FFFD per code point, prima in UTF-16
        assertEquals(listOf("\uFFFD", "\uD83D\uDE00"), listOf("\uD83D\uDE00", "\uFFFD").ordinate())
    }

    @Test
    fun pasqua() {
        assertEquals(LocalDate.of(2026, 4, 5), DateMobili.pasqua(2026))
        assertEquals(LocalDate.of(2027, 3, 28), DateMobili.pasqua(2027))
        assertEquals(331, DateMobili.ordinale("pasqua - 5g", 2026))
        assertEquals(307, DateMobili.ordinale("03-7", 2026))
        assertNull(DateMobili.ordinale("02-30", 2026))
    }

    @Test
    fun tramontoConOraLegale() {
        // Dal README: a Napoli il tramonto salta di un'ora col passaggio all'ora legale
        val sole = Sole(DEFAULT_LAT, DEFAULT_LON, ZoneId.of("Europe/Rome"))
        assertEquals(18 * 60 + 23, sole.minutiSolari("sunset", 0, LocalDate.of(2026, 3, 28)))
        assertEquals(19 * 60 + 24, sole.minutiSolari("sunset", 0, LocalDate.of(2026, 3, 29)))
    }

    @Test
    fun ancoreEMinmax() {
        assertEquals("sunset" to 2, Sole.parseAncora("sunset +2 m"))
        assertEquals("dawn" to -20, Sole.parseAncora("dawn -20m"))
        assertEquals("noon" to 120, Sole.parseAncora("noon+2h"))
        assertEquals("sunset" to -40, Sole.parseAncora("sunset-40"))
        assertNull(Sole.parseAncora("18:00"))
        assertEquals("min" to listOf("sunset +2 m", "18:00"), Sole.parseMinmax("min(sunset +2 m, 18:00)"))
        assertNull(Sole.parseMinmax("min(18:00)"))
    }

    @Test
    fun mazzoSenzaRipetizioniAlCambioDiGiro() {
        val motore = Motore(Config.leggi("{}"), "x", ZoneId.of("Europe/Rome"))
        val pool = (1..7).map { "img$it.jpg" }
        for (giro in 0..200) {
            val prima = motore.mazzo(pool, "firma", giro)
            val dopo = motore.mazzo(pool, "firma", giro + 1)
            assertEquals(pool.toSet(), prima.toSet())
            assertNotEquals("giro $giro", prima.last(), dopo.first())
        }
    }

    @Test
    fun percorsiPerDispositivo() {
        val config = Config.leggi(
            """{"base_path": "G:/Temi", "path_map": {"android-federico": "/storage/emulated/0/Temi/"}}""",
        )
        assertEquals("/storage/emulated/0/Temi/cartella/foto.jpg", risolviPercorso(config, "android-federico", "cartella/foto.jpg"))
        assertEquals("G:/Temi/foto.jpg", risolviPercorso(config, "sconosciuto", "foto.jpg"))
        // Un assoluto sotto una base conosciuta si rimappa sulla base del dispositivo
        assertEquals("/storage/emulated/0/Temi/a/b.png", risolviPercorso(config, "android-federico", "g:\\temi\\a\\b.png"))
        assertEquals("D:/altro/b.png", risolviPercorso(config, "android-federico", "D:/altro/b.png"))
    }

    @Test
    fun coordinatePerDispositivo() {
        val config = Config.leggi(
            """{"latitude": 45.0, "longitude": 9.0, "position_map": {"android-federico": {"latitude": 40.82}}}""",
        )
        assertEquals(40.82 to 9.0, config.coordinate("android-federico"))
        assertEquals(45.0 to 9.0, config.coordinate("altro"))
        assertEquals(DEFAULT_LAT to DEFAULT_LON, Config.leggi("{}").coordinate("altro"))
    }

    @Test
    fun mazzoDellaFinestraEScelta() {
        // Su ogni finestra di un mese, la prima carta del suo mazzo non ancora
        // uscita oggi e' proprio l'immagine scelta, e sceltaIn sulla giornata
        // intera da' la stessa finestra di scelta
        val testo = requireNotNull(javaClass.getResource("/riferimento/con_meteo/config.json")).readText()
        val motore = Motore(Config.leggi(testo), "Federico", ZoneId.of("Europe/Rome"))
        for (d in 0 until 31L) {
            val giorno = LocalDate.of(2027, 3, 15).plusDays(d)
            val sequenza = motore.sequenzaGiornaliera(giorno)
            val usate = HashSet<String>()
            for (f in sequenza) {
                val mazzo = motore.mazzoDi(f)
                assertEquals(f.pool, mazzo.size)
                assertEquals("$giorno ${f.minuto}", f.immagine, mazzo.firstOrNull { it !in usate } ?: mazzo[0])
                usate += f.immagine
            }
            for (ora in 0 until 24) {
                val adesso = giorno.atTime(ora, 30)
                assertEquals("$adesso", motore.scelta(adesso), motore.sceltaIn(adesso, sequenza))
            }
        }
    }
}
