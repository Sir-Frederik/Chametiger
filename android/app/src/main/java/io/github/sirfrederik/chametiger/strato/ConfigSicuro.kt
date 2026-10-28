package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import java.io.File
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.security.MessageDigest

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
        /**
         * `avviso` non nullo: il principale non si legge, questo e' l'ultimo
         * buono. `impronta`: le prime cifre dello SHA-256 dei byte del config
         * usato, le stesse che il tray scrive nel suo log.
         */
        data class Ok(val config: Config, val avviso: String?, val impronta: String) : Lettura
        data class Nessuna(val motivo: String) : Lettura
    }

    fun leggi(): Lettura {
        val motivo = try {
            val byte = principale.readBytes()
            val config = valida(byte)
            if (!copia.exists() || !copia.readBytes().contentEquals(byte)) scriviIntero(copia, byte)
            return Lettura.Ok(config, null, impronta(byte))
        } catch (e: Exception) {
            "${principale.name} non leggibile: ${e.message ?: e.javaClass.simpleName}"
        }

        return try {
            val byte = copia.readBytes()
            Lettura.Ok(valida(byte), motivo, impronta(byte))
        } catch (e: Exception) {
            Lettura.Nessuna("$motivo, e non c'e' una configurazione precedente")
        }
    }

    companion object {
        /** Come leggi_config di posizione_config.py: un config senza queste non e' un config. */
        fun valida(byte: ByteArray): Config {
            // Come open(..., encoding="utf-8"): un byte non UTF-8 rende il file illeggibile
            val testo = Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(byte)).toString()
            val config = Config.leggi(testo)
            require(config.libreria.isNotEmpty()) { "manca o e' vuota image_library" }
            require(!config.regole.vuote) { "manca o e' vuota random_rules" }
            return config
        }

        /** Le prime cifre dello SHA-256 dei byte del config, come impronta_config di posizione_config.py. */
        fun impronta(byte: ByteArray): String =
            MessageDigest.getInstance("SHA-256").digest(byte).joinToString("") { "%02x".format(it) }.take(CIFRE_IMPRONTA)

        const val CIFRE_IMPRONTA = 8
    }
}
