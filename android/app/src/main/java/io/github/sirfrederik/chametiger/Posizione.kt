package io.github.sirfrederik.chametiger

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.SystemClock
import androidx.core.content.ContextCompat
import androidx.core.location.LocationListenerCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.location.LocationRequestCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

// La posizione del telefono, chiesta col pulsante "Carica meteo" con
// l'app aperta: vale per il meteo e per alba e tramonto. Il lavoro in
// background la chiede solo prima di riscaricare il meteo, e solo col
// permesso "consenti sempre" (vedi LavoroSfondo); se non arriva, l'ultima salvata.
//
// Si chiede a tutti i fornitori accesi insieme e vince il primo che risponde:
// sul Redmi (MIUI, Android 11) il solo "network" spesso non rispondeva, e il
// pulsante ripiegava sulla posizione salvata anche col permesso concesso.

private const val ATTESA_MS = 30_000L
/** Una posizione che Android ha gia' e piu' recente di cosi' si usa senza chiederne un'altra. */
private const val FRESCA_MS = 5 * 60_000L
/** Se nessun fornitore risponde, va ancora bene una posizione nota di non piu' di cosi'. */
private const val RECENTE_MS = 60 * 60_000L

val PERMESSI_POSIZIONE = arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)

private fun concesso(context: Context, permesso: String) =
    ContextCompat.checkSelfPermission(context, permesso) == PackageManager.PERMISSION_GRANTED

/** Almeno quella approssimativa: con la sola approssimativa il GPS resta escluso. */
fun permessoPosizione(context: Context): Boolean =
    PERMESSI_POSIZIONE.any { concesso(context, it) }

/**
 * "Consenti sempre": senza, dal lavoro in background Android non da' la
 * posizione, ne' nuova ne' l'ultima nota. Sotto Android 10 non esiste e basta
 * l'altra.
 */
fun permessoSempre(context: Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
        concesso(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION)

/** Quella precisa, col GPS. Se manca il pulsante la richiede: dopo due rifiuti Android non chiede piu'. */
fun permessoGps(context: Context): Boolean = concesso(context, Manifest.permission.ACCESS_FINE_LOCATION)

/**
 * Una posizione del telefono, o null: niente permesso, localizzazione spenta,
 * nessuna risposta entro ATTESA_MS e nessuna posizione nota dell'ultima ora.
 */
suspend fun posizioneAttuale(context: Context): Location? {
    if (!permessoPosizione(context)) return null
    val lm = context.getSystemService(LocationManager::class.java) ?: return null
    if (!LocationManagerCompat.isLocationEnabled(lm)) return null
    val fornitori = lm.getProviders(true).filter {
        it != LocationManager.PASSIVE_PROVIDER &&
            (it != LocationManager.GPS_PROVIDER || concesso(context, Manifest.permission.ACCESS_FINE_LOCATION))
    }
    val nota = ultimaNota(lm, fornitori)
    if (nota != null && eta(nota) <= FRESCA_MS) return nota
    return withTimeoutOrNull(ATTESA_MS) { primaRisposta(context, lm, fornitori) }
        ?: nota?.takeIf { eta(it) <= RECENTE_MS }
}

private fun eta(l: Location): Long = (SystemClock.elapsedRealtimeNanos() - l.elapsedRealtimeNanos) / 1_000_000

/** La piu' recente fra quelle che i fornitori hanno gia'. */
private fun ultimaNota(lm: LocationManager, fornitori: List<String>): Location? =
    fornitori.mapNotNull {
        try {
            lm.getLastKnownLocation(it)
        } catch (e: SecurityException) {
            null
        }
    }.maxByOrNull { it.elapsedRealtimeNanos }

/**
 * La prima posizione nuova da uno qualunque dei fornitori; non ritorna finche'
 * non ne arriva una, il limite lo mette chi chiama. Richieste esplicite tolte
 * con removeUpdates: su MIUI getCurrentLocation ignorava sia l'annullamento
 * sia la scadenza, e la richiesta del GPS restava attiva per minuti.
 */
@SuppressLint("MissingPermission") // il permesso lo controlla posizioneAttuale; la richiesta gestisce SecurityException
private suspend fun primaRisposta(context: Context, lm: LocationManager, fornitori: List<String>): Location? {
    val ascoltatori = mutableListOf<LocationListenerCompat>()
    try {
        return suspendCancellableCoroutine { cont ->
            val richiesta = LocationRequestCompat.Builder(0L).build()
            // Le risposte arrivano tutte sul thread principale, come questo blocco
            val esecutore = ContextCompat.getMainExecutor(context)
            for (f in fornitori) {
                val ascoltatore = LocationListenerCompat { if (cont.isActive) cont.resume(it) }
                try {
                    LocationManagerCompat.requestLocationUpdates(lm, f, richiesta, esecutore, ascoltatore)
                    ascoltatori += ascoltatore
                } catch (e: SecurityException) {
                    // permesso tolto nel frattempo, o in background senza "consenti sempre"
                } catch (e: Exception) {
                    // fornitore sparito nel frattempo
                }
            }
            if (ascoltatori.isEmpty()) cont.resume(null)
        }
    } finally {
        ascoltatori.forEach { LocationManagerCompat.removeUpdates(lm, it) }
    }
}
