package io.github.sirfrederik.chametiger.motore

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject

// config.json letto come lo legge app.py: stesse chiavi, stessi default di
// ensure_defaults, stesse conversioni di str()/int()/bool() sui valori.

const val DEFAULT_LAT = 40.8518
const val DEFAULT_LON = 14.2681
const val DEFAULT_MINIMO_METEO = 2

enum class StatoMeteo(val tag: String) {
    ASCIUTTO("asciutto"),
    PIOGGIA("pioggia"),
    TEMPORALE("temporale");

    /** Pioggia o temporale: gli stati che cambiano il pool, come _TAG_METEO. */
    val piove: Boolean get() = this != ASCIUTTO
}

/**
 * Una fascia oraria. I campi dopo `veto` non esistono nel config: li aggiungono
 * patch_rule (lo strato del giorno) e _con_meteo (il tempo dell'ora), sempre
 * su una copia.
 */
data class Regola(
    val from: String?,
    val to: String?,
    val include: List<String> = emptyList(),
    val exclude: List<String> = emptyList(),
    val match: String = "all",
    val rotate: Int = 60,
    val prefer: List<String> = emptyList(),
    val preferMin: Int? = null,
    val veto: List<String> = emptyList(),
    val seasonExclude: List<String> = emptyList(),
    val seasonal: List<String> = emptyList(),
    val periodo: String? = null,
    val meteo: StatoMeteo? = null,
    val momenti: List<String> = emptyList(),
    val tema: List<String> = emptyList(),
) {
    val matchAny: Boolean get() = match == "any"
}

/** Le fasce di base o quelle proprie di un periodo: feriali, weekend, override. */
data class RegoleCasuali(
    val weekday: List<Regola>?,
    val weekend: List<Regola>?,
    val overrides: Map<String, List<Regola>?>,
    /** `random_rules` assente o `{}`: il periodo non ha fasce proprie. */
    val vuote: Boolean,
)

/** Una stagione o un evento. */
data class Periodo(
    val nome: String,
    val from: String,
    val to: String,
    val tags: List<String>,
    val veto: List<String>,
    val require: List<String>,
    val prefer: List<String>,
    val preferMin: Int,
    val regole: RegoleCasuali,
)

data class Config(
    val basePath: String,
    val pathMap: Map<String, String>,
    /** Nell'ordine del file: conta per i pareggi, come i dict di Python. */
    val libreria: Map<String, List<String>>,
    val regole: RegoleCasuali,
    val stagioni: List<Periodo>,
    val eventi: List<Periodo>,
    val meteoAttivo: Boolean,
    val meteoMinimo: Int,
    private val latitude: JsonElement?,
    private val longitude: JsonElement?,
    private val positionMap: JsonElement?,
) {
    /**
     * Latitudine e longitudine del dispositivo, come sun.coords: position_map
     * sopra latitude/longitude, Napoli se i valori non sono numeri.
     */
    fun coordinate(dispositivo: String): Pair<Double, Double> {
        val voce = (positionMap as? JsonObject)?.get(dispositivo)
        val mappa = when {
            voce == null || !pyBool(voce) -> JsonObject(emptyMap())
            voce is JsonObject -> voce
            else -> return DEFAULT_LAT to DEFAULT_LON
        }
        val lat = pyFloat(mappa["latitude"] ?: latitude ?: JsonPrimitive(DEFAULT_LAT))
        val lon = pyFloat(mappa["longitude"] ?: longitude ?: JsonPrimitive(DEFAULT_LON))
        if (lat == null || lon == null) return DEFAULT_LAT to DEFAULT_LON
        return lat to lon
    }

    /** Tutti i tag dichiarati da stagioni ed eventi: il vocabolario "stagionale". */
    val tagStagionali: Set<String> by lazy {
        (stagioni + eventi).flatMapTo(mutableSetOf()) { it.tags }
    }

    companion object {
        fun leggi(testo: String): Config = da(Json.parseToJsonElement(testo).jsonObject)

        fun da(cfg: JsonObject): Config {
            val meteo = cfg["meteo"]
            val m = if (meteo != null && meteo !is JsonNull) meteo as? JsonObject else null
            return Config(
                basePath = cfg["base_path"]?.let { pyStr(it) } ?: "",
                pathMap = (cfg["path_map"] as? JsonObject)
                    ?.mapValues { pyStr(it.value) } ?: emptyMap(),
                libreria = (cfg["image_library"] as? JsonObject)
                    ?.entries?.associateTo(LinkedHashMap()) { it.key to listaStr(it.value) }
                    ?: LinkedHashMap(),
                regole = regoleCasuali(cfg["random_rules"]),
                stagioni = listaPeriodi(cfg["seasons"]),
                eventi = listaPeriodi(cfg["events"]),
                // ensure_defaults mette {"attivo": true, ...} solo se la chiave manca
                meteoAttivo = if (meteo == null) true else pyBool(m?.get("attivo") ?: JsonPrimitive(true)),
                meteoMinimo = minimoMeteo(m),
                latitude = cfg["latitude"],
                longitude = cfg["longitude"],
                positionMap = cfg["position_map"],
            )
        }

        private fun minimoMeteo(m: JsonObject?): Int {
            val valore = m?.get("minimo") ?: return DEFAULT_MINIMO_METEO
            return maxOf(1, pyIntOf(valore) ?: return DEFAULT_MINIMO_METEO)
        }

        private fun listaPeriodi(e: JsonElement?): List<Periodo> =
            (e as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(::periodo) } ?: emptyList()

        private fun periodo(p: JsonObject) = Periodo(
            nome = p["name"]?.let { pyStr(it) } ?: "?",
            from = p["from"]?.let { pyStr(it) } ?: "",
            to = p["to"]?.let { pyStr(it) } ?: "",
            tags = listaStr(p["tags"]),
            veto = listaStr(p["veto"]),
            require = listaStr(p["require"]),
            prefer = listaStr(p["prefer"]),
            // int(period.get("prefer_min") or 0)
            preferMin = p["prefer_min"]?.takeIf { pyBool(it) }?.let { pyIntOf(it) } ?: 0,
            regole = regoleCasuali(p["random_rules"]),
        )

        private fun regoleCasuali(e: JsonElement?): RegoleCasuali {
            val o = e as? JsonObject
            val overrides = o?.get("overrides") as? JsonObject
            return RegoleCasuali(
                weekday = listaRegole(o?.get("weekday")),
                weekend = listaRegole(o?.get("weekend")),
                overrides = overrides?.mapValues { listaRegole(it.value) } ?: emptyMap(),
                vuote = o == null || o.isEmpty(),
            )
        }

        private fun listaRegole(e: JsonElement?): List<Regola>? =
            (e as? JsonArray)?.mapNotNull { (it as? JsonObject)?.let(::regola) }

        private fun regola(r: JsonObject) = Regola(
            from = r["from"]?.let { pyStr(it) },
            to = r["to"]?.let { pyStr(it) },
            include = listaStr(r["include"]),
            exclude = listaStr(r["exclude"]),
            match = r["match"]?.let { pyStr(it) } ?: "all",
            rotate = rotateDi(r["rotate_minutes"]),
            prefer = listaStr(r["prefer"]),
            preferMin = r["prefer_min"]?.takeIf { it !is JsonNull }?.let { pyIntOf(it) ?: 1 },
            veto = listaStr(r["veto"]),
        )

        /** _rotate_of: int(rotate_minutes), 60 se assente, non valido o minore di 1. */
        private fun rotateDi(e: JsonElement?): Int {
            val r = (e ?: return 60).let { pyIntOf(it) } ?: return 60
            return if (r >= 1) r else 60
        }
    }
}

// ── Conversioni alla Python ─────────────────────────────────────────────────

/** `str(x)` di Python. */
internal fun pyStr(e: JsonElement): String = when (e) {
    is JsonNull -> "None"
    is JsonPrimitive -> when {
        e.isString -> e.content
        e.booleanOrNull != null -> if (e.booleanOrNull == true) "True" else "False"
        else -> e.content
    }
    else -> e.toString()
}

/** `int(x)` di Python, o null dove Python solleverebbe un'eccezione. */
internal fun pyIntOf(e: JsonElement): Int? = when (e) {
    is JsonNull -> null
    is JsonPrimitive -> when {
        e.isString -> pyInt(e.content)
        e.booleanOrNull != null -> if (e.booleanOrNull == true) 1 else 0
        else -> e.content.toIntOrNull() ?: e.content.toDoubleOrNull()?.toInt()
    }
    else -> null
}

/** `float(x)` di Python, o null dove Python solleverebbe un'eccezione. */
internal fun pyFloat(e: JsonElement): Double? = when (e) {
    is JsonNull -> null
    is JsonPrimitive -> when {
        e.booleanOrNull != null && !e.isString -> if (e.booleanOrNull == true) 1.0 else 0.0
        else -> e.content.trim().toDoubleOrNull()
    }
    else -> null
}

/** `bool(x)` di Python. */
internal fun pyBool(e: JsonElement): Boolean = when (e) {
    is JsonNull -> false
    is JsonArray -> e.isNotEmpty()
    is JsonObject -> e.isNotEmpty()
    is JsonPrimitive -> when {
        e.isString -> e.content.isNotEmpty()
        e.booleanOrNull != null -> e.booleanOrNull == true
        else -> (e.content.toDoubleOrNull() ?: 0.0) != 0.0
    }
}

/** `list(x or [])` per una lista di tag. */
private fun listaStr(e: JsonElement?): List<String> =
    (e as? JsonArray)?.map { pyStr(it) } ?: emptyList()
