"""Teste da interface com uma janela de verdade (aparece por instantes) e um runner falso."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk

from huntera_bot import gui, updater
from huntera_bot.account import State


class StubRunner:
    def __init__(self, cfg, log):
        self.cfg, self.log = cfg, log
        self.running = False
        self.connected = False
        self.snapshot = {"states": {}, "groups": {}}

    def start(self):
        self.running = True
        self.connected = True

    def stop(self):
        self.running = False


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def find_button(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton) and child.cget("text") == text:
            return child
        found = find_button(child, text)
        if found:
            return found


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        gui.CONFIG_PATH = os.path.join(cls.tmp, "config.json")
        cls.root = ctk.CTk()
        cls.app = gui.App(cls.root, runner_factory=StubRunner)
        pump(cls.root, 0.5)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.quit()
        except Exception:
            pass

    def saved(self):
        with open(gui.CONFIG_PATH, encoding="utf-8") as file:
            return json.load(file)

    def test_1_catalog_and_search(self):
        self.assertEqual(self.app.catalog_list.size(), 75)
        self.app.search_var.set("vampire")
        pump(self.root, 0.2)
        names = [self.app.catalog_list.get(i) for i in range(self.app.catalog_list.size())]
        self.assertTrue(any("Vampire Crypt" in n for n in names))
        self.assertLess(len(names), 75)
        self.app.search_var.set("")

    def test_2_chain_add_is_sorted_by_progression(self):
        order = {h["name"]: h["order"] for h in self.app.hunts}
        for name in ("Rotworm Caves", "Rat Cellars"):          # adiciona fora de ordem
            idx = next(i for i, h in enumerate(self.app.shown) if h["name"] == name)
            self.app.catalog_list.selection_clear(0, "end")
            self.app.catalog_list.selection_set(idx)
            self.app._chain_add()
        chain = [c["name"] for c in self.app.cfg["bestiary_chain"]["hunts"]]
        self.assertEqual(chain, ["Rat Cellars", "Rotworm Caves"])
        self.assertLess(order["Rat Cellars"], order["Rotworm Caves"])
        self.assertEqual([c["name"] for c in self.saved()["bestiary_chain"]["hunts"]], chain)

    def test_3_tier_enable_move_remove(self):
        self.app.chain_list.selection_clear(0, "end")
        self.app.chain_list.selection_set(1)
        self.app._chain_select()
        self.app._tier_changed("Ousado")
        self.assertEqual(self.saved()["bestiary_chain"]["hunts"][1], {"name": "Rotworm Caves", "tier": "Ousado"})
        self.app._tier_changed(gui.TIERS[0])
        self.assertNotIn("tier", self.saved()["bestiary_chain"]["hunts"][1])
        self.app._chain_move(-1)
        self.assertEqual([c["name"] for c in self.app._chain()], ["Rotworm Caves", "Rat Cellars"])
        self.app._chain_sort()
        self.assertEqual([c["name"] for c in self.app._chain()], ["Rat Cellars", "Rotworm Caves"])
        self.app.chain_list.selection_clear(0, "end")
        self.app.chain_list.selection_set(1)
        self.app._chain_remove()
        self.assertEqual(len(self.app._chain()), 1)
        self.app.chain_enabled.set(True)
        self.app._chain_changed()
        self.assertTrue(self.saved()["bestiary_chain"]["enabled"])

    def test_4_rules_validation_and_save(self):
        self.app.rule_vars[("capacity_pct", None)].set("150")
        self.app._save_rules()
        self.assertEqual(self.app.cfg["capacity_pct"], 90)           # invalido: nao muda
        self.app.rule_vars[("capacity_pct", None)].set("85")
        self.app.rule_vars[("dispatch", "min_cap_pct")].set("55")
        self.app.dispatch_var.set(False)
        self.app.rule_vars[("training", "stamina_minutes")].set("20")
        self.app.training_var.set(True)
        self.app._save_rules()
        saved = self.saved()
        self.assertEqual((saved["capacity_pct"], saved["dispatch"]["min_cap_pct"], saved["dispatch"]["enabled"]), (85, 55, False))
        self.assertEqual((saved["training"]["stamina_minutes"], saved["training"]["enabled"]), (20, True))
        self.assertEqual(saved["training"]["skills"]["knight"], "Axe Fighting")        # o resto do bloco foi preservado

    def test_5_accounts_table(self):
        st = State(name="ALIADO DOIS", vocation="ELDER DRUID", phase="hunting", cap_pct=57.8, hunt_name="Rat Cellars",
                   bestiary_done=0, bestiary_total=1, dispatch_ready=True, stamina_min=343)
        self.app.runner.snapshot = {"states": {"ALIADO DOIS": st}, "groups": {"ALIADO DOIS": ("A + B", True, "ALIADO UM")}}
        self.app.runner.running = True
        self.app.runner.connected = True
        self.app._poll_accounts()
        rows = [self.app.tree.item(i, "values") for i in self.app.tree.get_children()]
        self.assertEqual(rows[0][:7], ("Aliado Dois", "Elder Druid", "caçando", "58%", "5:43h", "Rat Cellars", "0/1"))
        self.assertIn("time", rows[0][8])
        self.app.runner.running = False                          # o teste nao deve deixar o bot "rodando"
        self.app.runner.connected = False

    def test_6_training_tab_free_choice_per_character(self):
        from huntera_bot.memory import Memory
        gui.MEMORY_PATH = os.path.join(self.tmp, "memory.json")
        mem = Memory(gui.MEMORY_PATH)
        mem.set_options("Aliado Um", "Elite Knight", ["Club Fighting", "Sword Fighting", "Axe Fighting", "Magic Level"])
        mem.set_options("Aliado Dois", "Elder Druid", ["Magic Level", "Shielding"])
        self.app.training_names = None
        self.app._refresh_training({})
        rows = [w for w in self.app.training_frame.winfo_children()]
        self.assertEqual(len(rows), 2)
        self.app._training_changed("Aliado Um", "Sword Fighting")             # knight treinando sword
        self.assertEqual(self.saved()["training"]["by_name"], {"aliado um": "Sword Fighting"})
        self.app._training_changed("Aliado Dois", "Shielding")
        self.assertEqual(self.saved()["training"]["by_name"]["aliado dois"], "Shielding")
        self.app._training_changed("Aliado Um", gui.DEFAULT_CHOICE)            # volta ao padrao
        self.assertNotIn("aliado um", self.saved()["training"]["by_name"])

    def test_13_imbuements_tab_costs_and_plan(self):
        from huntera_bot.memory import Memory
        gui.MEMORY_PATH = os.path.join(self.tmp, "memory.json")
        mem = Memory(gui.MEMORY_PATH)
        empty = {"active": None, "minutes": None}
        mem.set_imbue("equipment", "mr sorc", {"name": "MR SORC", "vocation": "Elder Druid", "gold": 20_000,
                                               "items": {"vampire shield": [empty],
                                                         "crown helmet": [{"active": "Basic Void", "minutes": 75}, empty]}})
        mem.set_imbue("prices", "cultish robe", {"rows": [{"seller": "a", "qty": 99, "price": 151}]})
        self.app._refresh_imbuements({}, force=True)
        self.assertEqual(self.app.imbue_account.get(), "Mr Sorc")
        self.assertEqual(len(self.app.imbue_rows), 3)
        status = self.app.imbue_rows[("crown helmet", 0)][3].cget("text")
        self.assertEqual(status, "Roubo de mana Básico · 1h 15m")
        imb, tier, renew, _status, cost = self.app.imbue_rows[("vampire shield", 0)]
        imb.set("Proteção sagrado (Demon Presence)")
        self.app._imbue_recalc()
        self.assertEqual(cost.cget("text"), "8.775")                 # 25 x 151 + 5.000 de taxa
        self.assertIn("Total 8.775", self.app.imbue_summary.cget("text"))
        self.assertNotIn("FALTAM", self.app.imbue_summary.cget("text"))
        tier.set("Poderoso")                                          # sem preco dos outros materiais
        self.app._imbue_recalc()
        self.assertIn("FALTAM", self.app.imbue_summary.cget("text"))   # 250 mil > 20 mil de gold
        self.assertIn("preços ainda não lidos", self.app.imbue_summary.cget("text"))
        tier.set("Básico")
        renew.set(False)
        self.app._imbue_save()
        self.assertEqual(self.saved()["imbuements"]["plan"]["mr sorc"],
                         {"vampire shield": [{"imbuement": "Demon Presence", "tier": "Basic", "renew": False}]})
        imb.set(gui.imbuing.NONE)
        self.app._imbue_save()
        self.assertNotIn("mr sorc", self.saved()["imbuements"]["plan"])

    def test_14_default_hunt(self):
        self.app.default_hunt.set("Rat Cellars")
        self.app.default_tier.set("Agressivo")
        self.app._default_changed()
        self.assertEqual(self.saved()["default_hunt"], {"name": "Rat Cellars", "tier": "Agressivo"})
        self.app.default_hunt.set(gui.NO_DEFAULT)
        self.app.default_tier.set(gui.TIERS[0])
        self.app._default_changed()
        self.assertEqual(self.saved()["default_hunt"], {"name": "", "tier": ""})

    def _drain_log(self):
        """Texto do painel de log (o laco do app passa a fila pro painel)."""
        pump(self.root, 0.4)
        return self.app.log_box.get("1.0", "end")

    def test_8_update_up_to_date(self):
        with mock.patch.object(updater, "check_for_update", lambda log=print, **k: None):
            self.app.start_update()
            pump(self.root, 1.0)
        self.assertIn("última versão", self._drain_log())
        self.assertEqual(self.app.update_btn.cget("text"), "Atualizar")
        self.assertFalse(self.app.updating)

    def test_9_update_in_dev_mode_does_not_replace_anything(self):
        with mock.patch.object(updater, "check_for_update", lambda log=print, **k: {"version": "9.9.9", "asset_url": "x"}),                 mock.patch.object(updater, "is_frozen", lambda: False):
            self.app.start_update()
            pump(self.root, 1.0)
        self.assertIn("só funciona no executável", self._drain_log())
        self.assertIsNone(self.app.update_overlay)

    def test_10_update_flow_overlay_and_restart(self):
        calls = []
        with mock.patch.object(updater, "check_for_update", lambda log=print, **k: {"version": "9.9.9", "asset_url": "x"}),                 mock.patch.object(updater, "is_frozen", lambda: True),                 mock.patch.object(updater, "apply_update", lambda url, log, progress=None, **k: (progress(0.5), True)[1]),                 mock.patch.object(self.app, "quit", lambda: calls.append("quit")):
            self.app.start_update(confirm=False)
            pump(self.root, 0.8)
            self.assertTrue(self.app.updating)
            self.assertIsNotNone(self.app.update_overlay)                   # tela de carregamento cobrindo tudo
            pump(self.root, 2.5)
        self.assertEqual(calls, ["quit"])                                     # fecha pro .bat trocar o exe
        self.app.update_overlay.destroy()
        self.app.update_overlay = None
        self.app.updating = False

    def test_11_update_failure_restores_the_window(self):
        with mock.patch.object(updater, "check_for_update", lambda log=print, **k: {"version": "9.9.9", "asset_url": "x"}),                 mock.patch.object(updater, "is_frozen", lambda: True),                 mock.patch.object(updater, "apply_update", lambda url, log, progress=None, **k: False):
            self.app.start_update(confirm=False)
            pump(self.root, 1.5)
        self.assertFalse(self.app.updating)
        self.assertIsNone(self.app.update_overlay)
        self.assertIn("Não consegui aplicar", self._drain_log())

    def test_12_update_blocked_while_bot_runs(self):
        self.app.runner.running = True
        self.app.start_update()
        self.assertIn("Pare o bot", self._drain_log())
        self.app.runner.running = False

    def test_7_close_dialog_and_tray(self):
        self.app.request_close()
        pump(self.root, 0.4)
        self.assertTrue(self.app.close_dialog.winfo_exists())
        find_button(self.app.close_dialog, "Guardar na bandeja").invoke()
        pump(self.root, 1.0)
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertIsNotNone(self.app.tray_icon)
        self.app.tray_queue.put("open")
        pump(self.root, 1.0)
        self.assertEqual(self.root.state(), "normal")
        self.assertIsNone(self.app.tray_icon)


if __name__ == "__main__":
    unittest.main()
