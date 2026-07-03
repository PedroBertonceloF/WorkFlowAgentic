"""
Guarda um historico de links ja enviados na newsletter, pra evitar repetir o
mesmo item em edicoes seguidas enquanto ele ainda estiver dentro da janela
de "recente" (48h) das buscas.

Arquivo: data/sent_links.json -> {"<link>": "<data ISO em que foi enviado>"}
Mantido no git (nao e segredo) pra o GitHub Actions poder ler/atualizar.
"""

import json
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "data" / "sent_links.json"
RETENTION_DAYS = 7


def load_sent_links() -> dict[str, str]:
    if not LOG_PATH.exists():
        return {}
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def prune_old(sent: dict[str, str], today: date, days: int = RETENTION_DAYS) -> dict[str, str]:
    cutoff = today - timedelta(days=days)
    pruned = {}
    for link, sent_date_str in sent.items():
        try:
            sent_date = date.fromisoformat(sent_date_str)
        except ValueError:
            continue
        if sent_date >= cutoff:
            pruned[link] = sent_date_str
    return pruned


def mark_sent(sent: dict[str, str], links: list[str], today: date) -> dict[str, str]:
    for link in links:
        sent[link] = today.isoformat()
    return sent


def save_sent_links(sent: dict[str, str]) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    LOG_PATH.write_text(json.dumps(sent, indent=2, ensure_ascii=False), encoding="utf-8")
