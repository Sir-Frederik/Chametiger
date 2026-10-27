package io.github.sirfrederik.chametiger

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
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
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.Motivo
import io.github.sirfrederik.chametiger.strato.Valutazione
import io.github.sirfrederik.chametiger.strato.ZONA
import io.github.sirfrederik.chametiger.ui.theme.ChametigerMobileTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        LavoroSfondo.programma(this)
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
    val scope = rememberCoroutineScope()
    val cartella = remember { cartella(context) }
    var identita by remember { mutableStateOf(Identita.leggi(context)) }
    var bozza by remember { mutableStateOf(identita) }
    var giro by remember { mutableIntStateOf(0) }
    var stato by remember { mutableStateOf<Stato>(Stato.InCorso) }
    var occupato by remember { mutableStateOf(false) }

    // Ricalcola a ogni minuto, quando cambia l'identita' e dopo un'azione. Il
    // config si rilegge ogni volta: si aggiorna copiandolo via USB.
    LaunchedEffect(identita, giro) {
        while (true) {
            stato = withContext(Dispatchers.Default) { valuta(context) }
            val adesso = LocalDateTime.now(ZONA)
            delay(ChronoUnit.MILLIS.between(adesso, adesso.truncatedTo(ChronoUnit.MINUTES).plusMinutes(1)) + 50)
        }
    }

    // Un'azione sul Ciclo vero, con lo sfondo vero, fuori dal thread principale
    fun esegui(azione: (Ciclo) -> Unit) {
        occupato = true
        scope.launch {
            withContext(Dispatchers.Default) { azione(ciclo(context, SfondoTelefono(context))) }
            occupato = false
            giro++
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
        Batteria(context)
        HorizontalDivider()

        when (val s = stato) {
            Stato.InCorso -> Text("Calcolo in corso…")
            is Stato.Errore -> Text(s.messaggio, color = MaterialTheme.colorScheme.error)
            is Stato.Pronta -> Dettagli(s.anteprima)
        }

        HorizontalDivider()
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { esegui { it.giro() } }, enabled = !occupato) { Text("Applica ora") }
            OutlinedButton(onClick = { esegui { it.forza() } }, enabled = !occupato) { Text("Estrazione forzata") }
        }
        Text(
            "Lo sfondo cambia da solo ogni 15 minuti circa. Il log è chametiger.log nella cartella sopra.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

private fun valuta(context: Context): Stato {
    val identita = Identita.leggi(context)
    return when (val v = ciclo(context, SfondoTelefono(context)).valuta()) {
        is Valutazione.Errore -> Stato.Errore(v.messaggio)
        is Valutazione.Pronta -> try {
            Stato.Pronta(anteprima(v, identita))
        } catch (e: Exception) {
            Stato.Errore("Errore nel motore: $e")
        }
    }
}

/** Se il sistema puo' sopprimere i risvegli, e il modo per evitarlo. */
@Composable
private fun Batteria(context: Context) {
    val power = context.getSystemService(PowerManager::class.java)
    if (power.isIgnoringBatteryOptimizations(context.packageName)) return
    Text(
        "Ottimizzazione della batteria attiva: il sistema può saltare i risvegli e lo sfondo restare indietro.",
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodySmall,
    )
    OutlinedButton(onClick = {
        context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
    }) { Text("Apri le impostazioni della batteria") }
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
    a.avvisoConfig?.let { Voce("Config", "$it: uso l'ultimo letto", errore = true) }
    HorizontalDivider()

    val s = a.scelta
    if (s == null) {
        Text("${a.niente ?: "Nessuna immagine"}: lo sfondo resta quello che c'è.")
        return
    }
    Voce("Immagine", s.immagine)
    when (s.motivo) {
        Motivo.CANONICA -> {}
        Motivo.RIPIEGO -> Voce("Ripiego", "manca ${s.canonica}: questa vale solo adesso", errore = true)
        Motivo.FORZATA -> Voce("Estrazione forzata", "fino a fine finestra, al posto di ${s.canonica}")
    }
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
