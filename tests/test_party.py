"""Volta do server save e party montada pelo bot (mundo falso)."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from huntera_bot import config
from huntera_bot.account import parse_state
from huntera_bot.engine import Engine
from huntera_bot.memory import Memory
from test_engine import Clock, FakeAccount, World

NAMES = ("Aliado Um", "Aliado Dois", "Aliado Tres")


class PartyAccount(FakeAccount):
    def play(self, timeout=60):
        self.world.calls.append(("play", self.name))
        self.state.phase = "city"
        self.state.play_ready = False
        self.state.motd = True
        return True

    def close_motd(self):
        self.world.calls.append(("motd", self.name))
        self.state.motd = False

    def invite_to_party(self, names):
        self.world.calls.append(("invite", self.name, tuple(names)))
        for n in names:
            self.world.accounts[n.upper()].state.invite = ["ENTRAR", "RECUSAR"]
        return list(names)

    def answer_party_invite(self, leader, timeout=40):
        self.world.calls.append(("answer", self.name))
        self.state.invite = []
        if self.state.phase == "training":
            self.state.phase = "city"           # trocou de mundo: o treino cai
        party = self.world.__dict__.setdefault("party", [leader.title()])
        if self.name.title() not in party:
            party.append(self.name.title())
        for a in self.world.accounts.values():
            if a.name.title() in party:
                a.state.party_names = list(party)
                a.state.leader_name = leader.title()
        self.state.accept_all = True
        return True

    def share_costs(self):
        self.world.calls.append(("costs", self.name))
        self.world.accounts[self.name].state.costs_shared = True
        return True


def world_after_server_save(phase="city"):
    w = World()
    for n in NAMES:
        w.add(n)
        acc = w.accounts[n.upper()]
        party = PartyAccount(w, acc.state)
        party.state.phase = phase
        party.state.party_names = []
        party.state.leader_name = ""
        party.state.hunt_name = ""
        party.state.bestiary_total = None
        w.accounts[n.upper()] = party
    return w


def engine_for(world, memory=None, **party):
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["party"].update({"enabled": True, "leader": "aliado um", "members": ["aliado dois", "aliado tres"], **party})
    clock = Clock()
    logs = []
    engine = Engine(list(world.accounts.values()), cfg, log=logs.append, clock=clock, sleep=clock.sleep, memory=memory or Memory())
    return engine, clock, logs


def kinds(world, kind):
    return [c for c in world.calls if c[0] == kind]


class ParseTests(unittest.TestCase):
    def test_character_screen_during_server_save(self):
        st = parse_state({"select": True, "play_ready": False, "select_name": "Teusin Sorc",
                          "notice": "Server save. Tente de novo mais tarde."})
        self.assertEqual((st.phase, st.name, st.play_ready), ("select", "TEUSIN SORC", False))
        self.assertTrue(parse_state({"select": True, "play_ready": True}).play_ready)

    def test_party_flags(self):
        st = parse_state({"in_city": True, "motd": True, "invite": ["SEGUIR O LÍDER", "MANTER A ATUAL"],
                          "follow_switch": "Aceitar tudo do líder", "costs": "Cada um paga o seu"})
        self.assertEqual((st.motd, st.accept_all, st.costs_shared), (True, False, False))
        st = parse_state({"in_city": True, "follow_switch": "Parar de aceitar tudo", "costs": "Rateio ligado — nada gasto ainda"})
        self.assertEqual((st.accept_all, st.costs_shared), (True, True))
        self.assertIsNone(parse_state({"in_city": True}).accept_all)


class ServerSaveTests(unittest.TestCase):
    def test_waits_for_play_then_enters_and_closes_the_patch_notes(self):
        w = world_after_server_save(phase="select")
        engine, clock, logs = engine_for(w)
        engine.tick()
        self.assertEqual(kinds(w, "play"), [])                      # Jogar ainda desabilitado
        self.assertTrue(any("fora do jogo" in line for line in logs))
        for acc in w.accounts.values():
            acc.state.play_ready = True
        engine.tick()
        self.assertEqual(len(kinds(w, "play")), 3)
        self.assertEqual(len(kinds(w, "motd")), 3)

    def test_leader_invites_members_accept_and_costs_are_shared(self):
        w = world_after_server_save()
        engine, clock, logs = engine_for(w)
        engine.tick()
        self.assertEqual(kinds(w, "invite"), [("invite", "ALIADO UM", ("ALIADO DOIS", "ALIADO TRES"))])
        self.assertEqual(sorted(c[1] for c in kinds(w, "answer")), ["ALIADO DOIS", "ALIADO TRES"])
        self.assertEqual(kinds(w, "costs"), [("costs", "ALIADO UM")])
        self.assertEqual(kinds(w, "train"), [])                     # nao treina separado enquanto monta
        self.assertEqual(sorted(w.accounts["ALIADO UM"].state.party_names), ["Aliado Dois", "Aliado Tres", "Aliado Um"])

    def test_after_the_party_the_team_returns_to_the_last_hunt_even_after_restart(self):
        w = world_after_server_save()
        memory = Memory()
        memory.set_last_hunt(frozenset(a.name for a in w.accounts.values()), "Rat Cellars", None)
        engine, clock, logs = engine_for(w, memory=memory)
        engine.tick()                                               # monta a party
        engine.tick()                                               # comeca a contar o tempo parado
        clock.t += 200                                              # parado na cidade > idle_city_seconds
        engine.tick()
        starts = kinds(w, "start")
        self.assertTrue(starts)
        self.assertEqual(starts[0][2], "Rat Cellars")
        self.assertTrue(starts[0][4])                               # com o time

    def test_without_any_record_the_team_trains(self):
        w = world_after_server_save()
        engine, clock, logs = engine_for(w)
        engine.tick()
        engine.tick()
        clock.t += 200
        engine.tick()
        self.assertEqual(kinds(w, "start"), [])
        self.assertEqual(len(kinds(w, "train")), 3)

    def test_without_any_record_the_team_goes_to_the_default_hunt(self):
        w = world_after_server_save()
        engine, clock, logs = engine_for(w)
        engine.cfg["default_hunt"] = {"name": "Lower Roshamuul", "tier": "Agressivo"}
        engine.tick()
        engine.tick()
        clock.t += 200
        engine.tick()
        self.assertEqual(kinds(w, "train"), [])
        self.assertEqual(kinds(w, "start")[0][2:5], ("Lower Roshamuul", "Agressivo", True))

    def test_disabled_party_does_nothing(self):
        w = world_after_server_save()
        engine, clock, logs = engine_for(w, enabled=False)
        engine.tick()
        self.assertEqual(kinds(w, "invite"), [])

    def test_last_hunt_is_saved_while_hunting(self):
        w = world_after_server_save(phase="hunting")
        for acc in w.accounts.values():
            acc.state.hunt_name = "Spider Nest"
            acc.state.party_names = list(NAMES)
            acc.state.leader_name = "Aliado Um"
        memory = Memory()
        engine, clock, logs = engine_for(w, memory=memory)
        engine.tick()
        self.assertEqual(memory.get_last_hunt([a.name for a in w.accounts.values()])["hunt"], "Spider Nest")


class PullTests(unittest.TestCase):
    def _team(self):
        w = world_after_server_save(phase="hunting")
        for acc in w.accounts.values():
            acc.state.hunt_name = "Spider Nest"
            acc.state.party_names = list(NAMES)
            acc.state.leader_name = "Aliado Um"
        lider = w.accounts["ALIADO UM"].state
        lider.pull_hunt, lider.pull_tier = "Spider Nest", "Agressivo"
        return w

    def test_selling_cycle_returns_with_the_pull_the_leader_was_using(self):
        w = self._team()
        w.accounts["ALIADO DOIS"].state.cap_pct = 95.0
        engine, clock, logs = engine_for(w, enabled=False)
        engine.tick()
        self.assertEqual(kinds(w, "start")[0][2:4], ("Spider Nest", "Agressivo"))

    def test_pull_is_saved_with_the_last_hunt(self):
        w = self._team()
        memory = Memory()
        engine, clock, logs = engine_for(w, memory=memory, enabled=False)
        engine.tick()
        self.assertEqual(memory.get_last_hunt([a.name for a in w.accounts.values()]), {"hunt": "Spider Nest", "tier": "Agressivo"})

    def test_configured_pull_wins(self):
        w = self._team()
        w.accounts["ALIADO DOIS"].state.cap_pct = 95.0
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["hunt_tiers"]["Spider Nest"] = "Ousado"
        engine.tick()
        self.assertEqual(kinds(w, "start")[0][3], "Ousado")


class MarkedHuntTests(unittest.TestCase):
    def _team(self, hunt="Spider Nest", pull="Agressivo"):
        w = PullTests._team(PullTests())
        for acc in w.accounts.values():
            acc.state.hunt_name = hunt
        w.accounts["ALIADO UM"].state.pull_hunt = hunt
        w.accounts["ALIADO UM"].state.pull_tier = pull
        return w

    def test_hunting_elsewhere_switches_to_the_default_hunt(self):
        w = self._team()
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["default_hunt"] = {"name": "Lower Roshamuul", "tier": "Agressivo"}
        engine.tick()
        self.assertEqual(kinds(w, "start")[0][2:5], ("Lower Roshamuul", "Agressivo", True))

    def test_already_in_the_marked_hunt_and_pull_does_nothing(self):
        w = self._team(hunt="Lower Roshamuul")
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["default_hunt"] = {"name": "Lower Roshamuul", "tier": "Agressivo"}
        engine.tick()
        self.assertEqual(kinds(w, "leave"), [])

    def test_wrong_pull_is_fixed(self):
        w = self._team(hunt="Lower Roshamuul", pull="Cauteloso")
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["default_hunt"] = {"name": "Lower Roshamuul", "tier": "Agressivo"}
        engine.tick()
        self.assertEqual(kinds(w, "start")[0][2:4], ("Lower Roshamuul", "Agressivo"))

    def test_chain_wins_and_selling_returns_to_the_marked_hunt(self):
        w = self._team()
        w.accounts["ALIADO DOIS"].state.cap_pct = 95.0
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["default_hunt"] = {"name": "Lower Roshamuul", "tier": ""}
        engine.cfg["bestiary_chain"] = {"enabled": True, "hunts": [{"name": "Troll Hills", "tier": "Ousado"}, {"name": "Orc Camp"}]}
        engine.tick()
        self.assertEqual(kinds(w, "start")[0][2:4], ("Troll Hills", "Ousado"))

    def test_bot_started_with_the_team_idle_in_the_city_hunts_right_away(self):
        w = self._team()
        for acc in w.accounts.values():
            acc.state.phase = "city"
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["default_hunt"] = {"name": "Vampire Crypt", "tier": "Agressivo"}
        engine.tick()                                   # sem esperar os 90s
        self.assertEqual(kinds(w, "start")[0][2:5], ("Vampire Crypt", "Agressivo", True))

    def test_hunt_inside_the_chain_is_kept_until_the_bestiary_closes(self):
        w = self._team(hunt="Orc Camp")
        engine, clock, logs = engine_for(w, enabled=False)
        engine.cfg["bestiary_chain"] = {"enabled": True, "hunts": [{"name": "Troll Hills"}, {"name": "Orc Camp"}]}
        engine.tick()
        self.assertEqual(kinds(w, "leave"), [])


if __name__ == "__main__":
    unittest.main()
