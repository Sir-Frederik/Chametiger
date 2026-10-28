package io.github.sirfrederik.chametiger

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.DiarioFile
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Un giro ogni 15 minuti, il minimo che WorkManager consente. Non si tenta di
 * avvicinarsi ai 5 di check_interval_minutes: la decisione dipende
 * dall'orologio e non dalla storia, quindi un risveglio in ritardo mostra
 * l'immagine giusta qualche minuto dopo, mai quella sbagliata.
 *
 * WorkManager ricorda il lavoro anche dopo un riavvio del telefono.
 */
class LavoroSfondo(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        try {
            ciclo(applicationContext, SfondoTelefono(applicationContext)).giro()
        } catch (e: Exception) {
            // Mai un nuovo tentativo a raffica: il prossimo giro arriva comunque
            DiarioFile(File(cartella(applicationContext), Ciclo.NOME_LOG)).scrivi("[ERR] Giro: $e")
        }
        return Result.success()
    }

    companion object {
        private const val NOME = "sfondo"

        /** Idempotente: se il lavoro c'e' gia' lo lascia com'e', con i suoi tempi. */
        fun programma(context: Context) {
            val richiesta = PeriodicWorkRequestBuilder<LavoroSfondo>(15, TimeUnit.MINUTES).build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(NOME, ExistingPeriodicWorkPolicy.KEEP, richiesta)
        }
    }
}
