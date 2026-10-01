"""
Chametiger - Editor grafico della configurazione
Richiede: tkinter (stdlib), Pillow
"""

import copy
import json
import socket
import tkinter as tk
import subprocess
import sys
import threading
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import date, datetime, timedelta

import date_mobili
import sun
from versione import VERSIONE

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
    cfg.setdefault("tags", [])
    cfg.setdefault("image_library", {})
    # history_days NON viene piu' aggiunta qui: l'editor non la espone, e un
    # config che non la ha usa il default di app.py. Quelli che ce l'hanno la
    # conservano, cosi' il comportamento non cambia sotto i piedi a nessuno.
    cfg.setdefault("seasons", [])
    cfg.setdefault("events", [])
    cfg.setdefault("latitude", 40.8518)  # Napoli
    cfg.setdefault("longitude", 14.2681)

    rules = cfg.setdefault("random_rules", {})
    rules.setdefault("weekday", [])
    rules.setdefault("weekend", [])
    rules.setdefault("overrides", {})
    for day in WEEKDAYS_ORDER:
        rules["overrides"].setdefault(day, [])

    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
#  Finestra principale
# ═══════════════════════════════════════════════════════════════════════════════


class ChametigerEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Chametiger {VERSIONE} - Editor Configurazione")
        self.geometry("1040x780")
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
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            header,
            text=f"v{VERSIONE}",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(6, 0), pady=(6, 0))
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

        mascot_width = 0
        if HAS_PIL and HEADER_BG_IMAGE_FILE.is_file():
            try:
                header_bg_img = Image.open(HEADER_BG_IMAGE_FILE)
                # crop() elimina i margini trasparenti del PNG, che altrimenti
                # occuperebbero spazio coprendo le ultime tab.
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

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # place(in_=nb, ...) usa il Notebook come riferimento: relx=1.0 = bordo
        # destro, rely=0.0 = bordo superiore (la linea delle tab); anchor="se"
        # mette l'angolo in basso a destra dell'immagine su quel punto.
        if mascot_width:
            header_bg_label = tk.Label(self, image=self._header_bg_image, bg=BG, bd=0)
            header_bg_label.place(in_=nb, relx=1.0, rely=0.0, anchor="se")

        self._build_tags_tab(nb)
        self._build_library_tab(nb)
        self._build_periods_tab(nb)
        self._build_rule_tabs(nb)
        self._build_random_override_tab(nb)
        self._build_preview_tab(nb)
        self._build_settings_tab(nb)
        nb.select(nb.index("end") - 1)  # tab predefinita all'avvio: Impostazioni

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

    def _build_rule_tabs(self, nb: ttk.Notebook):
        self._rule_editors = []
        hint = (
            "Le regole di base valgono tutto l'anno, filtrate dalla stagione del giorno.\n"
            "Ordine: fasce degli eventi, fasce della stagione, override del giorno, "
            "poi feriali/weekend. La prima che copre l'ora attuale vince."
        )

        for key, label in (("weekday", "Feriali"), ("weekend", "Weekend")):
            frame = ttk.Frame(nb)
            nb.add(frame, text=label)
            tk.Label(
                frame, text=hint, bg=BG, fg=FG2, font=("Segoe UI", 9), justify="left"
            ).pack(anchor="w", padx=12, pady=(10, 6))
            ed = RuleEditor(frame, self.config_data, ["random_rules", key])
            ed.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self._rule_editors.append(ed)

    def _build_periods_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Stagioni ed eventi")
        self._periods_tab = PeriodsTab(frame, self.config_data, self)
        self._periods_tab.pack(fill="both", expand=True)

    def _build_preview_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Anteprima")
        self._preview_tab = PreviewTab(frame, self.config_data, self)
        self._preview_tab.pack(fill="both", expand=True)

    def _build_random_override_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="Override giorno")

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
                'Tema applicato.\nPremi "Salva configurazione" per mantenerlo ai prossimi avvii.',
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
        self._lat_var = tk.StringVar(
            value=str(self.config_data.get("latitude", 40.8518))
        )
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
        self._lon_var = tk.StringVar(
            value=str(self.config_data.get("longitude", 14.2681))
        )
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
                    text="Latitudine fra -90 e 90, longitudine fra -180 e 180.",
                    fg=DANGER,
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
        Tutte le regole che usano i tag, STAGIONI ED EVENTI COMPRESI: senza,
        rinominare o cancellare un tag lascerebbe i periodi che lo citano
        puntati su un tag che non esiste piu', in silenzio.
        """

        def raccogli(rules):
            out = list(rules.get("weekday", []) or []) + list(
                rules.get("weekend", []) or []
            )
            for day_rules in (rules.get("overrides", {}) or {}).values():
                out += list(day_rules or [])
            return out

        out = raccogli(self.config_data.get("random_rules", {}))
        periodi = list(self.config_data.get("seasons", []) or []) + list(
            self.config_data.get("events", []) or []
        )
        for period in periodi:
            # Il periodo stesso conta come utilizzo dei suoi tag. Le liste
            # vanno passate per RIFERIMENTO, non copiate: _rename e _delete le
            # modificano in place, e su una copia il rinomino non arriverebbe
            # mai al config.
            for chiave_periodo in ("require", "tags", "prefer", "veto"):
                lst = period.get(chiave_periodo)
                if isinstance(lst, list):
                    out.append({"include": lst})
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
        # immagini appena taggate: restano visibili anche se non rispettano più
        # il filtro, finché non si cambia filtro o ricerca
        self._pinned: set[str] = set()
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
        self._search_var.trace_add("write", lambda *_: self._on_filter_change())
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
        self._filter_cb.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

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
    def _on_filter_change(self):
        self._pinned.clear()
        self._refresh_list()

    def _refresh_list(self):
        self._listbox.delete(0, "end")
        library = self._library()
        search = self._search_var.get().strip().lower()
        ftag = self._filter_tag_var.get()

        for image in sorted(library.keys(), key=str.lower):
            tags = library.get(image) or []
            if image not in self._pinned:
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

        # Le immagini toccate restano in elenco (e selezionate) anche se ora
        # escono dal filtro, così si possono aggiungere più tag di fila
        self._pinned.update(images)

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
        motore = carica_motore()
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

        strati = self._strati_pertinenti(motore) if motore else []
        for r in rules:
            etichetta = descrivi_fascia(r, oggi, self.config_data)
            trovate, mancanti = conta(r)
            extra = f"  ({mancanti} non trovate su disco)" if mancanti else ""
            lines.append(f"{etichetta}: {trovate} immagini{extra}")

            # Ogni strato ammette tag diversi, quindi la stessa regola pesca da
            # pool diversi secondo il giorno. Il conteggio senza strato e'
            # quello che non si verifica mai nella realta'.
            for etichetta_strato, strato in strati:
                # La patch la fa il motore: rifarla qui significherebbe avere due
                # idee diverse di cosa vieta uno strato, e il conteggio della GUI
                # mentirebbe proprio dove serve.
                n, _ = conta(motore.patch_rule(r, strato, self.config_data))
                segnale = "   <-- poche" if n < 5 else ""
                lines.append(f"      in {etichetta_strato}: {n}{segnale}")

        self._mostra_verifica(lines)

    def _strati_pertinenti(self, motore) -> list[tuple[str, dict]]:
        """
        Gli strati in cui queste regole vengono davvero lette: le regole di base
        sotto ogni stagione, le fasce di un periodo solo nel suo strato.
        """
        if self.path[0] in ("seasons", "events"):
            periodo = self.config_data[self.path[0]][self.path[1]]
            return [
                (etichetta, s)
                for etichetta, s in strati_dell_anno(motore, self.config_data)
                if any(p is periodo for p in s["periodi"])
            ]
        return [
            (etichetta, s)
            for etichetta, s in strati_dell_anno(motore, self.config_data)
            if s["tipo"] == "stagione"
        ]

    def _mostra_verifica(self, lines: list[str]):
        """Con tante regole e periodi un messagebox esce dallo schermo: serve lo scroll."""
        dlg = tk.Toplevel(self)
        dlg.title("Verifica regole")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())

        ttk.Button(dlg, text="Chiudi", command=dlg.destroy).pack(
            side="bottom", anchor="e", padx=8, pady=(0, 8)
        )

        box = tk.Text(
            dlg,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 9),
            wrap="none",
            borderwidth=0,
            width=max(40, min(110, max(len(l) for l in lines) + 2)),
            height=min(30, len(lines) + 1),
        )
        scroll = ttk.Scrollbar(dlg, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")

        scroll.pack(side="right", fill="y", pady=8)
        box.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.focus_set()


def match_rule(image_tags, rule: dict) -> bool:
    """
    Stessa logica di app.image_matches_rule, comprese le stagioni vietate dal
    periodo: quelle non sono un divieto per tag ma per insieme, e l'immagine
    cade solo se ogni stagione che dichiara e' vietata.
    """
    tags = set(image_tags or [])

    vietate = set(rule.get("season_exclude") or ())
    if vietate:
        stagioni = tags & set(rule.get("seasonal") or vietate)
        if stagioni and stagioni <= vietate:
            return False
    for t in rule.get("exclude", []):
        if t in tags:
            return False
    if tags & set(rule.get("veto") or ()):
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


def strati_dell_anno(motore, config_data: dict) -> list[tuple[str, dict]]:
    """
    Gli strati distinti dell'anno in ordine di calendario, ognuno col percorso
    dalla stagione ('Inverno > Natale'): lo stesso evento sopra due stagioni
    diverse ammette tag diversi, ed e' giusto che compaia due volte.
    """
    visti, out = set(), []
    for d in range(366):
        g = date(2024, 1, 1) + timedelta(days=d)  # bisestile: c'e' anche il 29/2
        strati = motore.strati_del_giorno(config_data, g)
        for i, s in enumerate(strati):
            etichetta = " > ".join(x["nome"] for x in reversed(strati[i:]))
            if etichetta not in visti:
                visti.add(etichetta)
                out.append((etichetta, s))
    return out


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
            text="Ctrl+click per selezionarne più di uno. L'esclusione qui è secca:\n"
            "basta il tag e l'immagine è fuori. Le stagioni si gestiscono in "
            "Stagioni ed eventi.",
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
#  Tab: stagioni ed eventi
# ═══════════════════════════════════════════════════════════════════════════════


MESI_IT = [
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]

def md_valido(s: str) -> bool:
    """'10-20' o 'pasqua-5' validi. Il 29 febbraio si accetta: l'anno non entra nel confronto."""
    return date_mobili.valida(s)


def md_ordinale(s: str, anno: int | None = None) -> int | None:
    """
    '10-20' -> 1020, per i confronti fra date senza anno. Le date relative a
    Pasqua si risolvono nell'anno dato, di default quello corrente.
    """
    return date_mobili.ordinale(str(s or "").strip(), anno or date.today().year)


def md_leggibile(s: str, anno: int | None = None) -> str:
    """'10-20' -> '20 ottobre'; 'pasqua-5' -> 'pasqua-5 (31 marzo)' nell'anno dato."""
    o = md_ordinale(s, anno)
    if o is None:
        return str(s)
    testo = f"{o % 100} {MESI_IT[o // 100 - 1]}"
    if date_mobili.e_mobile(s):
        return f"{str(s).strip()} ({testo})"
    return testo


def md_breve(s: str) -> str:
    """'10-20' -> '20 ott'. Una data relativa a Pasqua resta scritta com'e'."""
    if date_mobili.e_mobile(s):
        return str(s).strip()
    o = md_ordinale(s)
    if o is None:
        return str(s)
    return f"{o % 100} {MESI_IT[o // 100 - 1][:3]}"


def md_copre(inizio: int, fine: int, giorno: date) -> bool:
    """Se l'intervallo (ordinali MMGG) contiene quel giorno. Gestisce il capodanno."""
    oggi = giorno.month * 100 + giorno.day
    if inizio <= fine:
        return inizio <= oggi <= fine
    return oggi >= inizio or oggi <= fine


def conta_fasce(period: dict) -> int:
    """Quante fasce proprie ha il periodo, override di giorno compresi."""
    quante = 0
    for valore in (period.get("random_rules") or {}).values():
        if isinstance(valore, list):
            quante += len(valore)
        elif isinstance(valore, dict):
            quante += sum(len(x or []) for x in valore.values())
    return quante


def etichetta_fasce(period: dict) -> str:
    """'2 fasce proprie' / '1 fascia propria' / 'nessuna fascia propria'."""
    n = conta_fasce(period)
    if not n:
        return "nessuna fascia propria"
    return "1 fascia propria" if n == 1 else f"{n} fasce proprie"


def giorno_anno(md: str) -> int | None:
    """
    '03-01' -> 60: indice del giorno su un anno bisestile, da 0 a 365. Le date
    relative a Pasqua cadono dove cadono quest'anno.
    """
    o = md_ordinale(md)
    if o is None:
        return None
    try:
        return date(2024, o // 100, o % 100).timetuple().tm_yday - 1
    except ValueError:
        return None


# Tinte chiare, leggibili sia sul tema scuro sia su quello chiaro. Le stagioni
# seguono l'ordine dell'elenco: inverno, primavera, estate, autunno.
COLORI_STAGIONI = ["#89b4fa", "#a6e3a1", "#f9e2af", "#fab387", "#94e2d5", "#b4befe"]
COLORI_EVENTI = ["#f38ba8", "#cba6f7", "#f5c2e7", "#eba0ac", "#74c7ec", "#f2cdcd"]

TIPI_PERIODO = {
    "seasons": ("Stagioni", "stagione", COLORI_STAGIONI),
    "events": ("Eventi", "evento", COLORI_EVENTI),
}


class GraficoAnno(tk.Canvas):
    """
    L'anno a colpo d'occhio: una riga per stagione e una per evento, coi mesi
    in colonna. Le sovrapposizioni si vedono incolonnate, e una riga cliccata
    seleziona il periodo nella sua tabella.
    """

    RIGA = 13
    TESTATA = 16
    SEPARATORE = 8
    MARGINE_SX = 112

    def __init__(self, parent, config_data: dict, on_click=None):
        super().__init__(parent, bg=BG2, highlightthickness=0, height=120)
        self.config_data = config_data
        self.on_click = on_click
        self.bind("<Configure>", lambda e: self.disegna())

    def disegna(self):
        self.delete("all")
        righe = [
            (chiave, i, p)
            for chiave in ("seasons", "events")
            for i, p in enumerate(self.config_data.get(chiave, []) or [])
        ]
        n_stagioni = len(self.config_data.get("seasons", []) or [])
        altezza = (
            self.TESTATA + len(righe) * self.RIGA + self.SEPARATORE + 6
            if righe
            else self.TESTATA + 24
        )
        if int(self.cget("height")) != altezza:
            self.configure(height=altezza)

        larghezza = self.winfo_width()
        if larghezza < self.MARGINE_SX + 100:
            return
        x0 = self.MARGINE_SX
        px = (larghezza - x0 - 10) / 366

        # L'anno in alto a sinistra: le date relative a Pasqua sono quelle sue
        self.create_text(
            6, 8, anchor="w", text=str(date.today().year), fill=FG2, font=("Segoe UI", 8)
        )

        # Mesi
        for m in range(12):
            x = x0 + giorno_anno(f"{m + 1:02d}-01") * px
            self.create_line(x, 14, x, altezza, fill=BG3)
            self.create_text(
                x + 15 * px, 8, text=MESI_IT[m][:3], fill=FG2, font=("Segoe UI", 8)
            )

        if not righe:
            self.create_text(
                x0, self.TESTATA + 10, anchor="w", fill=FG2, font=("Segoe UI", 9),
                text="Nessuna stagione e nessun evento.",
            )
            return

        for r, (chiave, i, p) in enumerate(righe):
            y = self.TESTATA + r * self.RIGA
            if r >= n_stagioni:
                y += self.SEPARATORE
            colori = TIPI_PERIODO[chiave][2]
            colore = colori[i % len(colori)]
            etichetta = f"{chiave}:{i}"

            self.create_text(
                x0 - 6, y + self.RIGA / 2, anchor="e", text=p.get("name", "?"),
                fill=FG, font=("Segoe UI", 8), tags=(etichetta,),
            )

            a, b = giorno_anno(p.get("from", "")), giorno_anno(p.get("to", ""))
            if a is None or b is None:
                continue
            # Un periodo a cavallo del capodanno diventa due barre
            pezzi = [(a, b)] if a <= b else [(a, 365), (0, b)]
            for inizio, fine in pezzi:
                self.create_rectangle(
                    x0 + inizio * px, y + 2, x0 + (fine + 1) * px, y + self.RIGA - 2,
                    fill=colore, outline="", tags=(etichetta,),
                )
            self.tag_bind(etichetta, "<Button-1>", lambda e, c=chiave, k=i: self._click(c, k))

        if n_stagioni and len(righe) > n_stagioni:
            y = self.TESTATA + n_stagioni * self.RIGA + self.SEPARATORE / 2
            self.create_line(4, y, larghezza - 4, y, fill=BG3, dash=(2, 2))

        # Oggi
        oggi = date.today()
        x = x0 + giorno_anno(f"{oggi.month:02d}-{oggi.day:02d}") * px
        self.create_line(x, 14, x, altezza, fill=DANGER, width=2)

    def _click(self, chiave: str, indice: int):
        if self.on_click:
            self.on_click(chiave, indice)


class TabellaPeriodi(tk.Frame):
    """Elenco delle stagioni o degli eventi, coi pulsanti per modificarlo."""

    def __init__(self, parent, config_data: dict, chiave: str, on_change):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.chiave = chiave
        self.on_change = on_change
        titolo, self._singolare, _ = TIPI_PERIODO[chiave]

        tk.Label(
            self, text=titolo, bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 10)
        ).pack(anchor="w", pady=(0, 4))

        self._tree = ttk.Treeview(
            self, columns=("nome", "dal", "al", "tag", "fasce"), show="headings", height=5
        )
        for c, t, w in (
            ("nome", "Nome", 95),
            ("dal", "Dal", 70),
            ("al", "Al", 70),
            ("tag", "Tag", 150),
            ("fasce", "Fasce", 42),
        ):
            self._tree.heading(c, text=t)
            self._tree.column(c, width=w, anchor="w")
        self._tree.bind("<Double-1>", lambda e: self._edit())

        bar = tk.Frame(self, bg=BG, pady=6)
        bar.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)
        for testo, cmd in (
            ("Nuovo", self._add),
            ("Modifica", self._edit),
            ("Elimina", self._delete),
            ("▲", lambda: self._move(-1)),
            ("▼", lambda: self._move(1)),
            ("Fasce", self._edit_rules),
        ):
            ttk.Button(bar, text=testo, command=cmd, width=max(2, len(testo) + 1)).pack(
                side="left", padx=(0, 4)
            )

        self.refresh()

    def _periods(self) -> list:
        return self.config_data.setdefault(self.chiave, [])

    def refresh(self):
        for i in self._tree.get_children():
            self._tree.delete(i)
        for idx, p in enumerate(self._periods()):
            n_regole = conta_fasce(p)
            self._tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    p.get("name", "?"),
                    md_breve(p.get("from", "")),
                    md_breve(p.get("to", "")),
                    (", ".join(p.get("tags") or []) or "-")
                    + ("  no " + ", ".join(p["veto"]) if p.get("veto") else ""),
                    n_regole or "-",
                ),
            )

    def seleziona(self, indice: int):
        if str(indice) in self._tree.get_children():
            self._tree.selection_set(str(indice))
            self._tree.see(str(indice))

    def _selected(self) -> int | None:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _changed(self, seleziona: int | None = None):
        self.refresh()
        if seleziona is not None:
            self.seleziona(seleziona)
        self.on_change()

    def _add(self):
        dlg = PeriodDialog(
            self, self.config_data, self.chiave, f"Nuovo {self._singolare}"
        )
        if dlg.result:
            self._periods().append(dlg.result)
            self._changed(len(self._periods()) - 1)

    def _edit(self):
        i = self._selected()
        if i is None:
            return
        dlg = PeriodDialog(
            self,
            self.config_data,
            self.chiave,
            f"Modifica {self._singolare}",
            initial=self._periods()[i],
            indice=i,
        )
        if dlg.result:
            self._periods()[i] = dlg.result
        # anche con Annulla: le fasce si scrivono subito e vanno ricontate
        self._changed(i)

    def _edit_rules(self):
        """Le fasce orarie proprie del periodo selezionato."""
        i = self._selected()
        if i is None:
            messagebox.showinfo("Fasce", f"Seleziona prima una riga fra le {TIPI_PERIODO[self.chiave][0].lower()}.")
            return
        PeriodRulesDialog(self, self.config_data, self.chiave, i)
        self._changed(i)

    def _delete(self):
        i = self._selected()
        if i is None:
            return
        nome = self._periods()[i].get("name", "?")
        if messagebox.askyesno("Conferma", f"Eliminare '{nome}'?"):
            del self._periods()[i]
            self._changed()

    def _move(self, delta: int):
        i = self._selected()
        if i is None:
            return
        j = i + delta
        periodi = self._periods()
        if not 0 <= j < len(periodi):
            return
        periodi[i], periodi[j] = periodi[j], periodi[i]
        self._changed(j)


class PeriodsTab(tk.Frame):
    """
    Stagioni ed eventi: il grafico dell'anno sopra, le due tabelle sotto.

    Le stagioni coprono l'anno, gli eventi ci si appoggiano sopra. Gli strati
    li compone il motore (app.strati_del_giorno): qui si editano soltanto.
    """

    def __init__(self, parent, config_data: dict, app):
        super().__init__(parent, bg=BG)
        self.config_data = config_data
        self.app = app
        self._build()

    def _build(self):
        intro = tk.Label(
            self,
            text="Le stagioni coprono l'anno e dove si sovrappongono valgono entrambe. "
            "Gli eventi si annidano sopra (sta sopra il piu' corto); nelle ore che le "
            "loro fasce non coprono si scende allo strato sotto.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
        )
        intro.pack(fill="x", padx=12, pady=(10, 6))
        # Va a capo sulla larghezza vera della tab, qualunque sia lo scaling
        intro.bind("<Configure>", lambda e: intro.configure(wraplength=e.width - 4))

        self._grafico = GraficoAnno(self, self.config_data, on_click=self._click_grafico)
        self._grafico.pack(fill="x", padx=12)

        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=12, pady=(4, 8))
        self._btn_verifica = ttk.Button(
            bar, text="Verifica anno", style="Accent.TButton", command=self._check_year
        )
        self._btn_verifica.pack(side="right", anchor="n")
        self._status = tk.Label(
            bar, bg=BG, fg=FG2, font=("Segoe UI", 9), justify="left", anchor="w",
            wraplength=820,
        )
        self._status.pack(side="left", fill="x", expand=True)


        tabelle = tk.Frame(self, bg=BG)
        tabelle.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        tabelle.columnconfigure(0, weight=1, uniform="t")
        tabelle.columnconfigure(1, weight=1, uniform="t")
        tabelle.rowconfigure(0, weight=1)
        self._tabelle = {}
        for col, chiave in enumerate(("seasons", "events")):
            t = TabellaPeriodi(tabelle, self.config_data, chiave, self._aggiornato)
            t.grid(row=0, column=col, sticky="nsew", padx=(0, 12) if col == 0 else 0)
            self._tabelle[chiave] = t

        self._aggiorna_copertura()

    def refresh(self):
        for t in self._tabelle.values():
            t.refresh()
        self._aggiornato()

    def _aggiornato(self):
        self._grafico.disegna()
        self._aggiorna_copertura()

    def _click_grafico(self, chiave: str, indice: int):
        self._tabelle[chiave].seleziona(indice)

    def _aggiorna_copertura(self):
        """
        Avvisa sui giorni dell'anno che nessuna stagione copre. Non e' cosmetico:
        un giorno scoperto non applica nessun filtro stagionale, e a luglio
        tornano le immagini invernali.
        """
        stagioni = self.config_data.get("seasons", []) or []
        if not stagioni:
            self._status.config(
                text="Nessuna stagione: le regole valgono uguali tutto l'anno.", fg=FG2
            )
            return

        intervalli = [
            (md_ordinale(p.get("from")), md_ordinale(p.get("to")), p.get("name", "?"))
            for p in stagioni
        ]
        scoperti, conteggi = [], {}
        for d in range(366):
            g = date(2024, 1, 1) + timedelta(days=d)
            nomi = [
                n
                for a, b, n in intervalli
                if a is not None and b is not None and md_copre(a, b, g)
            ]
            if not nomi:
                scoperti.append(g)
            else:
                chiave = "/".join(nomi)
                conteggi[chiave] = conteggi.get(chiave, 0) + 1

        riepilogo = "  ".join(f"{n} {c}gg" for n, c in conteggi.items())
        if not scoperti:
            self._status.config(text=f"Anno coperto.   {riepilogo}", fg=SUCCESS)
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
            text=f"{len(scoperti)} giorni senza stagione: {'; '.join(blocchi[:4])}"
            f"{' ...' if len(blocchi) > 4 else ''}\n{riepilogo}",
            fg=DANGER,
        )

    def _check_year(self):
        """
        Passa l'anno col motore vero e riporta le fasce con pochi candidati.
        E' la rete di sicurezza: un tag di troppo in un periodo puo' svuotare una
        fascia in una sola stagione, e sfogliando il config non si vede.

        Poi lancia verifica_immagini, che ricostruisce un anno intero di uscite
        per trovare le immagini che non escono mai. Ci mette qualche secondo,
        quindi gira in un thread e il rapporto arriva alla fine.
        """
        motore = carica_motore()
        if motore is None:
            return
        if "disabled" in self._btn_verifica.state():
            return  # verifica gia' in corso

        cfg = self.config_data
        righe, problemi = [], 0
        # Il 15 di ogni mese, piu' il primo giorno di ogni combinazione di
        # stagioni ed eventi: cosi' anche un evento di un giorno solo e ogni
        # transizione vengono controllati.
        anno = date.today().year
        campioni, viste_pile = {date(anno, m, 15) for m in range(1, 13)}, set()
        for d in range(365):
            g = date(anno, 1, 1) + timedelta(days=d)
            pila = motore.descrivi_giorno(cfg, g)
            if pila not in viste_pile:
                viste_pile.add(pila)
                campioni.add(g)
        campioni = sorted(campioni)

        self._status.config(text="Verifica in corso...", fg=FG2)
        self.update_idletasks()
        motore.invalida_cache_file()

        for g in campioni:
            nome = motore.descrivi_giorno(cfg, g)
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
                righe.append(
                    f"{g}  {nome}: solo {peggiore[0]} immagini su {peggiore[1]}"
                )
                problemi += 1
            elif peggiore and not senza_regola:
                righe.append(f"{g}  {nome}: minimo {peggiore[0]} immagini, ok")

        try:
            import verifica_immagini
        except Exception as e:
            self._aggiorna_copertura()
            self._mostra_rapporto(
                righe, problemi, [f"verifica_immagini.py non disponibile: {e}"], None
            )
            return

        # Copia: il thread non deve vedere le modifiche fatte nell'editor mentre gira
        cfg_copia = motore.ensure_defaults(copy.deepcopy(cfg))
        stato = {
            "fase": "fasce",
            "fatto": 0,
            "totale": 1,
            "esito": None,
            "errore": None,
        }

        def progresso(fase, fatto, totale):
            stato.update(fase=fase, fatto=fatto, totale=totale)

        def lavora():
            try:
                stato["esito"] = verifica_immagini.rapporto(
                    cfg_copia, progresso=progresso
                )
            except Exception as e:
                stato["errore"] = e

        self._btn_verifica.state(["disabled"])
        threading.Thread(target=lavora, daemon=True).start()
        self._attendi_immagini(stato, righe, problemi)

    def _attendi_immagini(
        self, stato: dict, righe_fasce: list[str], problemi_fasce: int
    ):
        """
        Aggiorna la barra di stato finche' il thread lavora. Tkinter non va
        toccato da un altro thread: il thread scrive solo in `stato`, e qui lo
        si legge dal thread della GUI.
        """
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return  # tab ricreata (cambio tema) mentre la verifica girava

        if stato["esito"] is None and stato["errore"] is None:
            fase = (
                "fasce vincenti"
                if stato["fase"] == "fasce"
                else "uscite giorno per giorno"
            )
            self._status.config(
                text=f"Verifica immagini: {fase} {stato['fatto']}/{stato['totale']}...",
                fg=FG2,
            )
            self.after(200, self._attendi_immagini, stato, righe_fasce, problemi_fasce)
            return

        self._btn_verifica.state(["!disabled"])
        self._aggiorna_copertura()
        if stato["errore"] is not None:
            self._mostra_rapporto(
                righe_fasce, problemi_fasce, [f"Errore: {stato['errore']}"], None
            )
        else:
            righe_img, problemi_img = stato["esito"]
            self._mostra_rapporto(righe_fasce, problemi_fasce, righe_img, problemi_img)

    def _mostra_rapporto(
        self,
        righe_fasce: list[str],
        problemi_fasce: int,
        righe_img: list[str],
        problemi_img: int | None,
    ):
        """Il rapporto completo in una finestra: in un messagebox non ci sta."""
        dlg = tk.Toplevel(self)
        dlg.title("Chametiger - Verifica anno")
        dlg.configure(bg=BG)
        dlg.geometry("900x560")

        esito_img = (
            "non eseguita"
            if problemi_img is None
            else f"{problemi_img} problemi" if problemi_img else "tutte escono"
        )
        esito_fasce = (
            f"{problemi_fasce} segnalazioni"
            if problemi_fasce
            else "nessuna segnalazione"
        )
        tutto_ok = not problemi_fasce and problemi_img == 0
        tk.Label(
            dlg,
            text=f"Fasce: {esito_fasce}   -   Immagini: {esito_img}",
            bg=BG,
            fg=SUCCESS if tutto_ok else DANGER,
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 0))

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

        testo = (
            "── Fasce (giorni campione) ──\n"
            + "\n".join(righe_fasce)
            + "\nUna fascia con poche immagini resta quasi fissa per tutta la stagione.\n\n"
            + "── Immagini (anno simulato da oggi) ──\n"
            + "\n".join(righe_img)
        )
        box.insert("1.0", testo)
        box.configure(state="disabled")

        scroll.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)


class PeriodDialog(tk.Toplevel):
    """Editor di una stagione o di un evento."""

    def __init__(
        self, parent, config_data: dict, chiave: str, title="Periodo", initial=None, indice=None
    ):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.config_data = config_data
        self.chiave = chiave
        self.result: dict | None = None
        self._initial = initial or {}
        # Le fasce si scrivono nel periodo appena le tocchi, mentre nome, date e
        # tag passano da `result` e si applicano solo con OK. Senza questa copia,
        # Annulla lascerebbe a meta' il lavoro: dati vecchi e fasce nuove.
        self.indice = indice
        self._fasce_prima = copy.deepcopy(self._initial.get("random_rules"))
        initial = self._initial
        all_tags = sorted(config_data.get("tags", []), key=str.lower)
        evento = chiave == "events"

        top = tk.Frame(self, bg=BG)
        top.grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 2))

        tk.Label(top, text="Nome", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        # NON chiamarlo _name: tkinter usa Misc._name per il nome del widget e
        # sovrascriverlo rompe destroy().
        self._nome = tk.StringVar(value=initial.get("name", ""))
        tk.Entry(
            top,
            textvariable=self._nome,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=18,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(6, 16))

        tk.Label(top, text="dal", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self._from = tk.StringVar(value=initial.get("from", "01-01"))
        tk.Entry(
            top,
            textvariable=self._from,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=8,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        tk.Label(top, text="al", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self._to = tk.StringVar(value=initial.get("to", "12-31"))
        tk.Entry(
            top,
            textvariable=self._to,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=8,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        self._date_lbl = tk.Label(self, bg=BG, fg=FG2, font=("Segoe UI", 9), anchor="w")
        self._date_lbl.grid(row=1, column=0, columnspan=4, sticky="w", padx=16)
        for var in (self._from, self._to):
            var.trace_add("write", lambda *_: self._aggiorna_date())

        tk.Label(
            self,
            text="Formato mese-giorno, senza anno: il periodo si ripete ogni anno.\n"
            "Se la data finale precede quella iniziale, il periodo scavalca il capodanno.\n"
            "Per le feste mobili: pasqua, pasqua-5, pasqua+2 (giorni prima o dopo Pasqua).",
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=16, pady=(2, 8))

        for col, (testo, colore) in enumerate(
            (
                ("Tag " + ("dell'evento" if evento else "della stagione"), SUCCESS),
                ("Vietati sempre", DANGER),
                ("Tag preferiti", ACCENT2),
                ("Tag obbligatori", ACCENT),
            )
        ):
            tk.Label(
                self, text=testo, bg=BG, fg=colore, font=("Segoe UI Semibold", 9)
            ).grid(row=3, column=col, sticky="w", padx=16, pady=(0, 2))

        self._tags = self._lista(all_tags, initial.get("tags", []))
        self._tags.grid(row=4, column=0, padx=16, sticky="n")
        self._veto = self._lista(all_tags, initial.get("veto", []))
        self._veto.grid(row=4, column=1, padx=16, sticky="n")
        self._pref = self._lista(all_tags, initial.get("prefer", []))
        self._pref.grid(row=4, column=2, padx=16, sticky="n")
        self._req = self._lista(all_tags, initial.get("require", []))
        self._req.grid(row=4, column=3, padx=16, sticky="n")

        pm = tk.Frame(self, bg=BG)
        pm.grid(row=5, column=0, columnspan=4, sticky="w", padx=16, pady=(8, 0))
        tk.Label(
            pm,
            text="Restringi ai preferiti solo se ne restano almeno",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 9),
        ).pack(side="left")
        self._prefer_min = tk.IntVar(value=int(initial.get("prefer_min", 1) or 1))
        tk.Spinbox(
            pm,
            from_=1,
            to=200,
            textvariable=self._prefer_min,
            width=5,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            buttonbackground=BG3,
            relief="flat",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=6)
        tk.Label(pm, text="immagini", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(
            side="left"
        )

        if evento:
            spiegazione = (
                "I tag dell'evento valgono solo nei suoi giorni, e solo nelle sue fasce:\n"
                "nelle ore che le fasce non coprono si scende allo strato sotto, fino alla\n"
                "stagione, coi divieti di quello strato. Un evento senza fasce proprie\n"
                "quindi non cambia niente. Fra due eventi sovrapposti sta sopra il piu' corto.\n"
            )
        else:
            spiegazione = (
                "I tag della stagione valgono solo nei suoi giorni. Dove due stagioni si\n"
                "sovrappongono valgono i tag di entrambe: e' la transizione.\n"
                "Un'immagine cade solo se TUTTI i suoi tag di stagione sono fuori periodo:\n"
                "una taggata inverno+primavera esce in entrambe le stagioni.\n"
            )
        tk.Label(
            self,
            text=spiegazione
            + "I vietati sempre escludono ogni immagine che ne ha anche uno solo, qualunque\n"
            "altro tag porti: valgono nei giorni del periodo, nelle sue fasce e in tutte\n"
            "quelle degli strati sotto (non in un evento annidato sopra, che decide da se').\n"
            "I preferiti restringono il pool solo se ne resta abbastanza: con pochi\n"
            "tag preferiti la fascia diventerebbe quasi fissa.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=16, pady=(8, 0))

        fasce = tk.Frame(self, bg=BG)
        fasce.grid(row=7, column=0, columnspan=4, sticky="w", padx=16, pady=(10, 0))
        self._btn_fasce = ttk.Button(fasce, text="Fasce orarie proprie", command=self._fasce)
        self._btn_fasce.pack(side="left")
        self._lbl_fasce = tk.Label(fasce, bg=BG, fg=FG2, font=("Segoe UI", 9))
        self._lbl_fasce.pack(side="left", padx=10)
        if indice is None:
            self._btn_fasce.state(["disabled"])
        self._aggiorna_fasce()

        bf = tk.Frame(self, bg=BG, pady=12)
        bf.grid(row=8, column=0, columnspan=4)
        ttk.Button(bf, text="OK", style="Accent.TButton", command=self._ok).pack(
            side="left", padx=8
        )
        ttk.Button(bf, text="Annulla", command=self._annulla).pack(side="left")

        self._aggiorna_date()
        self.protocol("WM_DELETE_WINDOW", self._annulla)
        self.grab_set()
        self.wait_window()

    def _periodo(self) -> dict:
        return self.config_data[self.chiave][self.indice]

    def _aggiorna_fasce(self):
        """La riga accanto al pulsante: quante fasce proprie ha il periodo."""
        if self.indice is None:
            self._lbl_fasce.config(
                text="Non e' ancora nell'elenco: confermalo con OK, poi riaprilo per aggiungerle."
            )
            return
        self._lbl_fasce.config(text=etichetta_fasce(self._periodo()))

    def _fasce(self):
        """Le fasce orarie proprie, nello stesso editor delle regole di base."""
        if self.indice is None:
            return
        PeriodRulesDialog(self, self.config_data, self.chiave, self.indice)
        # Il dialogo figlio si prende il grab e non lo restituisce da solo:
        # senza questo, il dialogo del periodo resterebbe cliccabile ma non piu'
        # modale, e l'elenco sotto si potrebbe modificare alle sue spalle.
        self.grab_set()
        self.lift()
        self._aggiorna_fasce()

    def _annulla(self):
        """Rimette le fasce com'erano all'apertura, poi chiude senza salvare."""
        if self.indice is not None:
            periodo = self._periodo()
            if self._fasce_prima is None:
                periodo.pop("random_rules", None)
            else:
                periodo["random_rules"] = copy.deepcopy(self._fasce_prima)
        self.destroy()

    def _lista(self, all_tags, selected) -> tk.Listbox:
        lb = tk.Listbox(
            self,
            bg=BG2,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground=BG,
            selectmode="multiple",
            width=20,
            height=10,
            relief="flat",
            borderwidth=0,
            exportselection=False,
            font=("Segoe UI", 9),
        )
        for i, t in enumerate(all_tags):
            lb.insert("end", t)
            if t in (selected or []):
                lb.selection_set(i)
        if lb.curselection():
            lb.see(lb.curselection()[0])
        return lb

    def _aggiorna_date(self):
        a, b = self._from.get().strip(), self._to.get().strip()
        if not (md_valido(a) and md_valido(b)):
            self._date_lbl.config(
                text="Date non valide (formato MM-GG, oppure pasqua-5).", fg=DANGER
            )
            return
        anno = date.today().year
        oa, ob = md_ordinale(a, anno), md_ordinale(b, anno)
        salto = " (scavalca il capodanno)" if oa > ob else ""
        giorni = sum(
            1
            for d in range(366)
            if md_copre(oa, ob, date(2024, 1, 1) + timedelta(days=d))
        )
        testo = f"Dal {md_leggibile(a, anno)} al {md_leggibile(b, anno)}{salto} - {giorni} giorni."
        if date_mobili.e_mobile(a) or date_mobili.e_mobile(b):
            # Pasqua si sposta: l'anno prossimo le stesse date cadono altrove

            def giorno(s, y):
                o = md_ordinale(s, y)
                return f"{o % 100} {MESI_IT[o // 100 - 1]}"

            testo = (
                f"Nel {anno} dal {giorno(a, anno)} al {giorno(b, anno)} ({giorni} giorni), "
                f"nel {anno + 1} dal {giorno(a, anno + 1)} al {giorno(b, anno + 1)}."
            )
        self._date_lbl.config(text=testo, fg=FG2)

    def _collect(self, lb) -> list[str]:
        return [lb.get(i) for i in lb.curselection()]

    def _ok(self):
        nome = self._nome.get().strip()
        if not nome:
            messagebox.showerror("Errore", "Dai un nome.", parent=self)
            return
        # Il nome entra nel log e nella firma delle regole: due periodi omonimi
        # si confonderebbero nell'anteprima e condividerebbero il memo.
        altri = [
            p.get("name")
            for chiave in ("seasons", "events")
            for i, p in enumerate(self.config_data.get(chiave, []) or [])
            if not (chiave == self.chiave and i == self.indice)
        ]
        if nome in altri:
            messagebox.showerror(
                "Errore", f"Esiste gia' una stagione o un evento chiamato '{nome}'.", parent=self
            )
            return

        a, b = self._from.get().strip(), self._to.get().strip()
        for etichetta, valore in (("iniziale", a), ("finale", b)):
            if not md_valido(valore):
                messagebox.showerror(
                    "Errore",
                    f"Data {etichetta} non valida: '{valore}'.\n"
                    "Formato MM-GG (es. 10-20), oppure pasqua, pasqua-5, pasqua+2.",
                    parent=self,
                )
                return

        # Si parte dal periodo com'era: le chiavi che questo dialogo non conosce
        # (e le fasce, che si editano a parte) restano intatte.
        period = {
            k: v
            for k, v in self._initial.items()
            if k not in ("name", "from", "to", "tags", "veto", "prefer", "prefer_min", "require")
        }
        period.update({"name": nome, "from": a, "to": b})
        tags = self._collect(self._tags)
        if tags:
            period["tags"] = tags
        veto = self._collect(self._veto)
        if veto:
            period["veto"] = veto
        preferiti = self._collect(self._pref)
        if preferiti:
            period["prefer"] = preferiti
            if int(self._prefer_min.get()) > 1:
                period["prefer_min"] = int(self._prefer_min.get())
        richiesti = self._collect(self._req)
        if richiesti:
            period["require"] = richiesti
        if self.indice is not None:
            # le fasce vivono nel config mentre le editi: vale quello che c'e' ora
            regole = self._periodo().get("random_rules")
            if regole:
                period["random_rules"] = regole
            else:
                period.pop("random_rules", None)

        self.result = period
        self.destroy()


class PeriodRulesDialog(tk.Toplevel):
    """
    Le fasce orarie proprie di una stagione o di un evento: stessa forma di
    `random_rules`, ma lette solo nei giorni del periodo, prima degli strati sotto
    e delle regole di base.

    Scrive dentro il periodo mentre lavori, come ogni altro editor scrive nella
    config in memoria: su disco ci va il pulsante "Salva configurazione". Le
    liste rimaste vuote si tolgono alla chiusura, cosi' un periodo senza fasce
    non si porta dietro un `random_rules` vuoto.
    """

    def __init__(self, parent, config_data: dict, chiave: str, indice: int):
        super().__init__(parent)
        self.config_data = config_data
        self.chiave = chiave
        self.indice = indice

        periodo = config_data[chiave][indice]
        nome = periodo.get("name", "?")
        tipo = TIPI_PERIODO[chiave][1]
        self.title(f"Chametiger - Fasce proprie: {nome}")
        self.configure(bg=BG)
        self.geometry("1020x580")
        self.minsize(900, 500)

        # Le liste devono esistere prima dei RuleEditor, che ci puntano dentro
        # per riferimento. Quelle rimaste vuote se ne vanno in _pota().
        regole = periodo.setdefault("random_rules", {})
        regole.setdefault("weekday", [])
        regole.setdefault("weekend", [])
        regole.setdefault("overrides", {})

        tk.Label(
            self,
            text=f"{nome} ({tipo})   dal {md_leggibile(periodo.get('from', ''))} "
            f"al {md_leggibile(periodo.get('to', ''))}",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))

        if chiave == "events":
            dove = "dell'evento"
            sotto = "allo strato sotto (l'evento che lo contiene o la stagione)"
        else:
            dove = "della stagione"
            sotto = "alle regole di base feriali/weekend"
        tk.Label(
            self,
            text=f"Valgono solo nei giorni {dove} e vengono lette prima degli strati "
            f"sotto.\nSe nessuna copre l'ora, si scende {sotto}.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=14, pady=(0, 8))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14)

        for chiave_regole, etichetta in (("weekday", "Feriali"), ("weekend", "Weekend")):
            frame = ttk.Frame(nb)
            nb.add(frame, text=etichetta)
            RuleEditor(
                frame, config_data, [chiave, indice, "random_rules", chiave_regole]
            ).pack(fill="both", expand=True, padx=10, pady=10)

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
        tk.Label(
            top,
            text="Hanno la precedenza sulle fasce feriali e weekend di questo periodo.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12)

        self._day_frame = tk.Frame(ov, bg=BG)
        self._day_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._refresh_day()

        bf = tk.Frame(self, bg=BG, pady=10)
        bf.pack(fill="x", padx=14)
        tk.Label(
            bf,
            text="Le modifiche finiscono su disco con Salva configurazione, "
            "in fondo alla finestra principale.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
        ).pack(side="left")
        ttk.Button(
            bf, text="Chiudi", style="Accent.TButton", command=self._chiudi
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.grab_set()
        self.wait_window()

    def _periodo(self) -> dict:
        return self.config_data[self.chiave][self.indice]

    def _refresh_day(self):
        giorno = self._day_var.get().split(" ")[0]
        self._periodo()["random_rules"]["overrides"].setdefault(giorno, [])
        for w in self._day_frame.winfo_children():
            w.destroy()
        RuleEditor(
            self._day_frame,
            self.config_data,
            [self.chiave, self.indice, "random_rules", "overrides", giorno],
        ).pack(fill="both", expand=True)

    def _chiudi(self):
        self._pota()
        self.destroy()

    def _pota(self):
        """
        Toglie le liste vuote create per poterle editare. Senza, ogni periodo
        aperto una volta si ritroverebbe un `random_rules` con tre contenitori
        vuoti, e la colonna "Fasce" direbbe comunque zero.
        """
        periodo = self._periodo()
        regole = periodo.get("random_rules") or {}

        overrides = regole.get("overrides") or {}
        for giorno in [g for g, elenco in overrides.items() if not elenco]:
            del overrides[giorno]
        if not overrides:
            regole.pop("overrides", None)

        for chiave in ("weekday", "weekend"):
            if chiave in regole and not regole[chiave]:
                del regole[chiave]

        if not regole:
            periodo.pop("random_rules", None)


# ═══════════════════════════════════════════════════════════════════════════════
#  Tab: anteprima di una giornata
# ═══════════════════════════════════════════════════════════════════════════════


class PreviewTab(tk.Frame):
    """
    La giornata risolta ora per ora: stagione ed eventi, regola vincente, orari solari
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

        tk.Label(top, text="Data:", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(
            side="left"
        )
        oggi = date.today()
        self._data = tk.StringVar(value=oggi.isoformat())
        tk.Entry(
            top,
            textvariable=self._data,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            width=12,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=8)

        for testo, delta in (
            ("-1 g", -1),
            ("+1 g", 1),
            ("+1 sett", 7),
            ("+1 mese", 30),
        ):
            ttk.Button(
                top, text=testo, width=8, command=lambda d=delta: self._sposta(d)
            ).pack(side="left", padx=2)

        ttk.Button(
            top, text="Calcola", style="Accent.TButton", command=self._calcola
        ).pack(side="left", padx=(12, 0))

        self._intestazione = tk.Label(
            self,
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
            anchor="w",
            justify="left",
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

        tk.Label(
            self,
            text="Nella colonna Tag:  a+b servono tutti   a/b ne basta uno   "
            "-tag escluso dalla regola   !tag vietato dal periodo   ~tag preferito.   La regola vincente dice "
            "anche da quale strato viene: evento, stagione o [stagione] per le regole di base.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 0))

        self._nota = tk.Label(
            self, bg=BG, fg=FG2, font=("Segoe UI", 9), anchor="w", justify="left"
        )
        self._nota.pack(fill="x", padx=12, pady=(2, 10))

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
            self._intestazione.config(
                text="Data non valida (formato AAAA-MM-GG).", fg=DANGER
            )
            return

        motore = carica_motore()
        if motore is None:
            return

        cfg = self.config_data
        lat, lon = coords_of(cfg)
        orari = sun.sun_times(giorno, lat, lon)
        pila = motore.descrivi_giorno(cfg, giorno)

        def hm(chiave):
            v = orari.get(chiave)
            return v.strftime("%H:%M") if v else "n.d."

        giorni_it = [
            "lunedi'",
            "martedi'",
            "mercoledi'",
            "giovedi'",
            "venerdi'",
            "sabato",
            "domenica",
        ]
        self._intestazione.config(
            text=f"{giorni_it[giorno.weekday()]} {giorno.strftime('%d/%m/%Y')}   "
            f"{pila}   |   "
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
                text="Nessuna regola copre questa giornata: lo sfondo resterebbe quello "
                "che c'e'.",
                fg=DANGER,
            )
            return

        for e in sequenza:
            rule = e["rule"]
            tag = []
            if rule.get("include"):
                tag.append(
                    ("+" if rule.get("match", "all") == "all" else "/").join(
                        rule["include"]
                    )
                )
            if rule.get("exclude"):
                tag.append("-" + ",-".join(rule["exclude"]))
            if rule.get("veto"):
                tag.append("!" + ",!".join(rule["veto"]))
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
            + (
                "   Attenzione: sotto le 5 immagini la fascia e' quasi fissa."
                if minimo < 5
                else ""
            ),
            fg=DANGER if minimo < 5 else FG2,
        )


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ChametigerEditor()
    app.mainloop()
