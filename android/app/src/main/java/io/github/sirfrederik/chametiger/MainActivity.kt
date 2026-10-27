package io.github.sirfrederik.chametiger

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import io.github.sirfrederik.chametiger.ui.theme.ChametigerMobileTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.io.File
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ChametigerMobileTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    SchermataAnteprima(Modifier.padding(innerPadding))
                }
            }
        }
    }
}

/** Il risultato di un calcolo: l'anteprima o il motivo per cui non c'e'. */
private sealed interface Stato {
    data object InCorso : Stato
    data class Pronta(val anteprima: Anteprima) : Stato
    data class Errore(val messaggio: String) : Stato
}

@Composable
private fun SchermataAnteprima(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val cartella = remember { cartella(context) }
    var identita by remember { mutableStateOf(Identita.leggi(context)) }
    var bozza by remember { mutableStateOf(identita) }
    var giro by remember { mutableIntStateOf(0) }
    var stato by remember { mutableStateOf<Stato>(Stato.InCorso) }

    // Ricalcola a ogni minuto e quando cambia l'identita'. Il config si rilegge
    // ogni volta: si aggiorna copiandolo via USB.
    LaunchedEffect(identita, giro) {
        while (true) {
            stato = withContext(Dispatchers.Default) { calcola(cartella, identita) }
            val adesso = LocalDateTime.now(ZONA)
            delay(ChronoUnit.MILLIS.between(adesso, adesso.truncatedTo(ChronoUnit.MINUTES).plusMinutes(1)) + 50)
        }
    }

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Chametiger", style = MaterialTheme.typography.headlineSmall)

        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = bozza,
                onValueChange = { bozza = it },
                label = { Text("Identità del dispositivo") },
                placeholder = { Text("android-federico") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            Button(
                onClick = {
                    Identita.scrivi(context, bozza)
                    identita = Identita.leggi(context)
                    bozza = identita
                },
                enabled = bozza.trim() != identita,
                modifier = Modifier.padding(start = 8.dp),
            ) { Text("Salva") }
        }

        Text("Cartella: ${cartella.path}", style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
        HorizontalDivider()

        when (val s = stato) {
            Stato.InCorso -> Text("Calcolo in corso…")
            is Stato.Errore -> Text(s.messaggio, color = MaterialTheme.colorScheme.error)
            is Stato.Pronta -> Dettagli(s.anteprima)
        }

        Button(onClick = { giro++ }) { Text("Ricalcola") }
    }
}

private fun calcola(cartella: File, identita: String): Stato {
    if (identita.isBlank()) return Stato.Errore("Imposta l'identità del dispositivo, per esempio android-federico.")
    return when (val lettura = leggiConfig(cartella)) {
        is LetturaConfig.Errore -> Stato.Errore(lettura.messaggio)
        is LetturaConfig.Letto -> try {
            Stato.Pronta(calcolaAnteprima(lettura.config, identita, LocalDateTime.now(ZONA), cartella))
        } catch (e: Exception) {
            Stato.Errore("Errore nel motore: $e")
        }
    }
}

private val DATA_ORA = DateTimeFormatter.ofPattern("EEEE d/M/yyyy HH:mm", Locale.ITALIAN)

@Composable
private fun Dettagli(a: Anteprima) {
    Voce("Adesso", "${a.adesso.format(DATA_ORA)} (${ZONA.id})")
    if (ZoneId.systemDefault() != ZONA) {
        Voce("Fuso del telefono", "${ZoneId.systemDefault().id}: ignorato, vale ${ZONA.id} come sui PC")
    }
    Voce(
        "Coordinate",
        "%.4f, %.4f ".format(Locale.ROOT, a.lat, a.lon) +
            if (a.inPositionMap) "(position_map di ${a.identita})"
            else "(${a.identita} non è in position_map: latitude/longitude del config)",
    )
    Voce("Pila del giorno", a.pila)
    Voce("Sole", a.orariSolari.joinToString("  ") { (nome, ora) -> "$nome $ora" })
    if (a.meteoAttivo) Voce("Meteo", "fisso su asciutto: allineato coi PC solo nelle ore senza pioggia")
    HorizontalDivider()

    val s = a.scelta
    if (s == null) {
        Text("Nessuna regola copre questo istante: lo sfondo resterebbe quello che c'è.")
        return
    }
    Voce("Immagine", s.immagine)
    Voce(
        "File",
        if (s.presente) "presente" else "MANCA: ${s.file.path}",
        errore = !s.presente,
    )
    Voce("Regola", s.origine)
    Voce("Fascia", s.fascia)
    if (s.tag.isNotEmpty()) Voce("Tag", s.tag)
    Voce("Pool", "${s.pool} immagini")
    Voce("Finestra", "dalle ${s.inizio}, ordinale ${s.ordinale}")
    Voce("Firma", s.firma, mono = true)
}

@Composable
private fun Voce(etichetta: String, valore: String, errore: Boolean = false, mono: Boolean = false) {
    Column(Modifier.fillMaxWidth()) {
        Text(etichetta, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
        Text(
            valore,
            style = MaterialTheme.typography.bodyMedium,
            color = if (errore) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
            fontFamily = if (mono) FontFamily.Monospace else null,
        )
    }
}
