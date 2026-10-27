package io.github.sirfrederik.chametiger.motore

import java.time.LocalDate

// Le date di stagioni ed eventi, come date_mobili.py: fisse ('12-25') o
// relative alla domenica di Pasqua ('pasqua-5'), confrontate come ordinali MMGG.

internal object DateMobili {
    private val GIORNI_MESE = intArrayOf(31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    private val PASQUA = Regex("""^pasqua\s*(?:([+-])\s*(\d{1,3})\s*g?)?$""", RegexOption.IGNORE_CASE)

    /** La domenica di Pasqua (calendario gregoriano, algoritmo di Meeus). */
    fun pasqua(anno: Int): LocalDate {
        val a = anno % 19
        val b = anno / 100
        val c = anno % 100
        val d = b / 4
        val e = b % 4
        val f = (b + 8) / 25
        val g = (b - f + 1) / 3
        val h = (19 * a + b - d - g + 15) % 30
        val i = c / 4
        val k = c % 4
        val l = (32 + 2 * e + 2 * i - h - k) % 7
        val m = (a + 11 * h + 22 * l) / 451
        val n = h + l - 7 * m + 114
        return LocalDate.of(anno, n / 31, n % 31 + 1)
    }

    /** 'pasqua-5' -> -5, 'pasqua' -> 0; null se la data non e' relativa a Pasqua. */
    fun scostamentoPasqua(s: String): Int? {
        val trovato = PASQUA.find(s.trim()) ?: return null
        val (segno, giorni) = trovato.destructured
        if (giorni.isEmpty()) return 0
        return if (segno == "-") -giorni.toInt() else giorni.toInt()
    }

    /** '10-20' -> (10, 20). Accetta anche 'AAAA-MM-GG', ignorando l'anno. */
    private fun fissa(s: String): Pair<Int, Int>? {
        var pezzi = s.trim().split("-")
        if (pezzi.size == 3) pezzi = pezzi.drop(1)
        if (pezzi.size != 2) return null
        val mese = pyInt(pezzi[0]) ?: return null
        val giorno = pyInt(pezzi[1]) ?: return null
        if (mese !in 1..12 || giorno < 1 || giorno > GIORNI_MESE[mese - 1]) return null
        return mese to giorno
    }

    /** La data come ordinale MMGG in quell'anno: '10-20' -> 1020, 'pasqua' -> 405 nel 2026. */
    fun ordinale(s: String, anno: Int): Int? {
        scostamentoPasqua(s)?.let { delta ->
            val g = pasqua(anno).plusDays(delta.toLong())
            return g.monthValue * 100 + g.dayOfMonth
        }
        val (mese, giorno) = fissa(s) ?: return null
        return mese * 100 + giorno
    }
}
