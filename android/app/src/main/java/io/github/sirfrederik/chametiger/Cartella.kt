package io.github.sirfrederik.chametiger

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Build
import io.github.sirfrederik.chametiger.strato.ApiDriveHttp
import io.github.sirfrederik.chametiger.strato.CartellaDrive
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.Diario
import io.github.sirfrederik.chametiger.strato.Sfondo
import io.github.sirfrederik.chametiger.strato.Sincro
import java.io.File
import java.security.MessageDigest

// Dove stanno config.json e le immagini sul telefono: la cartella privata
// esterna dell'app (Android/data/<pacchetto>/files). Non servono permessi e dal
// PC si raggiunge via USB. Le chiavi di image_library sono relative a questa
// cartella, come lo sono a base_path sui PC. Li' finisce anche chametiger.log,
// ed e' anche la cache delle immagini scaricate da Drive.

fun cartella(context: Context): File =
    requireNotNull(context.getExternalFilesDir(null)) { "Memoria esterna dell'app non disponibile" }

/** Il Ciclo di questo telefono, con l'identita' e la cartella Drive attuali. Uno nuovo per ogni uso. */
fun ciclo(context: Context, sfondo: Sfondo): Ciclo {
    val versione = context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty()
    return Ciclo(
        cartella = cartella(context),
        interna = context.filesDir,
        identita = Identita.leggi(context),
        versione = versione,
        sfondo = sfondo,
        drive = drive(context),
    )
}

/** Come raggiungere Drive, o null senza chiave nella build o senza link nelle impostazioni. */
private fun drive(context: Context): ((Diario) -> Sincro)? {
    val chiave = BuildConfig.DRIVE_API_KEY.takeIf { it.isNotBlank() } ?: return null
    val cartellaDrive = CartellaDrive.daLink(ImpostazioniDrive.link(context)) ?: return null
    val api = ApiDriveHttp(chiave, context.packageName, certificato(context))
    val tetto = ImpostazioniDrive.tettoMb(context).toLong() * 1024 * 1024
    return { diario ->
        Sincro(
            api, cartellaDrive, cartella(context), context.filesDir, diario,
            orologio = { System.currentTimeMillis() / 1000.0 },
            tettoByte = tetto,
            verifica = ::siDecodifica,
        )
    }
}

/** Se il file e' un'immagine: basta leggerne la misura, senza decodificarla tutta. */
private fun siDecodifica(file: File): Boolean {
    val misura = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.path, misura)
    return misura.outWidth > 0 && misura.outHeight > 0
}

/**
 * Lo SHA-1 del certificato con cui e' firmata l'app, come lo vuole
 * X-Android-Cert: esadecimale maiuscolo senza i due punti. E' quello che
 * Google confronta con la restrizione per app Android della chiave.
 */
@Suppress("DEPRECATION")
private fun certificato(context: Context): String {
    val pm = context.packageManager
    val firme = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        pm.getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
            ?.apkContentsSigners.orEmpty()
    } else {
        pm.getPackageInfo(context.packageName, PackageManager.GET_SIGNATURES).signatures.orEmpty()
    }
    val firma = firme.firstOrNull() ?: return ""
    return MessageDigest.getInstance("SHA-1").digest(firma.toByteArray()).joinToString("") { "%02X".format(it) }
}
