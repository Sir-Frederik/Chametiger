"""
   Chametiger — Editor grafico della configurazione
Richiede: tkinter (stdlib), tkcalendar (pip install tkcalendar)
"""

import json
import tkinter as tk
from PIL import Image, ImageTk 
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import datetime

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

# ── Colori tema scuro ─────────────────────────────────────────────────────────
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

# ── Colori tema chiaro ────────────────────────────────────────────────────────
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
#  Finestra principale
# ═══════════════════════════════════════════════════════════════════════════════


class  ChameleonEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chametiger — Editor Configurazione")
        self.iconbitmap(BASE_DIR / "icon.ico")
        self.geometry("920x680")
        self.minsize(800, 560)
        self.configure(bg=BG)
        self.config_data: dict = {}
        self._load_config()
        self._build_ui()
        self._apply_styles()

    # ── Carica / Salva config ─────────────────────────────────────────────────
    def _load_config(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                self.config_data = json.load(f)
        except FileNotFoundError:
            messagebox.showerror("Errore", f"config.json non trovato:\n{CONFIG_FILE}")
            self.destroy()

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Salvato", "Configurazione salvata con successo!")
        except Exception as e:
            messagebox.showerror("Errore salvataggio", str(e))

    # ── Stili ttk ─────────────────────────────────────────────────────────────
    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG3,
            foreground=FG2,
            padding=[12, 6],
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
            "Header.TLabel",
            background=BG,
            foreground=ACCENT,
            font=("Segoe UI Semibold", 11),
        )
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
            "Treeview", background=[("selected", ACCENT)], foreground=[("selected", BG)]
        )

    # ── Layout principale ─────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG, pady=12)
        header.pack(fill="x", padx=16)
        
        tk.Label(
            header,
            text="Chametiger",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI Semibold", 16),
        ).pack(side="left")
        tk.Label(
            header,
            text="Editor Configurazione Sfondi",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=12)

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self._build_schedule_tab(nb, "weekday", "📅  Giorni feriali")
        self._build_schedule_tab(nb, "weekend", "🌅  Weekend")
        self._build_overrides_tab(nb)
        self._build_special_tab(nb)
        self._build_settings_tab(nb)

        # Footer
        footer = tk.Frame(self, bg=BG, pady=8)
        footer.pack(fill="x", padx=16)
        ttk.Button(
            footer,
            text="💾  Salva configurazione",
            style="Accent.TButton",
            command=self._save_config,
        ).pack(side="right")
        ttk.Button(footer, text="🔄  Ricarica", command=self._reload).pack(
            side="right", padx=8
        )

    def _reload(self):
        self._load_config()
        messagebox.showinfo("Ricaricato", "Configurazione ricaricata dal disco.")

    # ── Tab schedule (weekday / weekend) ──────────────────────────────────────
    def _build_schedule_tab(self, nb: ttk.Notebook, key: str, label: str):
        frame = ttk.Frame(nb)
        nb.add(frame, text=label)
        SlotEditor(frame, self.config_data, ["schedules", key]).pack(
            fill="both", expand=True, padx=12, pady=12
        )

    # ── Tab override giorno ───────────────────────────────────────────────────
    def _build_overrides_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="🗓  Override giorno")

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
        cb.bind("<<ComboboxSelected>>", self._on_override_day_change)

        self._override_info = tk.Label(
            top,
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
            text="null = usa schedule base (weekday/weekend)",
        )
        self._override_info.pack(side="left", padx=12)

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
        self._override_slot_editor: SlotEditor | None = None
        self._refresh_override_ui()

    def _get_current_override_key(self) -> str:
        raw = self._override_day_var.get()
        return raw.split(" ")[0]

    def _on_override_day_change(self, *_):
        self._refresh_override_ui()

    def _toggle_override(self):
        key = self._get_current_override_key()
        if self._override_active_var.get():
            if self.config_data["overrides"].get(key) is None:
                self.config_data["overrides"][key] = []
        else:
            self.config_data["overrides"][key] = None
        self._refresh_override_ui()

    def _refresh_override_ui(self):
        key = self._get_current_override_key()
        active = self.config_data["overrides"].get(key) is not None
        self._override_active_var.set(active)

        for w in self._override_editor_frame.winfo_children():
            w.destroy()
        self._override_slot_editor = None

        if active:
            self._override_slot_editor = SlotEditor(
                self._override_editor_frame, self.config_data, ["overrides", key]
            )
            self._override_slot_editor.pack(fill="both", expand=True)
        else:
            tk.Label(
                self._override_editor_frame,
                text="Override non attivo — verrà usato lo schedule base.",
                bg=BG,
                fg=FG2,
                font=("Segoe UI Italic", 9),
            ).pack(pady=24)

    # ── Tab giorni speciali ───────────────────────────────────────────────────
    def _build_special_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="⭐  Giorni speciali")
        SpecialDaysEditor(frame, self.config_data).pack(
            fill="both", expand=True, padx=12, pady=12
        )

    # ── Tab impostazioni ──────────────────────────────────────────────────────
    def _build_settings_tab(self, nb: ttk.Notebook):
        frame = ttk.Frame(nb)
        nb.add(frame, text="⚙  Impostazioni")

        inner = tk.Frame(frame, bg=BG)
        inner.pack(padx=24, pady=24, anchor="nw")

        tk.Label(
            inner,
            text="Intervallo controllo (minuti):",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="w", pady=8)

        self._interval_var = tk.IntVar(
            value=self.config_data.get("check_interval_minutes", 5)
        )
        spin = tk.Spinbox(
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
        )
        spin.grid(row=0, column=1, padx=12, sticky="w")

        def apply_interval():
            self.config_data["check_interval_minutes"] = self._interval_var.get()

        ttk.Button(inner, text="Applica", command=apply_interval).grid(
            row=0, column=2, padx=4
        )

        tk.Label(
            inner,
            text="L'app controlla ogni N minuti se è necessario\ncambiare lo sfondo.",
            bg=BG,
            fg=FG2,
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=4)

        tk.Label(
            inner, text="Tema interfaccia:", bg=BG, fg=FG, font=("Segoe UI", 10)
        ).grid(row=2, column=0, sticky="w", pady=8)

        self._theme_var = tk.StringVar(value="Scuro")
        theme_cb = ttk.Combobox(
            inner,
            textvariable=self._theme_var,
            values=["Scuro", "Chiaro"],
            width=10,
            state="readonly",
        )
        theme_cb.grid(row=2, column=1, padx=12, sticky="w")

        def apply_and_restart():
            dark = self._theme_var.get() == "Scuro"
            apply_theme(dark)
            messagebox.showinfo("Tema", "Riavvia la GUI per applicare il tema.")

        ttk.Button(inner, text="Applica", command=apply_and_restart).grid(
            row=2, column=2, padx=4
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Componente riutilizzabile: editor lista di slot orari
# ═══════════════════════════════════════════════════════════════════════════════


class SlotEditor(tk.Frame):
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

    def _set_slots(self, slots: list):
        d = self.config_data
        for k in self.path[:-1]:
            d = d[k]
        d[self.path[-1]] = slots

    def _build(self):
        cols = ("from", "to", "label", "image")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        self._tree.heading("from", text="Dalle")
        self._tree.heading("to", text="Alle")
        self._tree.heading("label", text="Etichetta")
        self._tree.heading("image", text="Immagine")
        self._tree.column("from", width=70, anchor="center")
        self._tree.column("to", width=70, anchor="center")
        self._tree.column("label", width=160)
        self._tree.column("image", width=400)

        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        btns = tk.Frame(self, bg=BG, padx=8)
        btns.pack(side="left", fill="y")
        ttk.Button(btns, text="➕ Aggiungi", command=self._add_slot).pack(
            fill="x", pady=3
        )
        ttk.Button(btns, text="✏ Modifica", command=self._edit_slot).pack(
            fill="x", pady=3
        )
        ttk.Button(
            btns, text="🗑 Elimina", style="Danger.TButton", command=self._delete_slot
        ).pack(fill="x", pady=3)
        ttk.Button(btns, text="⬆ Su", command=self._move_up).pack(fill="x", pady=3)
        ttk.Button(btns, text="⬇ Giù", command=self._move_down).pack(fill="x", pady=3)

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
        if not sel:
            return None
        return self._tree.index(sel[0])

    def _add_slot(self):
        dlg = SlotDialog(self, title="Nuovo slot")
        if dlg.result:
            self._get_slots().append(dlg.result)
            self._refresh_tree()

    def _edit_slot(self):
        idx = self._selected_index()
        if idx is None:
            return
        slots = self._get_slots()
        dlg = SlotDialog(self, title="Modifica slot", initial=slots[idx])
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Dialog per aggiungere/modificare uno slot
# ═══════════════════════════════════════════════════════════════════════════════


class SlotDialog(tk.Toplevel):
    def __init__(self, parent, title="Slot", initial: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.result: dict | None = None

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
                width=28,
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
            width=22,
            font=("Segoe UI", 9),
        ).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(self, text="…", command=self._browse_image, width=3).grid(
            row=row, column=2, padx=(0, 8)
        )
        row += 1

        self._preview_photo = None
        self._preview_frame = tk.Frame(self, bg=BG)
        self._preview_frame.grid(
            row=row, column=0, columnspan=3, sticky="w", padx=16, pady=2
        )
        self._preview_img_label = tk.Label(self._preview_frame, bg=BG)
        self._preview_img_label.pack(side="left")
        self._preview_lbl = tk.Label(
            self._preview_frame,
            bg=BG,
            fg=FG2,
            font=("Segoe UI Italic", 8),
            anchor="w",
            justify="left",
        )
        self._preview_lbl.pack(side="left", padx=(8, 0))
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
            filetypes=[
                ("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("Tutti", "*.*"),
            ],
        )
        if path:
            self._image.set(path)

    def _clear_preview_image(self):
        self._preview_photo = None
        self._preview_img_label.config(image="", text="")

    def _update_preview(self, *_):
        p = self._image.get().strip()
        if p and Path(p).is_file():
            if HAS_PIL:
                try:
                    img = Image.open(p)
                    img.thumbnail((80, 80), Image.Resampling.LANCZOS)
                    self._preview_photo = ImageTk.PhotoImage(img)
                    self._preview_img_label.config(image=self._preview_photo, text="")
                except Exception:
                    self._clear_preview_image()
                    self._preview_lbl.config(
                        text=f"✔  {Path(p).name} (anteprima non disponibile)",
                        fg=SUCCESS,
                    )
                else:
                    self._preview_lbl.config(text=f"✔  {Path(p).name}", fg=SUCCESS)
            else:
                self._clear_preview_image()
                self._preview_lbl.config(
                    text=f"✔  {Path(p).name}",
                    fg=SUCCESS,
                )
        elif p:
            self._clear_preview_image()
            self._preview_lbl.config(text="⚠  File non trovato", fg=DANGER)
        else:
            self._clear_preview_image()
            self._preview_lbl.config(text="")

    def _validate_time(self, t: str) -> bool:
        try:
            h, m = t.strip().split(":")
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except Exception:
            return False

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
        self._date_listbox.bind("<<ListboxSelect>>", self._on_date_select)

        btns = tk.Frame(left, bg=BG)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="➕", command=self._add_date, width=4).pack(side="left")
        ttk.Button(
            btns, text="🗑", style="Danger.TButton", command=self._delete_date, width=4
        ).pack(side="left", padx=4)

        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._slot_frame = tk.Frame(right, bg=BG)
        self._slot_frame.pack(fill="both", expand=True)

        self._slot_editor: SlotEditor | None = None
        self._refresh_dates()

    def _refresh_dates(self):
        self._date_listbox.delete(0, "end")
        for d in sorted(self.config_data.get("special_days", {}).keys()):
            self._date_listbox.insert("end", d)

    def _on_date_select(self, *_):
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
        self._slot_editor = SlotEditor(
            self._slot_frame, self.config_data, ["special_days", self._selected_date]
        )
        self._slot_editor.pack(fill="both", expand=True)

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

        if date_str not in self.config_data.setdefault("special_days", {}):
            self.config_data["special_days"][date_str] = []
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
    app =  ChameleonEditor()
    app.mainloop()
