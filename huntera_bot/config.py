"""Configuracao do bot (config.json ao lado do projeto). O que nao estiver no
arquivo usa o padrao daqui; arquivo novo e' criado com os padroes."""
import copy
import json
import os

# habilidades que a tela de treino do jogo oferece (confirmado: as 6 para Knight e Druid)
ALL_SKILLS = ["Club Fighting", "Sword Fighting", "Axe Fighting", "Distance Fighting", "Shielding", "Magic Level"]

DEFAULTS = {
    # onde o IdleDeck esta com a depuracao remota ligada (o bot so' se conecta)
    "cdp_url": "http://127.0.0.1:9224",
    "poll_seconds": 3,
    # sai da hunt pra vender quando QUALQUER conta do time chegar nisso (% da capacidade usada)
    "capacity_pct": 90,
    "dispatch": {
        "enabled": True,
        # usa o 'Despachar loot' (1x por hora) quando a capacidade passar disso
        "min_cap_pct": 40,
    },
    "sell": {
        # marca TUDO que a venda rapida lista (so' mochila; a bolsa nao aparece la)
        "mark_all": True,
        # nomes de itens que NUNCA devem ser marcados (os ja marcados antes continuam)
        "keep": [],
    },
    # stamina (horas de hunt gratuitas): quando QUALQUER conta do time chegar em 'stamina_minutes'
    # todo o time vai pra cidade e cada conta inicia o treino da habilidade da sua vocacao
    "training": {
        "enabled": True,
        "stamina_minutes": 15,
        # volta pra caçada quando TODAS as contas do time chegarem nisso (600 = 10h)
        "resume_stamina_minutes": 600,
        # escolha por personagem (nome em minusculas -> habilidade); vazio = padrao da vocacao abaixo
        "by_name": {},
        "skills": {
            "knight": "Axe Fighting",
            "paladin": "Distance Fighting",
            "druid": "Magic Level",
            "sorcerer": "Magic Level",
        },
    },
    # quando o Bestiary da hunt fecha (N/N em todas as contas do time) vai pra proxima da lista
    "bestiary_chain": {
        "enabled": False,
        "hunts": [],          # ex: [{"name": "Rat Cellars"}, {"name": "Spider Nest", "tier": "Ousado"}]
    },
    # 'tier' por hunt: se vazio, o jogo ja vem com o ultimo pull salvo e o bot nao mexe
    "hunt_tiers": {},         # ex: {"Vampire Crypt": "Ousado"}
    # esperas (segundos)
    "timeouts": {"leave": 45, "start": 75, "window": 8},
    # conta parada na cidade (sem treino) por mais disso -> reinicia o treino ou volta pra hunt
    "idle_city_seconds": 90,
    # depois de um ciclo (ok ou falho) fica esse tempo sem tentar de novo no mesmo time
    "cooldown_ok_seconds": 120,
    "cooldown_fail_seconds": 600,
}


def default_skill(training_cfg, vocation):
    """Habilidade padrao da vocacao ('Elite Knight' -> knight -> Axe Fighting) ou None."""
    v = (vocation or "").casefold()
    for key, skill in training_cfg["skills"].items():
        if key in v:
            return skill
    return None


def _merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path):
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    else:
        save(path, DEFAULTS)
    return _merge(DEFAULTS, data)


def save(path, config):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
