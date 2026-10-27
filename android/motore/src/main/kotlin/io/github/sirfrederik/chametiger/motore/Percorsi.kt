package io.github.sirfrederik.chametiger.motore

// Dove sta l'immagine su questo dispositivo, come resolve_path di app.py: le
// chiavi della libreria sono relative a base_path, e path_map la sostituisce
// per dispositivo. Il percorso si separa sempre con '/', anche dove il Python
// su Windows mette '\'.

/** True per /percorso, C:/percorso e \\server/share, su qualunque sistema. */
fun percorsoAssoluto(p: String): Boolean {
    val s = p.replace("\\", "/")
    return s.startsWith("/") || (s.length > 1 && s[1] == ':')
}

/**
 * Il percorso dell'immagine su `dispositivo`:
 *  - relativo: concatenato alla cartella base del dispositivo
 *  - assoluto: rimappato sulla cartella base del dispositivo se inizia con una
 *    delle basi conosciute, altrimenti lasciato com'e'
 */
fun risolviPercorso(config: Config, dispositivo: String, immagine: String): String {
    val base = config.pathMap[dispositivo] ?: config.basePath
    if (!percorsoAssoluto(immagine)) return unisci(base, immagine)

    val normalizzato = immagine.replace("\\", "/")
    val conosciute = listOf(config.basePath) + config.pathMap.values
    for (kb in conosciute) {
        if (kb.isEmpty()) continue
        val kbNorm = kb.replace("\\", "/").trimEnd('/') + "/"
        if (normalizzato.lowercase().startsWith(kbNorm.lowercase())) {
            return unisci(base, normalizzato.substring(kbNorm.length))
        }
    }
    return immagine
}

private fun unisci(base: String, relativo: String): String {
    val r = relativo.replace("\\", "/")
    if (base.isEmpty()) return r
    return base.replace("\\", "/").trimEnd('/') + "/" + r.trimStart('/')
}
