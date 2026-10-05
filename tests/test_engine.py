import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from huntera_bot import config
from huntera_bot.account import State, parse_state
from huntera_bot.engine import Engine, build_groups


class World:
    """Mundo falso: as contas mudam de fase quando o bot age (como no jogo)."""

    def __init__(self):
        self.accounts = {}
        self.calls = []
        self.options_reads = []

    def add(self, name, leader="", party=(), cap=50.0, hunt="Rat Cellars", complete=False, dispatch=False,
            vocation="Elite Knight", stamina=400):
        st = State(name=name.upper(), vocation=vocation, phase="hunting", cap_pct=cap, hunt_name=hunt, party_names=list(party),
                   leader_name=leader, bestiary_done=1 if complete else 0, bestiary_total=1, dispatch_ready=dispatch,
                   stamina_min=stamina)
        acc = FakeAccount(self, st)
        self.accounts[st.name] = acc
        return acc


class FakeAccount:
    def __init__(self, world, state):
        self.world, self.state, self.name = world, state, state.name

    def read(self):
        return copy.copy(self.state)

    def leave_hunt(self, timeout=45):
        self.world.calls.append(("leave", self.name))
        team = [a for a in self.world.accounts.values() if self.state.leader_name.casefold() == self.name.casefold() and a.state.party_names and a.state.leader_name == self.state.leader_name]
        for acc in (team or [self]):
            acc.state.phase = "city"
        return True

    def sell_all(self, keep=(), mark_all=True):
        self.world.calls.append(("sell", self.name))
        self.state.cap_pct = 5.0
        return 3

    def dispatch_loot(self, keep=(), mark_all=True):
        self.world.calls.append(("dispatch", self.name))
        self.state.cap_pct = 20.0
        self.state.dispatch_ready = False

    def start_hunt(self, hunt, tier=None, team=False):
        self.world.calls.append(("start", self.name, hunt, tier, team))
        members = [a for a in self.world.accounts.values() if a.state.party_names] if team else [self]
        for acc in members:
            acc.state.phase = "hunting"
            acc.state.hunt_name = hunt
            acc.state.bestiary_done = 0

    def read_training_options(self):
        self.world.options_reads.append(self.name)
        return ["Club Fighting", "Sword Fighting", "Axe Fighting", "Distance Fighting", "Shielding", "Magic Level"]

    def start_training(self, skill):
        self.world.calls.append(("train", self.name, skill))
        self.state.phase = "training"

    def cancel_training(self, timeout=8):
        self.world.calls.append(("cancel", self.name))
        self.state.phase = "city"
        return True

    def close_windows(self):
        pass


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_engine(world, **cfg_over):
    cfg = config.load(os.devnull + ".none") if False else copy.deepcopy(config.DEFAULTS)
    cfg.update(cfg_over)
    clock = Clock()
    engine = Engine(list(world.accounts.values()), cfg, log=lambda m: None, clock=clock, sleep=clock.sleep)
    return engine, clock


TEAM = ("Aliado Um", "Aliado Dois")


def team_world(cap_leader=50.0, cap_follow=50.0):
    w = World()
    w.add("Aliado Um", leader="Aliado Um", party=TEAM, cap=cap_leader)
    w.add("Aliado Dois", leader="Aliado Um", party=TEAM, cap=cap_follow)
    return w


def vocation_world(stamina_ek=400, stamina_ed=400, cap=50.0):
    w = World()
    w.add("Aliado Um", leader="Aliado Um", party=TEAM, vocation="Elite Knight", stamina=stamina_ek, cap=cap)
    w.add("Aliado Dois", leader="Aliado Um", party=TEAM, vocation="Elder Druid", stamina=stamina_ed, cap=cap)
    return w


class ParseTests(unittest.TestCase):
    def test_stamina(self):
        self.assertEqual(parse_state({"stamina": "5:43h"}).stamina_min, 343)
        self.assertEqual(parse_state({"stamina": "0:15h"}).stamina_min, 15)
        self.assertIsNone(parse_state({}).stamina_min)

    def test_parse(self):
        st = parse_state({"name": "ALIADO DOIS", "vocation": "Elder Druid", "in_hunt": True, "in_city": False,
                          "cap_title": "Carregando 2306.10 de 3394.73 oz", "bestiary_head": "▾ Rat Cellars 0 / 1",
                          "dispatch": {"vis": True, "disabled": False, "cooling": True, "text": "PRONTO EM 59:58"},
                          "party": [{"name": "Aliado Um", "leader": True}, {"name": "Aliado Dois", "leader": False}]})
        self.assertEqual(st.phase, "hunting")
        self.assertAlmostEqual(st.cap_pct, 67.9, places=1)
        self.assertEqual((st.hunt_name, st.bestiary_done, st.bestiary_total), ("Rat Cellars", 0, 1))
        self.assertFalse(st.dispatch_ready)          # 'cooling' = em intervalo, mesmo com disabled=false
        self.assertEqual(st.leader_name, "Aliado Um")

    def test_training_phase(self):
        st = parse_state({"in_city": True, "training": True, "training_skill": "Magic Level"})
        self.assertEqual((st.phase, st.training_skill), ("training", "Magic Level"))
        self.assertEqual(parse_state({"in_hunt": True, "training": True}).phase, "hunting")

    def test_phases(self):
        self.assertEqual(parse_state({"loading": True, "in_hunt": True}).phase, "loading")
        self.assertEqual(parse_state({"leaving": True, "in_hunt": True}).phase, "leaving")
        self.assertEqual(parse_state({"in_city": True}).phase, "city")
        self.assertEqual(parse_state({}).phase, "unknown")


class GroupTests(unittest.TestCase):
    def test_team_is_case_insensitive_and_mutual(self):
        w = team_world()
        states = {n: a.read() for n, a in w.accounts.items()}
        groups = build_groups(list(w.accounts.values()), states)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0].is_team)
        self.assertEqual(groups[0].leader.name, "ALIADO UM")

    def test_not_mutual_is_solo(self):
        w = World()
        w.add("Aliado Um", leader="Aliado Um", party=("Aliado Um", "Druid Master"))
        w.add("Aliado Dois", leader="Aliado Um", party=TEAM)
        states = {n: a.read() for n, a in w.accounts.items()}
        self.assertEqual(len(build_groups(list(w.accounts.values()), states)), 2)


class EngineTests(unittest.TestCase):
    def test_team_capacity_cycle(self):
        w = team_world(cap_follow=91.0)             # so' a seguidora encheu
        engine, _ = make_engine(w)
        engine.tick()
        kinds = [c[0] for c in w.calls]
        self.assertEqual(kinds, ["leave", "sell", "sell", "start"])
        self.assertEqual(w.calls[0], ("leave", "ALIADO UM"))          # a LIDER sai
        self.assertEqual(w.calls[-1], ("start", "ALIADO UM", "Rat Cellars", None, True))   # a lider inicia COM O TIME
        self.assertTrue(all(a.state.phase == "hunting" for a in w.accounts.values()))

    def test_below_threshold_does_nothing(self):
        w = team_world(cap_leader=89.0, cap_follow=89.9)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_waits_while_someone_is_not_hunting(self):
        w = team_world(cap_follow=95.0)
        w.accounts["ALIADO DOIS"].state.phase = "loading"
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_solo_cycle_uses_solo_start(self):
        w = World()
        w.add("Solo One", cap=92.0)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [("leave", "SOLO ONE"), ("sell", "SOLO ONE"), ("start", "SOLO ONE", "Rat Cellars", None, False)])

    def test_cooldown_prevents_repeat(self):
        w = team_world(cap_follow=95.0)
        engine, clock = make_engine(w)
        engine.tick()
        n = len(w.calls)
        w.accounts["ALIADO DOIS"].state.cap_pct = 96.0
        engine.tick()                               # ainda no cooldown
        self.assertEqual(len(w.calls), n)
        clock.t += engine.cfg["cooldown_ok_seconds"] + 1
        engine.tick()
        self.assertGreater(len(w.calls), n)

    def test_failure_uses_long_cooldown(self):
        w = team_world(cap_follow=95.0)
        engine, clock = make_engine(w)
        w.accounts["ALIADO UM"].start_hunt = lambda *a, **k: None      # o time nao volta
        engine.cfg["timeouts"]["start"] = 3
        engine.tick()
        self.assertGreaterEqual(engine.cooldown[next(iter(engine.cooldown))] - clock.t, engine.cfg["cooldown_fail_seconds"] - 5)

    def test_bestiary_chain_goes_to_next_hunt(self):
        w = team_world()
        for a in w.accounts.values():
            a.state.bestiary_done = 1
        engine, _ = make_engine(w, bestiary_chain={"enabled": True, "hunts": [{"name": "Rat Cellars"}, {"name": "Spider Nest", "tier": "Ousado"}]})
        engine.tick()
        self.assertEqual(w.calls[-1], ("start", "ALIADO UM", "Spider Nest", "Ousado", True))

    def test_bestiary_needs_all_members(self):
        w = team_world()
        w.accounts["ALIADO UM"].state.bestiary_done = 1       # so' uma completou
        engine, _ = make_engine(w, bestiary_chain={"enabled": True, "hunts": [{"name": "Rat Cellars"}, {"name": "Spider Nest"}]})
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_bestiary_chain_end_does_nothing(self):
        w = team_world()
        for a in w.accounts.values():
            a.state.bestiary_done = 1
        engine, _ = make_engine(w, bestiary_chain={"enabled": True, "hunts": [{"name": "Rat Cellars"}]})
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_dispatch_only_when_ready_and_above_min(self):
        w = World()
        w.add("A", cap=45.0, dispatch=True)
        w.add("B", cap=30.0, dispatch=True)      # abaixo do minimo
        w.add("C", cap=60.0, dispatch=False)     # em intervalo
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [("dispatch", "A")])
        engine.tick()                             # nao repete logo em seguida
        self.assertEqual(w.calls, [("dispatch", "A")])

    def test_hunt_tier_from_config(self):
        w = team_world(cap_follow=95.0)
        engine, _ = make_engine(w, hunt_tiers={"Rat Cellars": "Ousado"})
        engine.tick()
        self.assertEqual(w.calls[-1], ("start", "ALIADO UM", "Rat Cellars", "Ousado", True))


class TrainingTests(unittest.TestCase):
    def test_low_stamina_sends_everyone_to_training_by_vocation(self):
        w = vocation_world(stamina_ek=400, stamina_ed=15)          # so' a ED chegou em 0:15h
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls[0], ("leave", "ALIADO UM"))        # a lider leva todos
        trains = [c for c in w.calls if c[0] == "train"]
        self.assertEqual(sorted(trains), [("train", "ALIADO DOIS", "Magic Level"), ("train", "ALIADO UM", "Axe Fighting")])
        self.assertNotIn("sell", [c[0] for c in w.calls])
        self.assertNotIn("start", [c[0] for c in w.calls])             # nao volta pra caçar

    def test_just_above_threshold_keeps_hunting(self):
        w = vocation_world(stamina_ek=16, stamina_ed=400)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_stamina_has_priority_over_capacity(self):
        w = vocation_world(stamina_ek=10, cap=95.0)
        engine, _ = make_engine(w)
        engine.tick()
        kinds = [c[0] for c in w.calls]
        self.assertIn("train", kinds)
        self.assertNotIn("sell", kinds)

    def test_training_can_be_disabled(self):
        w = vocation_world(stamina_ek=5)
        engine, _ = make_engine(w, training={**config.DEFAULTS["training"], "enabled": False})
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_skill_per_vocation(self):
        engine, _ = make_engine(World())
        self.assertEqual(engine.training_skill("Elite Knight"), "Axe Fighting")
        self.assertEqual(engine.training_skill("Royal Paladin"), "Distance Fighting")
        self.assertEqual(engine.training_skill("Elder Druid"), "Magic Level")
        self.assertEqual(engine.training_skill("Master Sorcerer"), "Magic Level")
        self.assertIsNone(engine.training_skill("Monk"))

    def test_solo_account_trains_alone(self):
        w = World()
        w.add("Solo Rp", vocation="Royal Paladin", stamina=12)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(w.calls, [("leave", "SOLO RP"), ("train", "SOLO RP", "Distance Fighting")])


class FreeTrainingTests(unittest.TestCase):
    def test_knight_can_train_anything_the_game_offers(self):
        w = vocation_world(stamina_ek=10)
        engine, _ = make_engine(w, training={**config.DEFAULTS["training"], "by_name": {"aliado um": "Magic Level", "aliado dois": "Shielding"}})
        engine.tick()
        trains = sorted(c for c in w.calls if c[0] == "train")
        self.assertEqual(trains, [("train", "ALIADO DOIS", "Shielding"), ("train", "ALIADO UM", "Magic Level")])

    def test_without_choice_uses_vocation_default(self):
        w = vocation_world(stamina_ek=10)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(sorted(c for c in w.calls if c[0] == "train"), [("train", "ALIADO DOIS", "Magic Level"), ("train", "ALIADO UM", "Axe Fighting")])

    def test_choice_not_offered_by_the_game_falls_back(self):
        w = vocation_world(stamina_ek=10)
        engine, _ = make_engine(w, training={**config.DEFAULTS["training"], "by_name": {"aliado um": "Fishing"}})
        engine.tick()                                      # 1o tick le as opcoes (Fishing nao existe) e ja manda treinar
        self.assertIn(("train", "ALIADO UM", "Axe Fighting"), w.calls)

    def test_options_are_read_once_and_remembered(self):
        w = vocation_world()
        engine, clock = make_engine(w)
        engine.tick()
        engine.tick()
        self.assertEqual(sorted(w.options_reads), ["ALIADO DOIS", "ALIADO UM"])        # 1 leitura por conta
        self.assertEqual(len(engine.memory.get_options("Aliado Um")["skills"]), 6)

    def test_failed_options_read_retries_later(self):
        w = vocation_world()
        engine, clock = make_engine(w)
        w.accounts["ALIADO DOIS"].read_training_options = lambda: None
        engine.tick()
        self.assertIsNone(engine.memory.get_options("Aliado Dois"))
        clock.t += 601
        w.accounts["ALIADO DOIS"].read_training_options = lambda: ["Magic Level"]
        engine.tick()
        self.assertEqual(engine.memory.get_options("Aliado Dois")["skills"], ["Magic Level"])


class ResumeTests(unittest.TestCase):
    def training_world(self, ek=650, ed=700):
        w = vocation_world(stamina_ek=ek, stamina_ed=ed)
        for a in w.accounts.values():
            a.state.phase = "training"
        return w

    def engine_with_memory(self, w, saved=True):
        from huntera_bot.memory import Memory
        mem = Memory()
        if saved:
            mem.set(("Aliado Um", "Aliado Dois"), {"hunt": "Vampire Crypt", "tier": "Ousado"})
        engine, clock = make_engine(w)
        engine.memory = mem
        return engine, clock

    def test_all_above_10h_cancels_training_and_returns_to_saved_hunt(self):
        w = self.training_world()
        engine, _ = self.engine_with_memory(w)
        engine.tick()
        kinds = [c[0] for c in w.calls]
        self.assertEqual(kinds[:2].count("cancel"), 2)
        self.assertEqual(w.calls[-1], ("start", "ALIADO UM", "Vampire Crypt", "Ousado", True))
        self.assertIsNone(engine.memory.get(("Aliado Um", "Aliado Dois")))      # usou e limpou

    def test_waits_if_any_account_is_below_10h(self):
        w = self.training_world(ek=599, ed=700)
        engine, _ = self.engine_with_memory(w)
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_no_memory_means_no_return(self):
        w = self.training_world()
        engine, _ = self.engine_with_memory(w, saved=False)
        engine.tick()
        self.assertEqual(w.calls, [])

    def test_training_remembers_the_hunt(self):
        w = vocation_world(stamina_ek=10)
        engine, _ = make_engine(w)
        engine.tick()
        self.assertEqual(engine.memory.get(("Aliado Um", "Aliado Dois")), {"hunt": "Rat Cellars", "tier": None})

    def test_training_phase_is_not_treated_as_hunting(self):
        w = self.training_world(ek=100, ed=100)           # treinando com pouca stamina: nao dispara nada
        engine, _ = self.engine_with_memory(w)
        engine.tick()
        self.assertEqual(w.calls, [])


if __name__ == "__main__":
    unittest.main()
