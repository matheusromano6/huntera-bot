"""Uma conta do Huntera = uma pagina do jogo no IdleDeck. Le o estado (uma
chamada so') e executa as acoes (sair, vender, despachar, iniciar caçada)."""
import json
import re
import time
from dataclasses import dataclass, field

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
  };
}"""

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

    @property
    def bestiary_complete(self):
        return bool(self.bestiary_total) and self.bestiary_done == self.bestiary_total


def parse_state(raw):
    """Converte o que a pagina devolveu em State (separado pra testar sem jogo)."""
    st = State(name=raw.get("name", ""), vocation=raw.get("vocation", ""))
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
    return st


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
        for window, closer in ((S.QS_WINDOW, S.QS_CANCEL), (S.HUNT_WINDOW, S.HUNT_CLOSE)):
            try:
                if self._visible(window):
                    self.page.click(closer, timeout=3000)
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
            self.page.click(S.LEAVE_BTN, timeout=3000)
        return self._wait(lambda: self.read().phase == "city", timeout, 0.7)

    def _open_quick_sell(self, via):
        if self._visible(S.QS_WINDOW):
            return
        # CONFIRMADO ao vivo: o botao fica DESABILITADO quando nao ha nada vendavel na mochila
        enabled = self.page.evaluate(
            "(s) => { const e = document.querySelector(s); return !!e && !e.disabled }", via)
        if not enabled:
            raise NothingToSell()
        self.page.click(via, timeout=3000)
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
                    self.page.locator(S.QS_ROW).nth(row["i"]).click(timeout=3000)
                continue
            if mark_all and not row["marked"]:
                self.page.locator(S.QS_ROW).nth(row["i"]).click(timeout=3000)
        time.sleep(0.4)
        state = self.page.evaluate(
            """(S) => { const c = document.querySelector(S.QS_CONFIRM);
                return {marked: document.querySelectorAll(S.QS_ROW + '.marked').length, text: c ? c.innerText.trim() : '', disabled: c ? !!c.disabled : true}; }""", _SEL)
        if state["marked"] == 0 or state["disabled"]:
            self.page.click(S.QS_CANCEL, timeout=3000)
            self._wait(lambda: not self._visible(S.QS_WINDOW), 4)
            return 0, "", []
        sold = [f"{r['name']} ({r['detail']})" for r in rows
                if r["name"].lower() not in keep and (r["marked"] or mark_all)]
        self.page.click(S.QS_CONFIRM, timeout=3000)
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
        self.page.click(S.START_NAV, timeout=3000)
        if not self._wait(lambda: self._visible(S.ORGANIZE) or self._visible(S.HUNT_WINDOW), 5):
            raise GameError("janela de caçada nao abriu")
        time.sleep(0.6)
        if self._visible(S.ORGANIZE):
            self.page.click(S.ORGANIZE, timeout=3000)
        entry = self.page.locator(S.HUNT_ENTRY.format(name=hunt))
        if not self._wait(lambda: entry.count() > 0, 6):
            raise GameError(f"hunt '{hunt}' nao encontrada na lista")
        entry.scroll_into_view_if_needed(timeout=3000)
        entry.click(timeout=3000)
        time.sleep(0.8)
        if tier:
            tiers = self.page.locator(S.HUNT_TIER).filter(has_text=tier)
            if tiers.count() == 0:
                raise GameError(f"pull '{tier}' nao existe em '{hunt}'")
            selected = "selected" in (tiers.first.get_attribute("class") or "")
            if not selected:
                tiers.first.click(timeout=3000)
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
            self.page.click(button, timeout=3000)
            time.sleep(0.8)
        except Exception:
            self.close_windows()
            raise

    def start_training(self, skill):
        """Caçar > Treino > habilidade > 'Treino online' > Iniciar treino. A conta TEM que estar na cidade
        (o botao fica desabilitado em caçada)."""
        try:
            self.page.click(S.START_NAV, timeout=3000)
            if not self._wait(lambda: self._visible(S.HUNT_WINDOW), 6):
                raise GameError("janela de caçada nao abriu")
            time.sleep(0.6)
            self.page.locator(S.HUNT_TAB).filter(has_text="Treino").first.click(timeout=3000)
            time.sleep(0.9)
            button = self.page.locator(S.TRAIN_SKILL).filter(has_text=skill)
            if button.count() == 0:
                raise GameError(f"habilidade '{skill}' nao encontrada")
            if "active" not in (button.first.get_attribute("class") or ""):
                button.first.click(timeout=3000)
                time.sleep(0.6)
            start = self.page.locator(S.TRAIN_MODE).filter(has_text="Treino online").locator(S.TRAIN_START)
            if start.count() == 0 or not start.first.is_enabled():
                reason = (start.first.get_attribute("title") if start.count() else "") or "botao indisponivel"
                raise GameError(f"treino online indisponivel: {reason}")
            start.first.click(timeout=3000)
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
            self.page.click(S.START_NAV, timeout=3000)
            if not self._wait(lambda: self._visible(S.HUNT_WINDOW), 6):
                return None
            time.sleep(0.5)
            self.page.locator(S.HUNT_TAB).filter(has_text="Treino").first.click(timeout=3000)
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
        try:
            self.page.click(S.TRAINING_CANCEL, timeout=2500)
        except Exception:
            # CONFIRMADO ao vivo: a janela da party pode ficar POR CIMA do painel de treino e
            # interceptar o clique real; o botao so' escuta 'click' - dispara direto nele.
            self.page.locator(S.TRAINING_CANCEL).first.dispatch_event("click")
        ok = self._wait(lambda: not self._visible(S.TRAINING), timeout)
        if ok:
            self.log(f"[{self.name}] treino cancelado")
        return ok

    def screenshot_state(self):
        return json.dumps(self.page.evaluate(READ_JS, _SEL), ensure_ascii=False)
