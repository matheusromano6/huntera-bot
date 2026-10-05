"""Catalogo das caçadas do Huntera (huntera_bot/data/hunts.json, baixado do proprio jogo).
A ORDEM do catalogo e' a progressao do jogo (Rat Cellars = 1a caçada) e e' usada como
"nivel" pra ordenar a escolha do Bestiary em cadeia."""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hunts.json")


def load(path=PATH):
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)["hunts"]
    except (OSError, ValueError, KeyError):
        return []


def search(hunts, text):
    """Filtra por nome da caçada OU de uma criatura (sem diferenciar maiusculas)."""
    text = (text or "").strip().casefold()
    if not text:
        return list(hunts)
    return [h for h in hunts if text in h["name"].casefold() or any(text in c.casefold() for c in h["creatures"])]


def by_name(hunts, name):
    return next((h for h in hunts if h["name"].casefold() == (name or "").casefold()), None)


def sort_chain(chain, hunts):
    """Ordena uma cadeia ([{'name', 'tier'?}]) pela progressao do jogo."""
    order = {h["name"].casefold(): h["order"] for h in hunts}
    return sorted(chain, key=lambda item: order.get(item["name"].casefold(), 10_000))
