"""
Chametiger - Editor grafico della configurazione
Richiede: tkinter (stdlib), Pillow, tkcalendar (opzionale)
"""

import json
import socket
import tkinter as tk
import subprocess
import sys
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import date, datetime, timedelta

import sun

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from tkcalendar import DateEntry

    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"
ICON_FILE = BASE_DIR / "icon.ico"
LOG_FILE = BASE_DIR / "chametiger.log"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}

WEEKDAYS_IT = {
    "monday": "Lunedì",
    "tuesday": "Martedì",
    "wednesday": "Mercoledì",
    "thursday": "Giovedì",
    "friday": "Venerdì",
    "saturday": "Sabato",
    "sunday": "Domenica",
}
WEEKDAYS_ORDER = list(WEEKDAYS_IT.keys())

# ── Colori tema scuro ────────────────────────────────────────────────────────
BG = "#1e1e2e"
BG2 = "#2a2a3e"
BG3 = "#313145"
ACCENT = "#7aa2f7"
ACCENT2 = "#bb9af7"
FG = "#cdd6f4"
FG2 = "#a6adc8"
DANGER = "#f38ba8"
SUCCESS = "#a6e3a1"
ENTRY_BG = "#1a1a2e"

# ── Colori tema chiaro ───────────────────────────────────────────────────────
BG_LIGHT = "#f5f5f0"
BG2_LIGHT = "#ebebe6"
BG3_LIGHT = "#ddddd8"
ACCENT_LIGHT = "#3d6fd4"
ACCENT2_LIGHT = "#7c4fb5"
FG_LIGHT = "#1e1e2e"
FG2_LIGHT = "#555570"
ENTRY_BG_LIGHT = "#ffffff"


def apply_theme(dark: bool):
    global BG, BG2, BG3, ACCENT, ACCENT2, FG, FG2, ENTRY_BG
    if dark:
        BG, BG2, BG3 = "#1e1e2e", "#2a2a3e", "#313145"
        ACCENT, ACCENT2 = "#7aa2f7", "#bb9af7"
        FG, FG2 = "#cdd6f4", "#a6adc8"
        ENTRY_BG = "#1a1a2e"
    else:
        BG, BG2, BG3 = BG_LIGHT, BG2_LIGHT, BG3_LIGHT
        ACCENT, ACCENT2 = ACCENT_LIGHT, ACCENT2_LIGHT
        FG, FG2 = FG_LIGHT, FG2_LIGHT
        ENTRY_BG = ENTRY_BG_LIGHT


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper condivisi
# ═══════════════════════════════════════════════════════════════════════════════


def current_base_path(config: dict) -> str:
    """Cartella base delle immagini per il PC su cui gira la GUI."""
    hostname = socket.gethostname()
    path_map = config.get("path_map", {})
    return path_map.get(hostname, config.get("base_path", ""))


def is_absolute_path(p: str) -> bool:
    """True per /percorso, C:/percorso e \\\\server/share (non dipende dall'OS)."""
    s = str(p).replace("\\", "/")
    return s.startswith("/") or (len(s) > 1 and s[1] == ":")


def resolve_image_path(config: dict, filename: str) -> str:
    """Stessa logica di app.resolve_path, duplicata per non importare il tray."""
    if not filename:
        return ""

    base_path = current_base_path(config)
    default_base = config.get("base_path", "")
    path_map = config.get("path_map", {})

    if not is_absolute_path(filename):
        return str(Path(base_path) / filename)

    normalized = filename.replace("\\", "/")
    for kb in [default_base] + list(path_map.values()):
        if not kb:
            continue
        kb_norm = kb.replace("\\", "/").rstrip("/") + "/"
        if normalized.lower().startswith(kb_norm.lower()):
            return str(Path(base_path) / normalized[len(kb_norm) :])

    return filename


def to_library_key(config: dict, absolute_path: str) -> str:
    """Converte un percorso assoluto in chiave relativa alla cartella base."""
    base = current_base_path(config).replace("\\", "/").rstrip("/")
    norm = str(absolute_path).replace("\\", "/")
    if base and norm.lower().startswith(base.lower() + "/"):
        return norm[len(base) + 1 :]
    return norm


def ensure_defaults(cfg: dict) -> dict:
    cfg.setdefault("mode", "scheduled")
    cfg.setdefault("tags", [])
    cfg.setdefault("image_library", {})
    cfg.setdefault("schedules", {}).setdefault("weekday", [])
    cfg["schedules"].setdefault("weekend", [])
    cfg.setdefault("overrides", {})
    cfg.setdefault("special_days", {})
    # history_days NON viene piu' aggiunta qui: l'editor non la espone, e un
    # config che non la ha usa il default di app.py. Quelli che ce l'hanno la
    # conservano, cosi' il comportamento non cambia sotto i piedi a nessuno.
    cfg.setdefault("periods", [])
    cfg.setdefault("latitude", 40.8518)   # Napoli
    cfg.setdefault("longitude", 14.2681)

    rules = cfg.setdefault("random_rules", {})
    rules.setdefault("weekday", [])
    rules.setdefault("weekend", [])
    rules.setdefault("overrides", {})
    for day in WEEKDAYS_ORDER:
        rules["overrides"].setdefault(day, [])
        cfg["overrides"].setdefault(day, None)

    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
#  Finestra principale
# ═══════════════════════════════════════════════════════════════════════════════


class ChametigerEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chametiger - Editor Configurazione")
        self.geometry("1040x720")
        self.minsize(900, 600)

        try:
            self.iconbitmap(ICON_FILE)
        except Exception:
            pass

        self.config_data: dict = {}
        self._load_config()
        self._rebuild_ui()

    def _rebuild_ui(self):
        # I widget leggono i colori globali (BG, FG, ...) solo quando vengono creati,
        # quindi per cambiare tema bisogna ricrearli tutti.
        apply_theme(self.config_data.get("theme", "dark") == "dark")
        for child in self.winfo_children():
            child.destroy()
        self.configure(bg=BG)
        self._apply_styles()
        self._build_ui()

    # ── Carica / Salva config ────────────────────────────────────────────────
    def _load_config(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                self.config_data = ensure_defaults(json.load(f))
        except FileNotFoundError:
            messagebox.showerror("Errore", f"config.json non trovato:\n{CONFIG_FILE}")
            self.destroy()
        except json.JSONDecodeError as e:
            messagebox.showerror("config.json non valido", str(e))
            self.destroy()

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Salvato", "Configurazione salvata con successo!")
        except Exception as e:
            messagebox.showerror("Errore salvataggio", str(e))

    def _reload(self):
        self._load_config()
        messagebox.showinfo(
            "Ricaricato",
            "Configurazione ricaricata. Riavvia la GUI per rivedere tutto.",
        )

    def _show_log(self):
        if not LOG_FILE.exists():
            messagebox.showinfo("Log", f"Nessun log ancora scritto:\n{LOG_FILE}")
            return

        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile leggere il log:\n{e}")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Chametiger - Log")
        dlg.configure(bg=BG)
        dlg.geometry("820x480")

        box = tk.Text(
            dlg,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 9),
            wrap="none",
            borderwidth=0,
        )
        scroll = ttk.Scrollbar(dlg, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scroll.set)

        box.insert("1.0", text)
        box.see("end")
        box.configure(state="disabled")

        scroll.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

    # ── Stili ttk ────────────────────────────────────────────────────────────
    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG3,
            foreground=FG2,
            padding=[10, 6],
            font=("Segoe UI", 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG2)],
            foreground=[("selected", ACCENT)],
        )
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 9))
        style.configure(
            "TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 9)
        )
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure(
            "TRadiobutton", background=BG, foreground=FG, font=("Segoe UI", 9)
        )
        style.map("TRadiobutton", background=[("active", BG)])
        style.configure(
            "TButton",
            background=BG3,
            foreground=FG,
            padding=[8, 4],
            font=("Segoe UI", 9),
        )
        style.map(
            "TButton", background=[("active", ACCENT)], foreground=[("active", BG)]
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground=BG,
            font=("Segoe UI Semibold", 9),
        )
        style.map("Accent.TButton", background=[("active", ACCENT2)])
        style.configure(
            "Danger.TButton", background=DANGER, foreground=BG, font=("Segoe UI", 9)
        )
        style.configure(
            "Treeview",
            background=BG2,
            foreground=FG,
            fieldbackground=BG2,
            rowheight=26,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=BG3,
            foreground=ACCENT,
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", BG)],
        )

    # ── Layout principale ────────────────────────────────────────────────────
    def _build_ui(self):
        header = tk.Frame(self, bg=BG, pady=12)
        header.pack(fill="x", padx=16)

        if HAS_PIL and ICON_FILE.is_file():
            try:
                ico = Image.open(ICON_FILE).resize((32, 32))
                self._header_icon = ImageTk.PhotoImage(ico)
                tk.Label(header, image=self._header_icon, bg=BG).pack(side="left")
            except Exception:
                pass

        tk.Label(
            header,
            text="Chametiger",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 16),
        ).pack(side="left", padx=6)
        tk.Label(
            header,
            text="Editor Configurazione Sfondi",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=12)

        # ── Immagine "mascotte" appoggiata sulla linea superiore delle tab ─────
        HEADER_BG_IMAGE_FILE = BASE_DIR / "mascotte.png"
        HEADER_BG_IMAGE_SCALE = 6  # 2 = dimezza, 3 = un terzo, ecc.
        MASCOT_GAP = 8  # spazio in pixel tra il badge "Modalità" e la mascotte

        mascot_width = 0
        if HAS_PIL and HEADER_BG_IMAGE_FILE.is_file():
            try:
                header_bg_img = Image.open(HEADER_BG_IMAGE_FILE)
                # crop() elimina i margini trasparenti del PNG, che altrimenti
                # occuperebbero spazio coprendo il badge "Modalità".
                header_bg_img = header_bg_img.crop(header_bg_img.getbbox())
                new_size = (
                    header_bg_img.width // HEADER_BG_IMAGE_SCALE,
                    header_bg_img.height // HEADER_BG_IMAGE_SCALE,
                )
                header_bg_img = header_bg_img.resize(new_size, Image.LANCZOS)
                # self._header_bg_image tiene un riferimento forte all'immagine:
                # senza, Tkinter la "garbage-collecta" e sparisce dallo schermo.
                self._header_bg_image = ImageTk.PhotoImage(header_bg_img)
                mascot_width = new_size[0]
            except Exception:
                self._header_bg_image = None

        # padx a destra = larghezza mascotte: il badge si sposta alla sua sinistra
        self._mode_badge = tk.Label(header, bg=BG, font=("Segoe UI Semibold", 10))
        self._mode_badge.pack(
            side="right", padx=(0, mascot_width + MASCOT_GAP if mascot_width else 0)
        )
        self._refresh_mode_badge()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # place(in_=nb, ...) usa il Notebook come riferimento: relx=1.0 = bordo
        # destro, rely=0.0 = bordo superiore (la linea delle tab); anchor="se"
        # mette l'angolo in basso a destra dell'immagine su quel punto.
        if mascot_width:
            header_bg_label = tk.Label(self, image=self._header_bg_image, bg=BG, bd=0)
            header_bg_label.place(in_=nb, relx=1.0, rely=0.0, anchor="se")

        self._build_scheduled_area(nb)
        self._build_random_area(nb)
        self._build_settings_tab(nb)
        nb.select(
            2
        )  # tab predefinita all'avvio: 0=Programmata, 1=Casuale, 2=Impostazioni

        footer = tk.Frame(self, bg=BG, pady=8)
        # before=nb: il footer riceve il suo spazio prima del Notebook, cosi'
        # non viene schiacciato quando il contenuto di una tab e' molto alto.
        footer.pack(side="bottom", fill="x", padx=16, before=nb)

        def open_terminal():
            try:
                subprocess.Popen(
                    ["cmd", "/k"],
                    cwd=str(BASE_DIR),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            except Exception as e:
                messagebox.showerror("Errore", f"Impossibile aprire il terminale:\n{e}")

        ttk.Button(footer, text="Apri terminale", command=open_terminal).pack(
            side="left"
        )
        ttk.Button(footer, text="Mostra log", command=self._show_log).pack(
            side="left", padx=6
        )
        ttk.Button(
            footer,
            text="Salva configurazione",
            style="Accent.TButton",
            command=self._save_config,
        ).pack(side="right")
        ttk.Button(footer, text="Ricarica", command=self._reload).pack(
            side="right", padx=8
        )

    def _refresh_mode_badge(self):
        if self.config_data.get("mode") == "random":
            self._mode_badge.config(text="Modalità: casuale", fg=ACCENT2)
        else:
            self._mode_badge.config(text="Modalità: programmata", fg=SUCCESS)

        # ── Macroarea: modalità programmata ──────────────────────────────────────

    def _build_scheduled_area(self, nb: ttk.Notebook):
        outer = ttk.Frame(nb)
        nb.add(outer, text="   Programmata   ")

        sub = ttk.Notebook(outer)
        sub.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_schedule_tab(sub, "weekday", "Feriali")
        self._build_schedule_tab(sub, "weekend", "Weekend")
        self._build_overrides_tab(sub)
        self._build_special_tab(sub)

    # ── Macroarea: modalità casuale ──────────────────────────────────────────
    def _build_random_area(self, nb: ttk.Notebook):
        outer = ttk.Frame(nb)
        nb.add(outer, text="   Casuale   ")

        sub = ttk.Notebook(outer)
        sub.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_tags_tab(sub)
        self._build_library_tab(sub)
        self._build_periods_tab(sub)

        self._rule_editors = []
        hint = (
            "Le regole vengono lette in quest'ordine: override del giorno, "
            "poi feriali/weekend.\nLa prima che copre l'ora attuale vince."
        )

        for key, label in (
            ("weekday", "Regole feriali"),
            ("weekend", "Regole weekend"),
        ):
            frame = ttk.Frame(sub)
            sub.add(frame, text=label)
            tk.Label(
                frame, text=hint, bg=BG, fg=FG2, font=("Segoe UI", 9), justify="left"
            ).pack(anchor="w", padx=12, pady=(10, 6))
            ed = RuleEditor(frame, self.config_data, ["random_rules", key])
            ed.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self._rule_editors.append(ed)

        self._build_random_override_tab(sub)
        self._build_preview_tab(sub)

    def _build_periods_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Periodi dell'anno")
        self._periods_tab = PeriodsTab(frame, self.config_data, self)
        self._periods_tab.pack(fill="both", expand=True)

    def _build_preview_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Anteprima giorno")
        self._preview_tab = PreviewTab(frame, self.config_data, self)
        self._preview_tab.pack(fill="both", expand=True)

    def _build_random_override_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Regole override giorno")

        top = tk.Frame(frame, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Giorno:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._rnd_day_var = tk.StringVar(value="monday")
        cb = ttk.Combobox(
            top,
            textvariable=self._rnd_day_var,
            values=[f"{v} ({WEEKDAYS_IT[v]})" for v in WEEKDAYS_ORDER],
            width=24,
            state="readonly",
        )
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_random_day())

        tk.Label(
            top,
            text="Queste regole hanno la precedenza su feriali e weekend.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12)

        self._rnd_day_frame = tk.Frame(frame, bg=BG)
        self._rnd_day_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._refresh_random_day()

    def _refresh_random_day(self):
        day = self._rnd_day_var.get().split(" ")[0]
        for w in self._rnd_day_frame.winfo_children():
            w.destroy()
        self._rnd_day_editor = RuleEditor(
            self._rnd_day_frame, self.config_data, ["random_rules", "overrides", day]
        )
        self._rnd_day_editor.pack(fill="both", expand=True)

    # ── Tab schedule (weekday / weekend) ─────────────────────────────────────
    def _build_schedule_tab(self, nb: ttk.Notebook, key: str, label: str):
        frame = ttk.Frame(nb)
        nb.add(frame, text=label)
        SlotEditor(frame, self.config_data, ["schedules", key]).pack(
            fill="both", expand=True, padx=12, pady=12
        )

    # ── Tab override giorno ──────────────────────────────────────────────────
    def _build_overrides_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Override giorno")

        top = tk.Frame(frame, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Giorno:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._override_day_var = tk.StringVar(value="monday")
        cb = ttk.Combobox(
            top,
            textvariable=self._override_day_var,
            values=[f"{v} ({WEEKDAYS_IT[v]})" for v in WEEKDAYS_ORDER],
            width=24,
            state="readonly",
        )
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_override_ui())

        tk.Label(
            top,
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            text="Override spento = usa lo schedule base",
        ).pack(side="left", padx=12)

        self._override_active_var = tk.BooleanVar()
        ttk.Checkbutton(
            top,
            text="Attiva override",
            variable=self._override_active_var,
            command=self._toggle_override,
        ).pack(side="right")

        self._override_editor_frame = tk.Frame(frame, bg=BG)
        self._override_editor_frame.pack(
            fill="both", expand=True, padx=12, pady=(0, 12)
        )
        self._refresh_override_ui()

    def _current_override_key(self) -> str:
        return self._override_day_var.get().split(" ")[0]

    def _toggle_override(self):
        key = self._current_override_key()
        if self._override_active_var.get():
            if self.config_data["overrides"].get(key) is None:
                self.config_data["overrides"][key] = []
        else:
            self.config_data["overrides"][key] = None
        self._refresh_override_ui()

    def _refresh_override_ui(self):
        key = self._current_override_key()
        active = self.config_data["overrides"].get(key) is not None
        self._override_active_var.set(active)

        for w in self._override_editor_frame.winfo_children():
            w.destroy()

        if active:
            SlotEditor(
                self._override_editor_frame, self.config_data, ["overrides", key]
            ).pack(fill="both", expand=True)
        else:
            tk.Label(
                self._override_editor_frame,
                text="Override non attivo: verrà usato lo schedule base.",
                bg=BG,
                fg=FG2,
                font=("Segoe UI Italic", 9),
            ).pack(pady=24)

    # ── Tab giorni speciali ──────────────────────────────────────────────────
    def _build_special_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Giorni speciali")
        SpecialDaysEditor(frame, self.config_data).pack(
            fill="both", expand=True, padx=12, pady=12
        )

    # ── Tab tag ──────────────────────────────────────────────────────────────
    def _build_tags_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Tag")
        self._tags_tab = TagsTab(frame, self.config_data, self)
        self._tags_tab.pack(fill="both", expand=True, padx=12, pady=12)

    # ── Tab libreria immagini ────────────────────────────────────────────────
    def _build_library_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Libreria")
        self._library_tab = LibraryTab(frame, self.config_data)
        self._library_tab.pack(fill="both", expand=True, padx=12, pady=12)

    # ── Tab regole casuali ───────────────────────────────────────────────────
    def _build_random_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Regole casuali")
        self._random_tab = RandomRulesTab(frame, self.config_data)
        self._random_tab.pack(fill="both", expand=True, padx=12, pady=12)

    # Chiamato dagli altri tab quando cambia l'elenco dei tag.
    # Era definita annidata dentro _build_random_tab, quindi non era un metodo e
    # ogni rinomina di tag finiva in AttributeError.
    def notify_tags_changed(self):
        if hasattr(self, "_library_tab"):
            self._library_tab.refresh_tag_widgets()
        for ed in getattr(self, "_rule_editors", []):
            ed.refresh_tree()
        if hasattr(self, "_rnd_day_editor"):
            self._rnd_day_editor.refresh_tree()
        if hasattr(self, "_random_tab"):
            self._random_tab.refresh_filters()
        if hasattr(self, "_periods_tab"):
            self._periods_tab.refresh()

    # ── Tab impostazioni ─────────────────────────────────────────────────────
    def _build_settings_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Impostazioni")

        inner = tk.Frame(frame, bg=BG)
        inner.pack(padx=24, pady=24, anchor="nw", fill="x")

        # Modalità
        tk.Label(
            inner,
            text="Modalità di funzionamento",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self._mode_var = tk.StringVar(value=self.config_data.get("mode", "scheduled"))

        def on_mode_change():
            self.config_data["mode"] = self._mode_var.get()
            self._refresh_mode_badge()

        ttk.Radiobutton(
            inner,
            text="Programmata (ogni slot ha la sua immagine fissa)",
            variable=self._mode_var,
            value="scheduled",
            command=on_mode_change,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=2)

        ttk.Radiobutton(
            inner,
            text="Casuale per tag (ogni slot pesca tra le immagini che hanno certi tag)",
            variable=self._mode_var,
            value="random",
            command=on_mode_change,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=2)

        tk.Label(
            inner,
            text="In modalità casuale i giorni speciali restano fissi,\n"
            "e se nessuna regola copre l'ora attuale si ripiega sulla modalità programmata.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 16))

        # Intervallo
        tk.Label(
            inner,
            text="Intervallo controllo (minuti):",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 10),
        ).grid(row=4, column=0, sticky="w", pady=8)

        self._interval_var = tk.IntVar(
            value=self.config_data.get("check_interval_minutes", 5)
        )
        tk.Spinbox(
            inner,
            from_=1,
            to=60,
            textvariable=self._interval_var,
            width=6,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            buttonbackground=BG3,
            relief="flat",
            font=("Segoe UI", 10),
        ).grid(row=4, column=1, padx=12, sticky="w")

        def apply_interval():
            self.config_data["check_interval_minutes"] = self._interval_var.get()

        ttk.Button(inner, text="Applica", command=apply_interval).grid(
            row=4, column=2, padx=4
        )

        # Qui c'era "Memoria estrazioni (giorni)", rimossa nella 3.0: prometteva di
        # influenzare quali immagini uscivano, ma la scelta viene dal mazzo e non
        # guarda log.json. Restava un solo effetto, la potatura dello storico, che
        # non e' una decisione da lasciare all'utente. La chiave history_days nel
        # config continua a essere rispettata se c'e'; senza, vale il default di
        # app.DEFAULT_HISTORY_DAYS.

        # Tema
        tk.Label(
            inner, text="Tema interfaccia:", bg=BG, fg=FG, font=("Segoe UI", 10)
        ).grid(row=7, column=0, sticky="w", pady=8)

        self._theme_var = tk.StringVar(
            value="Chiaro" if self.config_data.get("theme") == "light" else "Scuro"
        )
        ttk.Combobox(
            inner,
            textvariable=self._theme_var,
            values=["Scuro", "Chiaro"],
            width=10,
            state="readonly",
        ).grid(row=7, column=1, padx=12, sticky="w")

        def apply_and_restart():
            self.config_data["theme"] = (
                "dark" if self._theme_var.get() == "Scuro" else "light"
            )
            # after_idle: non distruggere il pulsante mentre sta ancora gestendo il click
            self.after_idle(self._rebuild_ui)
            messagebox.showinfo(
                "Tema",
                "Tema applicato.\nPremi \"Salva configurazione\" per mantenerlo ai prossimi avvii.",
            )

        ttk.Button(inner, text="Applica", command=apply_and_restart).grid(
            row=7, column=2, padx=4
        )

        # Cartella base
        # Cartella base delle immagini
        hostname = socket.gethostname()

        tk.Label(
            inner,
            text="Cartella base delle immagini:",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 10),
        ).grid(row=8, column=0, sticky="w", pady=(16, 4))

        self._base_var = tk.StringVar(value=current_base_path(self.config_data))
        tk.Entry(
            inner,
            textvariable=self._base_var,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=52,
            font=("Segoe UI", 9),
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=2)

        def browse_base():
            path = filedialog.askdirectory(
                title="Scegli la cartella base delle immagini",
                initialdir=self._base_var.get() or None,
            )
            if path:
                self._base_var.set(path)

        ttk.Button(inner, text="Sfoglia...", command=browse_base).grid(
            row=9, column=2, padx=4
        )

        self._base_only_here = tk.BooleanVar(
            value=hostname in self.config_data.get("path_map", {})
        )
        ttk.Checkbutton(
            inner,
            text=f"Vale solo per questo PC ({hostname})",
            variable=self._base_only_here,
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(4, 0))

        def apply_base():
            path = self._base_var.get().strip().replace("\\", "/").rstrip("/")
            if not path:
                self._base_status.config(text="Percorso vuoto.", fg=DANGER)
                return

            path_map = self.config_data.setdefault("path_map", {})
            if self._base_only_here.get():
                path_map[hostname] = path
            else:
                self.config_data["base_path"] = path
                path_map.pop(hostname, None)

            if Path(path).is_dir():
                self._base_status.config(text=f"Cartella impostata: {path}", fg=SUCCESS)
            else:
                self._base_status.config(
                    text=f"Impostata, ma la cartella non esiste: {path}", fg=DANGER
                )

        ttk.Button(inner, text="Applica cartella", command=apply_base).grid(
            row=11, column=0, sticky="w", pady=(8, 0)
        )

        # ── Coordinate per gli orari solari ─────────────────────────────────
        tk.Label(
            inner,
            text="Posizione (per alba, tramonto e crepuscolo)",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 11),
        ).grid(row=13, column=0, columnspan=3, sticky="w", pady=(24, 6))

        coord = tk.Frame(inner, bg=BG)
        coord.grid(row=14, column=0, columnspan=3, sticky="w")

        tk.Label(coord, text="Latitudine", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(
            side="left"
        )
        self._lat_var = tk.StringVar(value=str(self.config_data.get("latitude", 40.8518)))
        tk.Entry(
            coord,
            textvariable=self._lat_var,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=11,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(6, 16))

        tk.Label(coord, text="Longitudine", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(
            side="left"
        )
        self._lon_var = tk.StringVar(value=str(self.config_data.get("longitude", 14.2681)))
        tk.Entry(
            coord,
            textvariable=self._lon_var,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=11,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=6)

        citta = {
            "Napoli": (40.8518, 14.2681),
            "Roma": (41.9028, 12.4964),
            "Milano": (45.4642, 9.1900),
            "Torino": (45.0703, 7.6869),
            "Firenze": (43.7696, 11.2558),
            "Bologna": (44.4949, 11.3426),
            "Venezia": (45.4408, 12.3155),
            "Bari": (41.1171, 16.8719),
            "Palermo": (38.1157, 13.3615),
            "Cagliari": (39.2238, 9.1217),
        }

        def imposta_citta(_=None):
            nome = self._citta_var.get()
            if nome in citta:
                lat, lon = citta[nome]
                self._lat_var.set(str(lat))
                self._lon_var.set(str(lon))
                applica_coord()

        tk.Label(coord, text="oppure", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(
            side="left", padx=(16, 6)
        )
        self._citta_var = tk.StringVar()
        cb_citta = ttk.Combobox(
            coord,
            textvariable=self._citta_var,
            values=sorted(citta),
            width=12,
            state="readonly",
        )
        cb_citta.pack(side="left")
        cb_citta.bind("<<ComboboxSelected>>", imposta_citta)

        self._coord_status = tk.Label(
            inner, bg=BG, fg=FG2, font=("Segoe UI", 9), justify="left", anchor="w"
        )
        self._coord_status.grid(row=16, column=0, columnspan=3, sticky="w", pady=(6, 0))

        def applica_coord():
            try:
                lat = float(self._lat_var.get().strip().replace(",", "."))
                lon = float(self._lon_var.get().strip().replace(",", "."))
            except ValueError:
                self._coord_status.config(text="Coordinate non numeriche.", fg=DANGER)
                return
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self._coord_status.config(
                    text="Latitudine fra -90 e 90, longitudine fra -180 e 180.", fg=DANGER
                )
                return
            self.config_data["latitude"] = lat
            self.config_data["longitude"] = lon
            orari = sun.sun_times(date.today(), lat, lon)

            def hm(k):
                v = orari.get(k)
                return v.strftime("%H:%M") if v else "n.d."

            self._coord_status.config(
                text=f"Oggi qui: crepuscolo {hm('dawn')}, alba {hm('sunrise')}, "
                f"mezzogiorno solare {hm('noon')}, tramonto {hm('sunset')}, "
                f"crepuscolo serale {hm('dusk')}.\n"
                "L'ora legale e' gia' compresa: la applica il sistema operativo.",
                fg=SUCCESS,
            )
            if hasattr(self, "_preview_tab"):
                self._preview_tab._calcola()

        ttk.Button(inner, text="Applica posizione", command=applica_coord).grid(
            row=15, column=0, sticky="w", pady=(8, 0)
        )

        tk.Label(
            inner,
            text="Servono alle fasce ancorate al sole (sunset-40m, dawn-20m): con le\n"
            "coordinate sbagliate le fasce serali cadono nell'ora sbagliata.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
        ).grid(row=17, column=0, columnspan=3, sticky="w", pady=(4, 0))

        applica_coord()

        self._base_status = tk.Label(inner, bg=BG, fg=FG2, font=("Segoe UI", 9))
        self._base_status.grid(row=12, column=0, columnspan=3, sticky="w", pady=(4, 0))


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: gestione vocabolario tag
# ═══════════════════════════════════════════════════════════════════════════════


class TagsTab(tk.Frame):
    def __init__(self, parent, config_data: dict, app):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.app = app
        self._build()

    def _build(self):
        left = tk.Frame(self, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 16))

        tk.Label(
            left,
            text="Tag disponibili",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(0, 6))

        self._listbox = tk.Listbox(
            left,
            bg=BG2,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground=BG,
            width=26,
            height=18,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self._listbox.pack(fill="y", expand=True)

        btns = tk.Frame(left, bg=BG)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Aggiungi", command=self._add).pack(side="left")
        ttk.Button(btns, text="Rinomina", command=self._rename).pack(
            side="left", padx=4
        )
        ttk.Button(
            btns, text="Elimina", style="Danger.TButton", command=self._delete
        ).pack(side="left")

        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(
            right,
            text="Come funzionano i tag",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            right,
            text=(
                "Un tag è un'etichetta libera: mattino, lavoro, smart, pranzo,\n"
                "tramonto, notte, pioggia, natale... decidi tu il vocabolario.\n\n"
                "Ogni immagine della Libreria può averne quanti ne vuoi.\n\n"
                "Nelle Regole casuali scegli quali tag devono esserci e quali\n"
                "no: da lì nasce l'estrazione.\n\n"
                "Rinominare un tag aggiorna anche tutte le immagini e le regole\n"
                "che lo usano. Eliminarlo lo toglie da tutto."
            ),
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w")

        self._usage_lbl = tk.Label(
            right, bg=BG, fg=SUCCESS, font=("Segoe UI", 9), justify="left"
        )
        self._usage_lbl.pack(anchor="w", pady=12)

        self._listbox.bind("<<ListboxSelect>>", lambda e: self._refresh_usage())
        self._refresh()

    def _tags(self) -> list:
        return self.config_data.setdefault("tags", [])

    def _refresh(self):
        self._listbox.delete(0, "end")
        for t in sorted(self._tags(), key=str.lower):
            self._listbox.insert("end", t)
        self._refresh_usage()

    def _refresh_usage(self):
        sel = self._listbox.curselection()
        if not sel:
            self._usage_lbl.config(text="")
            return
        tag = self._listbox.get(sel[0])
        library = self.config_data.get("image_library", {})
        count = sum(1 for tags in library.values() if tag in (tags or []))
        self._usage_lbl.config(text=f"Il tag '{tag}' è assegnato a {count} immagini.")

    def _selected_tag(self) -> str | None:
        sel = self._listbox.curselection()
        return self._listbox.get(sel[0]) if sel else None

    def _add(self):
        name = simpledialog.askstring("Nuovo tag", "Nome del tag:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self._tags():
            messagebox.showinfo("Già presente", f"Il tag '{name}' esiste già.")
            return
        self._tags().append(name)
        self._refresh()
        self.app.notify_tags_changed()

    def _rename(self):
        old = self._selected_tag()
        if not old:
            return
        new = simpledialog.askstring(
            "Rinomina tag", "Nuovo nome:", initialvalue=old, parent=self
        )
        if not new:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self._tags():
            messagebox.showinfo("Già presente", f"Il tag '{new}' esiste già.")
            return

        tags = self._tags()
        tags[tags.index(old)] = new

        for image, img_tags in self.config_data.get("image_library", {}).items():
            if img_tags and old in img_tags:
                img_tags[img_tags.index(old)] = new

        for rule in self._all_rules():
            for field in ("include", "exclude", "prefer"):
                lst = rule.get(field, [])
                if old in lst:
                    lst[lst.index(old)] = new

        self._refresh()
        self.app.notify_tags_changed()

    def _delete(self):
        tag = self._selected_tag()
        if not tag:
            return
        if not messagebox.askyesno(
            "Conferma", f"Eliminare il tag '{tag}' da tutte le immagini e regole?"
        ):
            return

        self._tags().remove(tag)

        for img_tags in self.config_data.get("image_library", {}).values():
            if img_tags and tag in img_tags:
                img_tags.remove(tag)

        for rule in self._all_rules():
            for field in ("include", "exclude", "prefer"):
                if tag in rule.get(field, []):
                    rule[field].remove(tag)

        self._refresh()
        self.app.notify_tags_changed()

    def _all_rules(self):
        """
        Tutte le regole che usano i tag, PERIODI COMPRESI: senza i periodi,
        rinominare o cancellare un tag lascerebbe i periodi che lo citano
        puntati su un tag che non esiste piu', in silenzio.
        """

        def raccogli(rules):
            out = list(rules.get("weekday", []) or []) + list(rules.get("weekend", []) or [])
            for day_rules in (rules.get("overrides", {}) or {}).values():
                out += list(day_rules or [])
            return out

        out = raccogli(self.config_data.get("random_rules", {}))
        for period in self.config_data.get("periods", []) or []:
            # Il periodo stesso conta come utilizzo dei tag che filtra. Le liste
            # vanno passate per RIFERIMENTO, non copiate: _rename e _delete le
            # modificano in place, e su una copia il rinomino non arriverebbe
            # mai al config.
            voce = {}
            for chiave_periodo, chiave_regola in (
                ("require", "include"),
                ("exclude", "exclude"),
                ("prefer", "prefer"),
            ):
                lst = period.get(chiave_periodo)
                if isinstance(lst, list):
                    voce[chiave_regola] = lst
            if voce:
                out.append(voce)
            out += raccogli(period.get("random_rules", {}) or {})
        return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: libreria immagini e assegnazione tag
# ═══════════════════════════════════════════════════════════════════════════════


class LibraryTab(tk.Frame):
    def __init__(self, parent, config_data: dict):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self._preview_photo = None
        self._tag_vars: dict[str, tk.BooleanVar] = {}
        self._suspend_events = False
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────────
    def _build(self):
        # Barra superiore
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", pady=(0, 8))

        ttk.Button(top, text="Scansiona cartella base", command=self._scan_folder).pack(
            side="left"
        )
        ttk.Button(top, text="Aggiungi immagini...", command=self._add_files).pack(
            side="left", padx=6
        )
        ttk.Button(top, text="Rimuovi mancanti", command=self._clean_missing).pack(
            side="left"
        )
        ttk.Button(
            top,
            text="Togli dalla libreria",
            style="Danger.TButton",
            command=self._remove_selected,
        ).pack(side="left", padx=6)

        self._count_lbl = tk.Label(top, bg=BG, fg=FG2, font=("Segoe UI", 9))
        self._count_lbl.pack(side="right")

        # Filtri
        filt = tk.Frame(self, bg=BG)
        filt.pack(fill="x", pady=(0, 8))

        tk.Label(filt, text="Cerca:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_list())
        tk.Entry(
            filt,
            textvariable=self._search_var,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=28,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        tk.Label(filt, text="Filtra per tag:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(16, 0)
        )
        self._filter_tag_var = tk.StringVar(value="(tutti)")
        self._filter_cb = ttk.Combobox(
            filt,
            textvariable=self._filter_tag_var,
            width=20,
            state="readonly",
        )
        self._filter_cb.pack(side="left", padx=6)
        self._filter_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        # Corpo
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        self._listbox = tk.Listbox(
            left,
            bg=BG2,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground=BG,
            selectmode="extended",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        sb = ttk.Scrollbar(left, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._listbox.bind("<<ListboxSelect>>", lambda e: self._on_select())

        right = tk.Frame(body, bg=BG, width=300)
        right.pack(side="left", fill="y")
        right.pack_propagate(False)

        self._preview_lbl = tk.Label(right, bg=BG2, width=280, height=160)
        self._preview_lbl.pack(pady=(0, 8))

        self._name_lbl = tk.Label(
            right, bg=BG, fg=FG2, font=("Segoe UI", 8), wraplength=280, justify="left"
        )
        self._name_lbl.pack(anchor="w")

        tk.Label(
            right,
            text="Tag assegnati",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(10, 2))

        self._hint_lbl = tk.Label(
            right,
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
            wraplength=280,
            justify="left",
        )
        self._hint_lbl.pack(anchor="w", pady=(0, 6))

        # Area tag scrollabile
        tag_area = tk.Frame(right, bg=BG)
        tag_area.pack(fill="both", expand=True)

        self._tag_canvas = tk.Canvas(
            tag_area, bg=BG, highlightthickness=0, borderwidth=0
        )
        tag_sb = ttk.Scrollbar(
            tag_area, orient="vertical", command=self._tag_canvas.yview
        )
        self._tag_inner = tk.Frame(self._tag_canvas, bg=BG)

        self._tag_inner.bind(
            "<Configure>",
            lambda e: self._tag_canvas.configure(
                scrollregion=self._tag_canvas.bbox("all")
            ),
        )
        self._tag_window = self._tag_canvas.create_window(
            (0, 0), window=self._tag_inner, anchor="nw"
        )
        self._tag_canvas.configure(yscrollcommand=tag_sb.set)

        # la scrollbar va impacchettata per prima, altrimenti il canvas la spinge fuori
        tag_sb.pack(side="right", fill="y")
        self._tag_canvas.pack(side="left", fill="both", expand=True)

        # il frame interno si adatta alla larghezza del canvas
        self._tag_canvas.bind(
            "<Configure>",
            lambda e: self._tag_canvas.itemconfigure(self._tag_window, width=e.width),
        )

        # rotellina del mouse
        def _on_wheel(event):
            self._tag_canvas.yview_scroll(int(-event.delta / 120), "units")

        self._tag_canvas.bind(
            "<Enter>", lambda e: self._tag_canvas.bind_all("<MouseWheel>", _on_wheel)
        )
        self._tag_canvas.bind(
            "<Leave>", lambda e: self._tag_canvas.unbind_all("<MouseWheel>")
        )

        self.refresh_tag_widgets()
        self._refresh_list()

    # ── Dati ─────────────────────────────────────────────────────────────────
    def _library(self) -> dict:
        return self.config_data.setdefault("image_library", {})

    def _tags(self) -> list:
        return sorted(self.config_data.get("tags", []), key=str.lower)

    def refresh_tag_widgets(self):
        """Ricostruisce le checkbox dei tag (dopo modifiche al vocabolario)."""
        for w in self._tag_inner.winfo_children():
            w.destroy()
        self._tag_vars = {}

        tags = self._tags()
        if not tags:
            tk.Label(
                self._tag_inner,
                text="Nessun tag definito.\nCreali nel tab 'Tag'.",
                bg=BG,
                fg=FG2,
                font=("Segoe UI Italic", 9),
                justify="left",
            ).pack(anchor="w", pady=8)
        else:
            for t in tags:
                var = tk.BooleanVar()
                self._tag_vars[t] = var
                ttk.Checkbutton(
                    self._tag_inner,
                    text=t,
                    variable=var,
                    command=lambda tag=t: self._on_tag_toggle(tag),
                ).pack(anchor="w")

        self._filter_cb.configure(values=["(tutti)", "(senza tag)"] + tags)
        if self._filter_tag_var.get() not in ["(tutti)", "(senza tag)"] + tags:
            self._filter_tag_var.set("(tutti)")

        self._on_select()

    # ── Lista ────────────────────────────────────────────────────────────────
    def _refresh_list(self):
        self._listbox.delete(0, "end")
        library = self._library()
        search = self._search_var.get().strip().lower()
        ftag = self._filter_tag_var.get()

        for image in sorted(library.keys(), key=str.lower):
            tags = library.get(image) or []
            if search and search not in image.lower():
                continue
            if ftag == "(senza tag)" and tags:
                continue
            if ftag not in ("(tutti)", "(senza tag)") and ftag not in tags:
                continue
            marker = f"  [{', '.join(tags)}]" if tags else "  [-]"
            self._listbox.insert("end", image + marker)

        total = len(library)
        untagged = sum(1 for t in library.values() if not t)
        self._count_lbl.config(
            text=f"{self._listbox.size()} mostrate / {total} in libreria / {untagged} senza tag"
        )

    def _selected_images(self) -> list[str]:
        out = []
        for idx in self._listbox.curselection():
            raw = self._listbox.get(idx)
            out.append(raw.split("  [")[0])
        return out

    # ── Selezione ────────────────────────────────────────────────────────────
    def _on_select(self):
        images = self._selected_images()

        if not images:
            self._preview_lbl.config(image="", text="")
            self._preview_photo = None
            self._name_lbl.config(text="")
            self._hint_lbl.config(text="Seleziona una o più immagini.")
            self._suspend_events = True
            for var in self._tag_vars.values():
                var.set(False)
            self._suspend_events = False
            return

        if len(images) == 1:
            self._hint_lbl.config(text="")
            self._name_lbl.config(text=images[0])
            self._show_preview(images[0])
        else:
            self._preview_lbl.config(image="", text=f"{len(images)} immagini")
            self._preview_photo = None
            self._name_lbl.config(text="")
            self._hint_lbl.config(
                text="Selezione multipla: spuntare o togliere un tag lo applica a tutte."
            )

        # Le checkbox riflettono i tag comuni a tutte le selezionate
        library = self._library()
        common = None
        for img in images:
            tags = set(library.get(img) or [])
            common = tags if common is None else (common & tags)
        common = common or set()

        self._suspend_events = True
        for tag, var in self._tag_vars.items():
            var.set(tag in common)
        self._suspend_events = False

    def _show_preview(self, image_key: str):
        path = resolve_image_path(self.config_data, image_key)
        if not HAS_PIL:
            self._preview_lbl.config(image="", text="(Pillow non installato)")
            return
        if not Path(path).is_file():
            self._preview_lbl.config(image="", text="File non trovato")
            self._preview_photo = None
            return
        try:
            img = Image.open(path)
            img.thumbnail((270, 155), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(img)
            self._preview_lbl.config(image=self._preview_photo, text="")
        except Exception:
            self._preview_lbl.config(image="", text="Anteprima non disponibile")
            self._preview_photo = None

    # ── Toggle tag ───────────────────────────────────────────────────────────
    def _on_tag_toggle(self, tag: str):
        if self._suspend_events:
            return
        images = self._selected_images()
        if not images:
            return

        add = self._tag_vars[tag].get()
        library = self._library()

        for img in images:
            tags = library.setdefault(img, [])
            if add and tag not in tags:
                tags.append(tag)
            elif not add and tag in tags:
                tags.remove(tag)

        # Ricostruisce la lista mantenendo selezione e posizione di scorrimento
        selected = set(images)
        top = self._listbox.yview()[0]
        active = self._listbox.index("active")

        self._suspend_events = True
        self._refresh_list()

        first_visible = None
        for i in range(self._listbox.size()):
            if self._listbox.get(i).split("  [")[0] in selected:
                self._listbox.selection_set(i)
                if first_visible is None:
                    first_visible = i

        self._listbox.yview_moveto(top)
        if first_visible is not None:
            self._listbox.activate(first_visible)
            self._listbox.see(first_visible)
        elif active < self._listbox.size():
            self._listbox.activate(active)
            self._listbox.see(active)

        self._suspend_events = False

    # ── Azioni libreria ──────────────────────────────────────────────────────
    def _scan_folder(self):
        base = current_base_path(self.config_data)
        if not base or not Path(base).is_dir():
            messagebox.showerror(
                "Cartella non valida",
                f"La cartella base non esiste:\n{base or '(non impostata)'}",
            )
            return

        library = self._library()
        added = 0
        for path in sorted(Path(base).rglob("*")):
            if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
                continue
            key = to_library_key(self.config_data, path)
            if key not in library:
                library[key] = []
                added += 1

        self._refresh_list()
        messagebox.showinfo(
            "Scansione completata",
            f"{added} nuove immagini aggiunte.\nTotale in libreria: {len(library)}",
        )

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Aggiungi immagini alla libreria",
            initialdir=current_base_path(self.config_data) or None,
            filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp *.gif")],
        )
        if not paths:
            return
        library = self._library()
        added = 0
        for p in paths:
            key = to_library_key(self.config_data, p)
            if key not in library:
                library[key] = []
                added += 1
        self._refresh_list()
        messagebox.showinfo("Fatto", f"{added} immagini aggiunte.")

    def _clean_missing(self):
        library = self._library()
        missing = [
            img
            for img in library
            if not Path(resolve_image_path(self.config_data, img)).is_file()
        ]
        if not missing:
            messagebox.showinfo("Tutto a posto", "Tutte le immagini esistono.")
            return
        if not messagebox.askyesno(
            "Conferma", f"Rimuovere {len(missing)} immagini non più presenti su disco?"
        ):
            return
        for img in missing:
            library.pop(img, None)
        self._refresh_list()

    def _remove_selected(self):
        images = self._selected_images()
        if not images:
            return
        if not messagebox.askyesno(
            "Conferma", f"Togliere {len(images)} immagini dalla libreria?"
        ):
            return
        library = self._library()
        for img in images:
            library.pop(img, None)
        self._refresh_list()
        self._on_select()


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: regole casuali
# ═══════════════════════════════════════════════════════════════════════════════


class RandomRulesTab(tk.Frame):
    def __init__(self, parent, config_data: dict):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self._editors: list[RuleEditor] = []
        self._build()

    def _build(self):
        tk.Label(
            self,
            text="Le regole vengono lette in quest'ordine: override del giorno, poi "
            "feriali/weekend.\nLa prima che copre l'ora attuale vince.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        for key, label in (("weekday", "Feriali"), ("weekend", "Weekend")):
            frame = ttk.Frame(nb)
            nb.add(frame, text=label)
            ed = RuleEditor(frame, self.config_data, ["random_rules", key])
            ed.pack(fill="both", expand=True, padx=10, pady=10)
            self._editors.append(ed)

        # Override per giorno
        ov = ttk.Frame(nb)
        nb.add(ov, text="Override giorno")

        top = tk.Frame(ov, bg=BG, pady=8)
        top.pack(fill="x", padx=10)
        tk.Label(top, text="Giorno:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._day_var = tk.StringVar(value="monday")
        cb = ttk.Combobox(
            top,
            textvariable=self._day_var,
            values=[f"{v} ({WEEKDAYS_IT[v]})" for v in WEEKDAYS_ORDER],
            width=24,
            state="readonly",
        )
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_day())

        self._day_frame = tk.Frame(ov, bg=BG)
        self._day_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._refresh_day()

    def _refresh_day(self):
        day = self._day_var.get().split(" ")[0]
        for w in self._day_frame.winfo_children():
            w.destroy()
        self._day_editor = RuleEditor(
            self._day_frame, self.config_data, ["random_rules", "overrides", day]
        )
        self._day_editor.pack(fill="both", expand=True)

    def refresh_filters(self):
        """Chiamato quando cambia il vocabolario dei tag."""
        for ed in self._editors:
            ed.refresh_tree()
        if hasattr(self, "_day_editor"):
            self._day_editor.refresh_tree()


class RuleEditor(tk.Frame):
    """Lista di regole [{from, to, include, exclude, match, rotate_minutes}]."""

    def __init__(self, parent, config_data: dict, path: list[str]):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.path = path
        self._build()

    def _rules(self) -> list:
        d = self.config_data
        for k in self.path:
            d = d[k]
        return d

    def _build(self):
        cols = ("from", "to", "include", "exclude", "rotate")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        self._tree.heading("from", text="Dalle")
        self._tree.heading("to", text="Alle")
        self._tree.heading("include", text="Con i tag")
        self._tree.heading("exclude", text="Senza i tag")
        self._tree.heading("rotate", text="Cambia ogni")
        self._tree.column("from", width=60, anchor="center")
        self._tree.column("to", width=60, anchor="center")
        self._tree.column("include", width=230)
        self._tree.column("exclude", width=180)
        self._tree.column("rotate", width=100, anchor="center")

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        btns = tk.Frame(self, bg=BG, padx=8)
        btns.pack(side="left", fill="y")
        ttk.Button(btns, text="Aggiungi", command=self._add).pack(fill="x", pady=3)
        ttk.Button(btns, text="Modifica", command=self._edit).pack(fill="x", pady=3)
        ttk.Button(
            btns, text="Elimina", style="Danger.TButton", command=self._delete
        ).pack(fill="x", pady=3)
        ttk.Button(btns, text="Su", command=self._move_up).pack(fill="x", pady=3)
        ttk.Button(btns, text="Giù", command=self._move_down).pack(fill="x", pady=3)
        ttk.Button(btns, text="Verifica", command=self._check).pack(fill="x", pady=12)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self.refresh_tree()

    def refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        oggi = date.today()
        for r in self._rules():
            match = r.get("match", "all")
            inc = ", ".join(r.get("include", [])) or "(qualsiasi)"
            if match == "any" and r.get("include"):
                inc += "  [almeno uno]"
            lat, lon = coords_of(self.config_data)
            self._tree.insert(
                "",
                "end",
                values=(
                    sun.describe(r.get("from", ""), oggi, lat, lon),
                    sun.describe(r.get("to", ""), oggi, lat, lon),
                    inc,
                    ", ".join(r.get("exclude", [])) or "-",
                    f"{r.get('rotate_minutes', 60)} min",
                ),
            )

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        return self._tree.index(sel[0]) if sel else None

    def _add(self):
        dlg = RuleDialog(self, self.config_data, title="Nuova regola")
        if dlg.result:
            self._rules().append(dlg.result)
            self.refresh_tree()

    def _edit(self):
        idx = self._selected_index()
        if idx is None:
            return
        rules = self._rules()
        dlg = RuleDialog(
            self, self.config_data, title="Modifica regola", initial=rules[idx]
        )
        if dlg.result:
            rules[idx] = dlg.result
            self.refresh_tree()

    def _delete(self):
        idx = self._selected_index()
        if idx is None:
            return
        if messagebox.askyesno("Conferma", "Eliminare la regola selezionata?"):
            self._rules().pop(idx)
            self.refresh_tree()

    def _move_up(self):
        idx = self._selected_index()
        if idx is None or idx == 0:
            return
        rules = self._rules()
        rules[idx - 1], rules[idx] = rules[idx], rules[idx - 1]
        self.refresh_tree()
        self._tree.selection_set(self._tree.get_children()[idx - 1])

    def _move_down(self):
        idx = self._selected_index()
        rules = self._rules()
        if idx is None or idx >= len(rules) - 1:
            return
        rules[idx + 1], rules[idx] = rules[idx], rules[idx + 1]
        self.refresh_tree()
        self._tree.selection_set(self._tree.get_children()[idx + 1])

    def _check(self):
        """Quante immagini pesca ogni regola? Serve a scoprire le regole vuote."""
        rules = self._rules()
        if not rules:
            messagebox.showinfo("Verifica", "Nessuna regola in questo elenco.")
            return

        library = self.config_data.get("image_library", {})
        periodi = self.config_data.get("periods", []) or []
        oggi = date.today()
        lines = []

        def conta(regola):
            """Immagini che soddisfano la regola, e quante mancano dal disco."""
            trovate = mancanti = 0
            for image, tags in library.items():
                if not match_rule(tags, regola):
                    continue
                if Path(resolve_image_path(self.config_data, image)).is_file():
                    trovate += 1
                else:
                    mancanti += 1
            return trovate, mancanti

        for r in rules:
            etichetta = descrivi_fascia(r, oggi, self.config_data)
            trovate, mancanti = conta(r)
            extra = f"  ({mancanti} non trovate su disco)" if mancanti else ""
            lines.append(f"{etichetta}: {trovate} immagini{extra}")

            # Ogni periodo vieta tag diversi, quindi la stessa regola pesca da
            # pool diversi secondo la stagione. Il conteggio senza periodo e'
            # quello che non si verifica mai nella realta'.
            for p in periodi:
                vietati = set(p.get("exclude", []))
                richiesti = list(p.get("require", []))
                if not vietati and not richiesti:
                    continue
                patched = dict(r)
                if vietati:
                    patched["exclude"] = sorted(set(r.get("exclude", [])) | vietati)
                if richiesti:
                    patched["include"] = sorted(set(r.get("include", [])) | set(richiesti))
                n, _ = conta(patched)
                segnale = "   <-- poche" if n < 5 else ""
                lines.append(f"      in {p.get('name', '?')}: {n}{segnale}")

        messagebox.showinfo("Verifica regole", "\n".join(lines))


def match_rule(image_tags, rule: dict) -> bool:
    """Stessa logica di app.image_matches_rule."""
    tags = set(image_tags or [])
    for t in rule.get("exclude", []):
        if t in tags:
            return False
    include = rule.get("include", [])
    if not include:
        return True
    if rule.get("match", "all") == "any":
        return any(t in tags for t in include)
    return all(t in tags for t in include)


def valid_time(t: str) -> bool:
    """
    Orario valido: 'HH:MM' oppure un'ancora solare ('sunset', 'dawn-20m').
    Le ancore seguono il sole giorno per giorno, quindi una fascia scritta cosi'
    resta corretta da giugno a dicembre senza essere spostata a mano.
    """
    t = str(t).strip()
    if sun.is_solar(t):
        return True
    try:
        h, m = t.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        return False


def coords_of(config_data: dict) -> tuple[float, float]:
    return sun.coords(config_data)


def descrivi_fascia(rule: dict, giorno: date, config_data: dict) -> str:
    """'sunset-40m (19:18)-dusk+30m (20:58)' per la lista delle regole."""
    lat, lon = coords_of(config_data)
    return (
        f"{sun.describe(rule.get('from', '?'), giorno, lat, lon)}"
        f"-{sun.describe(rule.get('to', '?'), giorno, lat, lon)}"
    )


_MOTORE = None


def carica_motore():
    """
    Il motore di app.py, importato su richiesta e riusato.

    L'anteprima e la verifica anno chiamano le funzioni vere dello scheduler
    invece di riprodurne la logica: due implementazioni della stessa risoluzione
    divergerebbero, e un'anteprima che non coincide con la realta' e' peggio che
    non averla.
    """
    global _MOTORE
    if _MOTORE is None:
        try:
            import app

            _MOTORE = app
        except Exception as e:
            messagebox.showerror(
                "Motore non disponibile",
                f"Non riesco a caricare app.py:\n{e}\n\n"
                "Anteprima e verifica anno non sono disponibili.",
            )
            return None
    return _MOTORE


ANCORE_IT = [
    ("", "— orario fisso —"),
    ("dawn", "dawn — crepuscolo del mattino"),
    ("sunrise", "sunrise — alba"),
    ("noon", "noon — mezzogiorno solare"),
    ("sunset", "sunset — tramonto"),
    ("dusk", "dusk — crepuscolo della sera"),
]


class RuleDialog(tk.Toplevel):
    def __init__(self, parent, config_data: dict, title="Regola", initial=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.config_data = config_data
        self.result: dict | None = None

        initial = initial or {}
        all_tags = sorted(config_data.get("tags", []), key=str.lower)

        # Orari
        times = tk.Frame(self, bg=BG)
        times.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4))

        tk.Label(times, text="Dalle", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._from = tk.StringVar(value=initial.get("from", "09:00"))
        tk.Entry(
            times,
            textvariable=self._from,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=8,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        tk.Label(times, text="alle", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left"
        )
        self._to = tk.StringVar(value=initial.get("to", "12:00"))
        tk.Entry(
            times,
            textvariable=self._to,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=8,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        tk.Label(times, text="cambia ogni", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(16, 4)
        )
        self._rotate = tk.IntVar(value=int(initial.get("rotate_minutes", 60)))
        tk.Spinbox(
            times,
            from_=1,
            to=1440,
            textvariable=self._rotate,
            width=6,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            buttonbackground=BG3,
            relief="flat",
            font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Label(times, text="minuti", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(
            side="left", padx=4
        )

        # Liste tag
        tk.Label(
            self,
            text="Deve avere questi tag",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 9),
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(12, 2))
        tk.Label(
            self,
            text="Non deve avere questi tag",
            bg=BG,
            fg=DANGER,
            font=("Segoe UI Semibold", 9),
        ).grid(row=1, column=1, sticky="w", padx=16, pady=(12, 2))

        self._inc_list = self._make_tag_list(all_tags, initial.get("include", []))
        self._inc_list.grid(row=2, column=0, padx=16, sticky="n")

        self._exc_list = self._make_tag_list(all_tags, initial.get("exclude", []))
        self._exc_list.grid(row=2, column=1, padx=16, sticky="n")

        tk.Label(
            self,
            text="Ctrl+click per selezionarne più di uno.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))

        # Modalità match
        self._match = tk.StringVar(value=initial.get("match", "all"))
        mf = tk.Frame(self, bg=BG)
        mf.grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=8)
        ttk.Radiobutton(
            mf, text="Deve avere tutti i tag scelti", variable=self._match, value="all"
        ).pack(anchor="w")
        ttk.Radiobutton(
            mf, text="Ne basta almeno uno", variable=self._match, value="any"
        ).pack(anchor="w")

        # Aiuto sulle ancore solari, con l'orario che avrebbero oggi. Una fascia
        # scritta 'sunset-40m' non si controlla a occhio senza vedere che ora fa.
        lat, lon = coords_of(config_data)
        orari = sun.sun_times(date.today(), lat, lon)
        pezzi = [
            f"{nome} {orari[nome].strftime('%H:%M')}"
            for nome in ("dawn", "sunrise", "noon", "sunset", "dusk")
            if orari.get(nome)
        ]
        tk.Label(
            self,
            text="Negli orari puoi scrivere un'ancora solare invece dell'orologio:\n  "
            + "    ".join(pezzi)
            + "  (oggi)\ncon scostamento in minuti oppure ore: sunset-40m, dawn-20m, dusk+1h.",
            bg=BG,
            fg=ACCENT2,
            font=("Segoe UI", 8),
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 2))

        self._risolti = tk.Label(self, bg=BG, fg=FG2, font=("Segoe UI", 8), anchor="w")
        self._risolti.grid(row=6, column=0, columnspan=2, sticky="w", padx=16)
        for var in (self._from, self._to):
            var.trace_add("write", lambda *_: self._aggiorna_risolti())
        self._aggiorna_risolti()

        self._preview_lbl = tk.Label(
            self, bg=BG, fg=SUCCESS, font=("Segoe UI", 9), anchor="w"
        )
        self._preview_lbl.grid(row=7, column=0, columnspan=2, sticky="w", padx=16)

        # Bottoni
        bf = tk.Frame(self, bg=BG, pady=10)
        bf.grid(row=8, column=0, columnspan=2)
        ttk.Button(bf, text="Quante immagini?", command=self._count).pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="Annulla", command=self.destroy).pack(side="left")

        self.grab_set()
        self.wait_window()

    def _aggiorna_risolti(self):
        """Mostra a che ora cadono oggi gli estremi scritti, ancore comprese."""
        lat, lon = coords_of(self.config_data)
        oggi = date.today()
        pezzi = []
        for etichetta, var in (("dalle", self._from), ("alle", self._to)):
            valore = var.get().strip()
            if not valid_time(valore):
                pezzi.append(f"{etichetta} ?")
            elif sun.is_solar(valore):
                pezzi.append(f"{etichetta} {sun.describe(valore, oggi, lat, lon)}")
            else:
                pezzi.append(f"{etichetta} {valore}")
        self._risolti.config(text="Oggi: " + "   ".join(pezzi))

    def _make_tag_list(self, all_tags, selected) -> tk.Listbox:
        lb = tk.Listbox(
            self,
            bg=BG2,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground=BG,
            selectmode="multiple",
            width=26,
            height=9,
            relief="flat",
            borderwidth=0,
            exportselection=False,
            font=("Segoe UI", 9),
        )
        for i, t in enumerate(all_tags):
            lb.insert("end", t)
            if t in (selected or []):
                lb.selection_set(i)
        return lb

    def _collect(self, lb: tk.Listbox) -> list[str]:
        return [lb.get(i) for i in lb.curselection()]

    def _build_rule(self) -> dict:
        return {
            "from": self._from.get().strip(),
            "to": self._to.get().strip(),
            "include": self._collect(self._inc_list),
            "exclude": self._collect(self._exc_list),
            "match": self._match.get(),
            "rotate_minutes": int(self._rotate.get()),
        }

    def _count(self):
        rule = self._build_rule()
        library = self.config_data.get("image_library", {})
        n = sum(
            1
            for image, tags in library.items()
            if match_rule(tags, rule)
            and Path(resolve_image_path(self.config_data, image)).is_file()
        )
        self._preview_lbl.config(
            text=f"{n} immagini corrispondono a questa regola.",
            fg=SUCCESS if n else DANGER,
        )

    def _valid_time(self, t: str) -> bool:
        return valid_time(t)

    def _ok(self):
        rule = self._build_rule()
        if not self._valid_time(rule["from"]):
            messagebox.showerror("Errore", f"Orario 'Dalle' non valido: {rule['from']}")
            return
        if not self._valid_time(rule["to"]):
            messagebox.showerror("Errore", f"Orario 'Alle' non valido: {rule['to']}")
            return
        if not rule["include"] and not rule["exclude"]:
            if not messagebox.askyesno(
                "Nessun tag",
                "Questa regola non filtra nulla: pescherà da tutta la libreria.\nContinuare?",
            ):
                return
        self.result = rule
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: periodi dell'anno
# ═══════════════════════════════════════════════════════════════════════════════


MESI_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

GIORNI_MESE = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def md_valido(s: str) -> bool:
    """'10-20' valido. Il 29 febbraio si accetta: l'anno non entra nel confronto."""
    try:
        m, g = str(s).strip().split("-")
        m, g = int(m), int(g)
    except Exception:
        return False
    return 1 <= m <= 12 and 1 <= g <= GIORNI_MESE[m - 1]


def md_ordinale(s: str) -> int | None:
    """'10-20' -> 1020, per i confronti fra date senza anno."""
    try:
        m, g = str(s).strip().split("-")[-2:]
        return int(m) * 100 + int(g)
    except Exception:
        return None


def md_leggibile(s: str) -> str:
    """'10-20' -> '20 ottobre'."""
    try:
        m, g = str(s).strip().split("-")
        return f"{int(g)} {MESI_IT[int(m) - 1]}"
    except Exception:
        return str(s)


def md_copre(inizio: int, fine: int, giorno: date) -> bool:
    """Se l'intervallo (ordinali MMGG) contiene quel giorno. Gestisce il capodanno."""
    oggi = giorno.month * 100 + giorno.day
    if inizio <= fine:
        return inizio <= oggi <= fine
    return oggi >= inizio or oggi <= fine


class PeriodsTab(tk.Frame):
    """
    I periodi dell'anno: intervalli di date che modulano le regole casuali senza
    duplicarle. L'ordine conta, vince il primo che copre la data, quindi i periodi
    festivi vanno sopra quelli stagionali.
    """

    def __init__(self, parent, config_data: dict, app):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.app = app
        self._build()

    def _periods(self) -> list:
        return self.config_data.setdefault("periods", [])

    def _build(self):
        tk.Label(
            self,
            text="Vince il primo periodo che copre la data: i periodi festivi vanno "
            "sopra quelli stagionali.\nUn periodo non riscrive le regole, le filtra — "
            "e puo' portarsi fasce proprie solo per le ore che gli interessano.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 8))

        self._tree = ttk.Treeview(
            self,
            columns=("nome", "dal", "al", "tag", "regole"),
            show="headings",
            height=10,
        )
        for c, t, w in (
            ("nome", "Periodo", 130),
            ("dal", "Dal", 110),
            ("al", "Al", 110),
            ("tag", "Tag vietati / preferiti", 340),
            ("regole", "Fasce proprie", 100),
        ):
            self._tree.heading(c, text=t)
            self._tree.column(c, width=w, anchor="w")
        self._tree.pack(fill="both", expand=True, padx=12)
        self._tree.bind("<Double-1>", lambda e: self._edit())

        bar = tk.Frame(self, bg=BG, pady=8)
        bar.pack(fill="x", padx=12)
        for testo, cmd in (
            ("Aggiungi", self._add),
            ("Modifica", self._edit),
            ("Elimina", self._delete),
            ("Su", self._up),
            ("Giu'", self._down),
        ):
            ttk.Button(bar, text=testo, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(
            bar, text="Verifica anno", style="Accent.TButton", command=self._check_year
        ).pack(side="right")

        self._status = tk.Label(
            self, bg=BG, fg=FG2, font=("Segoe UI", 9), justify="left", anchor="w"
        )
        self._status.pack(fill="x", padx=12, pady=(0, 10))

        self.refresh()

    def refresh(self):
        for i in self._tree.get_children():
            self._tree.delete(i)
        for idx, p in enumerate(self._periods()):
            etichette = []
            if p.get("exclude"):
                etichette.append("vieta " + ", ".join(p["exclude"]))
            if p.get("prefer"):
                minimo = p.get("prefer_min")
                etichette.append(
                    "preferisce "
                    + ", ".join(p["prefer"])
                    + (f" (min {minimo})" if minimo else "")
                )
            if p.get("require"):
                etichette.append("richiede " + ", ".join(p["require"]))

            rr = p.get("random_rules") or {}
            n_regole = 0
            for valore in rr.values():
                if isinstance(valore, list):
                    n_regole += len(valore)
                elif isinstance(valore, dict):
                    n_regole += sum(len(x or []) for x in valore.values())

            self._tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    p.get("name", "?"),
                    md_leggibile(p.get("from", "")),
                    md_leggibile(p.get("to", "")),
                    "; ".join(etichette) or "-",
                    f"{n_regole} fasce" if n_regole else "-",
                ),
            )
        self._aggiorna_copertura()

    def _aggiorna_copertura(self):
        """
        Avvisa sui giorni dell'anno che nessun periodo copre. Non e' cosmetico: un
        giorno scoperto non applica nessun filtro stagionale, e a luglio tornano
        le immagini invernali.
        """
        periodi = self._periods()
        if not periodi:
            self._status.config(
                text="Nessun periodo: le regole valgono uguali tutto l'anno.", fg=FG2
            )
            return

        intervalli = [
            (md_ordinale(p.get("from")), md_ordinale(p.get("to")), p.get("name", "?"))
            for p in periodi
        ]
        scoperti, conteggi = [], {}
        for d in range(365):
            g = date(2026, 1, 1) + timedelta(days=d)
            nome = next(
                (n for a, b, n in intervalli if a is not None and b is not None and md_copre(a, b, g)),
                None,
            )
            if nome is None:
                scoperti.append(g)
            else:
                conteggi[nome] = conteggi.get(nome, 0) + 1

        riepilogo = "   ".join(f"{n}: {c}gg" for n, c in conteggi.items())
        if not scoperti:
            self._status.config(
                text=f"Anno coperto per intero.   {riepilogo}", fg=SUCCESS
            )
            return

        # Raggruppa i giorni scoperti in blocchi contigui, piu' leggibili di un elenco
        blocchi, inizio = [], scoperti[0]
        for corrente, successivo in zip(scoperti, scoperti[1:] + [None]):
            if successivo is None or (successivo - corrente).days > 1:
                a = md_leggibile(f"{inizio.month:02d}-{inizio.day:02d}")
                b = md_leggibile(f"{corrente.month:02d}-{corrente.day:02d}")
                blocchi.append(a if corrente == inizio else f"{a} - {b}")
                inizio = successivo
        self._status.config(
            text=f"{len(scoperti)} giorni senza periodo: {'; '.join(blocchi[:4])}"
            f"{' ...' if len(blocchi) > 4 else ''}\n{riepilogo}",
            fg=DANGER,
        )

    def _selected(self) -> int | None:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        dlg = PeriodDialog(self, self.config_data, "Nuovo periodo")
        if dlg.result:
            self._periods().append(dlg.result)
            self.refresh()

    def _edit(self):
        i = self._selected()
        if i is None:
            return
        dlg = PeriodDialog(
            self, self.config_data, "Modifica periodo", initial=self._periods()[i]
        )
        if dlg.result:
            self._periods()[i] = dlg.result
            self.refresh()

    def _delete(self):
        i = self._selected()
        if i is None:
            return
        nome = self._periods()[i].get("name", "?")
        if messagebox.askyesno("Conferma", f"Eliminare il periodo '{nome}'?"):
            del self._periods()[i]
            self.refresh()

    def _move(self, delta: int):
        i = self._selected()
        if i is None:
            return
        j = i + delta
        periodi = self._periods()
        if not 0 <= j < len(periodi):
            return
        periodi[i], periodi[j] = periodi[j], periodi[i]
        self.refresh()
        self._tree.selection_set(str(j))

    def _up(self):
        self._move(-1)

    def _down(self):
        self._move(1)

    def _check_year(self):
        """
        Passa l'anno col motore vero e riporta le fasce con pochi candidati.
        E' la rete di sicurezza: un tag di troppo in un periodo puo' svuotare una
        fascia in una sola stagione, e sfogliando il config non si vede.
        """
        motore = carica_motore()
        if motore is None:
            return

        cfg = self.config_data
        righe, problemi = [], 0
        campioni = sorted(
            {date(2026, m, 15) for m in range(1, 13)}
            | {date(2026, 10, 28), date(2026, 12, 25)}
        )

        self._status.config(text="Verifica in corso...", fg=FG2)
        self.update_idletasks()
        motore.invalida_cache_file()

        for g in campioni:
            nome = (motore.periodo_attivo(cfg, g) or {}).get("name", "-")
            viste, peggiore, senza_regola = set(), None, []
            for h in range(24):
                t = datetime(g.year, g.month, g.day, h, 0)
                cand = motore.regole_candidate(cfg, t)
                if not cand:
                    senza_regola.append(h)
                    continue
                rule = cand[0][0]
                sig = motore._rule_signature(rule)
                if sig in viste:
                    continue
                viste.add(sig)
                n = len(motore.candidates_for_rule(cfg, rule))
                if peggiore is None or n < peggiore[0]:
                    peggiore = (n, descrivi_fascia(rule, g, cfg))

            if senza_regola:
                ore = ", ".join(f"{h:02d}:00" for h in senza_regola)
                righe.append(f"{g}  {nome}: nessuna regola alle {ore}")
                problemi += 1
            if peggiore and peggiore[0] < 5:
                righe.append(f"{g}  {nome}: solo {peggiore[0]} immagini su {peggiore[1]}")
                problemi += 1
            elif peggiore and not senza_regola:
                righe.append(f"{g}  {nome}: minimo {peggiore[0]} immagini, ok")

        self._aggiorna_copertura()
        testo = "\n".join(righe)
        if problemi:
            messagebox.showwarning(
                "Verifica anno",
                f"{problemi} segnalazioni.\n\n{testo}\n\n"
                "Una fascia con poche immagini resta quasi fissa per tutta la stagione.",
            )
        else:
            messagebox.showinfo("Verifica anno", f"Nessun problema.\n\n{testo}")


class PeriodDialog(tk.Toplevel):
    """Editor di un singolo periodo dell'anno."""

    def __init__(self, parent, config_data: dict, title="Periodo", initial=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.config_data = config_data
        self.result: dict | None = None
        self._initial = initial or {}
        initial = self._initial
        all_tags = sorted(config_data.get("tags", []), key=str.lower)

        top = tk.Frame(self, bg=BG)
        top.grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 2))

        tk.Label(top, text="Nome", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        # NON chiamarlo _name: tkinter usa Misc._name per il nome del widget e
        # sovrascriverlo rompe destroy().
        self._nome = tk.StringVar(value=initial.get("name", ""))
        tk.Entry(
            top, textvariable=self._nome, bg=ENTRY_BG, fg=FG, insertbackground=FG,
            relief="flat", width=18, font=("Segoe UI", 9),
        ).pack(side="left", padx=(6, 16))

        tk.Label(top, text="dal", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self._from = tk.StringVar(value=initial.get("from", "01-01"))
        tk.Entry(
            top, textvariable=self._from, bg=ENTRY_BG, fg=FG, insertbackground=FG,
            relief="flat", width=8, font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        tk.Label(top, text="al", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self._to = tk.StringVar(value=initial.get("to", "12-31"))
        tk.Entry(
            top, textvariable=self._to, bg=ENTRY_BG, fg=FG, insertbackground=FG,
            relief="flat", width=8, font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        self._date_lbl = tk.Label(self, bg=BG, fg=FG2, font=("Segoe UI", 9), anchor="w")
        self._date_lbl.grid(row=1, column=0, columnspan=3, sticky="w", padx=16)
        for var in (self._from, self._to):
            var.trace_add("write", lambda *_: self._aggiorna_date())

        tk.Label(
            self,
            text="Formato mese-giorno, senza anno: il periodo si ripete ogni anno.\n"
            "Se la data finale precede quella iniziale, il periodo scavalca il capodanno.",
            bg=BG, fg=FG2, font=("Segoe UI Italic", 8), justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=16, pady=(2, 8))

        for col, (testo, colore) in enumerate(
            (
                ("Tag vietati in questo periodo", DANGER),
                ("Tag preferiti", ACCENT2),
                ("Tag obbligatori", ACCENT),
            )
        ):
            tk.Label(
                self, text=testo, bg=BG, fg=colore, font=("Segoe UI Semibold", 9)
            ).grid(row=3, column=col, sticky="w", padx=16, pady=(0, 2))

        self._exc = self._lista(all_tags, initial.get("exclude", []))
        self._exc.grid(row=4, column=0, padx=16, sticky="n")
        self._pref = self._lista(all_tags, initial.get("prefer", []))
        self._pref.grid(row=4, column=1, padx=16, sticky="n")
        self._req = self._lista(all_tags, initial.get("require", []))
        self._req.grid(row=4, column=2, padx=16, sticky="n")

        pm = tk.Frame(self, bg=BG)
        pm.grid(row=5, column=0, columnspan=3, sticky="w", padx=16, pady=(8, 0))
        tk.Label(
            pm,
            text="Restringi ai preferiti solo se ne restano almeno",
            bg=BG, fg=FG, font=("Segoe UI", 9),
        ).pack(side="left")
        self._prefer_min = tk.IntVar(value=int(initial.get("prefer_min", 1) or 1))
        tk.Spinbox(
            pm, from_=1, to=200, textvariable=self._prefer_min, width=5,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, buttonbackground=BG3,
            relief="flat", font=("Segoe UI", 9),
        ).pack(side="left", padx=6)
        tk.Label(pm, text="immagini", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")

        tk.Label(
            self,
            text="I vietati si sommano a quelli di ogni regola. I preferiti restringono il\n"
            "pool solo se ne resta abbastanza: con pochi tag preferiti la fascia\n"
            "diventerebbe quasi fissa. Le fasce orarie proprie del periodo si\n"
            "conservano, e si modificano a mano nel config.",
            bg=BG, fg=FG2, font=("Segoe UI Italic", 8), justify="left",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=16, pady=(8, 0))

        bf = tk.Frame(self, bg=BG, pady=12)
        bf.grid(row=7, column=0, columnspan=3)
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="Annulla", command=self.destroy).pack(side="left")

        self._aggiorna_date()
        self.grab_set()
        self.wait_window()

    def _lista(self, all_tags, selected) -> tk.Listbox:
        lb = tk.Listbox(
            self, bg=BG2, fg=FG, selectbackground=ACCENT, selectforeground=BG,
            selectmode="multiple", width=24, height=10, relief="flat",
            borderwidth=0, exportselection=False, font=("Segoe UI", 9),
        )
        for i, t in enumerate(all_tags):
            lb.insert("end", t)
            if t in (selected or []):
                lb.selection_set(i)
        return lb

    def _aggiorna_date(self):
        a, b = self._from.get().strip(), self._to.get().strip()
        if not (md_valido(a) and md_valido(b)):
            self._date_lbl.config(text="Date non valide (formato MM-GG).", fg=DANGER)
            return
        oa, ob = md_ordinale(a), md_ordinale(b)
        salto = " (scavalca il capodanno)" if oa > ob else ""
        giorni = sum(
            1
            for d in range(365)
            if md_copre(oa, ob, date(2026, 1, 1) + timedelta(days=d))
        )
        self._date_lbl.config(
            text=f"Dal {md_leggibile(a)} al {md_leggibile(b)}{salto} - {giorni} giorni.",
            fg=FG2,
        )

    def _collect(self, lb) -> list[str]:
        return [lb.get(i) for i in lb.curselection()]

    def _ok(self):
        nome = self._nome.get().strip()
        if not nome:
            messagebox.showerror("Errore", "Dai un nome al periodo.")
            return

        a, b = self._from.get().strip(), self._to.get().strip()
        for etichetta, valore in (("iniziale", a), ("finale", b)):
            if not md_valido(valore):
                messagebox.showerror(
                    "Errore",
                    f"Data {etichetta} non valida: '{valore}'.\nFormato MM-GG, es. 10-20.",
                )
                return

        period = {"name": nome, "from": a, "to": b}
        esclusi = self._collect(self._exc)
        if esclusi:
            period["exclude"] = esclusi
        preferiti = self._collect(self._pref)
        if preferiti:
            period["prefer"] = preferiti
            if int(self._prefer_min.get()) > 1:
                period["prefer_min"] = int(self._prefer_min.get())
        richiesti = self._collect(self._req)
        if richiesti:
            period["require"] = richiesti
        # Le fasce proprie non si editano qui: si conservano cosi' come sono.
        if self._initial.get("random_rules"):
            period["random_rules"] = self._initial["random_rules"]

        self.result = period
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: anteprima di una giornata
# ═══════════════════════════════════════════════════════════════════════════════


class PreviewTab(tk.Frame):
    """
    La giornata risolta ora per ora: periodo attivo, regola vincente, orari solari
    reali, pool e immagine che uscirebbe.

    Usa il motore di app.py, non una sua imitazione: se l'anteprima e lo scheduler
    divergessero, l'anteprima non servirebbe a niente.
    """

    def __init__(self, parent, config_data: dict, app):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.app = app
        self._build()

    def _build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(10, 6))

        tk.Label(top, text="Data:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        oggi = date.today()
        self._data = tk.StringVar(value=oggi.isoformat())
        tk.Entry(
            top, textvariable=self._data, bg=ENTRY_BG, fg=FG, insertbackground=FG,
            relief="flat", width=12, font=("Segoe UI", 10),
        ).pack(side="left", padx=8)

        for testo, delta in (("-1 g", -1), ("+1 g", 1), ("+1 sett", 7), ("+1 mese", 30)):
            ttk.Button(top, text=testo, width=8, command=lambda d=delta: self._sposta(d)).pack(
                side="left", padx=2
            )

        ttk.Button(
            top, text="Calcola", style="Accent.TButton", command=self._calcola
        ).pack(side="left", padx=(12, 0))

        self._intestazione = tk.Label(
            self, bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 10), anchor="w", justify="left"
        )
        self._intestazione.pack(fill="x", padx=12, pady=(2, 6))

        self._tree = ttk.Treeview(
            self,
            columns=("ora", "origine", "fascia", "tag", "pool", "immagine"),
            show="headings",
            height=16,
        )
        for c, t, w in (
            ("ora", "Ora", 60),
            ("origine", "Regola vincente", 210),
            ("fascia", "Fascia (orario reale)", 250),
            ("tag", "Tag", 250),
            ("pool", "Pool", 55),
            ("immagine", "Immagine", 300),
        ):
            self._tree.heading(c, text=t)
            self._tree.column(c, width=w, anchor="w")
        self._tree.pack(fill="both", expand=True, padx=12)

        self._nota = tk.Label(
            self, bg=BG, fg=FG2, font=("Segoe UI", 9), anchor="w", justify="left"
        )
        self._nota.pack(fill="x", padx=12, pady=(6, 10))

        self._calcola()

    def _sposta(self, giorni: int):
        try:
            g = date.fromisoformat(self._data.get().strip()) + timedelta(days=giorni)
        except ValueError:
            g = date.today()
        self._data.set(g.isoformat())
        self._calcola()

    def _calcola(self):
        for i in self._tree.get_children():
            self._tree.delete(i)

        try:
            giorno = date.fromisoformat(self._data.get().strip())
        except ValueError:
            self._intestazione.config(text="Data non valida (formato AAAA-MM-GG).", fg=DANGER)
            return

        motore = carica_motore()
        if motore is None:
            return

        cfg = self.config_data
        lat, lon = coords_of(cfg)
        orari = sun.sun_times(giorno, lat, lon)
        periodo = motore.periodo_attivo(cfg, giorno)

        def hm(chiave):
            v = orari.get(chiave)
            return v.strftime("%H:%M") if v else "n.d."

        giorni_it = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
        self._intestazione.config(
            text=f"{giorni_it[giorno.weekday()]} {giorno.strftime('%d/%m/%Y')}   "
            f"periodo: {periodo.get('name') if periodo else 'nessuno'}   |   "
            f"dawn {hm('dawn')}  alba {hm('sunrise')}  mezzogiorno {hm('noon')}  "
            f"tramonto {hm('sunset')}  dusk {hm('dusk')}",
            fg=ACCENT,
        )

        self._nota.config(text="Calcolo in corso...", fg=FG2)
        self.update_idletasks()
        motore.invalida_cache_file()

        try:
            sequenza = motore.sequenza_giornaliera(cfg, giorno)
        except Exception as e:
            self._nota.config(text=f"Errore nel motore: {e}", fg=DANGER)
            return

        if not sequenza:
            self._nota.config(
                text="Nessuna regola casuale copre questa giornata: si ripiegherebbe "
                "sulla modalita' programmata.",
                fg=DANGER,
            )
            return

        for e in sequenza:
            rule = e["rule"]
            tag = []
            if rule.get("include"):
                tag.append(("+" if rule.get("match", "all") == "all" else "/").join(rule["include"]))
            if rule.get("exclude"):
                tag.append("-" + ",-".join(rule["exclude"]))
            if rule.get("prefer"):
                tag.append("~" + ",~".join(rule["prefer"]))
            self._tree.insert(
                "",
                "end",
                values=(
                    f"{e['minuto'] // 60:02d}:{e['minuto'] % 60:02d}",
                    e["origine"],
                    descrivi_fascia(rule, giorno, cfg),
                    " ".join(tag),
                    e["pool"],
                    e["image"].replace("\\", "/").split("/")[-1],
                ),
            )

        distinte = len({e["image"] for e in sequenza})
        minimo = min(e["pool"] for e in sequenza)
        self._nota.config(
            text=f"{len(sequenza)} finestre, {distinte} immagini distinte "
            f"(nella stessa giornata non si ripetono). Pool piu' piccolo: {minimo} immagini."
            + ("   Attenzione: sotto le 5 immagini la fascia e' quasi fissa." if minimo < 5 else ""),
            fg=DANGER if minimo < 5 else FG2,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Editor slot (modalità programmata)
# ═══════════════════════════════════════════════════════════════════════════════


class SlotEditor(tk.Frame):
    """Lista di slot [{from, to, image, label}]."""

    def __init__(self, parent, config_data: dict, path: list[str]):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.path = path
        self._build()

    def _get_slots(self) -> list:
        d = self.config_data
        for k in self.path:
            d = d[k]
        return d

    def _build(self):
        cols = ("from", "to", "label", "image")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        self._tree.heading("from", text="Dalle")
        self._tree.heading("to", text="Alle")
        self._tree.heading("label", text="Etichetta")
        self._tree.heading("image", text="Immagine")
        self._tree.column("from", width=70, anchor="center")
        self._tree.column("to", width=70, anchor="center")
        self._tree.column("label", width=150)
        self._tree.column("image", width=420)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        btns = tk.Frame(self, bg=BG, padx=8)
        btns.pack(side="left", fill="y")
        ttk.Button(btns, text="Aggiungi", command=self._add_slot).pack(fill="x", pady=3)
        ttk.Button(btns, text="Modifica", command=self._edit_slot).pack(
            fill="x", pady=3
        )
        ttk.Button(
            btns, text="Elimina", style="Danger.TButton", command=self._delete_slot
        ).pack(fill="x", pady=3)
        ttk.Button(btns, text="Su", command=self._move_up).pack(fill="x", pady=3)
        ttk.Button(btns, text="Giù", command=self._move_down).pack(fill="x", pady=3)

        self._refresh_tree()
        self._tree.bind("<Double-1>", lambda e: self._edit_slot())

    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        for slot in self._get_slots():
            self._tree.insert(
                "",
                "end",
                values=(
                    slot.get("from", ""),
                    slot.get("to", ""),
                    slot.get("label", ""),
                    slot.get("image", ""),
                ),
            )

    def _selected_index(self) -> int | None:
        sel = self._tree.selection()
        return self._tree.index(sel[0]) if sel else None

    def _add_slot(self):
        dlg = SlotDialog(self, title="Nuovo slot", config_data=self.config_data)
        if dlg.result:
            self._get_slots().append(dlg.result)
            self._refresh_tree()

    def _edit_slot(self):
        idx = self._selected_index()
        if idx is None:
            return
        slots = self._get_slots()
        dlg = SlotDialog(
            self,
            title="Modifica slot",
            initial=slots[idx],
            config_data=self.config_data,
        )
        if dlg.result:
            slots[idx] = dlg.result
            self._refresh_tree()

    def _delete_slot(self):
        idx = self._selected_index()
        if idx is None:
            return
        slots = self._get_slots()
        if messagebox.askyesno(
            "Conferma", f"Eliminare lo slot '{slots[idx].get('label','')}'?"
        ):
            slots.pop(idx)
            self._refresh_tree()

    def _move_up(self):
        idx = self._selected_index()
        if idx is None or idx == 0:
            return
        slots = self._get_slots()
        slots[idx - 1], slots[idx] = slots[idx], slots[idx - 1]
        self._refresh_tree()
        self._tree.selection_set(self._tree.get_children()[idx - 1])

    def _move_down(self):
        idx = self._selected_index()
        slots = self._get_slots()
        if idx is None or idx >= len(slots) - 1:
            return
        slots[idx + 1], slots[idx] = slots[idx], slots[idx + 1]
        self._refresh_tree()
        self._tree.selection_set(self._tree.get_children()[idx + 1])


class SlotDialog(tk.Toplevel):
    def __init__(self, parent, title="Slot", initial=None, config_data=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.config_data = config_data or {}
        self.result: dict | None = None
        self._preview_photo = None

        initial = initial or {}
        row = 0

        def lbl(text, r):
            tk.Label(self, text=text, bg=BG, fg=FG, font=("Segoe UI", 9)).grid(
                row=r, column=0, sticky="w", padx=16, pady=6
            )

        def entry(r, var):
            e = tk.Entry(
                self,
                textvariable=var,
                bg=ENTRY_BG,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                width=30,
                font=("Segoe UI", 9),
            )
            e.grid(row=r, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
            return e

        lbl("Etichetta:", row)
        self._label = tk.StringVar(value=initial.get("label", ""))
        entry(row, self._label)
        row += 1

        lbl("Dalle (HH:MM):", row)
        self._from = tk.StringVar(value=initial.get("from", "08:00"))
        entry(row, self._from)
        row += 1

        lbl("Alle  (HH:MM):", row)
        self._to = tk.StringVar(value=initial.get("to", "12:00"))
        entry(row, self._to)
        row += 1

        lbl("Immagine:", row)
        self._image = tk.StringVar(value=initial.get("image", ""))
        tk.Entry(
            self,
            textvariable=self._image,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=24,
            font=("Segoe UI", 9),
        ).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(self, text="...", command=self._browse_image, width=3).grid(
            row=row, column=2, padx=(0, 8)
        )
        row += 1

        self._preview_img_label = tk.Label(self, bg=BG)
        self._preview_img_label.grid(row=row, column=0, columnspan=3, pady=4)
        row += 1

        self._preview_lbl = tk.Label(self, bg=BG, fg=FG2, font=("Segoe UI Italic", 8))
        self._preview_lbl.grid(row=row, column=0, columnspan=3, padx=16, pady=2)
        row += 1

        self._image.trace_add("write", self._update_preview)
        self._update_preview()

        bf = tk.Frame(self, bg=BG, pady=8)
        bf.grid(row=row, column=0, columnspan=3)
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="Annulla", command=self.destroy).pack(side="left")

        self.columnconfigure(1, weight=1)
        self.grab_set()
        self.wait_window()

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Seleziona immagine sfondo",
            initialdir=current_base_path(self.config_data) or None,
            filetypes=[
                ("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("Tutti", "*.*"),
            ],
        )
        if path:
            self._image.set(to_library_key(self.config_data, path))

    def _clear_preview_image(self):
        self._preview_photo = None
        self._preview_img_label.config(image="", text="")

    def _update_preview(self, *_):
        raw = self._image.get()
        path = resolve_image_path(self.config_data, raw) if raw else ""

        if path and Path(path).is_file():
            if HAS_PIL:
                try:
                    img = Image.open(path)
                    img.thumbnail((160, 100), Image.Resampling.LANCZOS)
                    self._preview_photo = ImageTk.PhotoImage(img)
                    self._preview_img_label.config(image=self._preview_photo, text="")
                    self._preview_lbl.config(text=Path(path).name, fg=SUCCESS)
                except Exception:
                    self._clear_preview_image()
                    self._preview_lbl.config(
                        text=f"{Path(path).name} (anteprima non disponibile)",
                        fg=SUCCESS,
                    )
            else:
                self._clear_preview_image()
                self._preview_lbl.config(text=Path(path).name, fg=SUCCESS)
        elif raw:
            self._clear_preview_image()
            self._preview_lbl.config(text="File non trovato", fg=DANGER)
        else:
            self._clear_preview_image()
            self._preview_lbl.config(text="")

    def _validate_time(self, t: str) -> bool:
        return valid_time(t)

    def _ok(self):
        frm = self._from.get().strip()
        to = self._to.get().strip()
        if not self._validate_time(frm):
            messagebox.showerror("Errore", f"Orario 'Dalle' non valido: {frm}")
            return
        if not self._validate_time(to):
            messagebox.showerror("Errore", f"Orario 'Alle' non valido: {to}")
            return
        self.result = {
            "from": frm,
            "to": to,
            "image": self._image.get().strip(),
            "label": self._label.get().strip(),
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  Editor giorni speciali
# ═══════════════════════════════════════════════════════════════════════════════


class SpecialDaysEditor(tk.Frame):
    def __init__(self, parent, config_data: dict):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self._selected_date: str | None = None
        self._build()

    def _build(self):
        left = tk.Frame(self, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 12))

        tk.Label(
            left, text="Date speciali", bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 10)
        ).pack(anchor="w", pady=(0, 6))

        self._date_listbox = tk.Listbox(
            left,
            bg=BG2,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground=BG,
            width=18,
            height=16,
            relief="flat",
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        self._date_listbox.pack(fill="y", expand=True)
        self._date_listbox.bind("<<ListboxSelect>>", lambda e: self._on_date_select())

        btns = tk.Frame(left, bg=BG)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Aggiungi", command=self._add_date).pack(side="left")
        ttk.Button(
            btns, text="Elimina", style="Danger.TButton", command=self._delete_date
        ).pack(side="left", padx=4)

        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._slot_frame = tk.Frame(right, bg=BG)
        self._slot_frame.pack(fill="both", expand=True)

        self._refresh_dates()

    def _refresh_dates(self):
        self._date_listbox.delete(0, "end")
        for d in sorted(self.config_data.get("special_days", {}).keys()):
            self._date_listbox.insert("end", d)

    def _on_date_select(self):
        sel = self._date_listbox.curselection()
        if not sel:
            return
        self._selected_date = self._date_listbox.get(sel[0])
        self._refresh_slot_editor()

    def _refresh_slot_editor(self):
        for w in self._slot_frame.winfo_children():
            w.destroy()
        if not self._selected_date:
            return
        tk.Label(
            self._slot_frame,
            text=f"Slot per {self._selected_date}",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(0, 6))
        SlotEditor(
            self._slot_frame, self.config_data, ["special_days", self._selected_date]
        ).pack(fill="both", expand=True)

    def _add_date(self):
        if HAS_CALENDAR:
            dlg = tk.Toplevel(self)
            dlg.title("Seleziona data")
            dlg.configure(bg=BG)
            dlg.resizable(False, False)
            tk.Label(
                dlg, text="Seleziona la data:", bg=BG, fg=FG, font=("Segoe UI", 9)
            ).pack(padx=16, pady=8)
            cal = DateEntry(
                dlg,
                width=12,
                date_pattern="yyyy-mm-dd",
                background=ACCENT,
                foreground=BG,
            )
            cal.pack(padx=16)
            result = [None]

            def ok():
                result[0] = cal.get()
                dlg.destroy()

            ttk.Button(dlg, text="OK", style="Accent.TButton", command=ok).pack(pady=12)
            dlg.grab_set()
            self.wait_window(dlg)
            date_str = result[0]
        else:
            date_str = simpledialog.askstring(
                "Data speciale", "Inserisci la data (YYYY-MM-DD):", parent=self
            )

        if not date_str:
            return
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "Errore", "Formato data non valido (atteso YYYY-MM-DD)."
            )
            return

        self.config_data.setdefault("special_days", {}).setdefault(date_str, [])
        self._refresh_dates()

    def _delete_date(self):
        if not self._selected_date:
            return
        if messagebox.askyesno(
            "Conferma", f"Eliminare il giorno speciale {self._selected_date}?"
        ):
            self.config_data["special_days"].pop(self._selected_date, None)
            self._selected_date = None
            for w in self._slot_frame.winfo_children():
                w.destroy()
            self._refresh_dates()


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ChametigerEditor()
    app.mainloop()
