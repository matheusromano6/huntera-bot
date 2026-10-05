"""python -m huntera_bot [--status] [--config caminho]

  --status   le as contas e mostra o estado (nao faz nada no jogo)
"""
import argparse
import logging
import os
import sys
import threading
import time

from . import VERSION, config
from .engine import Engine, build_groups
from .memory import Memory
from .idledeck import Pool
from .paths import app_dir

ROOT = app_dir()


def make_logger():
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    path = os.path.join(ROOT, "logs", f"huntera_{time.strftime('%Y-%m-%d')}.log")
    logger = logging.getLogger("huntera")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S")
    for handler in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger.info


def show_status(pool, log):
    from .engine import Engine
    accounts = pool.refresh()
    engine = Engine(accounts, config.DEFAULTS, log)
    states = engine.read_all()
    for st in states.values():
        cap = "?" if st.cap_pct is None else f"{st.cap_pct:.1f}% ({st.cap_used:.0f}/{st.cap_max:.0f} oz)"
        stam = "?" if st.stamina_min is None else f"{st.stamina_min // 60}:{st.stamina_min % 60:02d}h"
        print(f"- {st.name} ({st.vocation}) | {st.phase} | cap {cap} | stamina {stam} | hunt '{st.hunt_name}' bestiary {st.bestiary_done}/{st.bestiary_total}"
              f" | despacho {'PRONTO' if st.dispatch_ready else st.dispatch_text or '-'} | party {st.party_names} lider '{st.leader_name}'")
    for group in build_groups([a for a in accounts if a.name in states], states):
        print(f"  grupo: {group.label} ({'time' if group.is_team else 'solo'}; lider: {group.leader.name if group.leader else '-'})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="huntera_bot")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--status", action="store_true", help="so' le e mostra o estado das contas")
    args = ap.parse_args(argv)

    log = make_logger()
    cfg = config.load(args.config)
    pool = Pool(cfg["cdp_url"], log)
    pool.open()
    try:
        if args.status:
            show_status(pool, log)
            return 0
        log(f"huntera_bot {VERSION}")
        engine = Engine(pool.refresh(), cfg, log, refresh=pool.refresh, memory=Memory(os.path.join(ROOT, "memory.json")))
        stop = threading.Event()
        try:
            engine.run(stop)
        except KeyboardInterrupt:
            stop.set()
            log("interrompido")
        return 0
    finally:
        pool.close()


if __name__ == "__main__":
    sys.exit(main())
