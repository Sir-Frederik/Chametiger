package io.github.sirfrederik.chametiger

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

// La posizione del telefono per il meteo, chiesta solo col pulsante "Carica
// meteo" e con l'app aperta. Basta quella approssimativa: le previsioni stanno
// su una griglia di 0,01 gradi, circa un chilometro. Il lavoro in background
// usa l'ultima salvata e non chiede mai la posizione.

private const val ATTESA_MS = 20_000L

fun permessoPosizione(context: Context): Boolean =
    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
        PackageManager.PERMISSION_GRANTED

/** Una posizione fresca, o null: niente permesso, localizzazione spenta, nessuna risposta entro ATTESA_MS. */
suspend fun posizioneAttuale(context: Context): Location? {
    if (!permessoPosizione(context)) return null
    val lm = context.getSystemService(LocationManager::class.java) ?: return null
    if (!LocationManagerCompat.isLocationEnabled(lm)) return null
    // Col solo permesso approssimativo il GPS non si puo' chiedere
    val candidati = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        listOf(LocationManager.FUSED_PROVIDER, LocationManager.NETWORK_PROVIDER)
    } else {
        listOf(LocationManager.NETWORK_PROVIDER)
    }
    val fornitore = candidati.firstOrNull { lm.isProviderEnabled(it) } ?: return null
    return withTimeoutOrNull(ATTESA_MS) {
        suspendCancellableCoroutine { cont ->
            val annulla = CancellationSignal()
            cont.invokeOnCancellation { annulla.cancel() }
            LocationManagerCompat.getCurrentLocation(lm, fornitore, annulla, ContextCompat.getMainExecutor(context)) {
                if (cont.isActive) cont.resume(it)
            }
        }
    }
}
