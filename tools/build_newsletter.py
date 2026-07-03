"""
Monta o corpo HTML da newsletter diaria combinando 3 categorias de busca
(noticias, vagas, concursos) via Google News RSS e Remote OK, e escreve o
resultado em .tmp/newsletter_<data>.html (corpo) e
.tmp/newsletter_subject.txt (assunto).

Uso:
    python build_newsletter.py
"""

import html
import re
from datetime import date, datetime, timezone
from pathlib import Path

from dedup_log import load_sent_links, mark_sent, prune_old, save_sent_links
from fetch_google_news import fetch_recent
from fetch_remoteok_jobs import fetch_recent_jobs

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = BASE_DIR / ".tmp"

MAX_ITEMS_PER_SECTION = 5

NEWS_QUERIES = [
    "tecnologia inteligencia artificial noticia",
    "software engenharia noticia Brasil",
]
CONCURSOS_QUERIES = [
    "concurso publico TI analista de sistemas",
    "concurso publico tecnologia da informacao edital",
]

# Paleta neutra com um unico acento (sem roxo/gradiente "cara de IA")
COLOR_BG = "#f5f5f4"
COLOR_CARD_BG = "#ffffff"
COLOR_TEXT = "#292524"
COLOR_MUTED = "#78716c"
COLOR_ACCENT = "#0f5d6b"  # azul-petroleo
COLOR_BORDER = "#e7e5e4"

DARK_BG = "#1c1917"
DARK_CARD_BG = "#292524"
DARK_TEXT = "#f5f5f4"
DARK_MUTED = "#a8a29e"
DARK_ACCENT = "#5eead4"
DARK_BORDER = "#44403c"


def strip_html(raw: str, max_len: int = 160) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


def relative_time(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - dt
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "ha poucos minutos"
    if hours < 24:
        return f"ha {hours} hora{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"ha {days} dia{'s' if days != 1 else ''}"


def render_item(title: str, link: str, meta: str, summary: str = "") -> str:
    summary_html = (
        f'<p style="margin:4px 0 0;font-size:14px;line-height:1.5;'
        f'color:{COLOR_TEXT};">{html.escape(summary)}</p>'
        if summary
        else ""
    )
    return f"""
    <tr>
      <td style="padding:12px 0;border-bottom:1px solid {COLOR_BORDER};">
        <a href="{html.escape(link)}" style="font-size:15px;font-weight:600;
           color:{COLOR_ACCENT};text-decoration:none;">{html.escape(title)}</a>
        <p style="margin:4px 0 0;font-size:12px;color:{COLOR_MUTED};">{html.escape(meta)}</p>
        {summary_html}
      </td>
    </tr>
    """


def render_empty_row(message: str = "Nada de novo relevante hoje.") -> str:
    return f"""
    <tr>
      <td style="padding:12px 0;border-bottom:1px solid {COLOR_BORDER};
                 font-size:14px;color:{COLOR_MUTED};font-style:italic;">
        {html.escape(message)}
      </td>
    </tr>
    """


def render_section(icon: str, title: str, rows_html: str) -> str:
    return f"""
    <tr>
      <td style="padding:24px 0 8px;">
        <h2 style="margin:0;font-size:17px;font-weight:700;color:{COLOR_ACCENT};">
          {icon} {html.escape(title)}
        </h2>
      </td>
    </tr>
    <tr>
      <td>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          {rows_html}
        </table>
      </td>
    </tr>
    """


def build_news_rows(queries: list[str], sent_links: dict[str, str]) -> tuple[str, list[str]]:
    seen_links = set()
    rows = []
    included = []
    any_query_ok = False
    for query in queries:
        try:
            results = fetch_recent(query, hours=48, max_items=MAX_ITEMS_PER_SECTION)
            any_query_ok = True
        except Exception as exc:
            print(f"[aviso] falha ao buscar '{query}': {exc}")
            continue
        for item in results:
            link = item["link"]
            if link in seen_links or link in sent_links or len(rows) >= MAX_ITEMS_PER_SECTION:
                continue
            seen_links.add(link)
            included.append(link)
            meta = f"{item['source']} - {relative_time(item['pub_date'])}"
            rows.append(render_item(item["title"], link, meta))
    if rows:
        return "".join(rows), included
    if not any_query_ok:
        return render_empty_row("Nao foi possivel buscar essa categoria hoje (erro temporario)."), included
    return render_empty_row(), included


def build_jobs_rows(sent_links: dict[str, str]) -> tuple[str, list[str]]:
    try:
        jobs = fetch_recent_jobs(hours=48, max_items=MAX_ITEMS_PER_SECTION)
    except Exception as exc:
        print(f"[aviso] falha ao buscar vagas: {exc}")
        return render_empty_row("Nao foi possivel buscar essa categoria hoje (erro temporario)."), []
    rows = []
    included = []
    for job in jobs:
        if job["url"] in sent_links or len(rows) >= MAX_ITEMS_PER_SECTION:
            continue
        included.append(job["url"])
        meta = f"{job['company']} - {relative_time(job['posted'])}"
        summary = strip_html(job.get("description", ""))
        rows.append(render_item(job["position"], job["url"], meta, summary))
    return ("".join(rows) if rows else render_empty_row()), included


def build_body(sent_links: dict[str, str]) -> tuple[str, list[str]]:
    today_label = date.today().strftime("%d/%m/%Y")
    news_rows, news_included = build_news_rows(NEWS_QUERIES, sent_links)
    jobs_rows, jobs_included = build_jobs_rows(sent_links)
    concursos_rows, concursos_included = build_news_rows(CONCURSOS_QUERIES, sent_links)

    news_section = render_section("📰", "Noticias de Tecnologia", news_rows)
    jobs_section = render_section("💼", "Vagas Remotas de TI (Remote OK)", jobs_rows)
    concursos_section = render_section("📋", "Concursos Publicos de TI", concursos_rows)
    all_included = news_included + jobs_included + concursos_included

    body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style>
  body {{ background-color: {COLOR_BG}; }}
  .card {{ background-color: {COLOR_CARD_BG}; }}
  .muted {{ color: {COLOR_MUTED}; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background-color: {DARK_BG} !important; }}
    .card {{ background-color: {DARK_CARD_BG} !important; }}
    .text {{ color: {DARK_TEXT} !important; }}
    .muted {{ color: {DARK_MUTED} !important; }}
    .accent {{ color: {DARK_ACCENT} !important; }}
    .border-row {{ border-color: {DARK_BORDER} !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{COLOR_BG};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               class="card" style="max-width:600px;width:100%;background-color:{COLOR_CARD_BG};
               border-radius:8px;padding:24px 32px;">
          <tr>
            <td style="padding-bottom:16px;border-bottom:2px solid {COLOR_ACCENT};">
              <h1 style="margin:0;font-size:22px;font-weight:800;color:{COLOR_TEXT};">
                Newsletter Computacao
              </h1>
              <p style="margin:4px 0 0;font-size:13px;color:{COLOR_MUTED};">{today_label}</p>
            </td>
          </tr>
          {news_section}
          {jobs_section}
          {concursos_section}
          <tr>
            <td style="padding-top:24px;font-size:11px;color:{COLOR_MUTED};">
              Fontes: Google News RSS e Remote OK API. Gerado automaticamente todo dia.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return body, all_included


def main():
    TMP_DIR.mkdir(exist_ok=True)
    today = date.today()

    sent_links = prune_old(load_sent_links(), today)
    body, included_links = build_body(sent_links)

    body_path = TMP_DIR / f"newsletter_{today.isoformat()}.html"
    subject_path = TMP_DIR / "newsletter_subject.txt"

    body_path.write_text(body, encoding="utf-8")
    subject_path.write_text(f"Newsletter Computacao - {today.strftime('%d/%m/%Y')}", encoding="utf-8")

    sent_links = mark_sent(sent_links, included_links, today)
    save_sent_links(sent_links)

    print(f"Corpo escrito em {body_path}")


if __name__ == "__main__":
    main()
