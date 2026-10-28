package io.github.sirfrederik.chametiger.strato

import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Il log testuale del telefono, come chametiger.log dei PC: stesso formato di
 * riga, cosi' i due si confrontano quando i dispositivi non sono allineati.
 */
interface Diario {
    fun scrivi(messaggio: String)
}

class DiarioFile(
    private val file: File,
    private val orologio: () -> LocalDateTime = { LocalDateTime.now(ZONA) },
) : Diario {

    override fun scrivi(messaggio: String) {
        val riga = "[${orologio().format(ISTANTE)}] $messaggio"
        try {
            // Come log() di app.py: oltre la soglia si tiene la seconda meta'
            if (file.length() > MAX_BYTES) {
                val vecchio = file.readText(Charsets.UTF_8)
                file.writeText(vecchio.takeLast(MAX_BYTES / 2), Charsets.UTF_8)
            }
            file.appendText(riga + "\n", Charsets.UTF_8)
        } catch (e: Exception) {
            // Un log che non si scrive non deve fermare lo sfondo
        }
    }

    companion object {
        const val MAX_BYTES = 200_000
        private val ISTANTE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
    }
}
