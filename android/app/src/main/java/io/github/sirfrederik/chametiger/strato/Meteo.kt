@file:OptIn(ExperimentalSerializationApi::class)

package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.DEFAULT_SOGLIA_NUVOLE
import io.github.sirfrederik.chametiger.motore.FONTE_MET_NORWAY
import io.github.sirfrederik.chametiger.motore.FONTE_OPEN_METEO
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
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.long
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

// Il meteo da Met Norway o da Open-Meteo (ICON-2I), secondo "fonte" nel
// config, come meteo.py: le prossime 10 ore, ora attuale
// compresa, sulla posizione del telefono o sulle coordinate del config. Lo
// stato del meteo entra nella firma della regola, quindi nel mazzo: ogni
// scelta qui deve essere identica a quella del PC, a cominciare da come si
// legge un simbolo (vedi MeteoTest, che confronta le due implementazioni
// sulle stesse risposte).
//
// Le ore finiscono in meteo.json nella cartella dell'app, nello stesso formato
// del PC: i due file si confrontano a occhio.

const val ORE_PREVISTE = 10
private const val MAX_ETA_ORE = 12
private const val RIPROVA_MINUTI = 30
// "complete" e non "compact": solo lui ha le nubi per strato, che servono al nuvoloso
private const val URL_PREVISIONI = "https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=%.2f&lon=%.2f"
// ICON-2I: precipitation sono i mm caduti nell'ora PRIMA dell'orario indicato,
// weather_code serve solo per il temporale, le nubi basse e medie (%) per il
// nuvoloso. Orari in secondi dall'epoca.
private const val URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f" +
    "&hourly=precipitation,weather_code,cloud_cover_low,cloud_cover_mid" +
    "&models=italia_meteo_arpae_icon_2i" +
    "&forecast_hours=%d&timeformat=unixtime&timezone=GMT"

/** meteo.FONTI: il nome della fonte per log e schermata. */
/** Sotto la soglia della pioggia, da quanti mm l'ora e' nuvolosa: meteo.PIOGGIA_LEGGERA_MM. */
private const val PIOGGIA_LEGGERA_MM = 0.1

fun nomeFonte(fonte: String): String = if (fonte == FONTE_OPEN_METEO) "Open-Meteo ICON-2I" else "Met Norway"

/**
 * copertura_bassa: quanto cielo coprono le nubi basse e medie insieme (%),
 * come strati indipendenti. Le nubi alte non contano. Null se mancano tutti e
 * due gli strati. Stesse operazioni di meteo.py, nello stesso ordine.
 */
fun coperturaBassa(basse: Double?, medie: Double?): Double? {
    if (basse == null && medie == null) return null
    val b = basse ?: 0.0
    val m = medie ?: 0.0
    return 100 - (100 - b) * (100 - m) / 100
}

/**
 * stato_da_simbolo: 'heavyrainandthunder' -> temporale, 'rainshowers_day' ->
 * pioggia, pioggia leggera e 'cloudy' -> nuvoloso. Neve, nebbia, poco nuvoloso:
 * asciutto.
 */
fun statoDaSimbolo(simbolo: String): StatoMeteo {
    val s = simbolo.split("_")[0]
    return when {
        "thunder" in s -> StatoMeteo.TEMPORALE
        "rain" in s || "sleet" in s -> if (s.startsWith("light")) StatoMeteo.NUVOLOSO else StatoMeteo.PIOGGIA
        s == "cloudy" -> StatoMeteo.NUVOLOSO
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
 * forma attesa, come meteo.py. Un 'cloudy' e' nuvoloso solo se le nubi basse
 * e medie coprono almeno `nuvole` %; senza gli strati resta nuvoloso.
 */
fun previsioni(
    risposta: String,
    adesso: LocalDateTime,
    nuvole: Double = DEFAULT_SOGLIA_NUVOLE,
): LinkedHashMap<String, StatoMeteo> {
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
        if (chiave >= ora) {
            var stato = statoDaSimbolo(simbolo)
            if (simbolo.split("_")[0] == "cloudy") {
                val strati = dati["instant"]?.jsonObject?.get("details")?.jsonObject
                val coperto = coperturaBassa(
                    strati?.get("cloud_area_fraction_low")?.jsonPrimitive?.doubleOrNull,
                    strati?.get("cloud_area_fraction_medium")?.jsonPrimitive?.doubleOrNull,
                )
                if (coperto != null && coperto < nuvole) stato = StatoMeteo.ASCIUTTO
            }
            ore[chiave] = stato
        }
        if (ore.size == ORE_PREVISTE) break
    }
    return ore
}

/**
 * _previsioni_open_meteo: {ora locale: stato} dalla risposta di Open-Meteo,
 * dall'ora di `adesso` per ORE_PREVISTE ore. I mm di un orario sono quelli
 * caduti nell'ora prima: il valore delle 15:00 e' la pioggia dell'ora 14.
 * Temporale coi codici WMO 95-99, pioggia da `soglia` mm in su; sotto,
 * nuvoloso da PIOGGIA_LEGGERA_MM o con le nubi basse e medie da `nuvole` % in
 * su (coperturaBassa). Solleva se la
 * risposta non ha la forma attesa o non ha ore (fuori dall'area del modello i
 * valori sono null), come meteo.py.
 */
fun previsioniOpenMeteo(
    risposta: String,
    adesso: LocalDateTime,
    soglia: Double,
    nuvole: Double,
): LinkedHashMap<String, StatoMeteo> {
    val orari = Json.parseToJsonElement(risposta).jsonObject.getValue("hourly").jsonObject
    val tempi = orari.getValue("time").jsonArray
    val pioggia = orari.getValue("precipitation").jsonArray
    val codici = orari.getValue("weather_code").jsonArray
    val basse = orari.getValue("cloud_cover_low").jsonArray
    val medie = orari.getValue("cloud_cover_mid").jsonArray
    val ora = chiaveOra(adesso)
    val ore = LinkedHashMap<String, StatoMeteo>()
    for (i in 0 until listOf(tempi.size, pioggia.size, codici.size, basse.size, medie.size).min()) { // come zip
        val t = LocalDateTime.ofInstant(Instant.ofEpochSecond(tempi[i].jsonPrimitive.long), ZONA)
        val chiave = chiaveOra(t.minusHours(1))
        val mm = pioggia[i].jsonPrimitive.doubleOrNull
        if (chiave < ora || mm == null) continue
        val codice = codici[i].jsonPrimitive.intOrNull
        val coperto = coperturaBassa(basse[i].jsonPrimitive.doubleOrNull, medie[i].jsonPrimitive.doubleOrNull)
        ore[chiave] = when {
            codice != null && codice >= 95 -> StatoMeteo.TEMPORALE
            mm >= soglia -> StatoMeteo.PIOGGIA
            mm >= PIOGGIA_LEGGERA_MM || (coperto != null && coperto >= nuvole) -> StatoMeteo.NUVOLOSO
            else -> StatoMeteo.ASCIUTTO
        }
        if (ore.size == ORE_PREVISTE) break
    }
    check(ore.isNotEmpty()) { "nessuna ora nella risposta (fuori dall'area di ICON-2I?)" }
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
data class DatiMeteo(
    val scaricato: Double,
    val lat: Double,
    val lon: Double,
    val ore: Map<String, StatoMeteo>,
    /** I meteo.json di prima non hanno "fonte": erano di Met Norway. */
    val fonte: String = FONTE_MET_NORWAY,
)

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
    /** L'ultima posizione del telefono salvata col pulsante "Carica meteo"; null: valgono quelle del config. */
    private val posizione: Pair<Double, Double>? = null,
    /** La fonte scelta sul telefono (FONTE_MET_NORWAY o FONTE_OPEN_METEO); null: quella del config. */
    private val fonteTelefono: String? = null,
) {
    /** La fonte delle previsioni: quella scelta sul telefono, se no quella del config. */
    fun fonteDi(config: Config): String = fonteTelefono ?: config.meteoFonte

    private val userAgent get() = "Chametiger-Android/$versione github.com/Sir-Frederik/Chametiger"

    /**
     * _coords: le coordinate del meteo arrotondate, come la griglia delle
     * previsioni. Quelle del telefono se ce ne sono, se no quelle del config.
     */
    fun coordinate(config: Config): Pair<Double, Double> =
        (posizione ?: config.coordinate(identita)).let { (lat, lon) -> arrotonda2(lat) to arrotonda2(lon) }

    /** Da dove vengono le coordinate del meteo, per log e schermata. */
    fun origine(config: Config): String =
        coordinate(config).let { (lat, lon) -> "%.2f, %.2f".format(Locale.ROOT, lat, lon) } +
            if (posizione != null) " (posizione del telefono)" else " (coordinate del config)"

    fun leggi(): DatiMeteo? = try {
        val o = Json.parseToJsonElement(file.readText(Charsets.UTF_8)).jsonObject
        DatiMeteo(
            scaricato = o.getValue("scaricato").jsonPrimitive.doubleOrNull ?: 0.0,
            lat = o.getValue("lat").jsonPrimitive.doubleOrNull ?: Double.NaN,
            lon = o.getValue("lon").jsonPrimitive.doubleOrNull ?: Double.NaN,
            ore = (o["ore"] as? JsonObject).orEmpty().mapNotNull { (k, v) ->
                StatoMeteo.entries.firstOrNull { it.tag == (v as? JsonPrimitive)?.contentOrNull }?.let { k to it }
            }.toMap(),
            fonte = (o["fonte"] as? JsonPrimitive)?.contentOrNull ?: FONTE_MET_NORWAY,
        )
    } catch (e: Exception) {
        null
    }

    /** _valide: dati recenti, scaricati per la posizione attuale dalla fonte scelta. */
    fun valide(dati: DatiMeteo?, config: Config, adesso: LocalDateTime): Boolean {
        if (dati == null || !config.meteoAttivo) return false
        if (dati.fonte != fonteDi(config)) return false
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

    private fun ultimoErrore(): Double = try {
        fileErrore.readText().trim().toDouble()
    } catch (e: Exception) {
        0.0
    }

    /**
     * Se aggiornaSeServe scaricherebbe adesso: dati vecchi di aggiorna_ore, o di
     * un'altra posizione, e nessun errore negli ultimi RIPROVA_MINUTI. Il lavoro
     * in background lo chiede per leggere la posizione del telefono solo quando
     * serve.
     */
    fun daAggiornare(config: Config, adesso: LocalDateTime): Boolean {
        if (!config.meteoAttivo) return false
        val ora = secondi(adesso)
        val dati = leggi()
        if (valide(dati, config, adesso) && ora - dati!!.scaricato < config.meteoOre * 3600) return false
        return ora - ultimoErrore() >= RIPROVA_MINUTI * 60
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
        val ultimoErrore = ultimoErrore()
        if (!forza && !daAggiornare(config, adesso)) return false

        val (lat, lon) = coordinate(config)
        val fonte = fonteDi(config)
        val ore = try {
            if (fonte == FONTE_OPEN_METEO) {
                // Due ore in piu': la prima risposta e' l'ora attuale, che parla di quella prima
                val url = URL_OPEN_METEO.format(Locale.ROOT, lat, lon, ORE_PREVISTE + 2)
                previsioniOpenMeteo(rete.scarica(url, userAgent), adesso, config.meteoSogliaMm, config.meteoSogliaNuvole)
            } else {
                previsioni(rete.scarica(URL_PREVISIONI.format(Locale.ROOT, lat, lon), userAgent), adesso, config.meteoSogliaNuvole)
            }
        } catch (e: Exception) {
            if (forza || ultimoErrore == 0.0) {
                diario.scrivi("[METEO] Meteo non disponibile (${nomeFonte(fonte)}: ${e.message ?: e}): scelgo come col sereno.")
            }
            runCatching { scriviIntero(fileErrore, "$ora\n") }
            return false
        }

        val tutte = passateDiOggi(leggi(), config, adesso) + ore
        val nuovo = buildJsonObject {
            // Per esteso come lo scrive json.dump sul PC, non 1.79E9: i due file si confrontano a occhio
            put("scaricato", JsonUnquotedLiteral(BigDecimal.valueOf(ora).toPlainString()))
            put("lat", lat)
            put("lon", lon)
            put("fonte", fonte)
            put("ore", buildJsonObject { tutte.toSortedMap().forEach { (k, v) -> put(k, v.tag) } })
        }
        try {
            scriviIntero(file, JSON_LEGGIBILE.encodeToString(JsonObject.serializer(), nuovo) + "\n")
        } catch (e: Exception) {
            diario.scrivi("[METEO] Impossibile scrivere meteo.json: $e")
            return false
        }
        fileErrore.delete()
        diario.scrivi("[METEO] Aggiornato (${nomeFonte(fonte)}): ${riassunto(ore, adesso)}.")
        return true
    }

    /**
     * passate_di_oggi: le ore di oggi gia' passate nel meteo.json di prima, da
     * tenere nel nuovo. Il motore rifa' la sequenza del giorno dalla mezzanotte
     * col tempo di ogni ora: se il download buttasse le ore passate, queste
     * tornerebbero asciutte e la finestra di adesso potrebbe cambiare immagine
     * anche col tempo di quest'ora invariato. Solo se i dati di prima valevano
     * ancora: altrimenti il motore le vedeva gia' asciutte.
     */
    private fun passateDiOggi(dati: DatiMeteo?, config: Config, adesso: LocalDateTime): Map<String, StatoMeteo> {
        if (!valide(dati, config, adesso)) return emptyMap()
        val ora = chiaveOra(adesso)
        val oggi = ora.take(10) + "T"
        return dati!!.ore.filterKeys { it.startsWith(oggi) && it < ora }
    }

    /** Lo stato del meteo in una riga, per la schermata. La posizione la mostra la schermata a parte. */
    fun descrizione(config: Config, adesso: LocalDateTime): String {
        if (!config.meteoAttivo) return "disattivato nel config: i tag pioggia/temporale contano come gli altri"
        val dati = leggi()
        if (!valide(dati, config, adesso)) return "nessun dato valido: si sceglie come col sereno"
        val quando = LocalDateTime.ofInstant(Instant.ofEpochMilli((dati!!.scaricato * 1000).toLong()), ZONA)
        return "${riassunto(dati.ore, adesso)} (${nomeFonte(dati.fonte)}, scaricato alle ${quando.format(HH_MM)})"
    }

    private fun secondi(t: LocalDateTime): Double = t.atZone(ZONA).toInstant().toEpochMilli() / 1000.0

    companion object {
        private val HH_MM = DateTimeFormatter.ofPattern("HH:mm")
        private val JSON_LEGGIBILE = Json { prettyPrint = true }
    }
}
