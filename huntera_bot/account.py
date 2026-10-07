"""Uma conta do Huntera = uma pagina do jogo no IdleDeck. Le o estado (uma
chamada so') e executa as acoes (sair, vender, despachar, iniciar caçada)."""
import json
import re
import time
from dataclasses import dataclass, field

from . import imbuing
from . import selectors as S

READ_JS = """(S) => {
  const q = s => document.querySelector(s);
  const vis = e => !!e && e.getBoundingClientRect().width > 0;
  const txt = e => e ? (e.innerText || '').split(String.fromCharCode(10)).join(' ').trim() : '';
  const cap = q(S.CAPACITY);
  const leaveBtn = q(S.LEAVE_BTN);
  const dispatch = q(S.DISPATCH_BTN);
  const head = q(S.BESTIARY_HEAD);
  const stamina = q(S.STAMINA);
  const training = q(S.TRAINING);
  const members = Array.from(document.querySelectorAll(S.PARTY_MEMBER)).map(m => ({
    name: txt(m.querySelector(S.PARTY_NAME)), leader: vis(m.querySelector(S.PARTY_LEADER)), follow: vis(m.querySelector(S.PARTY_FOLLOW))}));
  return {
    name: txt(q(S.NAME)), vocation: txt(q(S.VOCATION)),
    loading: Array.from(document.querySelectorAll(S.WORLD_LOADING)).some(vis),
    in_hunt: vis(q(S.LEAVE_GROUP)), in_city: vis(q(S.CITY_MARKER)),
    leaving: !!leaveBtn && /^\\W*sain/i.test(txt(leaveBtn)),
    cap_title: cap ? (cap.getAttribute('title') || '') : null,
    stamina: stamina ? txt(stamina) : '',
    training: vis(training), training_skill: training ? txt(q(S.TRAINING_SKILL)) : '',
    dispatch: dispatch ? {vis: vis(dispatch), disabled: !!dispatch.disabled, cooling: dispatch.classList.contains('cooling'), text: txt(dispatch)} : null,
    bestiary_head: head ? txt(head) : '',
    bestiary_rows: Array.from(document.querySelectorAll(S.BESTIARY_ROW)).map(r => ({
      label: txt(r.querySelector(S.BESTIARY_LABEL)), count: txt(r.querySelector(S.BESTIARY_COUNT))})),
    party: members,
    toasts: Array.from(document.querySelectorAll(S.TOAST)).filter(vis).map(txt),
    gold: txt(q(S.GOLD)),
    select: !!q(S.CHAR_PLAY), play_ready: !!q(S.CHAR_PLAY) && !q(S.CHAR_PLAY).disabled,
    select_name: txt(q(S.CHAR_NAME)), notice: txt(q(S.CHAR_NOTICE)), motd: vis(q(S.MOTD)),
    invite: Array.from(document.querySelectorAll(S.PARTY_INVITE_BTN)).filter(vis).map(txt),
    follow_switch: txt(q(S.PARTY_SWITCH)), costs: txt(q(S.PARTY_COSTS_STATE)),
    pips: Array.from(document.querySelectorAll(S.EQUIP_SLOT)).map(s => ({
      equip: s.getAttribute('data-equip') || '', total: s.querySelectorAll(S.IMBUE_PIP).length,
      filled: s.querySelectorAll(S.IMBUE_PIP + '.filled').length})).filter(p => p.total > 0),
  };
}"""

# tooltip de cada item equipado com slot de imbuement: nome na 1a linha, depois os slots
EQUIP_JS = """(S) => Array.from(document.querySelectorAll(S.EQUIP_SLOT)).map((s, i) => ({
  i, equip: s.getAttribute('data-equip') || '', total: s.querySelectorAll(S.IMBUE_PIP).length})).filter(p => p.total > 0)"""

TOOLTIP_JS = """(S) => { const t = Array.from(document.querySelectorAll(S.TOOLTIP)).find(e => e.getBoundingClientRect().width > 0);
  return t ? t.innerText : ''; }"""

# santuario: itens EQUIPADOS com seus slots
SHRINE_JS = """(S) => Array.from(document.querySelectorAll(S.SHRINE_ITEM)).map((it, i) => ({
  i, name: ((it.querySelector(S.SHRINE_ITEM_NAME) || {}).innerText || '').trim(),
  where: ((it.querySelector(S.SHRINE_ITEM_WHERE) || {}).innerText || '').trim(),
  slots: Array.from(it.querySelectorAll(S.SHRINE_SLOT)).map(s => ({filled: s.classList.contains('filled'), title: s.title || ''}))}))"""

LINES_JS = """(S) => Array.from(document.querySelectorAll(S.SHRINE_LINE)).map(l => ({
  name: ((l.querySelector(S.SHRINE_LINE_NAME) || {}).innerText || '').trim(), disabled: !!l.disabled}))"""

MARKET_JS = """(S) => Array.from(document.querySelectorAll(S.MARKET_SELL_ROWS)).map(r => {
  const td = Array.from(r.querySelectorAll('td')).map(x => (x.innerText || '').trim());
  return {seller: td[0] || '', qty: parseInt((td[1] || '').replace(/[^0-9]/g, '')) || 0, price: parseInt((td[2] || '').replace(/[^0-9]/g, '')) || 0};
}).filter(r => r.qty > 0 && r.price > 0)"""

_SEL = {k: v for k, v in vars(S).items() if k.isupper() and isinstance(v, str)}
_CAP_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s+de\s+([0-9]+(?:\.[0-9]+)?)")
_STAMINA_RE = re.compile(r"(\d+):(\d{2})")
_HEAD_RE = re.compile(r"(.*?)\s*(\d+)\s*/\s*(\d+)\s*$")


@dataclass
class State:
    name: str = ""
    vocation: str = ""
    phase: str = "unknown"          # city | training | hunting | leaving | loading | unknown
    cap_pct: float | None = None
    cap_used: float | None = None
    cap_max: float | None = None
    hunt_name: str = ""
    bestiary_done: int | None = None
    bestiary_total: int | None = None
    bestiary_rows: list = field(default_factory=list)
    dispatch_ready: bool = False
    stamina_min: int | None = None    # minutos de hunt restantes
    training_skill: str = ""
    dispatch_text: str = ""
    party_names: list = field(default_factory=list)
    leader_name: str = ""
    toasts: list = field(default_factory=list)
    gold: int | None = None
    play_ready: bool = False        # tela de personagens com o Jogar habilitado (o jogo voltou)
    notice: str = ""                # aviso da tela de personagens ('Server save...')
    motd: bool = False              # 'PATCH NOTES' aberto depois de entrar
    invite: list = field(default_factory=list)   # botoes do cartao de party na tela
    accept_all: bool | None = None  # 'aceitar tudo do lider' ligado? (None = sem party)
    costs_shared: bool | None = None
    imbue_pips: list = field(default_factory=list)   # [(equip, slots, ativos)] - muda quando um imbuement entra/acaba

    @property
    def bestiary_complete(self):
        return bool(self.bestiary_total) and self.bestiary_done == self.bestiary_total


def parse_state(raw):
    """Converte o que a pagina devolveu em State (separado pra testar sem jogo)."""
    st = State(name=raw.get("name", ""), vocation=raw.get("vocation", ""))
    if raw.get("select"):           # fora do jogo: tela de personagens (server save ou caiu)
        st.phase = "select"
        st.name = st.name or (raw.get("select_name") or "").upper()   # igual ao cabecalho do jogo
        st.play_ready = bool(raw.get("play_ready"))
        st.notice = raw.get("notice") or ""
        return st
    if raw.get("loading"):
        st.phase = "loading"
    elif raw.get("leaving"):
        st.phase = "leaving"
    elif raw.get("in_hunt"):
        st.phase = "hunting"
    elif raw.get("training"):
        st.phase = "training"
        st.training_skill = raw.get("training_skill", "")
    elif raw.get("in_city"):
        st.phase = "city"
    m = _CAP_RE.search(raw.get("cap_title") or "")
    if m:
        st.cap_used, st.cap_max = float(m.group(1)), float(m.group(2))
        if st.cap_max > 0:
            st.cap_pct = round(100.0 * st.cap_used / st.cap_max, 1)
    head = _HEAD_RE.match((raw.get("bestiary_head") or "").strip())
    if head:
        st.hunt_name = re.sub(r"^[^A-Za-z]+", "", head.group(1)).strip()   # tira o simbolo do cabecalho
        st.bestiary_done, st.bestiary_total = int(head.group(2)), int(head.group(3))
    sm = _STAMINA_RE.search(raw.get("stamina") or "")
    if sm:
        st.stamina_min = int(sm.group(1)) * 60 + int(sm.group(2))
    st.bestiary_rows = raw.get("bestiary_rows") or []
    d = raw.get("dispatch")
    if d:
        st.dispatch_text = d.get("text", "")
        st.dispatch_ready = bool(d.get("vis")) and not d.get("disabled") and not d.get("cooling")
    party = raw.get("party") or []
    st.party_names = [p["name"] for p in party if p.get("name")]
    st.leader_name = next((p["name"] for p in party if p.get("leader")), "")
    st.toasts = raw.get("toasts") or []
    st.gold = imbuing.number(raw.get("gold"))
    st.motd = bool(raw.get("motd"))
    st.invite = raw.get("invite") or []
    switch = (raw.get("follow_switch") or "").casefold()
    st.accept_all = None if not switch else switch.startswith("parar")
    costs = (raw.get("costs") or "").casefold()
    st.costs_shared = None if not costs else costs.startswith("rateio ligado")
    st.imbue_pips = [(p["equip"], p["total"], p["filled"]) for p in raw.get("pips") or []]
    return st


def parse_tooltip(text):
    """Tooltip de item equipado -> (nome, [{'active', 'minutes'}]) - um por slot de imbuement, na ordem."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return "", []
    slots = []
    for line in lines[1:]:
        if line.casefold().startswith("slot de imbuement vazio") or line.casefold().startswith("empty imbuement slot"):
            slots.append({"active": None, "minutes": None})
            continue
        tier, family = imbuing.split_active(line.split("(")[0].strip())
        if tier and "(" in line:
            slots.append({"active": f"{tier} {family}", "minutes": imbuing.minutes(line)})
    return lines[0], slots


def parse_slot_title(title):
    """Title do slot no santuario: 'Basic Demon Presence — resta 20h 0m' / 'Slot de imbuement vazio'."""
    name, sep, rest = (title or "").partition("—")
    tier, family = imbuing.split_active(name.strip())
    if not sep or not tier:
        return {"active": None, "minutes": None}
    return {"active": f"{tier} {family}", "minutes": imbuing.minutes(rest)}


class GameError(Exception):
    pass


class NothingToSell(Exception):
    """Venda/despacho indisponivel porque nao ha item vendavel (nao e' erro)."""


class Account:
    def __init__(self, page, log=print):
        self.page = page
        self.log = log
        self.name = ""

    # ---------------------------------------------------------------- leitura
    def read(self):
        raw = self.page.evaluate(READ_JS, _SEL)
        st = parse_state(raw)
        self.name = st.name or self.name
        return st


    def _click(self, target, timeout=3000):
        """Clique robusto. CONFIRMADO ao vivo: janelas do HUD (party, 'Ratear custos da hunt') ficam POR CIMA
        de botoes (Sair da caçada, Cancelar treino) e o Playwright recusa o clique ('intercepts pointer
        events'). Nesse caso (e SO' nele) dispara o 'click' direto no botao; qualquer outro erro
        (invisivel, desabilitado, nao achou) continua sendo erro. 'target' = seletor ou locator."""
        locator = self.page.locator(target) if isinstance(target, str) else target
        try:
            locator.first.click(timeout=timeout)
        except Exception as error:
            if "intercepts pointer events" not in str(error):
                raise
            locator.first.dispatch_event("click")

    def _visible(self, selector):
        return self.page.evaluate(
            "(s) => { const e = document.querySelector(s); return !!e && e.getBoundingClientRect().width > 0 }", selector)

    def _wait(self, predicate, seconds, step=0.4):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(step)
        return predicate()

    def close_windows(self):
        """Fecha janelas que o bot abriu (sem confirmar nada)."""
        for window, closer in ((S.PROMPT, S.PROMPT_CANCEL), (S.QS_WINDOW, S.QS_CANCEL), (S.HUNT_WINDOW, S.HUNT_CLOSE),
                               (S.SHRINE_CLOSE, S.SHRINE_CLOSE), (S.TRADE_CLOSE, S.TRADE_CLOSE)):
            try:
                if self._visible(window):
                    self._click(closer, 3000)
                    time.sleep(0.5)
            except Exception:
                pass

    # ------------------------------------------------------------------ acoes
    def leave_hunt(self, timeout=45):
        """Clica em 'Sair da caçada' (contagem de 5s, sem confirmacao). Nao clica de novo se ja esta saindo."""
        st = self.read()
        if st.phase == "city":
            return True
        if st.phase == "hunting":
            self._click(S.LEAVE_BTN, 3000)
        return self._wait(lambda: self.read().phase == "city", timeout, 0.7)

    def _open_quick_sell(self, via):
        if self._visible(S.QS_WINDOW):
            return
        # CONFIRMADO ao vivo: o botao fica DESABILITADO quando nao ha nada vendavel na mochila
        enabled = self.page.evaluate(
            "(s) => { const e = document.querySelector(s); return !!e && !e.disabled }", via)
        if not enabled:
            raise NothingToSell()
        self._click(via, 3000)
        if not self._wait(lambda: self._visible(S.QS_WINDOW), 6):
            raise GameError("janela de venda nao abriu")

    def _mark_and_confirm(self, keep, mark_all):
        """Na janela aberta: marca (so' a mochila, que e' tudo o que a lista traz) e confirma.
        Retorna (itens_marcados, texto_do_botao)."""
        keep = {k.lower() for k in keep}
        rows = self.page.evaluate(
            """(S) => Array.from(document.querySelectorAll(S.QS_ROW)).map((r, i) => ({
                i, name: ((r.querySelector('strong') || {innerText: ''}).innerText || '').trim(),
                detail: ((r.querySelector('small') || {innerText: ''}).innerText || '').trim(),
                marked: r.classList.contains('marked') || r.getAttribute('aria-pressed') === 'true'}))""", _SEL)
        for row in rows:
            name = row["name"].lower()
            if name in keep:
                if row["marked"]:  # item protegido que estava marcado: desmarca
                    self._click(self.page.locator(S.QS_ROW).nth(row["i"]))
                continue
            if mark_all and not row["marked"]:
                self._click(self.page.locator(S.QS_ROW).nth(row["i"]))
        time.sleep(0.4)
        state = self.page.evaluate(
            """(S) => { const c = document.querySelector(S.QS_CONFIRM);
                return {marked: document.querySelectorAll(S.QS_ROW + '.marked').length, text: c ? c.innerText.trim() : '', disabled: c ? !!c.disabled : true}; }""", _SEL)
        if state["marked"] == 0 or state["disabled"]:
            self._click(S.QS_CANCEL, 3000)
            self._wait(lambda: not self._visible(S.QS_WINDOW), 4)
            return 0, "", []
        sold = [f"{r['name']} ({r['detail']})" for r in rows
                if r["name"].lower() not in keep and (r["marked"] or mark_all)]
        self._click(S.QS_CONFIRM, 3000)
        if not self._wait(lambda: not self._visible(S.QS_WINDOW), 6):
            raise GameError("a janela de venda nao fechou apos confirmar")
        return state["marked"], state["text"], sold

    def sell_all(self, keep=(), mark_all=True):
        """Venda rapida na CIDADE. Retorna quantos itens foram vendidos."""
        try:
            self._open_quick_sell(S.QUICK_SELL_BTN)
            marked, text, sold = self._mark_and_confirm(keep, mark_all)
            self.log(f"[{self.name}] venda rapida: {marked} item(ns) ({text or 'nada marcado'}): {'; '.join(sold)}")
            return marked
        except NothingToSell:
            self.log(f"[{self.name}] venda rapida: nada a vender")
            return 0
        except Exception:
            self.close_windows()
            raise

    def dispatch_loot(self, keep=(), mark_all=True):
        """'Despachar loot' DENTRO da hunt (1x por hora)."""
        try:
            self._open_quick_sell(S.DISPATCH_BTN)
            marked, text, sold = self._mark_and_confirm(keep, mark_all)
            self.log(f"[{self.name}] despacho: {marked} item(ns) ({text or 'nada marcado'}): {'; '.join(sold)}")
            return marked
        except NothingToSell:
            self.log(f"[{self.name}] despacho: nada a vender")
            return 0
        except Exception:
            self.close_windows()
            raise

    def open_hunt_entry(self, hunt, tier=None):
        """Caçar > Organizar caçada > escolhe a hunt (e o pull, se pedido). Deixa a janela aberta."""
        self._click(S.START_NAV, 3000)
        if not self._wait(lambda: self._visible(S.ORGANIZE) or self._visible(S.HUNT_WINDOW), 5):
            raise GameError("janela de caçada nao abriu")
        time.sleep(0.6)
        if self._visible(S.ORGANIZE):
            self._click(S.ORGANIZE, 3000)
        entry = self.page.locator(S.HUNT_ENTRY.format(name=hunt))
        if not self._wait(lambda: entry.count() > 0, 6):
            raise GameError(f"hunt '{hunt}' nao encontrada na lista")
        entry.scroll_into_view_if_needed(timeout=3000)
        self._click(entry)
        time.sleep(0.8)
        if tier:
            tiers = self.page.locator(S.HUNT_TIER).filter(has_text=tier)
            if tiers.count() == 0:
                raise GameError(f"pull '{tier}' nao existe em '{hunt}'")
            selected = "selected" in (tiers.first.get_attribute("class") or "")
            if not selected:
                self._click(tiers.first)
                time.sleep(0.5)

    def start_hunt(self, hunt, tier=None, team=False):
        """Inicia a caçada (solo ou com o time). Retorna sem esperar o carregamento."""
        try:
            self.open_hunt_entry(hunt, tier)
            button = S.START_TEAM if team else S.START_SOLO
            ok = self.page.evaluate(
                "(s) => { const e = document.querySelector(s); return !!e && e.getBoundingClientRect().width > 0 && !e.disabled }", button)
            if not ok:
                raise GameError("botao de iniciar indisponivel (" + ("time" if team else "solo") + ")")
            self._click(button, 3000)
            time.sleep(0.8)
        except Exception:
            self.close_windows()
            raise

    def start_training(self, skill):
        """Caçar > Treino > habilidade > 'Treino online' > Iniciar treino. A conta TEM que estar na cidade
        (o botao fica desabilitado em caçada)."""
        try:
            self._click(S.START_NAV, 3000)
            if not self._wait(lambda: self._visible(S.HUNT_WINDOW), 6):
                raise GameError("janela de caçada nao abriu")
            time.sleep(0.6)
            self._click(self.page.locator(S.HUNT_TAB).filter(has_text="Treino").first)
            time.sleep(0.9)
            button = self.page.locator(S.TRAIN_SKILL).filter(has_text=skill)
            if button.count() == 0:
                raise GameError(f"habilidade '{skill}' nao encontrada")
            if "active" not in (button.first.get_attribute("class") or ""):
                self._click(button.first)
                time.sleep(0.6)
            start = self.page.locator(S.TRAIN_MODE).filter(has_text="Treino online").locator(S.TRAIN_START)
            if start.count() == 0 or not start.first.is_enabled():
                reason = (start.first.get_attribute("title") if start.count() else "") or "botao indisponivel"
                raise GameError(f"treino online indisponivel: {reason}")
            self._click(start.first)
            time.sleep(1.2)
            self.log(f"[{self.name}] treino iniciado: {skill}")
        except Exception:
            self.close_windows()
            raise
        else:
            self.close_windows()      # se a janela continuar aberta, fecha (nao confirma nada)

    def read_training_options(self):
        """Habilidades que o jogo oferece a esta conta (Caçar > Treino), so' lendo. None se nao deu."""
        try:
            self._click(S.START_NAV, 3000)
            if not self._wait(lambda: self._visible(S.HUNT_WINDOW), 6):
                return None
            time.sleep(0.5)
            self._click(self.page.locator(S.HUNT_TAB).filter(has_text="Treino").first)
            time.sleep(0.9)
            skills = self.page.evaluate(
                """(S) => Array.from(document.querySelectorAll(S.TRAIN_SKILL)).filter(e => !e.disabled)
                    .map(e => ((e.querySelector('small') || {innerText: ''}).innerText || '').trim()).filter(Boolean)""", _SEL)
            return skills or None
        except Exception:
            return None
        finally:
            self.close_windows()

    def cancel_training(self, timeout=8):
        """Clica em 'Cancelar' no painel 'Treino ativo' (a conta fica na cidade)."""
        if not self._visible(S.TRAINING):
            return True
        self._click(S.TRAINING_CANCEL, 2500)
        ok = self._wait(lambda: not self._visible(S.TRAINING), timeout)
        if ok:
            self.log(f"[{self.name}] treino cancelado")
        return ok

    # ------------------------------------------------------- volta / party
    def play(self, timeout=60):
        """Tela de personagens com o Jogar habilitado: entra. True quando o jogo carregou (cidade/caçada)."""
        self._click(S.CHAR_PLAY, 4000)
        return self._wait(lambda: self.read().phase in ("city", "training", "hunting"), timeout, 1.0)

    def close_motd(self):
        """'PATCH NOTES' depois de entrar: Fechar."""
        if self._visible(S.MOTD):
            self._click(self.page.locator(S.MOTD_CLOSE).filter(has_text="Fechar").first)
            time.sleep(0.5)

    def invite_to_party(self, names):
        """LIDER: Amigos -> botao direito em cada nome -> 'Convidar para a party'. Retorna os convidados."""
        done = []
        try:
            if not self._visible(S.FRIENDS_WINDOW):          # o botao abre E fecha a lista
                self._click(S.FRIENDS_NAV, 3000)
                if not self._wait(lambda: self._visible(S.FRIENDS_WINDOW), 5):
                    raise GameError("a lista de amigos nao abriu")
                time.sleep(0.6)
            for name in names:
                entry = self.page.locator(S.FRIENDS_ENTRY).filter(
                    has=self.page.locator(S.FRIENDS_NAME).filter(has_text=re.compile(rf"^{re.escape(name)}\b", re.I)))
                if entry.count() == 0:
                    self.log(f"[{self.name}] {name} nao esta na lista de amigos (ou esta offline)")
                    continue
                entry.first.click(button="right", timeout=3000)
                item = self.page.locator(S.FRIENDS_MENU_ITEM).filter(has_text="Convidar para a party")
                if not self._wait(lambda: item.count() > 0, 3):
                    self._click(".context-backdrop", 2000)        # menu de contexto nao fecha com Escape
                    continue
                self._click(item.first)
                time.sleep(0.8)
                done.append(name)
        finally:
            try:
                if self._visible(S.FRIENDS_WINDOW):
                    self._click(S.FRIENDS_CLOSE, 3000)
            except Exception:
                pass
        return done

    def answer_party_invite(self, leader, timeout=40):
        """CONVIDADO: trata os cartoes ate' estar na party do lider seguindo-o e com 'aceitar tudo' ligado.
        Ordem vista ao vivo: 'ENTRAR E ACEITAR TUDO' (mesmo mundo) ou 'ENTRAR' (outro mundo: carrega) ->
        'SEGUIR O LÍDER'. Nunca clica em RECUSAR / MANTER A ATUAL."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            st = self.read()
            if st.phase in ("loading", "leaving"):
                time.sleep(1.0)
                continue
            clicked = False
            for label in ("ENTRAR E ACEITAR TUDO", "SEGUIR O LÍDER", "ENTRAR"):
                if any(b.strip().upper() == label for b in st.invite):
                    self._click(self.page.locator(S.PARTY_INVITE_BTN).filter(has_text=re.compile(rf"^\s*{label}\s*$", re.I)).first)
                    self.log(f"[{self.name}] party: {label.lower()}")
                    clicked = True
                    break
            if clicked:
                time.sleep(1.5)
                continue
            in_party = any(n.casefold() == leader.casefold() for n in st.party_names)
            if in_party and st.accept_all is False:
                self._click(S.PARTY_SWITCH, 3000)
                self.log(f"[{self.name}] party: aceitar tudo do lider ligado")
                time.sleep(1.0)
                continue
            if in_party and st.accept_all and not st.invite:
                return True
            time.sleep(1.0)
        return False

    def share_costs(self):
        """LIDER: 'Ratear custos da hunt' (se ainda nao estiver ligado)."""
        if self.read().costs_shared:
            return True
        offer = self.page.locator(S.PARTY_COSTS_OFFER)
        if offer.count() == 0 or not offer.first.is_visible():
            if self._visible(S.PARTY_NAV):
                self._click(S.PARTY_NAV, 3000)
                time.sleep(0.8)
        if offer.count() == 0:
            return False
        self._click(offer.first)
        return self._wait(lambda: bool(self.read().costs_shared), 5)

    # ------------------------------------------------------------- imbuements
    def read_equipment(self):
        """Itens equipados com slot de imbuement (passa o mouse em cada um e le o tooltip; funciona em
        qualquer lugar, inclusive em caçada). -> {item: [{'active', 'minutes'}]}"""
        out = {}
        try:
            for slot in self.page.evaluate(EQUIP_JS, _SEL):
                # CONFIRMADO ao vivo: o tooltip do item anterior pode continuar na tela e o nome vinha errado
                # (a arma sumia da leitura). Tira o mouse, espera o tooltip sumir e so' aceita um com o
                # numero certo de slots e um nome que ainda nao foi lido.
                for _attempt in range(3):
                    self.page.mouse.move(2, 2)
                    self._wait(lambda: not self.page.evaluate(TOOLTIP_JS, _SEL), 1.0, 0.1)
                    self.page.locator(S.EQUIP_SLOT).nth(slot["i"]).hover(timeout=3000)
                    self._wait(lambda: self.page.evaluate(TOOLTIP_JS, _SEL), 1.5, 0.1)
                    name, slots = parse_tooltip(self.page.evaluate(TOOLTIP_JS, _SEL))
                    if name and name not in out and len(slots) == slot["total"]:
                        out[name] = slots
                        break
                else:
                    self.log(f"[{self.name}] nao consegui ler o item do slot '{slot['equip']}'")
        finally:
            self.page.mouse.move(2, 2)
        return out

    def _shrine_open(self):
        if not self._visible(S.SHRINE_BTN):
            raise GameError("santuario indisponivel (a conta precisa estar na cidade)")
        if not self._visible(S.SHRINE_ITEM):
            self._click(S.SHRINE_BTN, 4000)
            if not self._wait(lambda: self._visible(S.SHRINE_ITEM), 8):
                raise GameError("o santuario de imbuements nao abriu")
            time.sleep(0.5)

    def _shrine_close(self):
        try:
            if self._visible(S.PROMPT):
                self._click(S.PROMPT_CANCEL, 2000)
            if self._visible(S.SHRINE_CLOSE):
                self._click(S.SHRINE_CLOSE, 3000)
                time.sleep(0.4)
        except Exception:
            pass

    def _shrine_items(self):
        return [it for it in self.page.evaluate(SHRINE_JS, _SEL) if it["where"].casefold().startswith(("equipado", "worn"))]

    def _shrine_item(self, item):
        found = next((it for it in self._shrine_items() if it["name"].casefold() == item.casefold()), None)
        if found is None:
            raise GameError(f"'{item}' nao esta equipado")
        return found

    def _shrine_select(self, item, family, tier):
        """Escolhe um slot VAZIO do item, o nivel e o imbuement. Erro se nao der."""
        it = self._shrine_item(item)
        free = next((n for n, s in enumerate(it["slots"]) if not s["filled"]), None)
        if free is None:
            raise GameError(f"'{item}' nao tem slot livre")
        card = self.page.locator(S.SHRINE_ITEM).nth(it["i"])
        self._click(card.locator(S.SHRINE_SLOT).nth(free))
        time.sleep(0.4)
        self._click(self.page.locator(S.SHRINE_TIER).filter(has_text=tier).first)
        time.sleep(0.3)
        lines = self.page.evaluate(LINES_JS, _SEL)
        index = next((n for n, line in enumerate(lines) if line["name"] == family), None)
        if index is None or lines[index]["disabled"]:
            raise GameError(f"'{item}' nao aceita {tier} {family}")
        self._click(self.page.locator(S.SHRINE_LINE).nth(index))
        time.sleep(0.6)
        head = self.page.locator(S.SHRINE_OFFER).first.inner_text().strip()
        if head != f"{tier} {family}":
            raise GameError(f"oferta errada na tela: '{head}'")

    def _counts(self):
        out = []
        for text in self.page.locator(S.SHRINE_COUNTS).all_inner_texts():
            have, _, need = text.partition("/")
            out.append((imbuing.number(have) or 0, imbuing.number(need) or 0))
        return out

    def shrine_read(self, scan_allowed=True):
        """Abre o santuario e le os itens equipados: slots (com o tempo exato) e, se pedido, o que cada item
        aceita por nivel. -> {item: {'slots': [...], 'allowed': {tier: [imbuements]} | None}}"""
        try:
            self._shrine_open()
            out = {}
            for it in self._shrine_items():
                slots = [parse_slot_title(s["title"]) if s["filled"] else {"active": None, "minutes": None} for s in it["slots"]]
                entry = {"slots": slots, "allowed": None}
                free = next((n for n, s in enumerate(it["slots"]) if not s["filled"]), None)
                if scan_allowed and free is not None:
                    card = self.page.locator(S.SHRINE_ITEM).nth(it["i"])
                    self._click(card.locator(S.SHRINE_SLOT).nth(free))
                    time.sleep(0.4)
                    allowed = {}
                    for tier in imbuing.TIERS:
                        self._click(self.page.locator(S.SHRINE_TIER).filter(has_text=tier).first)
                        time.sleep(0.3)
                        allowed[tier] = [line["name"] for line in self.page.evaluate(LINES_JS, _SEL) if not line["disabled"]]
                    for slot in slots:     # o que ja esta no item nao aparece na lista, mas e' aceito
                        tier, family = imbuing.split_active(slot["active"])
                        if tier:
                            for t in imbuing.TIERS[:imbuing.TIERS.index(tier) + 1]:
                                if family not in allowed[t]:
                                    allowed[t].append(family)
                    entry["allowed"] = allowed
                out[it["name"]] = entry
            return out
        finally:
            self._shrine_close()

    def shrine_offer(self, item, family, tier, catalog):
        """Le o que a conta tem para um imbuement. -> {'have': {material: qtd}, 'tokens_have': int|None}"""
        try:
            self._shrine_open()
            self._shrine_select(item, family, tier)
            mats = imbuing.materials(catalog, family, tier)
            have = {m["name"]: c[0] for m, c in zip(mats, self._counts())}
            tokens_have = None
            pay = self.page.locator(S.SHRINE_PAY).filter(has_text="Tokens")
            if pay.count():
                self._click(pay.first)
                time.sleep(0.3)
                counts = self._counts()
                tokens_have = counts[0][0] if counts else None
                self._click(self.page.locator(S.SHRINE_PAY).filter(has_text="Sources").first)
                time.sleep(0.2)
            return {"have": have, "tokens_have": tokens_have}
        finally:
            self._shrine_close()

    def shrine_apply(self, item, family, tier, protect, tokens=False):
        """Imbui (escolhe slot vazio, nivel, imbuement, forma de pagar e protecao; confirma). -> (ok, mensagem)"""
        try:
            self._shrine_open()
            self._shrine_select(item, family, tier)
            pay = self.page.locator(S.SHRINE_PAY).filter(has_text="Tokens" if tokens else "Sources")
            if pay.count():
                self._click(pay.first)
                time.sleep(0.3)
            counts = self._counts()
            if any(have < need for have, need in counts):
                raise GameError(f"faltam {'gold tokens' if tokens else 'materiais'} para {tier} {family}: {counts}")
            box = self.page.locator(S.SHRINE_PROTECT).first
            if box.is_checked() != bool(protect):
                box.click()
                time.sleep(0.3)
            if self.page.locator(S.SHRINE_APPLY).first.is_disabled():
                raise GameError("botao Imbuir desabilitado (gold insuficiente?)")
            self._click(S.SHRINE_APPLY, 3000)
            if not self._wait(lambda: self._visible(S.PROMPT), 5):
                raise GameError("a confirmacao do imbuement nao apareceu")
            text = self.page.locator(S.PROMPT).first.inner_text()
            if family not in text or item not in text:
                raise GameError(f"confirmacao inesperada: {text[:120]}")
            self._click(S.PROMPT_CONFIRM, 3000)
            status = self.page.locator(S.SHRINE_STATUS)
            if not self._wait(lambda: (status.get_attribute("class") or "") in ("ok", "failed"), 10):
                raise GameError("sem resposta do santuario")
            ok = status.get_attribute("class") == "ok"
            return ok, status.inner_text().strip()
        finally:
            self._shrine_close()

    def shrine_remove(self, item, family):
        """Remove um imbuement ativo (custa gold, nao devolve nada)."""
        try:
            self._shrine_open()
            it = self._shrine_item(item)
            index = next((n for n, s in enumerate(it["slots"])
                          if s["filled"] and imbuing.split_active(parse_slot_title(s["title"])["active"])[1] == family), None)
            if index is None:
                return True
            self._click(self.page.locator(S.SHRINE_ITEM).nth(it["i"]).locator(S.SHRINE_SLOT).nth(index))
            time.sleep(0.5)
            self._click(S.SHRINE_REMOVE, 3000)
            if not self._wait(lambda: self._visible(S.PROMPT), 5):
                raise GameError("a confirmacao de remover nao apareceu")
            self._click(S.PROMPT_CONFIRM, 3000)
            return self._wait(lambda: not any(
                s["filled"] and family in s["title"] for s in self._shrine_item(item)["slots"]), 8)
        finally:
            self._shrine_close()

    def _toasts(self):
        return self.page.evaluate("(s) => Array.from(document.querySelectorAll(s)).map(t => (t.innerText || '').trim())", S.TOAST)

    def _market_open(self):
        if not self._visible(S.MARKET_SEARCH):
            if not self._visible(S.TRADE_CLOSE):
                self._click(S.STORE_NAV, 4000)
                if not self._wait(lambda: self._visible(S.TRADE_TAB), 6):
                    raise GameError("a loja nao abriu")
                time.sleep(0.6)
            self._click(self.page.locator(S.TRADE_TAB).filter(has_text="LEIL").first)
            if not self._wait(lambda: self._visible(S.MARKET_SEARCH), 6):
                raise GameError("o leilao nao abriu")
            time.sleep(0.6)

    def _market_close(self):
        try:
            if self._visible(S.MARKET_SEARCH):
                self.page.locator(S.MARKET_SEARCH).fill("")
            if self._visible(S.TRADE_CLOSE):
                self._click(S.TRADE_CLOSE, 3000)
                time.sleep(0.4)
        except Exception:
            pass

    def _market_select(self, name):
        self.page.locator(S.MARKET_SEARCH).fill(name)
        time.sleep(0.8)
        items = self.page.locator(S.MARKET_ITEM)
        for n in range(items.count()):
            label = items.nth(n).locator(S.MARKET_ITEM_NAME)
            if label.count() and label.first.inner_text().strip().casefold() == name.casefold():
                self._click(items.nth(n))
                time.sleep(1.2)
                return True
        return False

    def market_offers(self, names):
        """Ofertas de VENDA do leilao (da mais barata). -> {material: [{'seller', 'qty', 'price'}]}"""
        out = {}
        try:
            self._market_open()
            for name in names:
                out[name] = self.page.evaluate(MARKET_JS, _SEL) if self._market_select(name) else []
        finally:
            self._market_close()
        return out

    def market_buy(self, name, qty, max_total):
        """Compra 'qty' das ofertas mais baratas sem passar de max_total de gold. -> (comprados, gasto)."""
        bought, spent = 0, 0
        try:
            self._market_open()
            if not self._market_select(name):
                raise GameError(f"'{name}' nao encontrado no leilao")
            while bought < qty:
                rows = self.page.evaluate(MARKET_JS, _SEL)
                if not rows:
                    break
                row = rows[0]
                take = min(qty - bought, row["qty"])
                if spent + take * row["price"] > max_total:
                    self.log(f"[{self.name}] leilao: {name} passaria do limite ({spent + take * row['price']} > {max_total}) - parei")
                    break
                self._click(self.page.locator(S.MARKET_SELL_ROWS).first.locator(S.MARKET_TAKE))
                if not self._wait(lambda: self._visible(S.MARKET_ACCEPT), 4):
                    raise GameError("o formulario de compra nao abriu")
                terms = self.page.locator(S.MARKET_ACCEPT_TERMS).first.inner_text()
                if imbuing.number(terms.split("cada")[0]) != row["price"]:
                    raise GameError(f"preco mudou na tela: {terms}")
                self.page.locator(S.MARKET_AMOUNT).first.fill(str(take))
                time.sleep(0.3)
                total = imbuing.number(self.page.locator(S.MARKET_TOTAL).first.inner_text())
                if total != take * row["price"]:
                    self._click(S.MARKET_DISMISS, 2000)
                    raise GameError(f"total inesperado: {total} (esperado {take * row['price']})")
                before = set(self._toasts())
                self._click(S.MARKET_CONFIRM, 3000)
                done = lambda: any(t not in before and "bought" in t and name.casefold() in t.casefold() for t in self._toasts())
                if not self._wait(done, 6):
                    raise GameError(f"o jogo nao confirmou a compra de {take}x {name}")
                time.sleep(0.6)
                bought += take
                spent += total
                self.log(f"[{self.name}] leilao: comprei {take}x {name} a {row['price']} ({total} gold)")
        finally:
            self._market_close()
        return bought, spent

    def screenshot_state(self):
        return json.dumps(self.page.evaluate(READ_JS, _SEL), ensure_ascii=False)
