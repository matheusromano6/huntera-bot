"""Conexao com o IdleDeck (que precisa estar aberto com a depuracao remota).
Cada conta do Huntera e' uma pagina 'huntera.com.br' na mesma conexao; paginas
de OUTROS jogos nunca sao tocadas."""
import urllib.request

from playwright.sync_api import sync_playwright

from .account import Account

GAME_HOST = "huntera.com.br"


def port_open(cdp_url, timeout=2):
    try:
        urllib.request.urlopen(f"{cdp_url}/json/version", timeout=timeout)
        return True
    except Exception:
        return False


class Pool:
    """Mantem a conexao e a lista de contas (paginas do Huntera)."""

    def __init__(self, cdp_url, log=print):
        self.cdp_url = cdp_url
        self.log = log
        self._pw = None
        self.browser = None
        self._accounts = {}      # id(page) -> Account

    def open(self):
        if not port_open(self.cdp_url):
            raise RuntimeError(f"IdleDeck sem depuracao remota em {self.cdp_url} (abra o IdleDeck com a porta ligada)")
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(self.cdp_url)

    def close(self):
        try:
            if self._pw:
                self._pw.stop()
        finally:
            self._pw = None
            self.browser = None

    def refresh(self):
        """Reencontra as paginas do Huntera (conta aberta/fechada depois do inicio)."""
        pages = [p for c in self.browser.contexts for p in c.pages if GAME_HOST in p.url]
        known = {}
        for page in pages:
            acc = self._accounts.get(id(page)) or Account(page, self.log)
            if acc.page is page:
                known[id(page)] = acc
        gone = set(self._accounts) - set(known)
        new = set(known) - set(self._accounts)
        self._accounts = known
        if gone or new:
            self.log(f"paginas do Huntera: {len(known)} (novas {len(new)}, fechadas {len(gone)})")
        # nomes ficam so' depois da 1a leitura
        for acc in known.values():
            if not acc.name:
                try:
                    acc.read()
                except Exception:
                    pass
        return list(known.values())
