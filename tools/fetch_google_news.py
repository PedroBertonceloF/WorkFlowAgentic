"""
Busca itens recentes no Google News RSS (gratuito, sem API key).

Uso como biblioteca:
    from fetch_google_news import fetch_recent
    items = fetch_recent("concurso publico TI", hours=48, max_items=8)

Uso via CLI (debug):
    python fetch_google_news.py "vaga estagio desenvolvedor Brasil"
"""

import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"


def fetch_recent(query: str, hours: int = 48, max_items: int = 8) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-BR"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date_raw = item.findtext("pubDate", "")
        source = item.findtext("source", "")
        try:
            pub_date = parsedate_to_datetime(pub_date_raw)
        except (TypeError, ValueError):
            continue
        if pub_date < cutoff:
            continue
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "pub_date": pub_date,
        })
        if len(items) >= max_items:
            break
    return items


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "tecnologia"
    for it in fetch_recent(q):
        print(f"- {it['title']} ({it['source']}) -> {it['link']}")
