"""Motor do bot: agrupa as contas em times (party) ou solo, decide e executa.

Regras (do mapeamento ao vivo):
- Time = contas gerenciadas que estao na MESMA party (uma lista a outra). A LIDER sai
  e leva todo mundo junto (5s); cada conta vende; a lider reinicia 'com o time'
  (todos precisam estar na cidade). Conta sem party faz tudo sozinha.
- Gatilho de capacidade: QUALQUER conta do time chegar em capacity_pct.
- Despacho (1x/hora) e' por conta e nao sai da hunt.
- Bestiary em cadeia: contador da hunt N/N em TODAS as contas -> proxima hunt da lista.
- Treino: com TODAS as contas do time treinando e stamina >= training.resume_stamina_minutes (10h) o time
  cancela o treino e volta pra hunt em que estava (lembrada em memory.json).
- Stamina: QUALQUER conta do time com <= training.stamina_minutes -> todo o time vai pra cidade e
  cada conta inicia o treino da habilidade da sua vocacao (EK axe, RP distance, ED/MS magic level).
- Nunca fica parado na cidade: conta na cidade (sem treino) por mais de idle_city_seconds -> se o time
  estava em treino (ou a stamina esta baixa) reinicia o treino; senao volta pra hunt conhecida.
- Nunca age enquanto alguem esta carregando/saindo; depois de um ciclo espera (cooldown).
"""
import time
from dataclasses import dataclass, field

from . import config
from .imbuer import Imbuer
from .memory import Memory


@dataclass
class Group:
    members: list                       # [Account]
    states: dict = field(default_factory=dict)   # nome -> State
    leader: object = None               # Account da lider (so' em time)

    @property
    def key(self):
        return frozenset(a.name for a in self.members)

    @property
    def is_team(self):
        return len(self.members) > 1

    @property
    def label(self):
        return " + ".join(sorted(self.key))


def build_groups(accounts, states):
    """accounts: lista de Account; states: {nome: State}. Time = ligacao MUTUA na party.
    Nomes comparados sem diferenciar maiusculas (o cabecalho do jogo vem em CAIXA ALTA,
    a party em 'Nome Normal')."""
    fold = str.casefold
    by_name = {a.name: a for a in accounts}
    parties = {n: {fold(x) for x in states[n].party_names} for n in by_name if n in states}
    parent = {n: n for n in by_name}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    names = list(by_name)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a in parties and b in parties and fold(b) in parties[a] and fold(a) in parties[b]:
                parent[find(a)] = find(b)

    comps = {}
    for n in names:
        comps.setdefault(find(n), []).append(n)
    groups = []
    for members in comps.values():
        group = Group(members=[by_name[n] for n in sorted(members)], states={n: states[n] for n in members if n in states})
        if group.is_team:
            leaders = {fold(s.leader_name) for s in group.states.values() if s.leader_name}
            for n in members:
                if fold(n) in leaders:
                    group.leader = by_name[n]
        groups.append(group)
    return groups


def group_bestiary(group):
    """Contador 'N/M' de quem do time mostra o rastreador (o menor, pra nao adiantar) ou ''."""
    tracked = [s for s in group.states.values() if s.bestiary_total]
    if not tracked:
        return ""
    s = min(tracked, key=lambda x: (x.bestiary_done or 0) / x.bestiary_total)
    return f"{s.bestiary_done}/{s.bestiary_total}"


class Engine:
    def __init__(self, accounts, cfg, log=print, clock=time.monotonic, sleep=time.sleep, refresh=None, memory=None):
        self.accounts = accounts
        self.memory = memory or Memory()
        self.refresh = refresh           # funcao opcional que reencontra as paginas (conta nova/fechada)
        self.last_refresh = 0.0
        self.cfg = cfg
        self.log = log
        self.clock = clock
        self.sleep = sleep
        self.cooldown = {}              # chave do grupo -> ate quando
        self.dispatch_cd = {}           # nome -> ate quando
        self.warned = {}                # (chave) -> ultimo aviso
        self.options_retry = {}         # nome -> quando tentar ler as opcoes de treino de novo
        self.last_status = 0.0
        self.last_phase = {}            # nome -> fase lida no tick anterior
        self.idle_since = {}            # chave do grupo -> desde quando alguem esta parado na cidade
        self.last_hunt = {}             # chave do grupo -> (hunt, tier) da ultima vez que estava caçando
        self.snapshot = {"states": {}, "groups": {}}   # lido pela interface (so' leitura)
        self.imbuer = Imbuer(cfg, self.memory, log, clock)

    # ---------------------------------------------------------------- leitura
    def read_all(self):
        states = {}
        for acc in self.accounts:
            try:
                st = acc.read()
                acc.name = st.name or acc.name
                states[acc.name] = st
            except Exception as error:   # pagina fechada/recarregando: tenta no proximo ciclo
                self.log(f"leitura falhou ({acc.name or '?'}): {error}")
        return states

    def _warn(self, key, message, every=600):
        now = self.clock()
        if now - self.warned.get(key, -1e9) >= every:
            self.warned[key] = now
            self.log(message)

    def _status(self, states):
        now = self.clock()
        if now - self.last_status < 60:
            return
        self.last_status = now
        parts = []
        for st in states.values():
            cap = "?" if st.cap_pct is None else f"{st.cap_pct:.0f}%"
            best = f" best {st.bestiary_done}/{st.bestiary_total}" if st.bestiary_total else ""
            stam = "" if st.stamina_min is None else f" st {st.stamina_min // 60}:{st.stamina_min % 60:02d}h"
            parts.append(f"{st.name}: {st.phase} cap {cap}{stam}{best}")
        self.log("status | " + " | ".join(parts))

    def group_hunt(self, group):
        """Hunt do time: a que alguma conta mostra no rastreador, senao a lembrada (treino/ultima caçada)."""
        current = next((s.hunt_name for s in group.states.values() if s.hunt_name), "")
        if current:
            return current
        saved = self.memory.get(group.key)
        if saved:
            return saved["hunt"]
        last = self.last_hunt.get(group.key)
        return last[0] if last else ""

    def _watch_phases(self, states):
        """Avisa quando uma conta sai do treino sem o bot mandar (com os avisos do jogo na tela)."""
        for name, st in states.items():
            before = self.last_phase.get(name)
            if before == "training" and st.phase != "training":
                toasts = " / ".join(st.toasts) if st.toasts else "nenhum aviso na tela"
                stam = "?" if st.stamina_min is None else f"{st.stamina_min // 60}:{st.stamina_min % 60:02d}h"
                self.log(f"[{name}] saiu do treino ({st.phase}, stamina {stam}) - avisos: {toasts}")
            self.last_phase[name] = st.phase

    # ----------------------------------------------------------------- decisao
    def _capacity_trigger(self, group):
        limit = self.cfg["capacity_pct"]
        full = [f"{n} {s.cap_pct:.0f}%" for n, s in group.states.items() if s.cap_pct is not None and s.cap_pct >= limit]
        return full

    def training_skill_for(self, name, vocation):
        """Habilidade de treino de UM personagem: a escolha dele (se o jogo a oferece) ou o padrao da vocacao."""
        chosen = (self.cfg["training"].get("by_name") or {}).get((name or "").casefold())
        if chosen:
            opts = self.memory.get_options(name)
            if opts is None or chosen in opts["skills"]:
                return chosen
            self._warn(("badskill", name), f"[{name}] o jogo nao oferece '{chosen}' a esta conta - usando o padrao da vocacao")
        return self.training_skill(vocation)

    def _ensure_options(self, acc, st):
        """Le UMA vez (e guarda em memory.json) as habilidades de treino que o jogo oferece a cada conta."""
        reader = getattr(acc, "read_training_options", None)
        if reader is None or st.phase not in ("hunting", "city", "training"):
            return
        if self.memory.get_options(st.name) is not None:
            return
        if self.clock() < self.options_retry.get(st.name, 0):
            return
        skills = reader()
        if skills:
            self.memory.set_options(st.name, st.vocation, skills)
            self.log(f"[{st.name}] treinos disponiveis: {', '.join(skills)}")
        else:
            self.options_retry[st.name] = self.clock() + 600

    def training_skill(self, vocation):
        """Habilidade de treino da vocacao ('Elite Knight' -> knight -> Axe Fighting)."""
        return config.default_skill(self.cfg["training"], vocation)

    def _stamina_trigger(self, group):
        tr = self.cfg["training"]
        if not tr.get("enabled"):
            return []
        return [f"{n} {s.stamina_min // 60}:{s.stamina_min % 60:02d}h" for n, s in group.states.items()
                if s.stamina_min is not None and s.stamina_min <= tr["stamina_minutes"]]

    def _chain_next(self, current):
        chain = self.cfg["bestiary_chain"]
        if not chain.get("enabled"):
            return None
        hunts = chain.get("hunts") or []
        names = [h["name"] for h in hunts]
        if current not in names:
            return None
        idx = names.index(current)
        return hunts[idx + 1] if idx + 1 < len(hunts) else None

    def decide(self, group):
        """Retorna (tipo, motivo, hunt_alvo, tier_alvo) ou None. tipo: 'training' | 'cycle'."""
        states = list(group.states.values())
        if not states or any(s.phase != "hunting" for s in states):
            return None
        current = next((s.hunt_name for s in states if s.hunt_name), "")
        low = self._stamina_trigger(group)
        if low:                      # stamina vem antes de tudo: sem ela nao ha mais hunt
            return ("training", "stamina baixa: " + ", ".join(low), current, None)
        imbue = self.imbuer.exit_reason(group)
        if imbue:                    # imbuement planejado faltando (primeira vez ou acabou com 'Renovar')
            return ("cycle", imbue, current, self.cfg["hunt_tiers"].get(current))
        full = self._capacity_trigger(group)
        if full:
            return ("cycle", "capacidade: " + ", ".join(full), current, self.cfg["hunt_tiers"].get(current))
        tracked = [s for s in states if s.bestiary_total]   # quem nao mostra o rastreador nao conta
        if tracked and all(s.bestiary_complete for s in tracked):
            nxt = self._chain_next(current)
            if nxt:
                tier = nxt.get("tier") or self.cfg["hunt_tiers"].get(nxt["name"])
                return ("cycle", f"bestiary de '{current}' completo", nxt["name"], tier)
            self._warn(("chain-end", current), f"bestiary de '{current}' completo, mas nao ha proxima hunt configurada")
        return None

    # --------------------------------------------------------------------- acao
    def _wait_all(self, group, phase, seconds):
        end = self.clock() + seconds
        while self.clock() < end:
            states = [m.read() for m in group.members]
            if all(s.phase == phase for s in states):
                return True
            self.sleep(1.0)
        return False

    def _to_city(self, group):
        """Faz o time/conta sair da caçada (a lider leva todos). True se todos ficaram na cidade."""
        tmo = self.cfg["timeouts"]
        starter = group.leader if group.is_team else group.members[0]
        starter.leave_hunt(tmo["leave"])
        if not self._wait_all(group, "city", tmo["leave"]):
            for m in group.members:
                if m.read().phase == "hunting":
                    m.leave_hunt(tmo["leave"])
            if not self._wait_all(group, "city", 15):
                return False
        return True

    def decide_resume(self, group):
        """Todas as contas treinando e com stamina suficiente -> (hunt, tier) memorizados, senao None."""
        states = list(group.states.values())
        if not states or any(s.phase not in ("training", "city") for s in states):
            return None
        need = self.cfg["training"]["resume_stamina_minutes"]
        if any(s.stamina_min is None or s.stamina_min < need for s in states):
            return None
        saved = self.memory.get(group.key)
        if saved:
            return saved["hunt"], saved.get("tier")
        hunt = self.group_hunt(group)      # sem memoria (time mudou/bot reaberto): a hunt que as contas mostram
        if hunt:
            self.log(f"[{group.label}] sem hunt na memoria - usando a que aparece no jogo: '{hunt}'")
            return hunt, self.cfg["hunt_tiers"].get(hunt)
        self._warn(("noresume", group.key), f"[{group.label}] stamina ok, mas nao sei em qual hunt voltar (sem memoria)")
        return None

    def run_resume(self, group, hunt, tier):
        """Cancela o treino de todos e inicia a hunt de novo (time: a lider)."""
        tmo = self.cfg["timeouts"]
        self.log(f"[{group.label}] STAMINA OK: cancelar o treino e voltar pra '{hunt}'" + (f" ({tier})" if tier else ""))
        for m in group.members:
            if not m.cancel_training():
                self.log(f"[{m.name}] nao consegui cancelar o treino")
                return False
        if not self._wait_all(group, "city", 10):
            return False
        self._imbue(group)
        starter = group.leader if group.is_team else group.members[0]
        if group.is_team and starter is None:
            self._warn(("noleader", group.key), f"[{group.label}] time sem lider gerenciada")
            return False
        for attempt in (1, 2):
            starter.start_hunt(hunt, tier, team=group.is_team)
            if self._wait_all(group, "hunting", tmo["start"]):
                self.memory.clear(group.key)
                self.log(f"[{group.label}] de volta em '{hunt}'")
                return True
            if not self._wait_all(group, "city", 5):
                break
        return False

    def run_training(self, group, reason, hunt=None, tier=None):
        """Todos pra cidade e cada conta inicia o treino da sua vocacao."""
        self.log(f"[{group.label}] TREINO ({reason}): sair da caçada e iniciar o treino de cada conta")
        if group.is_team and group.leader is None:
            self._warn(("noleader", group.key), f"[{group.label}] time sem lider gerenciada - nao vou sair sozinho")
            return False
        if not self._to_city(group):
            self.log(f"[{group.label}] nem todos chegaram na cidade - abortando")
            return False
        if hunt:      # lembra onde voltar quando a stamina recuperar
            self.memory.set(group.key, {"hunt": hunt, "tier": tier})
        self._imbue(group)
        return self._start_trainings(group, group.members)

    def _imbue(self, group):
        """Ja na cidade: cada conta compra e imbui o que estiver pendente (inclui renovar o que esta acabando)."""
        for m in group.members:
            try:
                self.imbuer.work(m)
            except Exception as error:
                self.log(f"[{m.name}] ERRO nos imbuements: {error}")

    def _start_trainings(self, group, members):
        ok = True
        for m in members:
            skill = self.training_skill_for(m.name, group.states[m.name].vocation if m.name in group.states else m.read().vocation)
            if not skill:
                self.log(f"[{m.name}] vocacao sem habilidade de treino configurada")
                ok = False
                continue
            try:
                m.start_training(skill)
            except Exception as error:
                self.log(f"[{m.name}] ERRO ao iniciar o treino: {error}")
                ok = False
        return ok

    def decide_idle(self, group):
        """Alguem parado na cidade (sem treino) ha idle_city_seconds e ninguem caçando/saindo/carregando.
        Retorna ('train', [contas]) | ('hunt', hunt, tier) | None."""
        states = group.states
        idle = [m for m in group.members if m.name in states and states[m.name].phase == "city"]
        if not states or not idle or any(s.phase not in ("city", "training") for s in states.values()):
            self.idle_since.pop(group.key, None)
            return None
        since = self.idle_since.setdefault(group.key, self.clock())
        if self.clock() - since < self.cfg["idle_city_seconds"]:
            return None
        tr = self.cfg["training"]
        saved = self.memory.get(group.key)
        known = (saved["hunt"], saved.get("tier")) if saved else self.last_hunt.get(group.key)
        if not known:
            current = next((s.hunt_name for s in states.values() if s.hunt_name), "")
            known = (current, self.cfg["hunt_tiers"].get(current)) if current else None
        stam = [s.stamina_min for s in states.values()]
        low = tr.get("enabled") and any(v is not None and v <= tr["stamina_minutes"] for v in stam)
        if tr.get("enabled") and (saved or low or not known):
            if not saved and known:
                self.memory.set(group.key, {"hunt": known[0], "tier": known[1]})
            return ("train", idle)
        if known:
            return ("hunt",) + tuple(known)
        return None

    def run_idle(self, group, decision):
        if decision[0] == "train":
            names = ", ".join(m.name for m in decision[1])
            self.log(f"[{group.label}] PARADO NA CIDADE ({names}): reiniciando o treino online")
            return self._start_trainings(group, decision[1])
        _, hunt, tier = decision
        self.log(f"[{group.label}] PARADO NA CIDADE: voltando pra '{hunt}'")
        return self.run_resume(group, hunt, tier)

    def run_cycle(self, group, reason, hunt, tier):
        """sair -> vender (todos) -> voltar. Retorna True se terminou todo mundo em hunt."""
        tmo = self.cfg["timeouts"]
        sell = self.cfg["sell"]
        self.log(f"[{group.label}] CICLO ({reason}): sair, vender e voltar pra '{hunt}'" + (f" ({tier})" if tier else ""))
        if group.is_team and group.leader is None:
            self._warn(("noleader", group.key), f"[{group.label}] time sem lider gerenciada - nao vou sair sozinho")
            return False

        # 1) sair (a lider leva todos; os que sobrarem saem sozinhos)
        starter = group.leader if group.is_team else group.members[0]
        starter.leave_hunt(tmo["leave"])
        if not self._wait_all(group, "city", tmo["leave"]):
            for m in group.members:
                if m.read().phase == "hunting":
                    m.leave_hunt(tmo["leave"])
            if not self._wait_all(group, "city", 15):
                self.log(f"[{group.label}] nem todos chegaram na cidade - abortando o ciclo")
                return False
        # 2) vender e imbuir
        for m in group.members:
            m.sell_all(sell["keep"], sell["mark_all"])
        self._imbue(group)
        # 3) voltar (time: so' a lider, os outros aceitam sozinhos; solo: ela mesma)
        for attempt in (1, 2):
            starter.start_hunt(hunt, tier, team=group.is_team)
            if self._wait_all(group, "hunting", tmo["start"]):
                self.log(f"[{group.label}] de volta em '{hunt}'")
                return True
            self.log(f"[{group.label}] inicio nao confirmou (tentativa {attempt})")
            if not self._wait_all(group, "city", 5):
                break
        return False

    def _handle_group(self, group):
        now = self.clock()
        if now < self.cooldown.get(group.key, 0):
            return
        if all(s.phase == "hunting" for s in group.states.values()):
            current = next((s.hunt_name for s in group.states.values() if s.hunt_name), "")
            if current:
                self.last_hunt[group.key] = (current, self.cfg["hunt_tiers"].get(current))
        resume = self.decide_resume(group)
        if resume:
            try:
                ok = self.run_resume(group, *resume)
            except Exception as error:
                self.log(f"[{group.label}] ERRO ao voltar do treino: {error}")
                ok = False
            self.cooldown[group.key] = self.clock() + (self.cfg["cooldown_ok_seconds"] if ok else self.cfg["cooldown_fail_seconds"])
            return
        idle = self.decide_idle(group)
        if idle:
            self.idle_since.pop(group.key, None)
            try:
                ok = self.run_idle(group, idle)
            except Exception as error:
                self.log(f"[{group.label}] ERRO ao tirar da cidade: {error}")
                ok = False
            self.cooldown[group.key] = self.clock() + (self.cfg["cooldown_ok_seconds"] if ok else self.cfg["cooldown_fail_seconds"])
            return
        decision = self.decide(group)
        if decision is None:
            return
        kind, reason, hunt, tier = decision
        if kind == "training":
            try:
                ok = self.run_training(group, reason, hunt, self.cfg["hunt_tiers"].get(hunt))
            except Exception as error:
                self.log(f"[{group.label}] ERRO no treino: {error}")
                ok = False
            self.cooldown[group.key] = self.clock() + (self.cfg["cooldown_ok_seconds"] if ok else self.cfg["cooldown_fail_seconds"])
            return
        if not hunt:
            self._warn(("nohunt", group.key), f"[{group.label}] {reason}, mas nao sei qual hunt retomar (rastreador vazio)")
            return
        try:
            ok = self.run_cycle(group, reason, hunt, tier)
        except Exception as error:
            self.log(f"[{group.label}] ERRO no ciclo: {error}")
            for m in group.members:
                try:
                    m.close_windows()
                except Exception:
                    pass
            ok = False
        wait = self.cfg["cooldown_ok_seconds"] if ok else self.cfg["cooldown_fail_seconds"]
        self.cooldown[group.key] = self.clock() + wait

    def _handle_dispatch(self, acc, st):
        d = self.cfg["dispatch"]
        if not d.get("enabled") or st.phase != "hunting" or not st.dispatch_ready:
            return
        if st.cap_pct is None or st.cap_pct < d["min_cap_pct"]:
            return
        if self.clock() < self.dispatch_cd.get(st.name, 0):
            return
        self.dispatch_cd[st.name] = self.clock() + 300
        try:
            acc.dispatch_loot(self.cfg["sell"]["keep"], self.cfg["sell"]["mark_all"])
        except Exception as error:
            self.log(f"[{st.name}] ERRO no despacho: {error}")

    # -------------------------------------------------------------------- laco
    def tick(self):
        if self.refresh and self.clock() - self.last_refresh >= 30:
            self.last_refresh = self.clock()
            self.accounts = self.refresh()
        states = self.read_all()
        groups = build_groups([a for a in self.accounts if a.name in states], states)
        self.snapshot = {
            "states": states,
            "groups": {m.name: (g.label, g.is_team, g.leader.name if g.leader else "") for g in groups for m in g.members},
            "hunts": {m.name: self.group_hunt(g) for g in groups for m in g.members},
            "bestiary": {m.name: group_bestiary(g) for g in groups for m in g.members},
        }
        self._status(states)
        self._watch_phases(states)
        for acc in self.accounts:
            st = states.get(acc.name)
            if st:
                try:
                    self._ensure_options(acc, st)
                except Exception as error:
                    self.log(f"[{st.name}] nao consegui ler as opcoes de treino: {error}")
                self._handle_dispatch(acc, st)
                try:
                    self.imbuer.observe(acc, st)
                except Exception as error:
                    self.log(f"[{st.name}] nao consegui ler os imbuements: {error}")
        if self.imbuer.requested:
            self.imbuer.refresh_all(self.accounts, states)
        for group in groups:
            self._handle_group(group)

    def run(self, stop_event):
        self.log(f"bot iniciado - {len(self.accounts)} conta(s)")
        while not stop_event.is_set():
            try:
                self.tick()
            except Exception as error:
                self.log(f"erro no laco: {error}")
            stop_event.wait(self.cfg["poll_seconds"])
        self.log("bot parado")
