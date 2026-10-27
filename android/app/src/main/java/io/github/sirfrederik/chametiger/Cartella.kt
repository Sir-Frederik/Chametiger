package io.github.sirfrederik.chametiger

import android.content.Context
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.Sfondo
import java.io.File

// Dove stanno config.json e le immagini sul telefono: la cartella privata
// esterna dell'app (Android/data/<pacchetto>/files). Non servono permessi e dal
// PC si raggiunge via USB. Le chiavi di image_library sono relative a questa
// cartella, come lo sono a base_path sui PC. Li' finisce anche chametiger.log.

fun cartella(context: Context): File =
    requireNotNull(context.getExternalFilesDir(null)) { "Memoria esterna dell'app non disponibile" }

/** Il Ciclo di questo telefono, con l'identita' attuale. Uno nuovo per ogni uso. */
fun ciclo(context: Context, sfondo: Sfondo): Ciclo = Ciclo(
    cartella = cartella(context),
    interna = context.filesDir,
    identita = Identita.leggi(context),
    versione = context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty(),
    sfondo = sfondo,
)
