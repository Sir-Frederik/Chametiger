package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import java.io.File

/**
 * config.json letto come lo legge il tray: mai vuoto o a meta'. Se non si
 * legge (assente, troncato da una copia interrotta, non JSON, senza
 * image_library o random_rules) si continua con l'ultimo letto con successo.
 *
 * Il lavoro periodico riparte da zero a ogni risveglio, quindi l'ultimo
 * buono non puo' restare in memoria come sul PC: e' una copia nella memoria
 * interna dell'app, rinnovata a ogni lettura riuscita. Non la si modifica mai
 * a mano, e non la legge nessun altro.
 */
class ConfigSicuro(private val principale: File, private val copia: File) {

    sealed interface Lettura {
        /** `avviso` non nullo: il principale non si legge, questo e' l'ultimo buono. */
        data class Ok(val config: Config, val avviso: String?) : Lettura
        data class Nessuna(val motivo: String) : Lettura
    }

    fun leggi(): Lettura {
        val motivo = try {
            val testo = principale.readText(Charsets.UTF_8)
            val config = valida(testo)
            if (!copia.exists() || copia.readText(Charsets.UTF_8) != testo) scriviIntero(copia, testo)
            return Lettura.Ok(config, null)
        } catch (e: Exception) {
            "${principale.name} non leggibile: ${e.message ?: e.javaClass.simpleName}"
        }

        val ultimo = try {
            valida(copia.readText(Charsets.UTF_8))
        } catch (e: Exception) {
            return Lettura.Nessuna("$motivo, e non c'e' una configurazione precedente")
        }
        return Lettura.Ok(ultimo, motivo)
    }

    companion object {
        /** Come leggi_config di posizione_config.py: un config senza queste non e' un config. */
        fun valida(testo: String): Config {
            val config = Config.leggi(testo)
            require(config.libreria.isNotEmpty()) { "manca o e' vuota image_library" }
            require(!config.regole.vuote) { "manca o e' vuota random_rules" }
            return config
        }
    }
}
