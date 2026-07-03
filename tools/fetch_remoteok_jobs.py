"""
Busca vagas remotas de tecnologia na API publica e gratuita do Remote OK.

Termos de uso da API: ao usar os resultados, deve-se linkar de volta para
Remote OK como fonte (ja feito no formato de saida abaixo).

Uso como biblioteca:
    from fetch_remoteok_jobs import fetch_recent_jobs
    jobs = fetch_recent_jobs(hours=48, max_items=8)
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://remoteok.com/api"
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"

RELEVANT_TAGS = {
    "dev", "engineer", "javascript", "python", "react", "junior",
    "web dev", "backend", "frontend", "full stack", "software", "java",
    "golang", "node", "sys admin", "data", "machine learning", "ai",
}


def fetch_recent_jobs(hours: int = 48, max_items: int = 8) -> list[dict]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = []
    for entry in data:
        date_raw = entry.get("date")
        tags = set(t.lower() for t in entry.get("tags", []))
        if not date_raw or not tags & RELEVANT_TAGS:
            continue
        try:
            posted = datetime.fromisoformat(date_raw)
        except ValueError:
            continue
        if posted < cutoff:
            continue
        jobs.append({
            "position": entry.get("position"),
            "company": entry.get("company"),
            "url": entry.get("url"),
            "posted": posted,
        })
        if len(jobs) >= max_items:
            break
    return jobs


if __name__ == "__main__":
    for job in fetch_recent_jobs():
        print(f"- {job['position']} @ {job['company']} -> {job['url']}")
