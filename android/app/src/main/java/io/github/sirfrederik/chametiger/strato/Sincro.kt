package io.github.sirfrederik.chametiger.strato

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.io.File
import java.net.URI
import java.security.MessageDigest

// Config e immagini da Drive, con una cache locale persistente.
//
// Drive comanda: il config.json scaricato sostituisce quello del telefono,
// purche' sia un config valido. Le immagini si scaricano quando servono, nella
// stessa cartella files/ delle copie via USB, e restano li': col tempo il
// telefono accumula quelle che usa davvero, e senza rete sceglie fra quelle.
// Il motore non sa niente di tutto questo: vede solo quali file ci sono.

/** La cartella condivisa, dal link incollato nelle impostazioni. */
data class CartellaDrive(val id: String, val resourceKey: String?) {
    companion object {
        private val ID = Regex("""^[A-Za-z0-9_-]{10,}$""")

        /** 'https://drive.google.com/drive/folders/<id>?resourcekey=<rk>', o l'id da solo. */
        fun daLink(link: String): CartellaDrive? {
            val t = link.trim()
            if (ID.matches(t)) return CartellaDrive(t, null)
            val uri = runCatching { URI(t) }.getOrNull() ?: return null
            val id = uri.path?.substringAfter("/folders/", "")?.substringBefore("/")?.takeIf { ID.matches(it) }
                ?: return null
            val rk = uri.rawQuery?.split("&")?.firstOrNull { it.startsWith("resourcekey=") }?.substringAfter("=")
            return CartellaDrive(id, rk?.takeIf { it.isNotEmpty() })
        }
    }
}

/** Un file della cartella, per chiave relativa ('Daffy and Porky/x.jpg'). */
data class VoceIndice(val id: String, val md5: String?, val dimensione: Long?, val resourceKey: String?) {
    fun comeVoce(nome: String) = VoceDrive(id, nome, false, md5, dimensione, resourceKey)
}

class Sincro(
    private val api: ApiDrive,
    private val cartellaDrive: CartellaDrive,
    /** La cartella files/: config.json e immagini, le stesse delle copie via USB. */
    private val files: File,
    /** La memoria interna: indice, dati della cache, ultimo errore. */
    interna: File,
    private val diario: Diario,
    /** Secondi dall'epoca, come time.time(). */
    private val orologio: () -> Double,
    private val tettoByte: Long,
    /** Se un file scaricato e' un'immagine che si decodifica. Sul telefono lo dice BitmapFactory. */
    private val verifica: (File) -> Boolean = { true },
) {
    private val fileIndice = File(interna, "drive_indice.json")
    private val fileCache = File(interna, "drive_cache.json")
    private val fileErrore = File(interna, "drive_errore.txt")

    private var indice: Map<String, VoceIndice>? = null
    private var indiceRinnovato = false
    private val cache: MutableMap<String, InCache> by lazy { leggiCache() }

    /** Dopo il primo errore di rete del giro non si riprova: ogni tentativo puo' costare un timeout. */
    private var offline = false

    /** Quanto si e' ricevuto da Drive in questo giro. */
    val byteGiro: Long get() = api.byteRicevuti

    private data class InCache(val md5: String?, val dimensione: Long, var uso: Double)

    // ── Config ───────────────────────────────────────────────────────────────

    /**
     * Confronta l'md5 del config.json su Drive con quello del telefono e lo
     * scarica solo se e' cambiato. Lo sostituisce solo se e' un config valido:
     * un file rotto su Drive non prende mai il posto di quello buono.
     */
    fun aggiornaConfig() {
        if (bloccato()) return
        val cercato = chiama { api.cerca(cartellaDrive.id, cartellaDrive.resourceKey, NOME_CONFIG) }
        if (cercato !is Esito.Ok) return
        val voce = cercato.valore ?: run {
            diario.scrivi("[WARN] Nella cartella Drive non c'e' $NOME_CONFIG: tengo quello del telefono")
            return
        }
        val locale = File(files, NOME_CONFIG)
        val prima = if (locale.isFile) locale.readBytes() else null
        if (prima != null && voce.md5 != null && md5(prima) == voce.md5) return

        val tmp = File(files, "$NOME_CONFIG.scaricando")
        if (chiama { api.scarica(voce, tmp) } !is Esito.Ok) {
            tmp.delete()
            return
        }
        try {
            val byte = tmp.readBytes()
            check(voce.md5 == null || md5(byte) == voce.md5) { "md5 diverso da quello di Drive" }
            ConfigSicuro.valida(byte)
            sostituisci(tmp, locale)
            val da = prima?.let { ConfigSicuro.impronta(it) } ?: "nessuno"
            diario.scrivi("[DRIVE] Config aggiornato da Drive: $da -> ${ConfigSicuro.impronta(byte)}")
            // Un config nuovo puo' nominare file nuovi: l'indice si rinnova
            indice = null
            fileIndice.delete()
        } catch (e: Exception) {
            diario.scrivi("[WARN] $NOME_CONFIG su Drive non usabile (${e.message}): tengo quello del telefono")
        } finally {
            tmp.delete()
        }
    }

    // ── Immagini ─────────────────────────────────────────────────────────────

    /**
     * Fa in modo che l'immagine sia sul telefono e uguale a quella su Drive.
     * True se adesso c'e', anche solo nella versione vecchia quando Drive non
     * risponde. Un file copiato via USB che Drive non conosce resta buono.
     */
    fun assicura(chiave: String, motivo: String = "Scaricata"): Boolean {
        val f = File(files, chiave)
        if (bloccato()) return f.isFile
        val voce = voceDi(chiave) ?: return f.isFile
        if (f.isFile && aggiornato(chiave, f, voce)) return true

        val tmp = File(f.parentFile, f.name + ".scaricando")
        f.parentFile?.mkdirs()
        val scaricato = chiama { api.scarica(voce.comeVoce(f.name), tmp) }
        if (scaricato !is Esito.Ok) {
            tmp.delete()
            return f.isFile
        }
        val byte = scaricato.valore
        try {
            val md5 = md5(tmp)
            check(voce.md5 == null || md5 == voce.md5) { "md5 diverso da quello di Drive" }
            check(verifica(tmp)) { "non e' un'immagine leggibile" }
            sostituisci(tmp, f)
            cache[chiave] = InCache(md5, f.length(), orologio())
            salvaCache()
            diario.scrivi("[DRIVE] $motivo $chiave (${kb(byte)})")
            return true
        } catch (e: Exception) {
            diario.scrivi("[WARN] Download di $chiave scartato: ${e.message}")
            return f.isFile
        } finally {
            tmp.delete()
        }
    }

    /** L'immagine e' appena stata mostrata: per il tetto, e' fra le piu' recenti. */
    fun usata(chiave: String) {
        val f = File(files, chiave)
        if (!f.isFile) return
        cache[chiave] = (cache[chiave] ?: InCache(null, f.length(), 0.0)).copy(uso = orologio())
        salvaCache()
    }

    /**
     * Sopra il tetto elimina le immagini usate meno di recente, mai quelle di
     * `protette` (la sequenza di oggi, quella di adesso e la prossima). Conta
     * e tocca solo i file della libreria, non config, log e meteo.
     */
    fun pulisci(libreria: Set<String>, protette: Set<String>) {
        val presenti = libreria.map { it to File(files, it) }.filter { it.second.isFile }
        var totale = presenti.sumOf { it.second.length() }
        if (totale <= tettoByte) return
        val prima = totale
        var eliminate = 0
        val candidate = presenti.filter { it.first !in protette }
            .sortedBy { (k, f) -> cache[k]?.uso?.takeIf { it > 0 } ?: (f.lastModified() / 1000.0) }
        for ((chiave, f) in candidate) {
            if (totale <= tettoByte) break
            val dimensione = f.length()
            if (f.delete()) {
                totale -= dimensione
                cache.remove(chiave)
                eliminate++
            }
        }
        salvaCache()
        diario.scrivi(
            "[DRIVE] Cache oltre il tetto (${mb(prima)} su ${mb(tettoByte)}): eliminate $eliminate immagini, ora ${mb(totale)}",
        )
    }

    // ── Indice ───────────────────────────────────────────────────────────────

    private fun voceDi(chiave: String): VoceIndice? {
        val salvato = leggiIndice()
        val fresco = indice ?: salvato?.takeIf { orologio() - it.first < ETA_INDICE_S }?.second
        fresco?.get(chiave)?.let {
            indice = fresco
            return it
        }
        // Indice assente o vecchio, o senza questa chiave. Una chiave che su
        // Drive non c'e' davvero non deve costare un elenco completo a ogni
        // giro: con l'indice fresco si rinnova solo se ha piu' di un'ora
        val eta = salvato?.let { orologio() - it.first } ?: Double.MAX_VALUE
        if (indiceRinnovato || (fresco != null && eta < ETA_PER_MANCANTE_S)) return fresco?.get(chiave)
        indiceRinnovato = true
        costruisciIndice()?.let {
            indice = it
            return it[chiave]
        }
        // Drive non risponde: meglio un indice vecchio che nessuno
        return salvato?.second?.get(chiave)
    }

    /** L'elenco ricorsivo della cartella: chiavi relative con '/', come in image_library. */
    private fun costruisciIndice(): Map<String, VoceIndice>? {
        val voci = LinkedHashMap<String, VoceIndice>()
        val daVisitare = ArrayDeque(listOf(Triple(cartellaDrive.id, cartellaDrive.resourceKey, "")))
        while (daVisitare.isNotEmpty()) {
            val (id, rk, prefisso) = daVisitare.removeFirst()
            val figli = chiama { api.elenca(id, rk) }
            if (figli !is Esito.Ok) return null
            for (v in figli.valore) {
                if (v.cartella) {
                    daVisitare += Triple(v.id, v.resourceKey, "$prefisso${v.nome}/")
                } else {
                    // Due file con lo stesso nome nella stessa cartella: vale il primo
                    voci.putIfAbsent("$prefisso${v.nome}", VoceIndice(v.id, v.md5, v.dimensione, v.resourceKey))
                }
            }
        }
        salvaIndice(voci)
        return voci
    }

    private fun leggiIndice(): Pair<Double, Map<String, VoceIndice>>? = try {
        val o = Json.parseToJsonElement(fileIndice.readText()).jsonObject
        if (o["cartella"]?.jsonPrimitive?.contentOrNull != cartellaDrive.id) null
        else (o.getValue("creato").jsonPrimitive.doubleOrNull ?: 0.0) to o.getValue("voci").jsonObject.mapValues { (_, v) ->
            val e = v.jsonObject
            VoceIndice(
                e.getValue("id").jsonPrimitive.content,
                e["md5"]?.jsonPrimitive?.contentOrNull,
                e["dimensione"]?.jsonPrimitive?.longOrNull,
                e["rk"]?.jsonPrimitive?.contentOrNull,
            )
        }
    } catch (e: Exception) {
        null
    }

    private fun salvaIndice(voci: Map<String, VoceIndice>) {
        val o = buildJsonObject {
            put("cartella", cartellaDrive.id)
            put("creato", orologio())
            put("voci", buildJsonObject {
                voci.forEach { (k, v) ->
                    put(k, buildJsonObject {
                        put("id", v.id)
                        v.md5?.let { put("md5", it) }
                        v.dimensione?.let { put("dimensione", it) }
                        v.resourceKey?.let { put("rk", it) }
                    })
                }
            })
        }
        runCatching { scriviIntero(fileIndice, o.toString()) }
    }

    // ── Cache ────────────────────────────────────────────────────────────────

    /** Se il file locale e' quello di Drive. L'md5 di un file mai visto si calcola una volta e si ricorda. */
    private fun aggiornato(chiave: String, f: File, voce: VoceIndice): Boolean {
        voce.md5 ?: return true
        val noto = cache[chiave]?.takeIf { it.dimensione == f.length() && it.md5 != null }?.md5
        val md5 = noto ?: md5(f).also {
            cache[chiave] = InCache(it, f.length(), cache[chiave]?.uso ?: 0.0)
            salvaCache()
        }
        return md5 == voce.md5
    }

    private fun leggiCache(): MutableMap<String, InCache> = try {
        Json.parseToJsonElement(fileCache.readText()).jsonObject.mapValuesTo(LinkedHashMap()) { (_, v) ->
            val e = v.jsonObject
            InCache(
                e["md5"]?.jsonPrimitive?.contentOrNull,
                e["dimensione"]?.jsonPrimitive?.longOrNull ?: -1,
                e["uso"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
            )
        }
    } catch (e: Exception) {
        LinkedHashMap()
    }

    private fun salvaCache() {
        val o: JsonObject = buildJsonObject {
            cache.forEach { (k, v) ->
                put(k, buildJsonObject {
                    v.md5?.let { put("md5", it) }
                    put("dimensione", v.dimensione)
                    put("uso", v.uso)
                })
            }
        }
        runCatching { scriviIntero(fileCache, o.toString()) }
    }

    // ── Errori ───────────────────────────────────────────────────────────────

    private sealed interface Esito<out T> {
        data class Ok<T>(val valore: T) : Esito<T>
        data object Fallita : Esito<Nothing>
    }

    /**
     * Esegue una chiamata a Drive. Gli errori si scrivono nel log una volta
     * per serie, come il meteo, e il primo successo dopo una serie lo dice.
     */
    private fun <T> chiama(azione: () -> T): Esito<T> {
        if (offline) return Esito.Fallita
        return try {
            val r = azione()
            if (fileErrore.exists()) {
                fileErrore.delete()
                diario.scrivi("[DRIVE] Di nuovo raggiungibile")
            }
            Esito.Ok(r)
        } catch (e: ErroreDrive) {
            errore(e)
            Esito.Fallita
        } catch (e: Exception) {
            errore(ErroreDrive(TipoErrore.RETE, null, e.message ?: e.javaClass.simpleName, e))
            Esito.Fallita
        }
    }

    private fun errore(e: ErroreDrive) {
        // Rete, server e chiave valgono per tutto il giro: insistere costa solo timeout
        if (e.tipo != TipoErrore.ACCESSO) offline = true
        val serie = runCatching { fileErrore.readText().trim().split("\t") }.getOrNull()
        val stessa = serie?.getOrNull(1) == e.tipo.name
        if (!stessa) {
            diario.scrivi(
                when (e.tipo) {
                    TipoErrore.RETE, TipoErrore.SERVER -> "[DRIVE] Non raggiungibile (${e.message}): uso le immagini in cache"
                    TipoErrore.CHIAVE -> "[DRIVE] La chiave API e' rifiutata (${e.message}): riprovo fra $RIPROVA_CHIAVE_MIN minuti"
                    TipoErrore.ACCESSO ->
                        "[DRIVE] Accesso negato (${e.message}). Se la cartella e' pubblica, il sospetto sono i resource key"
                },
            )
        }
        // Per la chiave la mezz'ora riparte da ogni rifiuto; per gli altri conta l'inizio della serie
        val da = if (stessa && e.tipo != TipoErrore.CHIAVE) serie!![0] else orologio().toString()
        runCatching { scriviIntero(fileErrore, "$da\t${e.tipo.name}\n") }
    }

    /** Dopo un rifiuto della chiave si aspetta mezz'ora: ogni giro darebbe lo stesso errore. */
    private fun bloccato(): Boolean {
        if (offline) return true
        val serie = runCatching { fileErrore.readText().trim().split("\t") }.getOrNull() ?: return false
        if (serie.getOrNull(1) != TipoErrore.CHIAVE.name) return false
        val da = serie[0].toDoubleOrNull() ?: return false
        return orologio() - da < RIPROVA_CHIAVE_MIN * 60
    }

    companion object {
        const val NOME_CONFIG = "config.json"
        private const val ETA_INDICE_S = 24 * 3600
        private const val ETA_PER_MANCANTE_S = 3600
        private const val RIPROVA_CHIAVE_MIN = 30

        fun md5(byte: ByteArray): String = MessageDigest.getInstance("MD5").digest(byte).joinToString("") { "%02x".format(it) }

        fun md5(f: File): String {
            val d = MessageDigest.getInstance("MD5")
            f.inputStream().use { ingresso ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val n = ingresso.read(buffer)
                    if (n < 0) break
                    d.update(buffer, 0, n)
                }
            }
            return d.digest().joinToString("") { "%02x".format(it) }
        }

        private fun sostituisci(tmp: File, f: File) {
            if (!tmp.renameTo(f)) {
                f.delete()
                check(tmp.renameTo(f)) { "impossibile scrivere ${f.path}" }
            }
        }

        fun kb(byte: Long): String = if (byte < 1024 * 1024) "${(byte + 512) / 1024} KB" else "%.1f MB".format(byte / 1048576.0)
        private fun mb(byte: Long): String = "%.0f MB".format(byte / 1048576.0)
    }
}
