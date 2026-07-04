"""
Busca artigos recentes no dev.to via API publica (gratuita, sem API key).

O dev.to ja fornece descricao (`description`), entao esses itens podem exibir
resumo mesmo sem IA. Retorna title/link/source/pub_date/description no mesmo
formato dos outros fetchers.

Uso como biblioteca:
    from fetch_devto import fetch_recent_articles
    items = fetch_recent_articles(hours=48, max_items=5)

Uso via CLI (debug):
    python fetch_devto.py
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://dev.to/api/articles"
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"

# Tags que interessam pra area de computacao/carreira.
TAGS = ("career", "programming", "webdev", "python", "javascript")


def _fetch_tag(tag: str, top_days: int, per_page: int) -> list[dict]:
    params = urllib.parse.urlencode({"tag": tag, "top": top_days, "per_page": per_page})
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def fetch_recent_articles(hours: int = 48, max_items: int = 5) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    top_days = max(1, hours // 24)
    seen = set()
    items = []
    for tag in TAGS:
        try:
            articles = _fetch_tag(tag, top_days, per_page=max_items)
        except Exception as exc:
            print(f"[aviso] falha ao buscar tag dev.to '{tag}': {exc}")
            continue
        for art in articles:
            link = (art.get("url") or "").strip()
            title = (art.get("title") or "").strip()
            if not link or not title or link in seen:
                continue
            pub_raw = art.get("published_at") or ""
            try:
                pub_date = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub_date < cutoff:
                continue
            seen.add(link)
            items.append({
                "title": title,
                "link": link,
                "source": f"dev.to - {art.get('user', {}).get('name', 'dev.to')}",
                "pub_date": pub_date,
                "description": art.get("description", ""),
            })
    items.sort(key=lambda i: i["pub_date"], reverse=True)
    return items[:max_items]


if __name__ == "__main__":
    for it in fetch_recent_articles():
        print(f"- {it['title']} ({it['source']}) -> {it['link']}")
