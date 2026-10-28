package io.github.sirfrederik.chametiger.strato

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.LocalDate

/** Config e immagini da Drive, con un Drive finto in memoria. */
class SincroTest {

    @get:Rule
    val tmp = TemporaryFolder()

    /** Una cartella Drive: file per id, figli per cartella. Conta le chiamate e puo' fallire. */
    private class DriveFinto : ApiDrive {
        val contenuti = HashMap<String, ByteArray>()
        val figli = HashMap<String, MutableList<VoceDrive>>()
        var errore: ErroreDrive? = null
        var chiamate = 0
        var scaricamenti = 0
        override var byteRicevuti = 0L

        fun file(cartella: String, nome: String, byte: ByteArray, md5: String? = Sincro.md5(byte)) {
            val id = "id-$cartella-$nome"
            contenuti[id] = byte
            val lista = figli.getOrPut(cartella) { mutableListOf() }
            lista.removeAll { it.nome == nome }
            lista += VoceDrive(id, nome, false, md5, byte.size.toLong(), null)
        }

        fun sottocartella(cartella: String, nome: String): String {
            val id = "dir-$nome"
            figli.getOrPut(cartella) { mutableListOf() } += VoceDrive(id, nome, true, null, null, null)
            figli.getOrPut(id) { mutableListOf() }
            return id
        }

        private fun conta() {
            chiamate++
            errore?.let { throw it }
        }

        override fun elenca(cartella: String, resourceKey: String?): List<VoceDrive> {
            conta()
            byteRicevuti += 1000
            return figli[cartella].orEmpty()
        }

        override fun cerca(cartella: String, resourceKey: String?, nome: String): VoceDrive? {
            conta()
            byteRicevuti += 300
            return figli[cartella].orEmpty().firstOrNull { it.nome == nome }
        }

        override fun scarica(voce: VoceDrive, destinazione: File): Long {
            conta()
            scaricamenti++
            val byte = contenuti.getValue(voce.id)
            destinazione.writeBytes(byte)
            byteRicevuti += byte.size
            return byte.size.toLong()
        }
    }

    private class DiarioFinto : Diario {
        val righe = mutableListOf<String>()
        override fun scrivi(messaggio: String) {
            righe += messaggio
        }
    }

    private val radice = "radice"
    private val files by lazy { tmp.newFolder("files") }
    private val interna by lazy { tmp.newFolder("interna") }
    private var adesso = 1_800_000_000.0

    private fun sincro(drive: DriveFinto, diario: Diario, tetto: Long = Long.MAX_VALUE) =
        Sincro(drive, CartellaDrive(radice, null), files, interna, diario, { adesso }, tetto)

    private val config = """{"image_library": {"a.jpg": ["x"], "sotto/b.jpg": ["x"]}, "random_rules": {"weekday": []}}"""

    @Test
    fun linkDellaCartella() {
        assertEquals(
            CartellaDrive("1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU", null),
            CartellaDrive.daLink("https://drive.google.com/drive/folders/1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU?usp=drive_link"),
        )
        assertEquals(
            CartellaDrive("1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU", "0-abc"),
            CartellaDrive.daLink("https://drive.google.com/drive/u/0/folders/1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU?resourcekey=0-abc"),
        )
        assertEquals(CartellaDrive("1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU", null), CartellaDrive.daLink(" 1gpvd52-tP15PHxvEWlB6mDqCMwfHV8VU "))
        assertNull(CartellaDrive.daLink("https://example.com/qualcosa"))
        assertNull(CartellaDrive.daLink(""))
    }

    @Test
    fun ilConfigSiScaricaSoloSeCambiaESoloSeValido() {
        val drive = DriveFinto().apply { file(radice, "config.json", config.toByteArray()) }
        val diario = DiarioFinto()

        sincro(drive, diario).aggiornaConfig()
        assertEquals(config, File(files, "config.json").readText())
        assertTrue(diario.righe.single(), diario.righe.single().startsWith("[DRIVE] Config aggiornato da Drive: nessuno -> "))

        // Stesso md5: una sola richiesta piccola, niente download
        sincro(drive, diario).aggiornaConfig()
        assertEquals(1, drive.scaricamenti)

        // Cambiato su Drive: si sostituisce, e il log dice le due impronte
        val nuovo = config.replace("\"x\"]}", "\"x\", \"y\"]}")
        drive.file(radice, "config.json", nuovo.toByteArray())
        sincro(drive, diario).aggiornaConfig()
        assertEquals(nuovo, File(files, "config.json").readText())
        assertEquals(
            "[DRIVE] Config aggiornato da Drive: ${ConfigSicuro.impronta(config.toByteArray())} -> ${ConfigSicuro.impronta(nuovo.toByteArray())}",
            diario.righe.last(),
        )

        // Un config rotto su Drive non prende il posto di quello buono
        for (rotto in listOf("{}", nuovo.take(30))) {
            drive.file(radice, "config.json", rotto.toByteArray())
            sincro(drive, diario).aggiornaConfig()
            assertEquals(nuovo, File(files, "config.json").readText())
            assertTrue(diario.righe.last(), diario.righe.last().startsWith("[WARN] config.json su Drive non usabile"))
        }
        // Ne' uno arrivato male: md5 diverso da quello dichiarato
        drive.file(radice, "config.json", config.toByteArray(), md5 = "0".repeat(32))
        sincro(drive, diario).aggiornaConfig()
        assertEquals(nuovo, File(files, "config.json").readText())
        assertFalse(File(files, "config.json.scaricando").exists())
    }

    @Test
    fun leImmaginiSiScaricanoUnaVoltaESiAggiornanoSeCambiano() {
        val drive = DriveFinto()
        val sotto = drive.sottocartella(radice, "sotto")
        drive.file(radice, "a.jpg", byteArrayOf(1, 2, 3))
        drive.file(sotto, "b.jpg", byteArrayOf(4, 5))
        val diario = DiarioFinto()

        assertTrue(sincro(drive, diario).assicura("sotto/b.jpg"))
        assertEquals(listOf<Byte>(4, 5), File(files, "sotto/b.jpg").readBytes().toList())
        assertEquals("[DRIVE] Scaricata sotto/b.jpg (0 KB)", diario.righe.last())

        // Gia' in cache e uguale: nessun download, e l'indice basta per sei ore
        val chiamate = drive.chiamate
        assertTrue(sincro(drive, diario).assicura("sotto/b.jpg"))
        assertEquals(chiamate, drive.chiamate)

        // Cambiata su Drive (md5 diverso): si riscarica dopo il rinnovo dell'indice
        drive.file(sotto, "b.jpg", byteArrayOf(9))
        adesso += 7 * 3600
        assertTrue(sincro(drive, diario).assicura("sotto/b.jpg"))
        assertEquals(listOf<Byte>(9), File(files, "sotto/b.jpg").readBytes().toList())

        // Copiata via USB uguale a Drive: si riconosce dall'md5, senza scaricarla
        File(files, "a.jpg").writeBytes(byteArrayOf(1, 2, 3))
        val scaricamenti = drive.scaricamenti
        assertTrue(sincro(drive, diario).assicura("a.jpg"))
        assertEquals(scaricamenti, drive.scaricamenti)
    }

    @Test
    fun unaChiaveCheSuDriveNonCeNonCostaUnElencoAOgniGiro() {
        val drive = DriveFinto().apply { file(radice, "a.jpg", byteArrayOf(1)) }
        val diario = DiarioFinto()
        assertTrue(sincro(drive, diario).assicura("a.jpg"))

        val prima = drive.chiamate
        assertFalse(sincro(drive, diario).assicura("orfana.jpg"))
        adesso += 15 * 60
        assertFalse(sincro(drive, diario).assicura("orfana.jpg"))
        assertEquals("indice fresco: nessun elenco", prima, drive.chiamate)

        // Dopo un'ora si riguarda, nel caso l'abbiano aggiunta
        adesso += 3600
        drive.file(radice, "orfana.jpg", byteArrayOf(2))
        assertTrue(sincro(drive, diario).assicura("orfana.jpg"))
    }

    @Test
    fun senzaReteSiUsaLaCacheESiScriveUnaVolta() {
        val drive = DriveFinto().apply {
            file(radice, "config.json", config.toByteArray())
            file(radice, "a.jpg", byteArrayOf(1))
        }
        val diario = DiarioFinto()
        sincro(drive, diario).run {
            aggiornaConfig()
            assicura("a.jpg")
        }

        drive.errore = ErroreDrive(TipoErrore.RETE, null, "Unable to resolve host")
        val s = sincro(drive, diario)
        val chiamate = drive.chiamate
        s.aggiornaConfig()
        assertTrue("la versione in cache resta buona", s.assicura("a.jpg"))
        assertFalse(s.assicura("sotto/b.jpg"))
        assertEquals("dopo il primo errore il giro non insiste", chiamate + 1, drive.chiamate)
        assertEquals("[DRIVE] Non raggiungibile (Unable to resolve host): uso le immagini in cache", diario.righe.last())

        val righe = diario.righe.size
        sincro(drive, diario).aggiornaConfig()
        assertEquals("una riga per serie", righe, diario.righe.size)

        drive.errore = null
        sincro(drive, diario).aggiornaConfig()
        assertEquals("[DRIVE] Di nuovo raggiungibile", diario.righe.last())
    }

    @Test
    fun unaChiaveRifiutataSiRiprovaDopoMezzOra() {
        val drive = DriveFinto().apply { file(radice, "config.json", config.toByteArray()) }
        drive.errore = ApiDriveHttp.classifica(
            403,
            """{"error": {"code": 403, "message": "Requests from this Android client application <empty> are blocked.",
                "status": "PERMISSION_DENIED", "details": [{"reason": "API_KEY_ANDROID_APP_BLOCKED"}]}}""",
        )
        val diario = DiarioFinto()
        sincro(drive, diario).aggiornaConfig()
        assertTrue(diario.righe.last(), diario.righe.last().startsWith("[DRIVE] La chiave API e' rifiutata (HTTP 403: API_KEY_ANDROID_APP_BLOCKED"))

        val chiamate = drive.chiamate
        adesso += 29 * 60
        sincro(drive, diario).aggiornaConfig()
        assertEquals("entro mezz'ora nessuna richiesta", chiamate, drive.chiamate)
        adesso += 2 * 60
        sincro(drive, diario).aggiornaConfig()
        assertEquals(chiamate + 1, drive.chiamate)
    }

    @Test
    fun gliErroriDiGoogleSiClassificano() {
        fun tipo(codice: Int, corpo: String) = ApiDriveHttp.classifica(codice, corpo).tipo
        assertEquals(
            TipoErrore.CHIAVE,
            tipo(400, """{"error": {"code": 400, "message": "API key not valid.", "errors": [{"reason": "badRequest"}], "details": [{"reason": "API_KEY_INVALID"}]}}"""),
        )
        assertEquals(TipoErrore.CHIAVE, tipo(403, """{"error": {"code": 403, "errors": [{"reason": "accessNotConfigured"}], "message": "Drive API has not been used"}}"""))
        assertEquals(TipoErrore.CHIAVE, tipo(403, """{"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [{"reason": "SERVICE_DISABLED"}]}}"""))
        assertEquals(TipoErrore.SERVER, tipo(403, """{"error": {"code": 403, "errors": [{"reason": "userRateLimitExceeded"}]}}"""))
        assertEquals(TipoErrore.SERVER, tipo(503, "Service Unavailable"))
        assertEquals(TipoErrore.SERVER, tipo(429, ""))
        assertEquals(TipoErrore.ACCESSO, tipo(404, """{"error": {"code": 404, "errors": [{"reason": "notFound"}], "message": "File not found: x."}}"""))
        assertEquals(TipoErrore.ACCESSO, tipo(403, """{"error": {"code": 403, "errors": [{"reason": "forbidden"}], "message": "forbidden"}}"""))
    }

    @Test
    fun ilTettoEliminaLeMenoUsateMaiQuelleDiOggi() {
        val libreria = (1..6).map { "img$it.jpg" }
        for ((i, k) in libreria.withIndex()) {
            File(files, k).writeBytes(ByteArray(1000))
            File(files, k).setLastModified(1_000_000L * (i + 1))
        }
        File(files, "config.json").writeBytes(ByteArray(5000))
        val diario = DiarioFinto()
        val s = sincro(DriveFinto(), diario, tetto = 3500)
        // img1 e' la piu' vecchia ma e' di oggi; img5 e' stata appena usata
        s.usata("img5.jpg")
        s.pulisci(libreria.toSet(), protette = setOf("img1.jpg"))

        val rimaste = libreria.filter { File(files, it).isFile }
        assertEquals(listOf("img1.jpg", "img5.jpg", "img6.jpg"), rimaste)
        assertTrue("config non si tocca", File(files, "config.json").isFile)
        assertTrue(diario.righe.single(), diario.righe.single().startsWith("[DRIVE] Cache oltre il tetto"))
    }

    // ── Il giro completo ─────────────────────────────────────────────────────

    private class SfondoFinto : Sfondo {
        var attuale: String? = null
        override fun giaMostrata(immagine: String) = attuale == immagine
        override fun applica(file: File, immagine: String) {
            attuale = immagine
        }
    }

    private val immagini = (0 until 30).map { "img%02d.jpg".format(it) }
    private val configGiro = """
        {
          "image_library": {${immagini.joinToString(",") { "\"$it\": [\"x\"]" }}},
          "random_rules": {
            "weekday": [{"from": "00:00", "to": "00:00", "include": ["x"], "rotate_minutes": 60}],
            "weekend": [{"from": "00:00", "to": "00:00", "include": ["x"], "rotate_minutes": 60}]
          },
          "meteo": {"attivo": false}
        }
    """.trimIndent()

    @Test
    fun ilGiroScaricaLaCanonicaEAnticipaLaProssima() {
        val drive = DriveFinto().apply {
            file(radice, "config.json", configGiro.toByteArray())
            immagini.forEachIndexed { i, k -> file(radice, k, byteArrayOf(i.toByte())) }
        }
        val diario = DiarioFinto()
        val ora = LocalDate.of(2027, 3, 10).atTime(10, 30)
        val ciclo = Ciclo(
            files, interna, "android-prova", "1.0", SfondoFinto(), diario,
            orologio = { ora },
            drive = { d -> sincro(drive, d) },
        )

        val v = ciclo.giro() as Valutazione.Pronta
        val d = v.decisione as Decisione.Mostra
        assertEquals("con Drive raggiungibile esce la canonica, non un ripiego", Motivo.CANONICA, d.motivo)
        val prossima = v.decisore.prossima(ora)!!.immagine
        assertTrue(File(files, d.immagine).isFile)
        assertTrue(File(files, prossima).isFile)
        assertTrue(diario.righe.any { it == "[DRIVE] Anticipata $prossima (0 KB)" })
        assertTrue(diario.righe.last(), diario.righe.last().startsWith("[OK] Sfondo impostato") && " | Drive " in diario.righe.last())

        // Senza rete e senza la canonica in cache: ripiego fra i file che ci sono
        val ciclo2 = Ciclo(
            files, interna, "android-prova", "1.0", SfondoFinto(), diario,
            orologio = { ora.plusHours(3) },
            drive = { d2 -> sincro(drive, d2) },
        )
        drive.errore = ErroreDrive(TipoErrore.RETE, null, "timeout")
        val d2 = (ciclo2.giro() as Valutazione.Pronta).decisione as Decisione.Mostra
        assertEquals(Motivo.RIPIEGO, d2.motivo)
        assertTrue(d2.immagine in setOf(d.immagine, prossima))
    }
}
