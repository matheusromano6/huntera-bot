import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from huntera_bot import selectors as S
from huntera_bot.account import Account


class FakeRow:
    def __init__(self, page, i):
        self.page, self.i = page, i

    def click(self, timeout=0):
        row = self.page.rows[self.i]
        row["marked"] = not row["marked"]


class FakeLocator:
    def __init__(self, page):
        self.page = page

    def nth(self, i):
        return FakeRow(self.page, i)


class FakePage:
    """Janela de venda falsa: botao habilitavel, linhas marcaveis, confirmar/cancelar."""

    def __init__(self, rows, button_enabled=True):
        self.rows = rows
        self.button_enabled = button_enabled
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
        return FakeLocator(self)

    def click(self, selector, timeout=0):
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

    def test_dispatch_uses_the_same_flow(self):
        page = FakePage(rows(("cheese", False)))
        self.assertEqual(self.acc(page).dispatch_loot(mark_all=True), 1)
        self.assertEqual(page.sold, ["cheese"])


if __name__ == "__main__":
    unittest.main()
