package io.github.sirfrederik.chametiger.strato

import java.io.File
import java.time.LocalDate

/**
 * Un'estrazione forzata: vale per la finestra in cui e' stata fatta, con le
 * stesse chiavi del memo di log.json (giorno, firma, ordinale). A mezzanotte
 * il giorno cambia e finisce, come sul PC. Vale solo per questo dispositivo.
 */
data class Forzata(val giorno: LocalDate, val firma: String, val ordinale: Int, val immagine: String)

interface MemoriaForzata {
    fun leggi(): Forzata?
    fun scrivi(forzata: Forzata?)
}

/** Una riga sola, separata da tabulazioni: la firma non ne contiene. */
class MemoriaForzataFile(private val file: File) : MemoriaForzata {

    override fun leggi(): Forzata? = try {
        val c = file.readText(Charsets.UTF_8).trimEnd('\n').split("\t")
        Forzata(LocalDate.parse(c[0]), c[2], c[1].toInt(), c[3])
    } catch (e: Exception) {
        null // assente o rovinata: nessuna forzata, si torna alla sequenza
    }

    override fun scrivi(forzata: Forzata?) {
        if (forzata == null) {
            file.delete()
            return
        }
        scriviIntero(file, "${forzata.giorno}\t${forzata.ordinale}\t${forzata.firma}\t${forzata.immagine}\n")
    }
}

/** Prima un file accanto, poi lo scambio: un'interruzione non lascia il file a meta'. */
internal fun scriviIntero(file: File, testo: String) = scriviIntero(file, testo.toByteArray(Charsets.UTF_8))

internal fun scriviIntero(file: File, byte: ByteArray) {
    file.parentFile?.mkdirs()
    val tmp = File(file.path + ".tmp")
    tmp.writeBytes(byte)
    if (!tmp.renameTo(file)) {
        file.delete()
        check(tmp.renameTo(file)) { "Impossibile scrivere ${file.path}" }
    }
}
