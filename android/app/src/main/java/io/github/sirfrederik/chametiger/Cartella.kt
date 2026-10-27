package io.github.sirfrederik.chametiger

import android.content.Context
import io.github.sirfrederik.chametiger.motore.Config
import java.io.File
import java.time.ZoneId

// Dove stanno config.json e le immagini sul telefono: la cartella privata
// esterna dell'app (Android/data/<pacchetto>/files). Non servono permessi e dal
// PC si raggiunge via USB. Le chiavi di image_library sono relative a questa
// cartella, come lo sono a base_path sui PC.

/**
 * Il fuso dei PC. L'ora "adesso" e gli orari solari si calcolano qui anche se
 * il telefono e' altrove: come le coordinate, un fuso locale diverso
 * sposterebbe i confini delle fasce e romperebbe l'allineamento.
 */
val ZONA: ZoneId = ZoneId.of("Europe/Rome")

const val NOME_CONFIG = "config.json"

fun cartella(context: Context): File =
    requireNotNull(context.getExternalFilesDir(null)) { "Memoria esterna dell'app non disponibile" }

/** Il config letto, o il motivo per cui non si puo' usare. */
sealed interface LetturaConfig {
    data class Letto(val config: Config) : LetturaConfig
    data class Errore(val messaggio: String) : LetturaConfig
}

fun leggiConfig(cartella: File): LetturaConfig {
    val file = File(cartella, NOME_CONFIG)
    if (!file.exists()) return LetturaConfig.Errore("Manca ${file.path}")
    return try {
        val config = Config.leggi(file.readText(Charsets.UTF_8))
        if (config.libreria.isEmpty()) LetturaConfig.Errore("$NOME_CONFIG senza image_library")
        else LetturaConfig.Letto(config)
    } catch (e: Exception) {
        LetturaConfig.Errore("$NOME_CONFIG non leggibile: ${e.message}")
    }
}
