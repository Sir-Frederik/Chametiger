package io.github.sirfrederik.chametiger.strato

import io.github.sirfrederik.chametiger.motore.Config
import io.github.sirfrederik.chametiger.motore.risolviSu
import java.io.File

/**
 * Le immagini presenti sul dispositivo. Il motore non lo chiede mai: il pool
 * viene dalle chiavi di image_library. Serve solo a chi deve mostrarle.
 */
interface Archivio {
    fun file(chiave: String): File
    fun esiste(chiave: String): Boolean
}

/** Le immagini nella cartella dell'app, con le chiavi relative a lei come a base_path sui PC. */
class ArchivioCartella(private val config: Config, private val cartella: File) : Archivio {
    override fun file(chiave: String): File = File(risolviSu(config, cartella.path, chiave))
    override fun esiste(chiave: String): Boolean = file(chiave).isFile
}
