package io.github.sirfrederik.chametiger.motore

// Le poche operazioni in cui Kotlin e Python danno risultati diversi. La
// specifica e' il Python: qui si riproduce il suo comportamento, non quello
// della JVM.

/** `x % y` di Python sui float: il risultato ha il segno del divisore. */
internal fun pyMod(x: Double, y: Double): Double {
    val mod = x % y // fmod, come in C
    if (mod == 0.0) return Math.copySign(0.0, y)
    return if ((y < 0) != (mod < 0)) mod + y else mod
}

/** `x // y` di Python sui float, con le stesse correzioni di float_floor_div. */
internal fun pyFloorDiv(x: Double, y: Double): Double {
    var mod = x % y
    var div = (x - mod) / y
    if (mod != 0.0) {
        if ((y < 0) != (mod < 0)) {
            mod += y
            div -= 1.0
        }
    }
    if (div == 0.0) return Math.copySign(0.0, x / y)
    var floordiv = Math.floor(div)
    if (div - floordiv > 0.5) floordiv += 1.0
    return floordiv
}

/**
 * L'ordine di `sorted()` sulle stringhe: per code point. Il compareTo di Kotlin
 * confronta unita' UTF-16, e i due divergono sui caratteri fuori dal piano base.
 */
internal val perCodePoint: Comparator<String> = Comparator { a, b ->
    var i = 0
    var j = 0
    while (i < a.length && j < b.length) {
        val ca = a.codePointAt(i)
        val cb = b.codePointAt(j)
        if (ca != cb) return@Comparator ca.compareTo(cb)
        i += Character.charCount(ca)
        j += Character.charCount(cb)
    }
    (a.length - i).compareTo(b.length - j)
}

internal fun Iterable<String>.ordinate(): List<String> = sortedWith(perCodePoint)

/** `int(s)` di Python sulle stringhe semplici: spazi ai lati e segno ammessi. */
internal fun pyInt(s: String): Int? = s.trim().toIntOrNull()
