"""
Gera resumos curtos (1 linha, PT-BR) para itens que so tem titulo (Google News
e Hacker News nao trazem descricao).

Duas camadas, sempre com degradacao graciosa:

1. IA (opcional): se GEMINI_API_KEY estiver setada, faz UMA unica chamada em
   lote ao Gemini (gemini-2.5-flash) com todos os titulos, usando grounding do
   Google Search pra resumir de forma factual (sem inventar). Mesmo padrao de
   cliente do projeto aquaia-ufms.
2. Fallback deterministico (sem chave, ou pros itens que a IA nao cobriu):
   busca a meta-descricao (og:description / <meta name=description>) da pagina.

Itens que ja tem `description` (dev.to, Remote OK) passam direto. O que nao tem
resumo em nenhuma camada simplesmente sai so com titulo, como antes. Nenhuma
falha aqui cancela o e-mail.

Uso como biblioteca:
    from summarize import enrich_summaries
    resumos = enrich_summaries(items)  # {link: resumo}
"""

import json
import os
import re
import urllib.request
from html import unescape

USER_AGENT = "Mozilla/5.0 (WorkFlowAgent newsletter bot)"
MAX_SUMMARY_LEN = 180


def _clip(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > MAX_SUMMARY_LEN:
        text = text[:MAX_SUMMARY_LEN].rsplit(" ", 1)[0] + "..."
    return text


def _extract_meta_description(link: str, timeout: int = 8) -> str:
    """Le a meta-descricao da pagina. Links do Google News redirecionam por JS
    e nao expoem meta util, entao sao pulados."""
    if not link or "news.google.com" in link:
        return ""
    try:
        req = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get_content_type()
            if ctype and not ctype.startswith("text"):
                return ""
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read(200_000).decode(charset, "replace")
    except Exception:
        return ""

    patterns = (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    )
    for pattern in patterns:
        m = re.search(pattern, raw, re.IGNORECASE)
        if m:
            return _clip(unescape(m.group(1)))
    return ""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _gemini_summaries(items: list[dict]) -> dict[str, str]:
    """Uma unica chamada em lote. Devolve {link: resumo} (pode vir parcial)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not items:
        return {}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[summarize] google-genai nao instalado; usando fallback deterministico.")
        return {}

    numbered = "\n".join(f'{i}. {it["title"]}' for i, it in enumerate(items, 1))
    prompt = (
        "Voce ajuda a montar uma newsletter de tecnologia em portugues do Brasil.\n"
        "Para cada manchete numerada abaixo, escreva UM resumo de 1 frase (ate 25 "
        "palavras), factual e neutro, em PT-BR. Use a busca para confirmar o "
        "contexto; se nao tiver certeza, resuma o tema pela propria manchete SEM "
        "inventar fatos, numeros ou nomes.\n"
        'Responda SOMENTE um objeto JSON no formato {"1": "resumo", "2": "resumo"} '
        "com a chave sendo o numero da manchete.\n\n"
        f"{numbered}"
    )
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        data = _extract_json(response.text)
    except Exception as exc:
        print(f"[summarize] Gemini indisponivel, usando fallback: {exc}")
        return {}

    out = {}
    for i, it in enumerate(items, 1):
        val = data.get(str(i))
        if isinstance(val, str) and val.strip():
            out[it["link"]] = _clip(val)
    return out


def enrich_summaries(items: list[dict]) -> dict[str, str]:
    """Recebe itens (com title, link e opcionalmente description) e devolve
    {link: resumo}. Uma unica chamada ao Gemini no maximo."""
    summaries: dict[str, str] = {}
    title_only: list[dict] = []
    for it in items:
        desc = (it.get("description") or "").strip()
        if desc:
            summaries[it["link"]] = _clip(desc)
        else:
            title_only.append(it)

    if os.getenv("GEMINI_API_KEY"):
        summaries.update(_gemini_summaries(title_only))

    # Fallback deterministico pros que ainda nao tem resumo.
    for it in title_only:
        if it["link"] not in summaries:
            meta = _extract_meta_description(it["link"])
            if meta:
                summaries[it["link"]] = meta
    return summaries


if __name__ == "__main__":
    demo = [
        {"title": "Python 3.13 lanca com melhorias de performance", "link": "https://www.python.org/"},
    ]
    for link, summary in enrich_summaries(demo).items():
        print(f"{link}\n  -> {summary}")
