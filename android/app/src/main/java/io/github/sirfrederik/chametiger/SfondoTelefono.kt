package io.github.sirfrederik.chametiger

import android.app.WallpaperManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import io.github.sirfrederik.chametiger.strato.Sfondo
import java.io.File

/**
 * Lo sfondo della schermata principale (FLAG_SYSTEM). Il blocco schermo resta
 * com'e': lo decidiamo dopo.
 *
 * Ricorda l'immagine applicata e l'id che WallpaperManager le ha dato. Se lo
 * sfondo e' cambiato da fuori l'id non coincide piu', e il giro dopo rimette
 * quello giusto. Ricorda anche il velo scuro: cambiandolo, la stessa immagine
 * si rimette col velo nuovo.
 */
class SfondoTelefono(context: Context) : Sfondo {
    private val gestore = WallpaperManager.getInstance(context)
    private val memoria = context.getSharedPreferences("sfondo", Context.MODE_PRIVATE)
    private val schermo = context.resources.displayMetrics
    private val velo = ImpostazioniSfondo.velo(context)

    override fun giaMostrata(immagine: String): Boolean =
        memoria.getString(IMMAGINE, null) == immagine &&
            memoria.getInt(VELO, 0) == velo &&
            memoria.getInt(ID, ID_NESSUNO) == gestore.getWallpaperId(WallpaperManager.FLAG_SYSTEM)

    override fun applica(file: File, immagine: String) {
        val bitmap = decodifica(file)
        try {
            // Il velo: nero semitrasparente sopra l'immagine, solo qui e non sul file
            if (velo > 0) Canvas(bitmap).drawColor(Color.argb(velo * 255 / 100, 0, 0, 0))
            val id = gestore.setBitmap(bitmap, null, true, WallpaperManager.FLAG_SYSTEM)
            check(id != 0) { "WallpaperManager ha rifiutato lo sfondo" }
            memoria.edit().putString(IMMAGINE, immagine).putInt(ID, id).putInt(VELO, velo).apply()
        } finally {
            bitmap.recycle()
        }
    }

    /**
     * Le immagini sono sfondi da desktop: a piena risoluzione possono esaurire
     * la memoria. Si legge solo la misura, poi si decodifica con il campionamento
     * piu' grosso che copre ancora lo schermo in entrambe le direzioni, senza
     * ingrandire: il sistema poi ritaglia al centro.
     */
    private fun decodifica(file: File): Bitmap {
        val misura = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, misura)
        require(misura.outWidth > 0 && misura.outHeight > 0) { "Non e' un'immagine leggibile: ${file.path}" }

        // Lo schermo in verticale, o di piu' se il launcher chiede uno sfondo largo
        val larghezza = maxOf(minOf(schermo.widthPixels, schermo.heightPixels), gestore.desiredMinimumWidth)
        val altezza = maxOf(maxOf(schermo.widthPixels, schermo.heightPixels), gestore.desiredMinimumHeight)
        var campione = 1
        while (misura.outWidth / (campione * 2) >= larghezza && misura.outHeight / (campione * 2) >= altezza) {
            campione *= 2
        }

        // Modificabile, per poterci stendere sopra il velo
        val opzioni = BitmapFactory.Options().apply {
            inSampleSize = campione
            inMutable = true
        }
        return requireNotNull(BitmapFactory.decodeFile(file.path, opzioni)) { "Decodifica fallita: ${file.path}" }
    }

    companion object {
        private const val IMMAGINE = "immagine"
        private const val ID = "id"
        private const val VELO = "velo"
        private const val ID_NESSUNO = Int.MIN_VALUE
    }
}
