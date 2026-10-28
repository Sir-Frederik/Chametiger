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
    fun leggi(context: Context): String = preferenze(context).getString("identita", "").orEmpty()

    fun scrivi(context: Context, identita: String) {
        preferenze(context).edit().putString("identita", identita.trim()).apply()
    }
}

/**
 * La cartella Drive da cui arrivano config e immagini, e il tetto della cache.
 * Senza link (o senza chiave API nella build) valgono solo i file copiati via
 * USB, come prima.
 */
object ImpostazioniDrive {
    const val TETTO_MB_DEFAULT = 300

    fun link(context: Context): String = preferenze(context).getString("drive_link", "").orEmpty()

    fun scriviLink(context: Context, link: String) {
        preferenze(context).edit().putString("drive_link", link.trim()).apply()
    }

    fun tettoMb(context: Context): Int = preferenze(context).getInt("tetto_mb", TETTO_MB_DEFAULT)

    fun scriviTettoMb(context: Context, mb: Int) {
        preferenze(context).edit().putInt("tetto_mb", mb.coerceAtLeast(10)).apply()
    }
}

/**
 * Il velo scuro steso sopra lo sfondo, in percentuale: da' piu' contrasto a
 * icone e testi. Riguarda solo come si mostra l'immagine, non quale esce, e il
 * file in cache resta l'originale.
 */
object ImpostazioniSfondo {
    const val VELO_MAX = 60

    fun velo(context: Context): Int = preferenze(context).getInt("velo", 0)

    fun scriviVelo(context: Context, percento: Int) {
        preferenze(context).edit().putInt("velo", percento.coerceIn(0, VELO_MAX)).apply()
    }
}

private fun preferenze(context: Context) = context.getSharedPreferences("impostazioni", Context.MODE_PRIVATE)
