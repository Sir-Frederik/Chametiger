package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.StatoMeteo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime

/**
 * Il meteo del telefono contro meteo.py. Le risposte di Met Norway e cio' che
 * meteo.py ne ricava stanno in resources/meteo, generati da
 * motore/riferimento/genera_riferimento_meteo.py: stessa risposta, stesse
 * dieci ore, stesso riassunto nel log.
 */
class MeteoTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private fun risorsa(nome: String): String =
        requireNotNull(javaClass.getResource("/meteo/$nome")) { "Manca $nome" }.readText(Charsets.UTF_8)

    private val righe = risorsa("atteso.tsv").lines().filter { it.isNotBlank() && !it.startsWith("#") }.map { it.split("\t") }

    @Test
    fun ogniSimboloComeMeteoPy() {
        val simboli = righe.filter { it[0] == "S" }
        assertTrue(simboli.size > 100)
        val diversi = simboli.filter { (_, simbolo, stato) -> statoDaSimbolo(simbolo).tag != stato }
        assertEquals("Simboli classificati diversamente: $diversi", emptyList<List<String>>(), diversi)
    }

    @Test
    fun stesseDieciOreDaStessaRisposta() {
        val casi = righe.filter { it[0] == "P" || it[0] == "E" }
        assertTrue(casi.size > 20)
        for (c in casi) {
            val adesso = LocalDateTime.parse(c[2])
            if (c[0] == "E") {
                try {
                    previsioni(risorsa(c[1]), adesso)
                    fail("${c[1]} ${c[2]}: meteo.py solleva, il telefono no")
                } catch (e: Exception) {
                    // come meteo.py
                }
                continue
            }
            val ore = previsioni(risorsa(c[1]), adesso)
            val attese = c[3].split(",").filter { it.isNotEmpty() }
            assertEquals("${c[1]} ${c[2]}", attese, ore.map { (k, v) -> "$k=${v.tag}" })
            assertEquals("${c[1]} ${c[2]} riassunto", c[4], riassunto(ore, adesso))
        }
    }

    @Test
    fun coordinateArrotondateComePython() {
        // round(x, 2) di Python, compresi i casi in cui il double sta appena sotto o sopra la meta'
        val attesi = mapOf(40.8199 to 40.82, 14.3414 to 14.34, 2.675 to 2.67, 0.125 to 0.12, 0.375 to 0.38, -14.345 to -14.35)
        for ((x, atteso) in attesi) assertEquals("round($x, 2)", atteso, arrotonda2(x), 0.0)
    }

    // ── Il download e il ripiego, come aggiorna_se_serve ─────────────────────

    private val config = Config.leggi(
        """{"image_library": {"a.jpg": ["x"]}, "random_rules": {"weekday": []},
            "latitude": 40.8199, "longitude": 14.3414, "meteo": {"attivo": true, "aggiorna_ore": 5}}""",
    )

    private class ReteFinta(var risposta: String?) : Rete {
        val chiamate = mutableListOf<Pair<String, String>>()
        override fun scarica(url: String, userAgent: String): String {
            chiamate += url to userAgent
            return risposta ?: throw IllegalStateException("HTTP 503")
        }
    }

    private class DiarioFinto : Diario {
        val righe = mutableListOf<String>()
        override fun scrivi(messaggio: String) {
            righe += messaggio
        }
    }

    private fun meteo(rete: Rete, diario: Diario) =
        Meteo(File(tmp.root, "meteo.json"), File(tmp.root, "interna/meteo_errore.txt"), "android-federico", "1.0", diario, rete)

    @Test
    fun scaricaConCadenzaEUserAgent() {
        val rete = ReteFinta(risorsa("reale.json"))
        val diario = DiarioFinto()
        val adesso = LocalDateTime.of(2026, 10, 28, 11, 10)

        assertTrue(meteo(rete, diario).aggiornaSeServe(config, adesso))
        val (url, ua) = rete.chiamate.single()
        assertEquals("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=40.82&lon=14.34", url)
        assertTrue(ua, ua.startsWith("Chametiger-Android/1.0 ") && "github.com" in ua)
        assertEquals("[METEO] Aggiornato (Met Norway): niente pioggia nelle prossime 10 ore.", diario.righe.single())

        // Ogni processo nuovo, come un risveglio: entro aggiorna_ore non riscarica
        assertFalse(meteo(rete, diario).aggiornaSeServe(config, adesso.plusHours(4)))
        assertTrue(meteo(rete, diario).aggiornaSeServe(config, adesso.plusHours(5)))
        assertEquals(2, rete.chiamate.size)

        // Le ore scaricate alle 16:10 arrivano al motore giorno per giorno, come
        // del_giorno legge meteo.json: le 16-23 di oggi e le 00-01 di domani,
        // e restano le 11-15 del download di prima
        val fonte = meteo(rete, diario).fonte(config, adesso.plusHours(5))
        assertEquals((11..23).toSet(), fonte.ore(LocalDate.of(2026, 10, 28)).keys)
        assertEquals(setOf(0, 1), fonte.ore(LocalDate.of(2026, 10, 29)).keys)
        assertTrue(fonte.ore(LocalDate.of(2026, 10, 28)).values.all { it == StatoMeteo.ASCIUTTO })
    }

    @Test
    fun laPosizioneDelTelefonoVinceSulConfig() {
        val rete = ReteFinta(risorsa("reale.json"))
        val adesso = LocalDateTime.of(2026, 10, 28, 11, 10)
        val milano = 45.4642 to 9.19
        fun m(posizione: Pair<Double, Double>?) = Meteo(
            File(tmp.root, "meteo.json"), File(tmp.root, "interna/meteo_errore.txt"),
            "android-federico", "1.0", DiarioFinto(), rete, posizione,
        )

        assertTrue(m(milano).aggiornaSeServe(config, adesso))
        assertEquals("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=45.46&lon=9.19", rete.chiamate.single().first)
        assertEquals("45.46, 9.19 (posizione del telefono)", m(milano).origine(config))
        // Scaricati per Milano: valgono finche' il telefono resta li', non sulle coordinate del config
        assertFalse(m(milano).fonte(config, adesso).ore(adesso.toLocalDate()).isEmpty())
        assertTrue(m(null).fonte(config, adesso).ore(adesso.toLocalDate()).isEmpty())
        assertEquals("40.82, 14.34 (coordinate del config)", m(null).origine(config))
    }

    @Test
    fun senzaReteSiRiprovaDopoMezzOraESiSceglieComeColSereno() {
        val rete = ReteFinta(null)
        val diario = DiarioFinto()
        val adesso = LocalDateTime.of(2026, 10, 28, 11, 10)

        assertFalse(meteo(rete, diario).aggiornaSeServe(config, adesso))
        assertEquals("[METEO] Meteo non disponibile (Met Norway: HTTP 503): scelgo come col sereno.", diario.righe.single())
        assertTrue(meteo(rete, diario).fonte(config, adesso).ore(adesso.toLocalDate()).isEmpty())

        // Entro mezz'ora non riprova; dopo si', ma il log lo dice una volta per serie
        assertFalse(meteo(rete, diario).aggiornaSeServe(config, adesso.plusMinutes(29)))
        assertEquals(1, rete.chiamate.size)
        assertFalse(meteo(rete, diario).aggiornaSeServe(config, adesso.plusMinutes(31)))
        assertEquals(2, rete.chiamate.size)
        assertEquals(1, diario.righe.size)

        // Torna la rete: scarica, e la serie di errori finisce
        rete.risposta = risorsa("reale.json")
        assertTrue(meteo(rete, diario).aggiornaSeServe(config, adesso.plusMinutes(62)))
        rete.risposta = null
        assertFalse(meteo(rete, diario).aggiornaSeServe(config, adesso.plusHours(7)))
        assertEquals("[METEO] Meteo non disponibile (Met Norway: HTTP 503): scelgo come col sereno.", diario.righe.last())
    }

    @Test
    fun datiVecchiOdAltroveNonValgono() {
        val rete = ReteFinta(risorsa("ora_legale.json"))
        val adesso = LocalDateTime.of(2027, 3, 27, 19, 0)
        val diario = DiarioFinto()
        assertTrue("scaricato: ${diario.righe}", meteo(rete, diario).aggiornaSeServe(config, adesso))
        val m = meteo(rete, DiarioFinto())

        assertEquals(StatoMeteo.PIOGGIA, m.fonte(config, adesso).ore(LocalDate.of(2027, 3, 27))[19])
        // Oltre le 12 ore, o con le coordinate cambiate, ogni ora e' asciutta
        // L'eta' e' tempo vero, come time.time(): stanotte l'ora legale salta
        // un'ora, quindi alle 08:00 di domani sono passate 12 ore e valgono ancora
        assertFalse("12 ore vere", m.fonte(config, adesso.plusHours(13)).ore(LocalDate.of(2027, 3, 27)).isEmpty())
        assertTrue("13 ore vere", m.fonte(config, adesso.plusHours(14)).ore(LocalDate.of(2027, 3, 27)).isEmpty())
        val altrove = Config.leggi(
            """{"image_library": {"a.jpg": []}, "random_rules": {"weekday": []}, "latitude": 45.46, "longitude": 9.19}""",
        )
        assertTrue("altrove", m.fonte(altrove, adesso).ore(LocalDate.of(2027, 3, 27)).isEmpty())
    }

    @Test
    fun leOrePassateDiOggiRestanoQuelleDiPrima() {
        // Il caso del 6/11: alle 10:06 pioggia dalle 11, alle 12:11 un download
        // che parte dalle 12. Se la pioggia delle 11 sparisse, la sequenza del
        // giorno cambierebbe e con lei la finestra di adesso.
        val adesso = LocalDateTime.of(2026, 10, 28, 11, 10)
        fun prima(scaricato: LocalDateTime) = File(tmp.root, "meteo.json").writeText(
            """{"scaricato": ${scaricato.atZone(ZONA).toEpochSecond()}, "lat": 40.82, "lon": 14.34, "ore": {
                "2026-10-27T23": "pioggia", "2026-10-28T09": "pioggia", "2026-10-28T10": "temporale",
                "2026-10-28T11": "pioggia"}}""",
        )

        prima(adesso.minusHours(2))
        assertTrue(meteo(ReteFinta(risorsa("reale.json")), DiarioFinto()).aggiornaSeServe(config, adesso, forza = true))
        val oggi = meteo(ReteFinta(null), DiarioFinto()).fonte(config, adesso).ore(LocalDate.of(2026, 10, 28))
        assertEquals(StatoMeteo.PIOGGIA, oggi[9])
        assertEquals(StatoMeteo.TEMPORALE, oggi[10])
        // L'ora attuale e le seguenti vengono dal download nuovo, ieri non si tiene
        assertEquals(StatoMeteo.ASCIUTTO, oggi[11])
        assertEquals((9..20).toSet(), oggi.keys)
        assertFalse("ieri", "2026-10-27T23" in meteo(ReteFinta(null), DiarioFinto()).leggi()!!.ore)

        // Dati di prima ormai scaduti: il motore vedeva gia' le ore asciutte, restano asciutte
        prima(adesso.minusHours(13))
        assertTrue(meteo(ReteFinta(risorsa("reale.json")), DiarioFinto()).aggiornaSeServe(config, adesso, forza = true))
        assertEquals((11..20).toSet(), meteo(ReteFinta(null), DiarioFinto()).fonte(config, adesso).ore(LocalDate.of(2026, 10, 28)).keys)
    }

    @Test
    fun meteoDisattivatoNonScarica() {
        val rete = ReteFinta(risorsa("reale.json"))
        val spento = Config.leggi("""{"image_library": {"a.jpg": []}, "random_rules": {"weekday": []}, "meteo": {"attivo": false}}""")
        assertFalse(meteo(rete, DiarioFinto()).aggiornaSeServe(spento, LocalDateTime.of(2026, 10, 28, 11, 0)))
        assertTrue(rete.chiamate.isEmpty())
    }
}
