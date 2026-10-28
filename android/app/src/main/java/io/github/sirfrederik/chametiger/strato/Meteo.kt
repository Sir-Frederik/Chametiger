@file:OptIn(ExperimentalSerializationApi::class)

package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.FonteMeteo
import io.github.sirfrederik.chametiger.motore.StatoMeteo
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonUnquotedLiteral
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

// Il meteo da Met Norway, come meteo.py: le prossime 10 ore, ora attuale
// compresa, sulle coordinate del config. Lo stato del meteo entra nella firma
// della regola, quindi nel mazzo: ogni scelta qui deve essere identica a quella
// del PC, a cominciare da come si legge un simbolo (vedi MeteoTest, che
// confronta le due implementazioni sulle stesse risposte).
//
// Le ore finiscono in meteo.json nella cartella dell'app, nello stesso formato
// del PC: i due file si confrontano a occhio.

const val ORE_PREVISTE = 10
private const val MAX_ETA_ORE = 12
private const val RIPROVA_MINUTI = 30
private const val URL_PREVISIONI = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%.2f&lon=%.2f"

/** stato_da_simbolo: 'heavyrainandthunder' -> temporale, 'lightrainshowers_day' -> pioggia. Neve e nebbia: asciutto. */
fun statoDaSimbolo(simbolo: String): StatoMeteo {
    val s = simbolo.split("_")[0]
    return when {
        "thunder" in s -> StatoMeteo.TEMPORALE
        "rain" in s || "sleet" in s -> StatoMeteo.PIOGGIA
        else -> StatoMeteo.ASCIUTTO
    }
}

private val CHIAVE = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH")

/** _chiave: l'ora locale come la scrive meteo.json, '2026-10-28T14'. */
fun chiaveOra(t: LocalDateTime): String = t.format(CHIAVE)

/**
 * _previsioni: {ora locale: stato} dalla risposta di locationforecast,
 * dall'ora di `adesso` per ORE_PREVISTE ore. Gli orari arrivano in UTC e
 * passano a ZONA, come fromtimestamp sul PC. Solleva se la risposta non ha la
 * forma attesa, come meteo.py.
 */
fun previsioni(risposta: String, adesso: LocalDateTime): LinkedHashMap<String, StatoMeteo> {
    val serie = Json.parseToJsonElement(risposta).jsonObject
        .getValue("properties").jsonObject.getValue("timeseries").jsonArray
    val ora = chiaveOra(adesso)
    val ore = LinkedHashMap<String, StatoMeteo>()
    for (passo in serie) {
        val dati = passo.jsonObject.getValue("data").jsonObject
        // .get("next_1_hours", {}).get("summary", {}).get("symbol_code")
        val simbolo = dati["next_1_hours"]?.jsonObject?.get("summary")?.jsonObject?.get("symbol_code")
            ?.jsonPrimitive?.contentOrNull
        if (simbolo.isNullOrEmpty()) continue // oltre le prime ~60 ore si passa a passi di 6 ore
        val utc = Instant.parse(passo.jsonObject.getValue("time").jsonPrimitive.content)
        val chiave = chiaveOra(LocalDateTime.ofInstant(utc, ZONA))
        if (chiave >= ora) ore[chiave] = statoDaSimbolo(simbolo)
        if (ore.size == ORE_PREVISTE) break
    }
    return ore
}

/** riassunto: 'pioggia 14-17, temporale 20-21' sulle ore a venire, per il log. */
fun riassunto(ore: Map<String, StatoMeteo>, adesso: LocalDateTime): String {
    val ora = chiaveOra(adesso)
    data class Tratto(val stato: StatoMeteo, val da: String, var a: String, var ultima: String)
    val tratti = mutableListOf<Tratto>()
    for (chiave in ore.keys.sorted()) {
        val stato = ore.getValue(chiave)
        if (chiave < ora || stato == StatoMeteo.ASCIUTTO) continue
        val h = chiave.takeLast(2)
        val prima = chiaveOra(LocalDateTime.parse("$chiave:00").minusHours(1)) // _precedente
        val ultimo = tratti.lastOrNull()
        if (ultimo != null && ultimo.stato == stato && ultimo.ultima == prima) {
            ultimo.a = h
            ultimo.ultima = chiave
        } else {
            tratti += Tratto(stato, h, h, chiave)
        }
    }
    if (tratti.isEmpty()) return "niente pioggia nelle prossime $ORE_PREVISTE ore"
    return tratti.joinToString(", ") { "${it.stato.tag} ${it.da}-${"%02d".format(it.a.toInt() + 1)}" }
}

/** round(x, 2) di Python: arrotondamento al pari sul valore esatto del double. */
fun arrotonda2(x: Double): Double = BigDecimal(x).setScale(2, RoundingMode.HALF_EVEN).toDouble()

/** Chi scarica davvero: HTTP sul telefono, una risposta finta nei test. */
fun interface Rete {
    /** Il corpo della risposta. Un'eccezione per errori di rete o risposte non 2xx. */
    fun scarica(url: String, userAgent: String): String
}

object ReteHttp : Rete {
    override fun scarica(url: String, userAgent: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            // Come curl --max-time 20 sul PC
            c.connectTimeout = 20_000
            c.readTimeout = 20_000
            c.setRequestProperty("User-Agent", userAgent)
            val codice = c.responseCode
            if (codice !in 200..299) throw IllegalStateException("HTTP $codice")
            return c.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            c.disconnect()
        }
    }
}

/** Il contenuto di meteo.json. `scaricato` in secondi dall'epoca, come time.time(). */
data class DatiMeteo(val scaricato: Double, val lat: Double, val lon: Double, val ore: Map<String, StatoMeteo>)

/**
 * Il meteo del telefono: download, meteo.json e ripiego, come meteo.py.
 *
 * Senza dati validi (nessuna rete, file vecchio, coordinate cambiate) ogni ora
 * vale asciutto, e si sceglie come col sereno. Dopo un download fallito si
 * riprova dopo RIPROVA_MINUTI: il momento dell'errore sta nella memoria
 * interna, perche' ogni risveglio e' un processo nuovo, e il log lo dice una
 * volta per serie di errori come il tray.
 */
class Meteo(
    private val file: File,
    private val fileErrore: File,
    private val identita: String,
    private val versione: String,
    private val diario: Diario,
    private val rete: Rete = ReteHttp,
) {
    private val userAgent get() = "Chametiger-Android/$versione github.com/Sir-Frederik/Chametiger"

    /** _coords: le coordinate del dispositivo arrotondate, come la griglia delle previsioni. */
    fun coordinate(config: Config): Pair<Double, Double> =
        config.coordinate(identita).let { (lat, lon) -> arrotonda2(lat) to arrotonda2(lon) }

    fun leggi(): DatiMeteo? = try {
        val o = Json.parseToJsonElement(file.readText(Charsets.UTF_8)).jsonObject
        DatiMeteo(
            scaricato = o.getValue("scaricato").jsonPrimitive.doubleOrNull ?: 0.0,
            lat = o.getValue("lat").jsonPrimitive.doubleOrNull ?: Double.NaN,
            lon = o.getValue("lon").jsonPrimitive.doubleOrNull ?: Double.NaN,
            ore = (o["ore"] as? JsonObject).orEmpty().mapNotNull { (k, v) ->
                StatoMeteo.entries.firstOrNull { it.tag == (v as? JsonPrimitive)?.contentOrNull }?.let { k to it }
            }.toMap(),
        )
    } catch (e: Exception) {
        null
    }

    /** _valide: dati recenti e scaricati per la posizione attuale. */
    fun valide(dati: DatiMeteo?, config: Config, adesso: LocalDateTime): Boolean {
        if (dati == null || !config.meteoAttivo) return false
        val (lat, lon) = coordinate(config)
        if (dati.lat != lat || dati.lon != lon) return false
        val eta = secondi(adesso) - dati.scaricato
        return eta >= 0 && eta <= MAX_ETA_ORE * 3600
    }

    /** del_giorno, per il motore: le ore note di quel giorno; le altre, o tutte senza dati validi, asciutte. */
    fun fonte(config: Config, adesso: LocalDateTime): FonteMeteo {
        val dati = leggi()?.takeIf { valide(it, config, adesso) } ?: return FonteMeteo.NESSUNA
        return FonteMeteo { giorno ->
            val prefisso = "$giorno" + "T"
            dati.ore.filterKeys { it.startsWith(prefisso) }.mapKeys { it.key.takeLast(2).toInt() }
        }
    }

    /**
     * aggiorna_se_serve: riscarica se i dati sono piu' vecchi di aggiorna_ore o
     * la posizione e' cambiata; con forza=true subito, anche dopo un errore
     * recente. True se ha scaricato. Non solleva mai.
     */
    fun aggiornaSeServe(config: Config, adesso: LocalDateTime, forza: Boolean = false): Boolean {
        if (!config.meteoAttivo) {
            if (forza) diario.scrivi("[METEO] Meteo disattivato nel config (\"attivo\": false).")
            return false
        }
        val ora = secondi(adesso)
        val ultimoErrore = try {
            fileErrore.readText().trim().toDouble()
        } catch (e: Exception) {
            0.0
        }
        if (!forza) {
            val dati = leggi()
            if (valide(dati, config, adesso) && ora - dati!!.scaricato < config.meteoOre * 3600) return false
            if (ora - ultimoErrore < RIPROVA_MINUTI * 60) return false
        }

        val (lat, lon) = coordinate(config)
        val ore = try {
            previsioni(rete.scarica(URL_PREVISIONI.format(Locale.ROOT, lat, lon), userAgent), adesso)
        } catch (e: Exception) {
            if (forza || ultimoErrore == 0.0) {
                diario.scrivi("[METEO] Meteo non disponibile (Met Norway: ${e.message ?: e}): scelgo come col sereno.")
            }
            runCatching { scriviIntero(fileErrore, "$ora\n") }
            return false
        }

        val nuovo = buildJsonObject {
            // Per esteso come lo scrive json.dump sul PC, non 1.79E9: i due file si confrontano a occhio
            put("scaricato", JsonUnquotedLiteral(BigDecimal.valueOf(ora).toPlainString()))
            put("lat", lat)
            put("lon", lon)
            put("ore", buildJsonObject { ore.toSortedMap().forEach { (k, v) -> put(k, v.tag) } })
        }
        try {
            scriviIntero(file, JSON_LEGGIBILE.encodeToString(JsonObject.serializer(), nuovo) + "\n")
        } catch (e: Exception) {
            diario.scrivi("[METEO] Impossibile scrivere meteo.json: $e")
            return false
        }
        fileErrore.delete()
        diario.scrivi("[METEO] Aggiornato (Met Norway): ${riassunto(ore, adesso)}.")
        return true
    }

    /** Lo stato del meteo in una riga, per la schermata. */
    fun descrizione(config: Config, adesso: LocalDateTime): String {
        if (!config.meteoAttivo) return "disattivato nel config: i tag pioggia/temporale contano come gli altri"
        val dati = leggi()
        if (!valide(dati, config, adesso)) return "nessun dato valido: si sceglie come col sereno"
        val quando = LocalDateTime.ofInstant(Instant.ofEpochMilli((dati!!.scaricato * 1000).toLong()), ZONA)
        return "${riassunto(dati.ore, adesso)} (Met Norway, scaricato alle ${quando.format(HH_MM)})"
    }

    private fun secondi(t: LocalDateTime): Double = t.atZone(ZONA).toInstant().toEpochMilli() / 1000.0

    companion object {
        private val HH_MM = DateTimeFormatter.ofPattern("HH:mm")
        private val JSON_LEGGIBILE = Json { prettyPrint = true }
    }
}
