package io.github.sirfrederik.chametiger.strato

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

// L'accesso a Drive: una cartella condivisa con "chiunque abbia il link",
// letta con una chiave API. Niente OAuth: lo scope drive.readonly e' riservato,
// e in modalita' di prova il token scade ogni settimana in silenzio.

/** Un file o una sottocartella di Drive. */
data class VoceDrive(
    val id: String,
    val nome: String,
    val cartella: Boolean,
    val md5: String?,
    val dimensione: Long?,
    val resourceKey: String?,
)

/** Che tipo di errore: decide se riprovare subito o aspettare. */
enum class TipoErrore {
    /** Niente rete, timeout: si usa la cache e si riprova al giro dopo. */
    RETE,

    /** 5xx, 429 o quota: passeggero, come la rete. */
    SERVER,

    /** La chiave: non valida, API non abilitata, app non autorizzata. Inutile insistere. */
    CHIAVE,

    /** 403 o 404 su un file: indice vecchio, o resource key. */
    ACCESSO,
}

class ErroreDrive(val tipo: TipoErrore, val codice: Int?, val motivo: String, causa: Throwable? = null) :
    IOException(if (codice != null) "HTTP $codice: $motivo" else motivo, causa)

/** Le due operazioni che servono. Un finto nei test, HTTP sul telefono. */
interface ApiDrive {
    /** I figli diretti della cartella, file e sottocartelle, senza quelli nel cestino. */
    fun elenca(cartella: String, resourceKey: String?): List<VoceDrive>

    /** Il config.json della cartella, se c'e': una richiesta piccola, da fare a ogni giro. */
    fun cerca(cartella: String, resourceKey: String?, nome: String): VoceDrive?

    /** Il contenuto del file, scritto in `destinazione`. Ritorna i byte scaricati. */
    fun scarica(voce: VoceDrive, destinazione: File): Long

    /** I byte ricevuti finora, elenchi compresi: il traffico di un giro, per il log. */
    val byteRicevuti: Long
}

/**
 * Drive API v3 con la chiave. Manda sempre X-Android-Package e
 * X-Android-Cert: con la restrizione per app Android attiva sulla chiave,
 * Google le controlla; senza, le ignora.
 */
class ApiDriveHttp(
    private val chiave: String,
    private val pacchetto: String,
    /** SHA-1 del certificato di firma, esadecimale maiuscolo senza i due punti. */
    private val certificato: String,
) : ApiDrive {

    override var byteRicevuti = 0L
        private set

    override fun elenca(cartella: String, resourceKey: String?): List<VoceDrive> {
        val voci = mutableListOf<VoceDrive>()
        var pagina: String? = null
        do {
            val o = json(
                "files",
                mapOf(
                    "q" to "'$cartella' in parents and trashed=false",
                    "fields" to "nextPageToken,files($CAMPI)",
                    "pageSize" to "1000",
                ) + (pagina?.let { mapOf("pageToken" to it) } ?: emptyMap()),
                resourceKey?.let { "$cartella/$it" },
            )
            o["files"]?.jsonArray?.forEach { voci += voce(it.jsonObject) }
            pagina = o["nextPageToken"]?.jsonPrimitive?.contentOrNull
        } while (pagina != null)
        return voci
    }

    override fun cerca(cartella: String, resourceKey: String?, nome: String): VoceDrive? {
        val o = json(
            "files",
            mapOf(
                "q" to "'$cartella' in parents and name='${nome.replace("'", "\\'")}' and trashed=false",
                "fields" to "files($CAMPI)",
            ),
            resourceKey?.let { "$cartella/$it" },
        )
        return o["files"]?.jsonArray?.firstOrNull()?.let { voce(it.jsonObject) }
    }

    override fun scarica(voce: VoceDrive, destinazione: File): Long {
        val c = apri("files/${voce.id}", mapOf("alt" to "media"), voce.resourceKey?.let { "${voce.id}/$it" })
        try {
            controlla(c)
            var totale = 0L
            c.inputStream.use { ingresso ->
                destinazione.outputStream().use { uscita ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val n = ingresso.read(buffer)
                        if (n < 0) break
                        uscita.write(buffer, 0, n)
                        totale += n
                        byteRicevuti += n
                    }
                }
            }
            return totale
        } catch (e: ErroreDrive) {
            throw e
        } catch (e: IOException) {
            throw ErroreDrive(TipoErrore.RETE, null, e.message ?: e.javaClass.simpleName, e)
        } finally {
            c.disconnect()
        }
    }

    private fun json(percorso: String, parametri: Map<String, String>, resourceKey: String?): JsonObject {
        val c = apri(percorso, parametri, resourceKey)
        try {
            controlla(c)
            val corpo = c.inputStream.use { it.readBytes() }
            byteRicevuti += corpo.size
            return Json.parseToJsonElement(String(corpo, Charsets.UTF_8)).jsonObject
        } catch (e: ErroreDrive) {
            throw e
        } catch (e: IOException) {
            throw ErroreDrive(TipoErrore.RETE, null, e.message ?: e.javaClass.simpleName, e)
        } finally {
            c.disconnect()
        }
    }

    private fun apri(percorso: String, parametri: Map<String, String>, resourceKey: String?): HttpURLConnection {
        val query = (parametri + ("key" to chiave)).entries.joinToString("&") { (k, v) ->
            "$k=" + URLEncoder.encode(v, "UTF-8")
        }
        try {
            val c = URL("$BASE/$percorso?$query").openConnection() as HttpURLConnection
            c.connectTimeout = 20_000
            c.readTimeout = 60_000
            c.setRequestProperty("X-Android-Package", pacchetto)
            c.setRequestProperty("X-Android-Cert", certificato)
            // I file condivisi via link dopo il 2021 possono chiedere il resource key
            resourceKey?.let { c.setRequestProperty("X-Goog-Drive-Resource-Keys", it) }
            return c
        } catch (e: IOException) {
            throw ErroreDrive(TipoErrore.RETE, null, e.message ?: e.javaClass.simpleName, e)
        }
    }

    private fun controlla(c: HttpURLConnection) {
        val codice = try {
            c.responseCode
        } catch (e: IOException) {
            throw ErroreDrive(TipoErrore.RETE, null, e.message ?: e.javaClass.simpleName, e)
        }
        if (codice in 200..299) return
        val corpo = runCatching { c.errorStream?.bufferedReader()?.use { it.readText() } }.getOrNull().orEmpty()
        throw classifica(codice, corpo)
    }

    companion object {
        private const val BASE = "https://www.googleapis.com/drive/v3"
        private const val CAMPI = "id,name,mimeType,md5Checksum,size,resourceKey"
        const val TIPO_CARTELLA = "application/vnd.google-apps.folder"

        private fun voce(o: JsonObject) = VoceDrive(
            id = o.getValue("id").jsonPrimitive.content,
            nome = o.getValue("name").jsonPrimitive.content,
            cartella = o["mimeType"]?.jsonPrimitive?.contentOrNull == TIPO_CARTELLA,
            md5 = o["md5Checksum"]?.jsonPrimitive?.contentOrNull,
            dimensione = o["size"]?.jsonPrimitive?.contentOrNull?.toLongOrNull(),
            resourceKey = o["resourceKey"]?.jsonPrimitive?.contentOrNull,
        )

        /**
         * Il tipo di errore dalla risposta di Google. I motivi della chiave
         * stanno in error.errors[].reason o in error.details[].reason, a
         * seconda dell'API e della restrizione che ha bloccato la richiesta.
         */
        fun classifica(codice: Int, corpo: String): ErroreDrive {
            val errore = runCatching { Json.parseToJsonElement(corpo).jsonObject["error"]?.jsonObject }.getOrNull()
            val messaggio = errore?.get("message")?.jsonPrimitive?.contentOrNull ?: corpo.take(200)
            val motivi = buildList {
                errore?.get("errors")?.jsonArray?.forEach { e ->
                    e.jsonObject["reason"]?.jsonPrimitive?.contentOrNull?.let(::add)
                }
                errore?.get("details")?.jsonArray?.forEach { d ->
                    d.jsonObject["reason"]?.jsonPrimitive?.contentOrNull?.let(::add)
                }
                errore?.get("status")?.jsonPrimitive?.contentOrNull?.let(::add)
            }
            val descrizione = (motivi.distinct().joinToString(", ").takeIf { it.isNotEmpty() }?.let { "$it: " } ?: "") + messaggio
            val chiave = motivi.any { m ->
                MOTIVI_CHIAVE.any { it.equals(m, ignoreCase = true) } || m.startsWith("API_KEY", ignoreCase = true)
            }
            val quota = motivi.any { m -> MOTIVI_QUOTA.any { it.equals(m, ignoreCase = true) } }
            val tipo = when {
                chiave -> TipoErrore.CHIAVE
                codice == 429 || codice >= 500 || quota -> TipoErrore.SERVER
                else -> TipoErrore.ACCESSO
            }
            return ErroreDrive(tipo, codice, descrizione)
        }

        private val MOTIVI_CHIAVE = listOf(
            "keyInvalid", "keyExpired", "accessNotConfigured", "ipRefererBlocked", "forbiddenByRestrictions",
            "API_KEY_INVALID", "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_SERVICE_BLOCKED", "SERVICE_DISABLED",
        )
        private val MOTIVI_QUOTA = listOf("rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "RESOURCE_EXHAUSTED")
    }
}
