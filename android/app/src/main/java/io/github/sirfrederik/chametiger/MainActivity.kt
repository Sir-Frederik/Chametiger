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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.sirfrederik.chametiger.strato.CartellaDrive
import io.github.sirfrederik.chametiger.strato.Ciclo
import io.github.sirfrederik.chametiger.strato.Motivo
import io.github.sirfrederik.chametiger.strato.Valutazione
import io.github.sirfrederik.chametiger.strato.ZONA
import io.github.sirfrederik.chametiger.ui.theme.ChametigerMobileTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale
import kotlin.math.roundToInt

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
    var giro by remember { mutableIntStateOf(0) }
    var stato by remember { mutableStateOf<Stato>(Stato.InCorso) }
    var occupato by remember { mutableStateOf(false) }
    var esitoRicontrollo by remember { mutableStateOf<String?>(null) }

    // Ricalcola a ogni minuto, quando cambia un'impostazione e dopo un'azione. Il
    // config si rilegge ogni volta: si aggiorna copiandolo via USB.
    LaunchedEffect(giro) {
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

        Campo("Identità del dispositivo", "android-federico", Identita.leggi(context)) {
            Identita.scrivi(context, it)
            giro++
        }
        Campo("Cartella Drive (link)", "https://drive.google.com/drive/folders/…", ImpostazioniDrive.link(context)) {
            ImpostazioniDrive.scriviLink(context, it)
            giro++
        }
        Campo(
            "Tetto della cache (MB)", ImpostazioniDrive.TETTO_MB_DEFAULT.toString(),
            ImpostazioniDrive.tettoMb(context).toString(), numerico = true,
        ) {
            it.toIntOrNull()?.let { mb -> ImpostazioniDrive.scriviTettoMb(context, mb) }
            giro++
        }
        Text(statoDrive(context, cartella), style = MaterialTheme.typography.bodySmall)
        Velo(context, abilitato = !occupato) { esegui { it.giro() } }

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
        // Dopo aver sostituito su Drive delle immagini con versioni migliori e lo stesso nome
        OutlinedButton(
            onClick = {
                esitoRicontrollo = "Ricontrollo in corso…"
                esegui { esitoRicontrollo = it.ricontrolla() }
            },
            enabled = !occupato,
        ) { Text("Ricontrolla le immagini") }
        esitoRicontrollo?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        Text(
            "Lo sfondo cambia da solo ogni 15 minuti circa. Il log è chametiger.log nella cartella sopra.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

/** Un'impostazione con il suo pulsante Salva, attivo solo quando il testo cambia. */
@Composable
private fun Campo(etichetta: String, esempio: String, iniziale: String, numerico: Boolean = false, salva: (String) -> Unit) {
    var salvato by remember { mutableStateOf(iniziale) }
    var bozza by remember { mutableStateOf(iniziale) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = bozza,
            onValueChange = { bozza = it },
            label = { Text(etichetta) },
            placeholder = { Text(esempio) },
            singleLine = true,
            keyboardOptions = if (numerico) KeyboardOptions(keyboardType = KeyboardType.Number) else KeyboardOptions.Default,
            modifier = Modifier.weight(1f),
        )
        Button(
            onClick = {
                salvato = bozza.trim()
                bozza = salvato
                salva(salvato)
            },
            enabled = bozza.trim() != salvato,
            modifier = Modifier.padding(start = 8.dp),
        ) { Text("Salva") }
    }
}

/**
 * Il velo scuro sopra lo sfondo. Si salva quando si lascia lo slider, e
 * `applica` rimette subito lo sfondo col velo nuovo.
 */
@Composable
private fun Velo(context: Context, abilitato: Boolean, applica: () -> Unit) {
    var velo by remember { mutableFloatStateOf(ImpostazioniSfondo.velo(context).toFloat()) }
    Column(Modifier.fillMaxWidth()) {
        Text(
            "Velo scuro sullo sfondo: ${velo.roundToInt()}%" + if (velo.roundToInt() == 0) " (nessuno)" else "",
            style = MaterialTheme.typography.labelLarge,
        )
        Slider(
            value = velo,
            onValueChange = { velo = it },
            valueRange = 0f..ImpostazioniSfondo.VELO_MAX.toFloat(),
            // A passi di 5: 0, 5, ..., 60
            steps = ImpostazioniSfondo.VELO_MAX / 5 - 1,
            enabled = abilitato,
            onValueChangeFinished = {
                ImpostazioniSfondo.scriviVelo(context, velo.roundToInt())
                applica()
            },
        )
    }
}

/** Se Drive e' in uso, e quanto occupa la cache. */
private fun statoDrive(context: Context, cartella: File): String {
    if (BuildConfig.DRIVE_API_KEY.isBlank()) return "Drive: nessuna chiave API in questa build, valgono i file copiati via USB."
    val link = ImpostazioniDrive.link(context)
    if (link.isBlank()) return "Drive: incolla il link della cartella per scaricare config e immagini."
    val drive = CartellaDrive.daLink(link) ?: return "Drive: il link non è di una cartella Drive."
    val esclusi = setOf(Ciclo.NOME_CONFIG, Ciclo.NOME_LOG, "meteo.json")
    val occupati = cartella.walkTopDown().filter { it.isFile && it.name !in esclusi }.sumOf { it.length() }
    return "Drive: cartella ${drive.id.take(8)}…, cache %.0f MB su un tetto di %d MB."
        .format(Locale.ROOT, occupati / 1048576.0, ImpostazioniDrive.tettoMb(context))
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
    Voce("Meteo", a.meteo)
    Voce("Config", a.impronta + (a.avvisoConfig?.let { " (ultimo letto: $it)" } ?: ""), errore = a.avvisoConfig != null, mono = a.avvisoConfig == null)
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
