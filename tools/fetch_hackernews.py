"""
Busca stories recentes e relevantes no Hacker News via API publica Algolia
(gratuita, sem API key).

Filtra por pontuacao minima pra trazer so o que teve tracao na comunidade, e
por recencia (ultimas 48h). Retorna o mesmo formato dos outros fetchers de
noticia (title/link/source/pub_date) pra encaixar direto no build_newsletter.

Uso como biblioteca:
    from fetch_hackernews import fetch_recent_stories
    items = fetch_recent_stories(hours=48, max_items=5, min_points=100)

Uso via CLI (debug):
    python fetch_hackernews.py
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://news.ycombinator.com/item?id="
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"


def fetch_recent_stories(hours: int = 48, max_items: int = 5, min_points: int = 100) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
    params = urllib.parse.urlencode({
        "tags": "story",
        "numericFilters": f"points>={min_points},created_at_i>={since}",
        "hitsPerPage": max_items * 3,
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())

    items = []
    for hit in data.get("hits", []):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        # Se a story nao tem URL externa, aponta pra discussao no HN.
        link = hit.get("url") or (ITEM_URL + str(hit.get("objectID", "")))
        created = hit.get("created_at_i")
        try:
            pub_date = datetime.fromtimestamp(int(created), tz=timezone.utc)
        except (TypeError, ValueError):
            continue
        items.append({
            "title": title,
            "link": link,
            "source": f"Hacker News ({hit.get('points', 0)} pts)",
            "pub_date": pub_date,
        })
        if len(items) >= max_items:
            break
    return items


if __name__ == "__main__":
    for it in fetch_recent_stories():
        print(f"- {it['title']} ({it['source']}) -> {it['link']}")
