"""
Busca editais abertos no SIGProj da UFMS (sigproj.ufms.br).

A pagina publica (/publico/editais) e uma SPA, mas a API por tras dela e
aberta: GET https://sigproj.ufms.br/api/editais devolve JSON com nome,
descricao, dataAbertura e dataEncerramento. Aqui filtramos so os editais com
inscricao aberta (encerramento no futuro), ignorando rascunhos e editais de
teste, ordenados pelo prazo mais proximo primeiro.

Uso como biblioteca:
    from fetch_sigproj_ufms import fetch_open_editais
    editais = fetch_open_editais(max_items=5)

Uso via CLI (debug):
    python fetch_sigproj_ufms.py
"""

import json
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone

API_URL = "https://sigproj.ufms.br/api/editais"
EDITAL_URL = "https://sigproj.ufms.br/publico/editais/{id}"
USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_open_editais(max_items: int = 5) -> list[dict]:
    """Editais do SIGProj UFMS com inscricao aberta, prazo mais curto primeiro."""
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        entries = json.loads(resp.read())

    now = datetime.now(timezone.utc)
    editais = []
    for entry in entries:
        nome = (entry.get("nome") or "").strip()
        abertura = _parse_date(entry.get("dataAbertura"))
        encerramento = _parse_date(entry.get("dataEncerramento"))
        if not nome or not encerramento:
            continue
        if entry.get("rascunho") or re.search(r"\(teste\)", _normalize(nome)):
            continue
        if encerramento <= now or (abertura and abertura > now):
            continue
        editais.append({
            "title": nome,
            "link": EDITAL_URL.format(id=entry["id"]),
            "source": entry.get("programaNome") or "SIGProj UFMS",
            "pub_date": abertura or now,
            "description": f"Inscrições até {encerramento.astimezone().strftime('%d/%m/%Y')}.",
            "_deadline": encerramento,
        })

    editais.sort(key=lambda e: e["_deadline"])
    for e in editais:
        del e["_deadline"]
    return editais[:max_items]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for edital in fetch_open_editais(max_items=10):
        print(f"- {edital['description']} {edital['title'][:80]} -> {edital['link']}")
