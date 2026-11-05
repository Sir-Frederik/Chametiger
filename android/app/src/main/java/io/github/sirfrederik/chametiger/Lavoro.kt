package io.github.sirfrederik.chametiger

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.DiarioFile
import kotlinx.coroutines.runBlocking
import java.io.File
import java.util.Locale
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
        val contesto = applicationContext
        val diario = DiarioFile(File(cartella(contesto), Ciclo.NOME_LOG))
        try {
            // Prima di riscaricare il meteo, la posizione di adesso: il Ciclo
            // si costruisce dopo, cosi' meteo e sole la usano gia' in questo giro
            if (ciclo(contesto, SfondoTelefono(contesto)).meteoDaAggiornare()) aggiornaPosizione(contesto, diario)
            ciclo(contesto, SfondoTelefono(contesto)).giro()
        } catch (e: Exception) {
            // Mai un nuovo tentativo a raffica: il prossimo giro arriva comunque
            diario.scrivi("[ERR] Giro: $e")
        }
        return Result.success()
    }

    /**
     * La posizione del telefono, nuova o l'ultima che Android conosce
     * dell'ultima ora, salvata come quella del pulsante Carica meteo. Se non
     * arriva resta quella salvata prima, o le coordinate del config.
     */
    private fun aggiornaPosizione(context: Context, diario: DiarioFile) {
        if (!permessoPosizione(context)) return
        if (!permessoSempre(context)) {
            diario.scrivi("[METEO] Posizione non letta in background: manca il permesso \"consenti sempre\", uso l'ultima salvata.")
            return
        }
        val fix = runBlocking { posizioneAttuale(context) }
        if (fix == null) {
            diario.scrivi("[METEO] Posizione del telefono non disponibile: uso l'ultima salvata.")
            return
        }
        PosizioneTelefono.scrivi(context, fix.latitude, fix.longitude, fix.time)
        diario.scrivi("[METEO] Posizione del telefono aggiornata in background: %.4f, %.4f.".format(Locale.ROOT, fix.latitude, fix.longitude))
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
