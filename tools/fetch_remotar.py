"""
Busca vagas remotas brasileiras na API publica do Remotar (remotar.com.br),
filtrando pela area de dados (categoria "Data Science / Analytics" ou
palavras-chave no titulo) e priorizando estagio/junior.

A API pagina de 50 em 50 (`?page=N`) e traz categoria, empresa, descricao e
data de publicacao. Nao ha campo de senioridade, entao ela e inferida do
titulo (estagio/estagiario -> estagio; junior/jr -> junior).

Uso como biblioteca:
    from fetch_remotar import fetch_data_jobs
    jobs = fetch_data_jobs(hours=168, max_items=5)

Uso via CLI (debug):
    python fetch_remotar.py
"""

import json
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://api.remotar.com.br/jobs?page={page}"
JOB_URL = "https://remotar.com.br/job/{id}"
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"

DATA_CATEGORY = "data science / analytics"
DATA_TITLE_PATTERN = re.compile(
    r"\b(dados|data|analytics|bi|business intelligence|power ?bi|"
    r"machine learning|ciencia de dados|sql|etl|dashboards?)\b"
)
# Igual ao fetch_programathor: quem esta comecando primeiro.
LEVEL_RANK = {"estagio": 0, "junior": 1, "": 2}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _extract_level(title: str) -> str:
    norm = _normalize(title)
    if "estagi" in norm:  # estagio, estagiario(a)
        return "estagio"
    if "junior" in norm or re.search(r"\bjr\b", norm):
        return "junior"
    return ""


def fetch_data_jobs(hours: int = 168, max_items: int = 5, pages: int = 2,
                    levels: tuple = ("estagio", "junior")) -> list[dict]:
    """Vagas da area de dados publicadas nas ultimas `hours` horas, apenas dos
    niveis em `levels`, ordenadas por nivel (estagio primeiro) e recencia."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = []
    for page in range(1, pages + 1):
        req = urllib.request.Request(API_URL.format(page=page),
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            entries = json.loads(resp.read()).get("data", [])
        for entry in entries:
            if entry.get("expired"):
                continue
            try:
                pub_date = datetime.fromisoformat(entry.get("createdAt", ""))
            except ValueError:
                continue
            if pub_date < cutoff:
                continue
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            categories = {
                ((c.get("category") or {}).get("name") or "").lower()
                for c in entry.get("jobCategories") or []
            }
            if DATA_CATEGORY not in categories and not DATA_TITLE_PATTERN.search(_normalize(title)):
                continue
            level = _extract_level(title)
            if level not in levels:
                continue
            link = (entry.get("externalLink") if entry.get("isExternalLink")
                    else JOB_URL.format(id=entry["id"]))
            company = (entry.get("company") or {}).get("name") or "Remotar"
            jobs.append({
                "title": f"{title} — {company}",
                "link": link,
                "source": "Remotar",
                "level": level,
                "pub_date": pub_date,
                "description": entry.get("subtitle") or "",
                "_rank": LEVEL_RANK.get(level, 2),
            })

    jobs.sort(key=lambda j: (j["_rank"], -j["pub_date"].timestamp()))
    for j in jobs:
        del j["_rank"]
    return jobs[:max_items]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for job in fetch_data_jobs(levels=("estagio", "junior", "")):
        print(f"- [{job['level'] or '?'}] {job['title']} -> {job['link']}")
