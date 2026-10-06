"""Imbuements no motor com um mundo falso: sair da caçada, comprar, imbuir e voltar."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from huntera_bot import config, imbuing
from huntera_bot.engine import Engine
from huntera_bot.memory import Memory
from test_engine import Clock, FakeAccount, World

CAT = imbuing.load()


class ImbueAccount(FakeAccount):
    """Conta falsa com santuario e leilao: o slot do item enche quando imbui."""

    def __init__(self, world, state, gold, items, market):
        super().__init__(world, state)
        self.state.gold = gold
        self.items = items              # {item: [slot]}
        self.market = market            # {material: [ofertas]}
        self.have = {}
        self.fail_next = 0

    def read(self):
        st = super().read()
        st.imbue_pips = [(item, len(s), sum(1 for x in s if x["active"])) for item, s in sorted(self.items.items())]
        return st

    def read_equipment(self):
        self.world.calls.append(("equip", self.name))
        return copy.deepcopy(self.items)

    def shrine_read(self, scan_allowed=True):
        self.world.calls.append(("shrine", self.name))
        allowed = imbuing.known_items(CAT)
        return {item: {"slots": copy.deepcopy(s), "allowed": allowed.get(item) if scan_allowed else None}
                for item, s in self.items.items()}

    def shrine_offer(self, item, family, tier, catalog):
        mats = imbuing.materials(catalog, family, tier)
        return {"have": {m["name"]: min(self.have.get(m["name"], 0), m["count"]) for m in mats}, "tokens_have": 0}

    def market_offers(self, names):
        return {n: copy.deepcopy(self.market.get(n, [])) for n in names}

    def market_buy(self, name, qty, max_total):
        cost, short = imbuing.walk(self.market.get(name, []), qty)
        bought = qty - short
        self.world.calls.append(("buy", self.name, name, bought))
        self.have[name] = self.have.get(name, 0) + bought
        self.state.gold -= cost
        return bought, cost

    def shrine_apply(self, item, family, tier, protect, tokens=False):
        info = CAT[family]["tiers"][tier]
        self.world.calls.append(("imbue", self.name, item, f"{tier} {family}", protect))
        self.state.gold -= info["gold"] + (info["protection_gold"] if protect else 0)
        for m in info["materials"]:
            self.have[m["name"]] -= m["count"]
        if self.fail_next:
            self.fail_next -= 1
            return False, "falhou"
        slot = next(s for s in self.items[item] if not s["active"])
        slot.update(active=f"{tier} {family}", minutes=1200)
        return True, f"{tier} {family} aplicado."

    def shrine_remove(self, item, family):
        self.world.calls.append(("remove", self.name, item, family))
        for s in self.items[item]:
            if s["active"] and family in s["active"]:
                s.update(active=None, minutes=None)
        return True


ROBES = {"cultish robe": [{"seller": "a", "qty": 7, "price": 151}, {"seller": "b", "qty": 100, "price": 151}]}
EMPTY = {"active": None, "minutes": None}


def setup(gold=2_000_000, items=None, market=None, plan=None, phase="hunting"):
    world = World()
    world.add("Mr Sorc")                  # solo
    base = world.accounts["MR SORC"]
    acc = ImbueAccount(world, base.state, gold, items if items is not None else {"vampire shield": [dict(EMPTY)]},
                       market if market is not None else copy.deepcopy(ROBES))
    acc.state.phase = phase
    world.accounts["MR SORC"] = acc
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["imbuements"]["plan"] = {"mr sorc": plan if plan is not None else
                                 {"vampire shield": [{"imbuement": "Demon Presence", "tier": "Basic", "renew": True}]}}
    clock = Clock()
    logs = []
    engine = Engine([acc], cfg, log=logs.append, clock=clock, sleep=clock.sleep, memory=Memory())
    return world, acc, engine, clock, logs


def kinds(world, kind):
    return [c for c in world.calls if c[0] == kind]


class ImbuerTests(unittest.TestCase):
    def test_leaves_buys_imbues_and_returns_to_the_hunt(self):
        world, acc, engine, clock, logs = setup()
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [("leave", "MR SORC")])
        self.assertEqual(kinds(world, "buy"), [("buy", "MR SORC", "cultish robe", 25)])
        self.assertEqual(kinds(world, "imbue"), [("imbue", "MR SORC", "vampire shield", "Basic Demon Presence", False)])
        self.assertEqual(acc.items["vampire shield"][0]["active"], "Basic Demon Presence")
        self.assertEqual(acc.state.phase, "hunting")
        self.assertEqual(acc.state.gold, 2_000_000 - 3_775 - 5_000)
        # na volta nada mais pendente: nao sai de novo
        world.calls.clear()
        clock.t += 500
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [])

    def test_powerful_buys_with_protection(self):
        market = {m: [{"seller": "x", "qty": 999, "price": 100}] for m in ("protective charm", "sabretooth", "vexclaw talon")}
        plan = {"stonecutter axe": [{"imbuement": "Strike", "tier": "Powerful", "renew": True}]}
        world, acc, engine, clock, logs = setup(items={"stonecutter axe": [dict(EMPTY)]}, market=market, plan=plan)
        engine.tick()
        self.assertEqual(sorted(c[2] for c in kinds(world, "buy")), ["protective charm", "sabretooth", "vexclaw talon"])
        self.assertEqual(kinds(world, "imbue")[0][4], True)

    def test_does_not_leave_without_gold(self):
        world, acc, engine, clock, logs = setup(gold=1_000)
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [])
        self.assertTrue(any("nao vou sair" in line for line in logs))

    def test_no_stock_blocks_and_does_not_keep_leaving(self):
        world, acc, engine, clock, logs = setup(market={"cultish robe": [{"seller": "a", "qty": 3, "price": 151}]})
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [("leave", "MR SORC")])
        self.assertEqual(kinds(world, "imbue"), [])
        self.assertTrue(any("sem estoque" in line for line in logs))
        self.assertEqual(acc.state.phase, "hunting")          # voltou pra caçada mesmo assim
        world.calls.clear()
        clock.t += 300
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [])           # bloqueado por 1h

    def test_failed_attempt_buys_again_and_retries(self):
        world, acc, engine, clock, logs = setup()
        acc.fail_next = 1
        engine.tick()
        self.assertEqual(len(kinds(world, "imbue")), 2)
        self.assertEqual(len(kinds(world, "buy")), 2)
        self.assertEqual(acc.items["vampire shield"][0]["active"], "Basic Demon Presence")

    def test_once_only_is_not_redone_when_it_ends(self):
        plan = {"vampire shield": [{"imbuement": "Demon Presence", "tier": "Basic", "renew": False}]}
        world, acc, engine, clock, logs = setup(plan=plan)
        engine.tick()
        self.assertEqual(len(kinds(world, "imbue")), 1)
        acc.items["vampire shield"][0].update(active=None, minutes=None)     # acabou
        world.calls.clear()
        clock.t += 500
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [])

    def test_in_the_city_for_selling_it_also_renews_what_is_ending(self):
        items = {"vampire shield": [{"active": "Basic Demon Presence", "minutes": 20}]}
        world, acc, engine, clock, logs = setup(items=items)
        acc.state.cap_pct = 95.0                                            # ciclo de venda
        engine.tick()
        self.assertEqual(kinds(world, "remove"), [("remove", "MR SORC", "vampire shield", "Demon Presence")])
        self.assertEqual(len(kinds(world, "imbue")), 1)
        self.assertEqual(acc.items["vampire shield"][0]["minutes"], 1200)

    def test_selling_cycle_with_nothing_due_does_not_open_the_shrine(self):
        items = {"vampire shield": [{"active": "Basic Demon Presence", "minutes": 900}]}
        world, acc, engine, clock, logs = setup(items=items)
        acc.state.cap_pct = 95.0
        engine.tick()
        self.assertEqual(kinds(world, "sell"), [("sell", "MR SORC")])
        self.assertEqual(kinds(world, "shrine"), [])
        self.assertEqual(kinds(world, "imbue"), [])

    def test_active_with_time_left_does_not_trigger(self):
        items = {"vampire shield": [{"active": "Basic Demon Presence", "minutes": 20}]}
        world, acc, engine, clock, logs = setup(items=items)
        engine.tick()
        self.assertEqual(kinds(world, "leave"), [])       # < 30 min so' renova se ja for a cidade


if __name__ == "__main__":
    unittest.main()
