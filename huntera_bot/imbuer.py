"""Imbuements no motor: le o equipamento das contas, decide quando o time precisa ir a' cidade
(imbuement planejado faltando) e, na cidade, compra os materiais no leilao e imbui.

- Leitura do equipamento: tooltip dos itens (funciona em caçada) no inicio, quando as bolinhas de imbuement
  mudam e a cada 15 min; o santuario (so' na cidade) da' o tempo exato e o que cada item aceita.
- Saida da caçada: um imbuement planejado nao esta no item (primeira vez ou acabou com 'Renovar') e o
  gold da conta cobre a estimativa. Ja na cidade (venda/treino) renova tambem o que tiver < renew_before_minutes.
- Falhou (sem estoque, sem gold, erro): bloqueia aquele imbuement por um tempo pra nao ficar saindo a toa."""
from . import imbuing

EQUIP_EVERY = 900          # s entre leituras de tooltip sem mudanca nas bolinhas
SCAN_EVERY = 600           # s entre leituras do santuario pra descobrir o que um item aceita
BLOCK_NO_STOCK = 3600
BLOCK_NO_GOLD = 1800
BLOCK_ERROR = 1800
MAX_TRIES = 3


def gp(value):
    return f"{int(value or 0):,}".replace(",", ".")


class Imbuer:
    def __init__(self, cfg, memory, log, clock, catalog=None):
        self.cfg, self.memory, self.log, self.clock = cfg, memory, log, clock
        self.catalog = catalog if catalog is not None else imbuing.load()
        self.pips = {}             # nome -> assinatura das bolinhas da ultima leitura de tooltip
        self.equip_at = {}         # nome -> quando leu o tooltip
        self.scan_at = {}          # nome -> quando leu o santuario
        self.blocked = {}          # (nome, item, imbuement) -> ate quando
        self.warned = {}
        self.requested = False     # interface pediu 'Ler contas e preços'

    # ------------------------------------------------------------- dados
    @property
    def settings(self):
        return self.cfg.get("imbuements") or {}

    def plan(self, name):
        return imbuing.plan_for(self.cfg, name)

    def equipment(self, name):
        """{item: [slots]} lido por ultimo (memory.json)."""
        return (self.memory.imbue()["equipment"].get(name.casefold()) or {}).get("items") or {}

    def _store_equipment(self, st, items):
        self.memory.set_imbue("equipment", st.name.casefold(), {
            "name": st.name, "vocation": st.vocation, "gold": st.gold, "items": items, "at": self.clock()})

    def _done(self, name):
        return set(self.memory.imbue().get("done", {}).get(name.casefold(), []))

    def _mark_done(self, name, item, family):
        done = self._done(name) | {imbuing.done_key(item, family)}
        self.memory.set_imbue("done", name.casefold(), sorted(done))

    def _warn(self, key, message, every=1800):
        now = self.clock()
        if now - self.warned.get(key, -1e9) >= every:
            self.warned[key] = now
            self.log(message)

    def _blocked(self, name, task):
        return self.clock() < self.blocked.get((name, task["item"], task["imbuement"]), 0)

    def _block(self, name, task, seconds):
        self.blocked[(name, task["item"], task["imbuement"])] = self.clock() + seconds

    def tasks(self, name, early=False):
        early_min = self.settings.get("renew_before_minutes", 30) if early else None
        return [t for t in imbuing.pending(self.plan(name), self.equipment(name), early_min, self._done(name))
                if not self._blocked(name, t)]

    def estimate(self, name, task):
        """Custo estimado com o que o bot ja leu (precos e quanto a conta tem)."""
        imbue = self.memory.imbue()
        have = imbue.get("have", {}).get(name.casefold(), {})
        prices = {k: v.get("rows") for k, v in imbue.get("prices", {}).items()}
        tokens = imbue.get("tokens", {}).get(name.casefold(), 0) or 0
        return imbuing.entry_cost(self.catalog, task["imbuement"], task["tier"], have, prices,
                                  self.settings.get("use_tokens"), tokens)

    # ---------------------------------------------------------- leitura
    def observe(self, acc, st):
        """A cada ciclo: mantem o equipamento lido (tooltip) e aprende o que cada item aceita (santuario)."""
        if st.phase not in ("hunting", "city", "training") or not hasattr(acc, "read_equipment"):
            return
        now = self.clock()
        sig = tuple(st.imbue_pips)
        if self.pips.get(st.name) != sig or now - self.equip_at.get(st.name, -1e9) >= EQUIP_EVERY:
            items = acc.read_equipment()
            if len(items) < len(st.imbue_pips):      # algum item nao foi lido: mantem o que ja sabia dele
                items = {**self.equipment(st.name), **items}
            self.pips[st.name] = sig
            self.equip_at[st.name] = now
            self._store_equipment(st, items)
        if st.phase in ("city", "training") and now - self.scan_at.get(st.name, -1e9) >= SCAN_EVERY:
            known = self.memory.imbue()["items"]
            if any(item not in known for item in self.equipment(st.name)):
                self.scan(acc, st, allowed=True)

    def scan(self, acc, st, allowed=None):
        """Santuario: tempo exato de cada slot e (se tiver item novo) o que cada item aceita, por nome de item."""
        self.scan_at[st.name] = self.clock()
        if allowed is None:
            known = self.memory.imbue()["items"]
            allowed = not self.equipment(st.name) or any(item not in known for item in self.equipment(st.name))
        shrine = acc.shrine_read(scan_allowed=allowed)
        known = self.memory.imbue()["items"]
        for item, info in shrine.items():
            if info.get("allowed"):
                self.memory.set_imbue("items", item, info["allowed"])
            elif allowed and item not in known:
                # todos os slots ocupados: nao da' pra ler agora; {} = nao insistir (a interface usa o catalogo)
                self.memory.set_imbue("items", item, {})
        self._store_equipment(st, {item: info["slots"] for item, info in shrine.items()})

    def read_prices(self, acc, names=None):
        names = sorted(names if names is not None else self.planned_materials())
        if not names:
            return {}
        offers = acc.market_offers(names)
        for name, rows in offers.items():
            self.memory.set_imbue("prices", name, {"rows": rows[:30], "at": self.clock()})
        return offers

    def planned_materials(self):
        out = set()
        for entries_by_item in ((self.settings.get("plan") or {}).values()):
            for entries in entries_by_item.values():
                for e in entries or []:
                    if e and e.get("imbuement") in self.catalog:
                        out |= {m["name"] for m in imbuing.materials(self.catalog, e["imbuement"], e.get("tier") or "Basic")}
        return out

    def refresh_all(self, accounts, states):
        """Botao 'Ler contas e preços': equipamento de todas, santuario das que estao na cidade e precos."""
        self.requested = False
        city = None
        for acc in accounts:
            st = states.get(acc.name)
            if not st or st.phase not in ("hunting", "city", "training"):
                continue
            try:
                if st.phase in ("city", "training"):
                    self.scan(acc, st, allowed=True)
                    city = city or acc
                    self._read_have(acc, st)
                else:
                    self._store_equipment(st, acc.read_equipment())
                    self.equip_at[st.name] = self.clock()
            except Exception as error:
                self.log(f"[{st.name}] imbuements: nao consegui ler ({error})")
        source = city or next((a for a in accounts if a.name in states), None)
        if source:
            try:
                self.read_prices(source)
            except Exception as error:
                self.log(f"imbuements: nao consegui ler os precos do leilao ({error})")
        self.log("imbuements: contas e precos atualizados")

    def _read_have(self, acc, st):
        """Quanto a conta tem dos materiais do plano (so' dos imbuements que ainda faltam)."""
        have = dict(self.memory.imbue().get("have", {}).get(st.name.casefold(), {}))
        for task in imbuing.pending(self.plan(st.name), self.equipment(st.name)):
            info = acc.shrine_offer(task["item"], task["imbuement"], task["tier"], self.catalog)
            have.update(info["have"])
            if info.get("tokens_have") is not None:
                self.memory.set_imbue("tokens", st.name.casefold(), info["tokens_have"])
        self.memory.set_imbue("have", st.name.casefold(), have)

    # ------------------------------------------------------------ decisao
    def exit_reason(self, group):
        """Motivo pra sair da caçada (algum imbuement planejado faltando e com gold), ou None."""
        reasons = []
        for name, st in group.states.items():
            tasks = self.tasks(name)
            if not tasks:
                continue
            total = sum(self.estimate(name, t)["total"] for t in tasks)
            if st.gold is not None and total > st.gold:
                self._warn(("gold", name), f"[{name}] imbuements pendentes (~{gp(total)} gold) mas a conta tem {gp(st.gold)} - nao vou sair")
                continue
            reasons.append(f"{name}: " + ", ".join(f"{t['tier']} {t['imbuement']} ({t['item']})" for t in tasks))
        return ("imbuement: " + "; ".join(reasons)) if reasons else None

    # -------------------------------------------------------------- acao
    def work(self, acc, early=True):
        """Na cidade: compra o que falta e imbui tudo o que estiver pendente desta conta."""
        st = acc.read()
        if st.phase not in ("city", "training") or not self.plan(st.name):
            return
        if not self.tasks(st.name, early=early):
            return     # nada faltando nem perto de acabar (o tooltip ja da' o tempo em horas)
        try:
            self.scan(acc, st)
        except Exception as error:
            self.log(f"[{st.name}] imbuements: nao consegui abrir o santuario ({error})")
            return
        tasks = self.tasks(st.name, early=early)
        for task in tasks:
            label = f"{task['tier']} {task['imbuement']} em {task['item']}"
            try:
                if task["kind"] == "early":
                    gold = acc.read().gold or 0
                    if gold < imbuing.REMOVE_COST + self.estimate(st.name, task)["total"]:
                        self.log(f"[{st.name}] {label}: sem gold pra renovar antes de acabar")
                        self._block(st.name, task, BLOCK_NO_GOLD)
                        continue
                    self.log(f"[{st.name}] {label}: menos de {self.settings.get('renew_before_minutes', 30)} min - removendo pra renovar")
                    acc.shrine_remove(task["item"], task["imbuement"])
                self._do(acc, st.name, task, label)
            except Exception as error:
                self.log(f"[{st.name}] ERRO no imbuement ({label}): {error}")
                self._block(st.name, task, BLOCK_ERROR)
                acc.close_windows()
        if tasks:
            try:
                self.scan(acc, acc.read())
            except Exception:
                pass

    def _do(self, acc, name, task, label):
        use_tokens = bool(self.settings.get("use_tokens"))
        for attempt in range(1, MAX_TRIES + 1):
            info = acc.shrine_offer(task["item"], task["imbuement"], task["tier"], self.catalog)
            tokens_have = info.get("tokens_have") or 0
            self.memory.set_imbue("tokens", name.casefold(), tokens_have)
            mats = [m["name"] for m in imbuing.materials(self.catalog, task["imbuement"], task["tier"])]
            prices = {} if use_tokens and tokens_have >= self.catalog[task["imbuement"]]["tiers"][task["tier"]]["gold_tokens"] \
                else self.read_prices(acc, mats)
            cost = imbuing.entry_cost(self.catalog, task["imbuement"], task["tier"], info["have"], prices, use_tokens, tokens_have)
            if cost["no_stock"]:
                self.log(f"[{name}] {label}: sem estoque no leilao de {', '.join(cost['no_stock'])} - tento de novo em 1h")
                self._block(name, task, BLOCK_NO_STOCK)
                return False
            gold = acc.read().gold or 0
            if cost["total"] > gold:
                self.log(f"[{name}] {label}: custa {gp(cost['total'])} e a conta tem {gp(gold)} - pulando")
                self._block(name, task, BLOCK_NO_GOLD)
                return False
            for material, qty in cost["buy"].items():
                limit = int(imbuing.walk(prices[material], qty)[0] * 1.1) + 1
                bought, _ = acc.market_buy(material, qty, limit)
                if bought < qty:
                    self.log(f"[{name}] {label}: so' consegui comprar {bought}/{qty} {material}")
                    self._block(name, task, BLOCK_NO_STOCK)
                    return False
            pay = "gold tokens" if cost["pay"] == "tokens" else "materiais"
            self.log(f"[{name}] imbuindo {label} ({pay}, protecao {'sim' if cost['protect'] else 'nao'}, "
                     f"~{gp(cost['total'])} gold)")
            ok, message = acc.shrine_apply(task["item"], task["imbuement"], task["tier"], cost["protect"], cost["pay"] == "tokens")
            if ok:
                self.log(f"[{name}] {message or label + ' aplicado'}")
                if not task["renew"]:
                    self._mark_done(name, task["item"], task["imbuement"])
                return True
            self.log(f"[{name}] {label}: falhou (tentativa {attempt}) - {message}")
        self._block(name, task, BLOCK_ERROR)
        return False
