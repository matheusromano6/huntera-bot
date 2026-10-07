"""Memoria pequena em disco (memory.json): em qual hunt cada time estava quando foi pro treino,
pra voltar pra ela mesmo se o bot for fechado e aberto de novo."""
import json
import os


def key(names):
    return ",".join(sorted(n.casefold() for n in names))


class Memory:
    def __init__(self, path=None):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as file:
                    self.data = json.load(file)
            except (OSError, ValueError):
                self.data = {}

    # opcoes de treino que o jogo oferece a cada conta (lidas pelo bot)
    def get_options(self, name):
        return (self.data.get("options") or {}).get(name.casefold())

    def set_options(self, name, vocation, skills):
        self.data.setdefault("options", {})[name.casefold()] = {"name": name, "vocation": vocation, "skills": list(skills)}
        self._save()

    def all_options(self):
        return dict(self.data.get("options") or {})

    # imbuements: o que o bot leu do jogo (a interface mostra isso mesmo com as contas em caçada)
    def imbue(self):
        return self.data.setdefault("imbue", {"items": {}, "equipment": {}, "have": {}, "prices": {}})

    def set_imbue(self, section, key_, value):
        self.imbue().setdefault(section, {})[key_] = value
        self._save()

    # ultima caçada de cada time (sobrevive a fechar o bot e ao server save)
    def get_last_hunt(self, names):
        return (self.data.get("last_hunt") or {}).get(key(names))

    def set_last_hunt(self, names, hunt, tier):
        value = {"hunt": hunt, "tier": tier}
        if self.get_last_hunt(names) != value:
            self.data.setdefault("last_hunt", {})[key(names)] = value
            self._save()

    def get(self, names):
        return self.data.get(key(names))

    def set(self, names, value):
        self.data[key(names)] = value
        self._save()

    def clear(self, names):
        self.data.pop(key(names), None)
        self._save()

    def _save(self):
        if not self.path:
            return
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
