package io.github.sirfrederik.chametiger

import android.content.Context

/**
 * L'identita' del dispositivo: la chiave con cui il telefono si cerca in
 * position_map, come l'hostname per i PC. Si imposta a mano e non si ricava
 * mai da Build.MODEL o simili: se cambiasse dopo un aggiornamento di sistema
 * non sarebbe piu' nel config, e il telefono passerebbe alle coordinate di
 * default senza una ragione visibile.
 */
object Identita {
    private const val FILE = "impostazioni"
    private const val CHIAVE = "identita"

    fun leggi(context: Context): String =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(CHIAVE, "").orEmpty()

    fun scrivi(context: Context, identita: String) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putString(CHIAVE, identita.trim())
            .apply()
    }
}
