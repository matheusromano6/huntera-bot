"""Imbuements: catalogo (data/imbuements.json, lido do santuario do jogo), custos e o que falta fazer.
So' logica (sem jogo) pra testar; quem le/clica e' account.py e quem decide quando e' engine.py.

Regras (mapeadas ao vivo):
- Materiais ACUMULAM: Intricate = mat1+mat2, Powerful = mat1+mat2+mat3. Taxa 5k/30k/200k.
- Protecao (+10k/+30k/+50k) = 100% de sucesso; sem ela 90/70/50% e a falha consome gold+materiais.
  AUTOMATICA: liga quando o custo esperado sem ela ((taxa+materiais)/chance) passa do custo com ela.
- Mesmo imbuement nao repete no item; slot ocupado so' sai com Remover (15k, sem reembolso).
- Dura 20h de caçada. Plano do usuario: por conta e item, lista de {imbuement, tier, renew}."""
import json
import os
import re

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "imbuements.json")
TIERS = ["Basic", "Intricate", "Powerful"]
REMOVE_COST = 15_000           # 'Remover — 15.000 gp' (lido no jogo; o bot usa o valor da tela quando abre)
NONE = "Não imbuir"


# nomes em portugues so' para a interface (o jogo e o plano usam os nomes em ingles)
LABELS = {
    "Void": "Roubo de mana", "Vampirism": "Roubo de vida", "Strike": "Crítico", "Epiphany": "Magic level",
    "Slash": "Espada", "Chop": "Machado", "Bash": "Clava", "Precision": "Distância", "Blockade": "Escudo",
    "Scorch": "Dano de fogo", "Venom": "Dano de terra", "Frost": "Dano de gelo", "Electrify": "Dano de energia",
    "Reap": "Dano de morte", "Lich Shroud": "Proteção morte", "Snake Skin": "Proteção terra",
    "Dragon Hide": "Proteção fogo", "Quara Scale": "Proteção gelo", "Cloud Fabric": "Proteção energia",
    "Demon Presence": "Proteção sagrado", "Swiftness": "Velocidade", "Featherweight": "Capacidade",
}
TIER_LABELS = {"Basic": "Básico", "Intricate": "Intrincado", "Powerful": "Poderoso"}


def label(family):
    """'Strike' -> 'Crítico (Strike)' (o nome do jogo fica entre parenteses)."""
    return f"{LABELS[family]} ({family})" if family in LABELS else family


def label_active(text):
    """'Powerful Strike' -> 'Crítico Poderoso'."""
    tier, family = split_active(text)
    return f"{LABELS.get(family, family)} {TIER_LABELS[tier]}" if tier else text


def load(path=PATH):
    """{nome: {'name', 'desc', 'seen_on', 'tiers': {tier: {gold, success_pct, protection_gold, gold_tokens, materials}}}}"""
    try:
        with open(path, encoding="utf-8") as file:
            return {e["name"]: e for e in json.load(file)["imbuements"]}
    except (OSError, ValueError, KeyError):
        return {}


def known_items(catalog):
    """{item: {tier: [imbuements]}} do que ja foi visto no santuario (o bot completa lendo o jogo)."""
    out = {}
    for imb in catalog.values():
        for item in imb.get("seen_on", []):
            for tier in TIERS:
                out.setdefault(item, {t: [] for t in TIERS})[tier].append(imb["name"])
    return out


def number(text):
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def split_active(text):
    """'Basic Demon Presence' -> ('Basic', 'Demon Presence'); qualquer outra coisa -> (None, texto)."""
    text = (text or "").strip()
    tier, _, family = text.partition(" ")
    return (tier, family) if tier in TIERS and family else (None, text)


_TIP = re.compile(r"\((\d+)\s*(hora|minuto|h\b|m\b)", re.I)


def minutes(text):
    """'20h 0m' / '45m' (santuario) ou '(20 horas)' / '(30 minutos)' (tooltip) -> minutos. None se nao achou."""
    text = text or ""
    tip = _TIP.search(text)
    if tip:
        value = int(tip.group(1))
        return value * 60 if tip.group(2).lower().startswith("h") else value
    m = re.search(r"(\d+)\s*h\s*(\d+)\s*m|(\d+)\s*h|(\d+)\s*m", text)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1)) * 60 + int(m.group(2))
    if m.group(3):
        return int(m.group(3)) * 60
    return int(m.group(4))


def walk(rows, qty):
    """Compra 'qty' das ofertas de venda (ja ordenadas da mais barata). -> (custo, faltou)."""
    left, cost = qty, 0
    for row in rows or []:
        if left <= 0:
            break
        take = min(left, row["qty"])
        cost += take * row["price"]
        left -= take
    return cost, max(left, 0)


def protect_auto(tier_info, materials_value):
    """Liga a protecao quando o custo esperado sem ela e' maior (tentativas ate' acertar = 1/chance)."""
    fee, prot, chance = tier_info["gold"], tier_info["protection_gold"], tier_info["success_pct"] / 100
    if chance >= 1:
        return False
    return (fee + materials_value) / chance > fee + prot + materials_value


def materials(catalog, family, tier):
    return catalog[family]["tiers"][tier]["materials"]


def entry_cost(catalog, family, tier, have=None, prices=None, use_tokens=False, tokens_have=0):
    """Custo de UM imbuement. have = {material: qtd que a conta tem}; prices = {material: [ofertas]}.
    Retorna dict: fee, protect, protection, pay ('tokens'|'materials'), buy {material: qtd}, buy_cost,
    no_stock [materiais sem estoque suficiente], unknown [materiais sem preco lido], total (gold)."""
    info = catalog[family]["tiers"][tier]
    have, prices = have or {}, prices or {}
    out = {"fee": info["gold"], "protect": False, "protection": 0, "pay": "materials", "buy": {},
           "buy_cost": 0, "no_stock": [], "unknown": [], "tokens": info["gold_tokens"]}
    value = 0                      # valor do que a tentativa consome (pra decidir a protecao)
    if use_tokens and tokens_have >= info["gold_tokens"]:
        out["pay"] = "tokens"
    else:
        for mat in info["materials"]:
            name, need = mat["name"], mat["count"]
            rows = prices.get(name)
            if rows is None:
                out["unknown"].append(name)
            else:
                value += walk(rows, need)[0]
            missing = max(0, need - int(have.get(name, 0)))
            if missing:
                out["buy"][name] = missing
                if rows is not None:
                    cost, short = walk(rows, missing)
                    out["buy_cost"] += cost
                    if short:
                        out["no_stock"].append(name)
    out["protect"] = protect_auto(info, value)
    out["protection"] = info["protection_gold"] if out["protect"] else 0
    out["total"] = out["fee"] + out["protection"] + out["buy_cost"]
    return out


def plan_for(cfg, name):
    """Plano de uma conta: {item: [{'imbuement', 'tier', 'renew', 'done'?} | None, ...]}"""
    return ((cfg.get("imbuements") or {}).get("plan") or {}).get((name or "").casefold(), {})


def done_key(item, family):
    return f"{item}|{family}"


def pending(plan, equipment, early_minutes=None, done=()):
    """O que fazer numa conta. equipment = {item: [{'active': 'Basic X' | None, 'minutes': int | None}, ...]}.
    -> [{'item', 'imbuement', 'tier', 'renew', 'kind': 'apply' | 'early'}]
    'apply': o imbuement planejado nao esta no item (primeira vez, ou acabou e 'renew'); so' ate' o numero
    de slots livres. 'early': esta ativo com menos de early_minutes e 'renew' (so' quando ja estiver na cidade).
    done = chaves done_key() do que era pra fazer UMA vez (sem 'renew') e ja foi feito."""
    tasks = []
    for item, entries in (plan or {}).items():
        slots = equipment.get(item)
        if slots is None:                  # item nao esta equipado agora
            continue
        active = {split_active(s["active"])[1]: s for s in slots if s.get("active")}
        free = sum(1 for s in slots if not s.get("active"))
        for entry in entries or []:
            if not entry or entry.get("imbuement") in (None, "", NONE):
                continue
            family = entry["imbuement"]
            slot = active.get(family)
            base = {"item": item, "imbuement": family, "tier": entry.get("tier") or TIERS[0], "renew": bool(entry.get("renew"))}
            if slot is None:
                if not entry.get("renew") and done_key(item, family) in done:
                    continue               # era pra fazer uma vez so' e ja foi feito
                if free > 0:
                    free -= 1
                    tasks.append({**base, "kind": "apply"})
            elif (early_minutes is not None and entry.get("renew") and slot.get("minutes") is not None
                  and slot["minutes"] < early_minutes):
                tasks.append({**base, "kind": "early"})
    return tasks
