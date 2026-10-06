import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from huntera_bot import imbuing
from huntera_bot.account import parse_slot_title, parse_tooltip

CAT = imbuing.load()


class CatalogTests(unittest.TestCase):
    def test_catalog_has_the_22_imbuements_with_cumulative_materials(self):
        self.assertEqual(len(CAT), 22)
        for imb in CAT.values():
            b, i, p = (imb["tiers"][t]["materials"] for t in imbuing.TIERS)
            self.assertEqual(i[:1], b)
            self.assertEqual(p[:2], i)

    def test_known_items_come_from_what_was_seen_in_the_shrine(self):
        items = imbuing.known_items(CAT)
        self.assertIn("Epiphany", items["wand of voodoo"]["Powerful"])
        self.assertIn("Swiftness", items["boots of haste"]["Basic"])


class ParseTests(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(imbuing.minutes("20h 0m"), 1200)
        self.assertEqual(imbuing.minutes("resta 1h 05m"), 65)
        self.assertEqual(imbuing.minutes("45m"), 45)
        self.assertEqual(imbuing.minutes("Basic Demon Presence (20 horas)"), 1200)
        self.assertEqual(imbuing.minutes("(1 hora)"), 60)
        self.assertEqual(imbuing.minutes("(30 minutos)"), 30)
        self.assertIsNone(imbuing.minutes("Slot de imbuement vazio"))

    def test_split_active_and_number(self):
        self.assertEqual(imbuing.split_active("Powerful Demon Presence"), ("Powerful", "Demon Presence"))
        self.assertEqual(imbuing.split_active("Vazio"), (None, "Vazio"))
        self.assertEqual(imbuing.number("Imbuir — 200.000 gp"), 200000)

    def test_tooltip_of_an_equipped_item(self):
        text = ("vampire shield\nDefesa: 34\nClassificação: 1\nBasic Demon Presence (20 horas)\n"
                "Valor no Npc: 15.000\nValor no leilão: 16.500\n38.00 oz")
        name, slots = parse_tooltip(text)
        self.assertEqual(name, "vampire shield")
        self.assertEqual(slots, [{"active": "Basic Demon Presence", "minutes": 1200}])
        name, slots = parse_tooltip("crown helmet\nArmadura: 7\nSlot de imbuement vazio\nSlot de imbuement vazio\n29.50 oz")
        self.assertEqual(slots, [{"active": None, "minutes": None}] * 2)

    def test_slot_title_in_the_shrine(self):
        self.assertEqual(parse_slot_title("Basic Demon Presence — resta 19h 42m"), {"active": "Basic Demon Presence", "minutes": 1182})
        self.assertEqual(parse_slot_title("Slot de imbuement vazio"), {"active": None, "minutes": None})


class CostTests(unittest.TestCase):
    def test_walk_buys_from_the_cheapest_rows(self):
        rows = [{"qty": 7, "price": 151}, {"qty": 10, "price": 151}, {"qty": 100, "price": 200}]
        self.assertEqual(imbuing.walk(rows, 25), (7 * 151 + 10 * 151 + 8 * 200, 0))
        self.assertEqual(imbuing.walk(rows[:1], 25), (7 * 151, 18))

    def test_protection_is_automatic(self):
        powerful = CAT["Strike"]["tiers"]["Powerful"]
        basic = CAT["Strike"]["tiers"]["Basic"]
        intricate = CAT["Strike"]["tiers"]["Intricate"]
        self.assertTrue(imbuing.protect_auto(powerful, 0))          # 50% de chance: sempre compensa
        self.assertFalse(imbuing.protect_auto(basic, 3_775))        # materiais baratos: arrisca os 90%
        self.assertTrue(imbuing.protect_auto(basic, 200_000))
        self.assertFalse(imbuing.protect_auto(intricate, 20_000))
        self.assertTrue(imbuing.protect_auto(intricate, 60_000))

    def test_powerful_strike_with_every_material_costs_fee_plus_protection(self):
        have = {"protective charm": 20, "sabretooth": 25, "vexclaw talon": 5}
        prices = {m: [{"qty": 999, "price": 1000}] for m in have}
        c = imbuing.entry_cost(CAT, "Strike", "Powerful", have, prices)
        self.assertEqual((c["fee"], c["protection"], c["buy"], c["total"]), (200_000, 50_000, {}, 250_000))

    def test_missing_materials_are_bought(self):
        prices = {"cultish robe": [{"qty": 7, "price": 151}, {"qty": 100, "price": 151}]}
        c = imbuing.entry_cost(CAT, "Demon Presence", "Basic", {}, prices)
        self.assertEqual(c["buy"], {"cultish robe": 25})
        self.assertEqual(c["buy_cost"], 3_775)
        self.assertFalse(c["protect"])
        self.assertEqual(c["total"], 8_775)

    def test_no_stock_and_unknown_prices_are_flagged(self):
        c = imbuing.entry_cost(CAT, "Swiftness", "Intricate", {}, {"damselfly wing": [{"qty": 99, "price": 5400}], "compass": []})
        self.assertEqual(c["no_stock"], ["compass"])
        c = imbuing.entry_cost(CAT, "Swiftness", "Basic", {}, {})
        self.assertEqual(c["unknown"], ["damselfly wing"])

    def test_tokens_only_when_enabled_and_available(self):
        c = imbuing.entry_cost(CAT, "Void", "Basic", {}, {}, use_tokens=True, tokens_have=2)
        self.assertEqual((c["pay"], c["buy"], c["total"]), ("tokens", {}, 5_000))
        c = imbuing.entry_cost(CAT, "Void", "Basic", {}, {}, use_tokens=True, tokens_have=1)
        self.assertEqual(c["pay"], "materials")
        c = imbuing.entry_cost(CAT, "Void", "Basic", {}, {}, use_tokens=False, tokens_have=9)
        self.assertEqual(c["pay"], "materials")


class PendingTests(unittest.TestCase):
    EMPTY = {"active": None, "minutes": None}

    def test_planned_imbuement_missing_from_the_item_is_applied(self):
        plan = {"royal helmet": [{"imbuement": "Void", "tier": "Powerful", "renew": True}, None]}
        equipment = {"royal helmet": [self.EMPTY, self.EMPTY]}
        tasks = imbuing.pending(plan, equipment)
        self.assertEqual([(t["item"], t["imbuement"], t["tier"], t["kind"]) for t in tasks],
                         [("royal helmet", "Void", "Powerful", "apply")])

    def test_active_imbuement_is_left_alone_until_close_to_the_end(self):
        plan = {"royal helmet": [{"imbuement": "Void", "tier": "Basic", "renew": True}]}
        active = {"royal helmet": [{"active": "Basic Void", "minutes": 25}]}
        self.assertEqual(imbuing.pending(plan, active), [])
        early = imbuing.pending(plan, active, early_minutes=30)
        self.assertEqual([t["kind"] for t in early], ["early"])
        self.assertEqual(imbuing.pending(plan, {"royal helmet": [{"active": "Basic Void", "minutes": 40}]}, 30), [])

    def test_without_renew_it_is_done_once(self):
        plan = {"backpack": [{"imbuement": "Featherweight", "tier": "Basic", "renew": False}]}
        equipment = {"backpack": [self.EMPTY]}
        self.assertEqual(len(imbuing.pending(plan, equipment)), 1)
        done = {imbuing.done_key("backpack", "Featherweight")}
        self.assertEqual(imbuing.pending(plan, equipment, done=done), [])
        self.assertEqual(imbuing.pending(plan, {"backpack": [{"active": "Basic Featherweight", "minutes": 5}]}, 30, done), [])

    def test_never_more_than_the_free_slots_and_only_equipped_items(self):
        plan = {"rift bow": [{"imbuement": "Strike", "tier": "Basic", "renew": True},
                             {"imbuement": "Void", "tier": "Basic", "renew": True}],
                "magic plate armor": [{"imbuement": "Lich Shroud", "tier": "Basic", "renew": True}]}
        equipment = {"rift bow": [{"active": "Basic Scorch", "minutes": 300}, self.EMPTY]}
        tasks = imbuing.pending(plan, equipment)
        self.assertEqual([t["imbuement"] for t in tasks], ["Strike"])


if __name__ == "__main__":
    unittest.main()
