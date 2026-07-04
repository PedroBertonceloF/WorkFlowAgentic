"""
Busca vagas tech brasileiras no RSS gratuito do ProgramaThor.

Diferente do Remote OK (vagas remotas internacionais), o ProgramaThor lista
vagas do Brasil e marca a senioridade no titulo (#Estagio, #Junior, #Pleno,
#Senior). Aqui priorizamos estagio/junior/pleno, que e o que interessa pra
quem esta comecando.

Uso como biblioteca:
    from fetch_programathor import fetch_recent_br_jobs
    jobs = fetch_recent_br_jobs(hours=72, max_items=5)

Uso via CLI (debug):
    python fetch_programathor.py
"""

import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RSS_URL = "https://programathor.com.br/jobs.rss"
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"

# Ordem de prioridade (quem esta comecando primeiro). Nivel desconhecido fica
# antes de senior. Usado pra ordenar, nao pra excluir.
LEVEL_RANK = {"estagio": 0, "junior": 1, "pleno": 2, "": 3, "senior": 4}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower()


def _extract_level(title: str) -> str:
    """Devolve a senioridade encontrada no titulo (#Estagio, #Junior...) ou ''."""
    norm = _normalize(title)
    for level in ("estagio", "junior", "pleno", "senior"):
        if f"#{level}" in norm or level in norm:
            return level
    return ""


def _clean_title(title: str) -> str:
    """Remove o prefixo 'Vaga:' e o bloco de tags (#Senioridade #Area...) que
    fica no fim do titulo. Corta a partir do primeiro ' #' pra lidar com tags
    de varias palavras (#Full Stack) sem quebrar nomes como 'C#'."""
    title = re.sub(r"^\s*Vaga:\s*", "", title)
    title = re.sub(r"\s+#.*$", "", title)
    return title.strip()


def fetch_recent_br_jobs(hours: int = 120, max_items: int = 5) -> list[dict]:
    """Vagas tech BR das ultimas `hours` horas, ordenadas priorizando
    estagio/junior/pleno (sem excluir senior), e depois pela mais recente."""
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = []
    for item in root.iter("item"):
        raw_title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date_raw = item.findtext("pubDate", "")
        if not raw_title or not link:
            continue
        try:
            pub_date = parsedate_to_datetime(pub_date_raw)
        except (TypeError, ValueError):
            continue
        if pub_date < cutoff:
            continue

        level = _extract_level(raw_title)
        jobs.append({
            "title": _clean_title(raw_title),
            "link": link,
            "source": "ProgramaThor",
            "level": level,  # '' | estagio | junior | pleno | senior (vira selo no e-mail)
            "pub_date": pub_date,
            "_rank": LEVEL_RANK.get(level, 3),
        })

    jobs.sort(key=lambda j: (j["_rank"], -j["pub_date"].timestamp()))
    for j in jobs:
        del j["_rank"]
    return jobs[:max_items]


if __name__ == "__main__":
    for job in fetch_recent_br_jobs():
        print(f"- {job['title']} ({job['source']}) -> {job['link']}")
