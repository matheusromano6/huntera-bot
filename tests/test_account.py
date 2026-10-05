import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from huntera_bot import selectors as S
from huntera_bot.account import Account


class FakeRow:
    def __init__(self, page, i):
        self.page, self.i = page, i

    @property
    def first(self):
        return self

    def click(self, timeout=0):
        row = self.page.rows[self.i]
        row["marked"] = not row["marked"]

    dispatch_event = lambda self, name: self.click()


class FakeLocator:
    """Locator de seletor: clicar delega pro page.click; dispatch_event e' o clique direto (sem checar cobertura)."""

    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    def nth(self, i):
        return FakeRow(self.page, i)

    def click(self, timeout=0):
        self.page.click(self.selector, timeout)

    def dispatch_event(self, name):
        self.page.dispatched.append(self.selector)
        self.page.effect(self.selector)


class FakePage:
    """Janela de venda falsa: botao habilitavel, linhas marcaveis, confirmar/cancelar, botoes 'cobertos'."""

    def __init__(self, rows, button_enabled=True, covered=(), broken=None):
        self.rows = rows
        self.button_enabled = button_enabled
        self.covered = set(covered)          # seletores que a janela da party cobre ('intercepts pointer events')
        self.broken = broken or {}           # seletor -> mensagem de erro (ex: invisivel)
        self.dispatched = []
        self.window = False
        self.sold = None
        self.cancelled = False

    def evaluate(self, js, arg=None):
        if "!!e && !e.disabled" in js:
            return self.button_enabled
        if "getBoundingClientRect().width > 0 }" in js and arg == S.QS_WINDOW:
            return self.window
        if "detail" in js:
            return [{"i": i, "name": r["name"], "detail": r["detail"], "marked": r["marked"]} for i, r in enumerate(self.rows)]
        if "marked:" in js and "text:" in js:
            n = sum(1 for r in self.rows if r["marked"])
            return {"marked": n, "text": f"Vender por {n} gp", "disabled": n == 0}
        raise AssertionError("js inesperado: " + js[:60])

    def locator(self, selector):
        return FakeLocator(self, selector)

    def click(self, selector, timeout=0):
        if selector in self.broken:
            raise RuntimeError(self.broken[selector])
        if selector in self.covered:
            raise RuntimeError("<span>Party</span> from <section class=party-window> subtree intercepts pointer events")
        self.effect(selector)

    def effect(self, selector):
        if selector in (S.QUICK_SELL_BTN, S.DISPATCH_BTN):
            self.window = True
        elif selector == S.QS_CONFIRM:
            self.sold = [r["name"] for r in self.rows if r["marked"]]
            self.window = False
        elif selector == S.QS_CANCEL:
            self.cancelled = True
            self.window = False


def rows(*specs):
    return [{"name": n, "detail": f"1 x {n}", "marked": m} for n, m in specs]


class SellTests(unittest.TestCase):
    def acc(self, page):
        a = Account(page, log=lambda m: None)
        a.name = "TESTE"
        a._wait = lambda pred, seconds, step=0.4: pred()
        return a

    def test_disabled_button_means_nothing_to_sell(self):
        page = FakePage(rows(), button_enabled=False)
        self.assertEqual(self.acc(page).sell_all(), 0)
        self.assertFalse(page.window)

    def test_marks_everything_in_the_backpack(self):
        page = FakePage(rows(("cheese", True), ("might ring", False), ("stone skin amulet", False)))
        n = self.acc(page).sell_all(mark_all=True)
        self.assertEqual(n, 3)
        self.assertEqual(sorted(page.sold), ["cheese", "might ring", "stone skin amulet"])

    def test_keep_list_is_never_sold_and_is_unmarked(self):
        page = FakePage(rows(("cheese", True), ("might ring", True), ("stone skin amulet", False)))
        self.acc(page).sell_all(keep=["Might Ring"], mark_all=True)
        self.assertEqual(sorted(page.sold), ["cheese", "stone skin amulet"])

    def test_nothing_marked_cancels(self):
        page = FakePage(rows(("might ring", False)))
        self.assertEqual(self.acc(page).sell_all(mark_all=False), 0)
        self.assertTrue(page.cancelled)
        self.assertIsNone(page.sold)

    def test_covered_button_is_clicked_directly(self):
        """A janela da party por cima do botao (visto ao vivo) nao pode impedir a venda."""
        page = FakePage(rows(("cheese", True)), covered={S.DISPATCH_BTN, S.QS_CONFIRM})
        self.assertEqual(self.acc(page).dispatch_loot(), 1)
        self.assertEqual(page.sold, ["cheese"])
        self.assertEqual(sorted(page.dispatched), sorted([S.DISPATCH_BTN, S.QS_CONFIRM]))

    def test_other_click_errors_are_not_swallowed(self):
        page = FakePage(rows(("cheese", True)), broken={S.QS_CONFIRM: "element is not visible"})
        with self.assertRaises(RuntimeError):
            self.acc(page).sell_all()
        self.assertEqual(page.dispatched, [])                 # sem 'intercepts': nao forca o clique

    def test_dispatch_uses_the_same_flow(self):
        page = FakePage(rows(("cheese", False)))
        self.assertEqual(self.acc(page).dispatch_loot(mark_all=True), 1)
        self.assertEqual(page.sold, ["cheese"])


if __name__ == "__main__":
    unittest.main()
