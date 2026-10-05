"""Interface do bot do Huntera (CustomTkinter): contas, regras, cadeia de Bestiary e log.
Fechar (X) pergunta se fecha de vez ou guarda na bandeja; minimizar vai pra bandeja (Windows)."""
import datetime
import importlib
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import VERSION, catalog, config
from .memory import Memory
from .paths import app_dir, resource_dir
from .runner import Runner

ROOT = app_dir()
CONFIG_PATH = os.path.join(ROOT, "config.json")
MEMORY_PATH = os.path.join(ROOT, "memory.json")
DEFAULT_CHOICE = "Padrão da vocação"
BG, PANEL, PANEL_ALT, BORDER = "#101418", "#161c22", "#1d252d", "#2b3640"
TEXT, MUTED, ACCENT, ACCENT_HOVER, DANGER, WARN = "#e6edf3", "#8b98a5", "#3fb950", "#2ea043", "#f85149", "#d29922"
TIERS = ["(padrao do jogo)", "Cauteloso", "Ousado", "Agressivo"]
PHASES = {"hunting": "caçando", "city": "cidade", "training": "treinando", "leaving": "saindo", "loading": "carregando", "unknown": "?"}
MAX_LOG_LINES = 500


class App:
    def __init__(self, root, runner_factory=Runner):
        self.root = root
        root.title(f"HUNTERA BOT  v{VERSION}")
        root.geometry("920x680")
        root.configure(fg_color=BG)
        icon = os.path.join(resource_dir(), "icon.ico")
        if os.path.exists(icon):
            try:
                root.iconbitmap(icon)
            except Exception:
                pass
        self.cfg = config.load(CONFIG_PATH)
        self.log_queue = queue.Queue()
        self.runner = runner_factory(self.cfg, self.log)
        self.hunts = catalog.load()
        self.tray_icon = None
        self.tray_queue = queue.Queue()
        self.close_dialog = None

        self._build_header()
        self.tabs = ctk.CTkTabview(root, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                                   segmented_button_selected_hover_color=ACCENT_HOVER, text_color="#04140a")
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        for name in ("Contas", "Regras", "Treino", "Bestiary", "Log"):
            self.tabs.add(name)
        self._build_accounts(self.tabs.tab("Contas"))
        self._build_rules(self.tabs.tab("Regras"))
        self._build_training(self.tabs.tab("Treino"))
        self._build_bestiary(self.tabs.tab("Bestiary"))
        self._build_log(self.tabs.tab("Log"))

        root.protocol("WM_DELETE_WINDOW", self.request_close)
        if sys.platform == "win32":
            root.bind("<Unmap>", self._on_unmap)
        root.after(100, self._poll_log)
        root.after(2000, self._poll_accounts)
        root.after(300, self._poll_tray)

    # ------------------------------------------------------------------ util
    def log(self, message):
        self.log_queue.put(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")

    def save(self):
        config.save(CONFIG_PATH, self.cfg)

    def _poll_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                count = int(self.log_box.index("end-1c").split(".")[0])
                if count > MAX_LOG_LINES:
                    self.log_box.delete("1.0", f"{count - MAX_LOG_LINES}.0")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)

    # ---------------------------------------------------------------- header
    def _build_header(self):
        bar = ctk.CTkFrame(self.root, fg_color=PANEL, corner_radius=8)
        bar.pack(fill="x", padx=14, pady=14)
        ctk.CTkLabel(bar, text="HUNTERA BOT", font=("Segoe UI", 18, "bold"), text_color=TEXT).pack(side="left", padx=14, pady=10)
        self.status = ctk.CTkLabel(bar, text="● PARADO", font=("Segoe UI", 13, "bold"), text_color=MUTED)
        self.status.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(bar, text="Parar", width=80, command=self.stop, state="disabled",
                                      fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT)
        self.stop_btn.pack(side="right", padx=4)
        self.start_btn = ctk.CTkButton(bar, text="Iniciar", width=90, command=self.start, fg_color=ACCENT,
                                       hover_color=ACCENT_HOVER, text_color="#04140a")
        self.start_btn.pack(side="right", padx=4)

    def start(self):
        self.runner.start()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def stop(self):
        self.runner.stop()
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal")
        self.status.configure(text="● PARADO", text_color=MUTED)

    # ---------------------------------------------------------------- contas
    def _build_accounts(self, tab):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("H.Treeview", background=PANEL_ALT, fieldbackground=PANEL_ALT, foreground=TEXT, rowheight=28, borderwidth=0)
        style.configure("H.Treeview.Heading", background=PANEL, foreground=MUTED, borderwidth=0)
        style.map("H.Treeview", background=[("selected", BORDER)])
        cols = ("conta", "voc", "fase", "cap", "stam", "hunt", "best", "desp", "grupo")
        heads = ("Conta", "Vocação", "Fase", "Capacidade", "Stamina", "Hunt", "Bestiary", "Despacho", "Grupo")
        widths = (120, 105, 80, 85, 75, 120, 70, 85, 160)
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", style="H.Treeview", height=8)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.accounts_note = ctk.CTkLabel(
            tab, text="Abra o IdleDeck com a depuração remota e as contas do Huntera; clique em Iniciar.",
            text_color=MUTED, wraplength=840, justify="left")
        self.accounts_note.pack(anchor="w", padx=12, pady=(0, 10))

    def _poll_accounts(self):
        snap = self.runner.snapshot
        if self.runner.running:
            if self.runner.connected:
                self.status.configure(text="● RODANDO", text_color=ACCENT)
            else:
                self.status.configure(text="● CONECTANDO...", text_color=MUTED)
        elif self.stop_btn.cget("state") == "normal":   # a thread caiu sozinha (erro)
            self.stop()
        self._refresh_training(snap["states"])
        self.tree.delete(*self.tree.get_children())
        for name, st in sorted(snap["states"].items()):
            group = snap["groups"].get(name, ("", False, ""))
            cap = "-" if st.cap_pct is None else f"{st.cap_pct:.0f}%"
            best = f"{st.bestiary_done}/{st.bestiary_total}" if st.bestiary_total else "-"
            desp = "pronto" if st.dispatch_ready else (st.dispatch_text.replace("PRONTO EM ", "") or "-")
            stam = "-" if st.stamina_min is None else f"{st.stamina_min // 60}:{st.stamina_min % 60:02d}h"
            kind = ("time · líder " + group[2].title()) if group[1] else "solo"
            self.tree.insert("", "end", values=(name.title(), st.vocation.title(), PHASES.get(st.phase, st.phase), cap, stam, st.hunt_name or "-", best, desp, kind))
        self.root.after(2000, self._poll_accounts)

    # ---------------------------------------------------------------- regras
    def _build_rules(self, tab):
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(anchor="nw", padx=14, pady=14)
        self.rule_vars = {}

        def row(r, label, key, sub=None, hint=""):
            ctk.CTkLabel(grid, text=label, text_color=TEXT).grid(row=r, column=0, sticky="w", pady=6, padx=(0, 14))
            value = self.cfg[key] if sub is None else self.cfg[key][sub]
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(grid, textvariable=var, width=90, fg_color=PANEL_ALT).grid(row=r, column=1, sticky="w")
            ctk.CTkLabel(grid, text=hint, text_color=MUTED).grid(row=r, column=2, sticky="w", padx=12)
            self.rule_vars[(key, sub)] = var

        row(0, "Sair para vender com", "capacity_pct", None, "% da capacidade usada, de QUALQUER conta do time (ex.: 90)")
        row(2, "Despacho a partir de", "dispatch", "min_cap_pct", "% de capacidade (o despacho vale 1x por hora e não sai da hunt)")
        row(3, "Treino quando faltar", "training", "stamina_minutes", "minutos de stamina (hunt gratuita) - de QUALQUER conta do time")
        row(4, "Pausa após um ciclo", "cooldown_ok_seconds", None, "segundos")
        row(5, "Pausa após uma falha", "cooldown_fail_seconds", None, "segundos")
        self.dispatch_var = tk.BooleanVar(value=self.cfg["dispatch"]["enabled"])
        ctk.CTkCheckBox(grid, text="Usar o Despachar loot", variable=self.dispatch_var, fg_color=ACCENT, text_color=TEXT).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        self.training_var = tk.BooleanVar(value=self.cfg["training"]["enabled"])
        ctk.CTkCheckBox(grid, text="Mandar o time pro treino quando a stamina acabar", variable=self.training_var, fg_color=ACCENT,
                        text_color=TEXT).grid(row=6, column=0, columnspan=3, sticky="w", pady=6)
        ctk.CTkButton(grid, text="Salvar regras", command=self._save_rules, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#04140a").grid(row=7, column=0, sticky="w", pady=16)
        self.rules_msg = ctk.CTkLabel(grid, text="", text_color=MUTED)
        self.rules_msg.grid(row=7, column=1, columnspan=2, sticky="w")
        ctk.CTkLabel(tab, text="O bot vende TUDO o que estiver na mochila (a bolsa não entra). Proteja antes o que quiser guardar. "
                               "No treino: Knight = Axe Fighting, Paladin = Distance Fighting, Druid/Sorcerer = Magic Level.",
                     text_color=MUTED, wraplength=840, justify="left").pack(anchor="w", padx=14)

    def _save_rules(self):
        try:
            new = {}
            for (key, sub), var in self.rule_vars.items():
                number = float(var.get().replace(",", "."))
                if number < 0 or (key == "capacity_pct" and not 1 <= number <= 100):
                    raise ValueError(key)
                new[(key, sub)] = int(number) if number == int(number) else number
        except ValueError:
            self.rules_msg.configure(text="Valor inválido (capacidade entre 1 e 100; o resto, números positivos).", text_color=DANGER)
            return
        for (key, sub), value in new.items():
            if sub is None:
                self.cfg[key] = value
            else:
                self.cfg[key][sub] = value
        self.cfg["dispatch"]["enabled"] = bool(self.dispatch_var.get())
        self.cfg["training"]["enabled"] = bool(self.training_var.get())
        self.save()
        self.rules_msg.configure(text="Salvo.", text_color=ACCENT)

    # ----------------------------------------------------------------- treino
    def _build_training(self, tab):
        ctk.CTkLabel(tab, text="O que cada personagem treina quando a stamina acabar (uma habilidade por personagem). "
                               "As opções vêm do que o jogo oferece a cada conta; sem escolha, vale o padrão da vocação.",
                     text_color=MUTED, wraplength=860, justify="left").pack(anchor="w", padx=14, pady=(12, 4))
        self.training_frame = ctk.CTkScrollableFrame(tab, fg_color=PANEL_ALT)
        self.training_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.training_names = None
        self._refresh_training({})

    def _training_accounts(self, states):
        """{nome: (vocacao, [habilidades])} das contas ja lidas (memory.json) + as ao vivo."""
        out = {}
        for key, info in Memory(MEMORY_PATH).all_options().items():
            out[info["name"].title()] = (info.get("vocation", ""), info.get("skills") or config.ALL_SKILLS)
        for name, st in states.items():
            if name.title() not in out:
                out[name.title()] = (st.vocation, config.ALL_SKILLS)
        return out

    def _refresh_training(self, states):
        accounts = self._training_accounts(states)
        signature = tuple(sorted((n, v, tuple(s)) for n, (v, s) in accounts.items()))
        if signature == self.training_names:
            return
        self.training_names = signature
        for child in self.training_frame.winfo_children():
            child.destroy()
        if not accounts:
            ctk.CTkLabel(self.training_frame, text="Nenhuma conta vista ainda. Abra as contas no IdleDeck e clique em Iniciar.", text_color=MUTED).pack(pady=20)
            return
        for name, (vocation, skills) in sorted(accounts.items()):
            default = config.default_skill(self.cfg["training"], vocation)
            row = ctk.CTkFrame(self.training_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=5)
            ctk.CTkLabel(row, text=f"{name} · {vocation.title()}", text_color=TEXT, width=260, anchor="w").pack(side="left")
            chosen = (self.cfg["training"].get("by_name") or {}).get(name.casefold())
            values = [DEFAULT_CHOICE] + list(skills)
            var = tk.StringVar(value=chosen if chosen in skills else DEFAULT_CHOICE)
            ctk.CTkOptionMenu(row, values=values, variable=var, width=200, fg_color=PANEL,
                              command=lambda value, n=name: self._training_changed(n, value)).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"padrão: {default or '-'}", text_color=MUTED).pack(side="left", padx=8)

    def _training_changed(self, name, value):
        by_name = self.cfg["training"].setdefault("by_name", {})
        if value == DEFAULT_CHOICE:
            by_name.pop(name.casefold(), None)
        else:
            by_name[name.casefold()] = value
        self.save()
        self.log(f"treino de {name}: {value if value != DEFAULT_CHOICE else 'padrão da vocação'}")

    # -------------------------------------------------------------- bestiary
    def _build_bestiary(self, tab):
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.chain_enabled = tk.BooleanVar(value=self.cfg["bestiary_chain"]["enabled"])
        ctk.CTkCheckBox(top, text="Ir para a próxima hunt quando o Bestiary da atual fechar (em todas as contas do time)",
                        variable=self.chain_enabled, command=self._chain_changed, fg_color=ACCENT, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(top, text="A lista segue a progressão do jogo (Rat Cellars = 1ª). Escolha à esquerda, adicione, e ajuste a ordem e o pull à direita.",
                     text_color=MUTED, wraplength=860, justify="left").pack(anchor="w", pady=(4, 0))

        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        left = ctk.CTkFrame(body, fg_color=PANEL_ALT)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_catalog())
        ctk.CTkEntry(left, textvariable=self.search_var, placeholder_text="Buscar caçada ou criatura...", fg_color=BG).pack(fill="x", padx=8, pady=8)
        self.catalog_list = self._listbox(left)
        ctk.CTkButton(left, text="Adicionar à cadeia →", command=self._chain_add, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#04140a").pack(pady=8)

        right = ctk.CTkFrame(body, fg_color=PANEL_ALT)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(right, text="Cadeia (na ordem)", text_color=TEXT).pack(anchor="w", padx=10, pady=(10, 4))
        self.chain_list = self._listbox(right)
        self.chain_list.bind("<<ListboxSelect>>", lambda e: self._chain_select())
        controls = ctk.CTkFrame(right, fg_color="transparent")
        controls.pack(pady=6)
        for text, cmd in (("Subir", lambda: self._chain_move(-1)), ("Descer", lambda: self._chain_move(1)),
                          ("Remover", self._chain_remove), ("Ordenar por progressão", self._chain_sort)):
            ctk.CTkButton(controls, text=text, width=70 if text != "Ordenar por progressão" else 150, command=cmd, fg_color=PANEL,
                          hover_color=BORDER, text_color=TEXT).pack(side="left", padx=3)
        tier_row = ctk.CTkFrame(right, fg_color="transparent")
        tier_row.pack(pady=(0, 10))
        ctk.CTkLabel(tier_row, text="Pull da selecionada:", text_color=MUTED).pack(side="left", padx=6)
        self.tier_var = tk.StringVar(value=TIERS[0])
        ctk.CTkOptionMenu(tier_row, values=TIERS, variable=self.tier_var, command=self._tier_changed, fg_color=PANEL, width=160).pack(side="left")
        self._refresh_catalog()
        self._refresh_chain()

    def _listbox(self, parent):
        box = tk.Listbox(parent, bg=BG, fg=TEXT, selectbackground=BORDER, selectforeground=TEXT, highlightthickness=0,
                         borderwidth=0, activestyle="none", font=("Segoe UI", 10), exportselection=False)
        box.pack(fill="both", expand=True, padx=8)
        return box

    def _chain(self):
        return self.cfg["bestiary_chain"]["hunts"]

    def _refresh_catalog(self):
        self.shown = catalog.search(self.hunts, self.search_var.get())
        self.catalog_list.delete(0, "end")
        for h in self.shown:
            self.catalog_list.insert("end", f"{h['order']:>2} · {h['name']}  —  {', '.join(h['creatures'])}")

    def _refresh_chain(self, select=None):
        self.chain_list.delete(0, "end")
        for i, item in enumerate(self._chain(), 1):
            self.chain_list.insert("end", f"{i}. {item['name']}   [{item.get('tier') or 'pull padrão'}]")
        if select is not None and 0 <= select < len(self._chain()):
            self.chain_list.selection_set(select)
            self._chain_select()

    def _chain_changed(self):
        self.cfg["bestiary_chain"]["enabled"] = bool(self.chain_enabled.get())
        self.save()

    def _chain_add(self):
        for index in self.catalog_list.curselection():
            hunt = self.shown[index]
            if not any(c["name"] == hunt["name"] for c in self._chain()):
                self._chain().append({"name": hunt["name"]})
        self.cfg["bestiary_chain"]["hunts"] = catalog.sort_chain(self._chain(), self.hunts)
        self.save()
        self._refresh_chain()

    def _chain_selected(self):
        sel = self.chain_list.curselection()
        return sel[0] if sel else None

    def _chain_select(self):
        i = self._chain_selected()
        if i is not None:
            self.tier_var.set(self._chain()[i].get("tier") or TIERS[0])

    def _tier_changed(self, value):
        i = self._chain_selected()
        if i is None:
            return
        if value == TIERS[0]:
            self._chain()[i].pop("tier", None)
        else:
            self._chain()[i]["tier"] = value
        self.save()
        self._refresh_chain(i)

    def _chain_move(self, delta):
        i = self._chain_selected()
        if i is None or not 0 <= i + delta < len(self._chain()):
            return
        chain = self._chain()
        chain[i], chain[i + delta] = chain[i + delta], chain[i]
        self.save()
        self._refresh_chain(i + delta)

    def _chain_remove(self):
        i = self._chain_selected()
        if i is not None:
            self._chain().pop(i)
            self.save()
            self._refresh_chain()

    def _chain_sort(self):
        self.cfg["bestiary_chain"]["hunts"] = catalog.sort_chain(self._chain(), self.hunts)
        self.save()
        self._refresh_chain()

    # ------------------------------------------------------------------- log
    def _build_log(self, tab):
        self.log_box = ctk.CTkTextbox(tab, fg_color=BG, text_color=TEXT, font=("Consolas", 11), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkButton(tab, text="Abrir pasta dos logs", command=lambda: os.startfile(os.path.join(ROOT, "logs")) if os.path.isdir(os.path.join(ROOT, "logs")) else None,
                      fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT).pack(anchor="e", padx=8, pady=(0, 8))

    # ------------------------------------------------------- fechar / bandeja
    def request_close(self):
        if sys.platform != "win32":
            self.quit()
            return
        if self.close_dialog is not None and self.close_dialog.winfo_exists():
            self.close_dialog.lift()
            return
        win = ctk.CTkToplevel(self.root)
        win.title("Fechar o bot")
        win.geometry("430x200")
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        self.close_dialog = win

        def choose(action):
            win.destroy()
            if action == "tray":
                self.hide_to_tray()
            elif action == "quit":
                self.quit()

        ctk.CTkLabel(win, text="O que deseja fazer?", text_color=TEXT, font=("Segoe UI", 13)).pack(padx=20, pady=(20, 6))
        hint = ("O bot está rodando: na bandeja ele continua; fechar de vez para tudo." if self.runner.running
                else "Na bandeja o app fica escondido; fechar de vez encerra o programa.")
        ctk.CTkLabel(win, text=hint, text_color=MUTED, wraplength=390).pack(padx=20, pady=(0, 16))
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Guardar na bandeja", command=lambda: choose("tray"), fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#04140a").pack(side="left", padx=6)
        ctk.CTkButton(row, text="Fechar de vez", command=lambda: choose("quit"), fg_color=PANEL_ALT, hover_color=BORDER, text_color=TEXT).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancelar", command=lambda: choose("cancel"), fg_color="transparent", hover_color=BORDER, text_color=MUTED).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))

    def _on_unmap(self, event):
        if event.widget is not self.root:
            return
        try:
            if self.root.state() == "iconic":
                self.root.after(50, self.hide_to_tray)
        except tk.TclError:
            pass

    def hide_to_tray(self):
        if sys.platform != "win32" or self.tray_icon is not None:
            return
        try:
            pystray = importlib.import_module("pystray")
            image_module = importlib.import_module("PIL.Image")
            icon_path = os.path.join(resource_dir(), "icon.ico")
            image = image_module.open(icon_path) if os.path.exists(icon_path) else image_module.new("RGB", (64, 64), ACCENT)
            menu = pystray.Menu(
                pystray.MenuItem("Abrir", lambda icon, item: self.tray_queue.put("open"), default=True),
                pystray.MenuItem("Fechar de vez", lambda icon, item: self.tray_queue.put("quit")))
            self.tray_icon = pystray.Icon("HunteraBot", image, "HUNTERA BOT", menu)
            self.tray_icon.run_detached()
        except Exception as error:
            self.tray_icon = None
            self.log(f"Bandeja indisponivel ({error}) - o app fica so minimizado.")
            return
        self.root.withdraw()

    def _stop_tray(self):
        icon, self.tray_icon = self.tray_icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def show_from_tray(self):
        self._stop_tray()
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _poll_tray(self):
        try:
            while True:
                action = self.tray_queue.get_nowait()
                if action == "open":
                    self.show_from_tray()
                elif action == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(300, self._poll_tray)

    def quit(self):
        self.runner.stop()
        self._stop_tray()
        self.root.destroy()


def main():
    root = ctk.CTk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
