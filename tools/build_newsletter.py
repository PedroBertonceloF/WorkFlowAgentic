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
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from dedup_log import load_sent_links, mark_sent, prune_old, save_sent_links
from fetch_devto import fetch_recent_articles
from fetch_google_news import fetch_recent
from fetch_hackernews import fetch_recent_stories
from fetch_programathor import fetch_recent_br_jobs
from fetch_remotar import fetch_data_jobs
from fetch_remoteok_jobs import fetch_recent_jobs
from fetch_sigproj_ufms import fetch_open_editais
from summarize import enrich_summaries

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

# Secao "Estagios em Dados": ProgramaThor filtrado por area + Google News
ESTAGIO_DADOS_QUERIES = [
    'vaga estagio "analise de dados" OR "ciencia de dados"',
    '"programa de estagio" dados tecnologia',
]
DATA_PATTERN = re.compile(
    r"\b(dados|data|analytics|bi|business intelligence|power ?bi|"
    r"machine learning|ciencia de dados|sql|etl|dashboards?)\b"
)
LEVEL_LABEL = {"estagio": "Estágio", "junior": "Júnior"}

# Identidade visual PBF (ver .claude/LOGO.png) + regra 60-30-10 do ColorSheet:
# 60% fundo off-white, 30% apoio azul, 10% destaque navy.
BRAND_NAVY = "#1a3a5f"     # primaria / destaque (headers, links)
SUPPORT_BLUE = "#aabccf"   # secundaria (bordas, detalhes)
OFF_WHITE = "#f7f7f7"      # fundo
ACCENT_GREY = "#687d6a"    # apoio (metadados)

COLOR_BG = OFF_WHITE
COLOR_CARD_BG = "#ffffff"
COLOR_TEXT = "#1f2d3d"     # navy suavizado, legivel pra corpo
COLOR_MUTED = ACCENT_GREY
COLOR_ACCENT = BRAND_NAVY
COLOR_BORDER = SUPPORT_BLUE

DARK_BG = "#0f2233"        # navy profundo
DARK_CARD_BG = "#16293b"
DARK_TEXT = OFF_WHITE
DARK_MUTED = SUPPORT_BLUE
DARK_ACCENT = SUPPORT_BLUE
DARK_BORDER = "#2a4055"

FONT_STACK = "'Poppins',-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"


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
        f'<p class="text" style="margin:4px 0 0;font-size:14px;line-height:1.5;'
        f'color:{COLOR_TEXT};">{html.escape(summary)}</p>'
        if summary
        else ""
    )
    return f"""
    <tr>
      <td class="border-row" style="padding:12px 0;border-bottom:1px solid {COLOR_BORDER};">
        <a class="accent" href="{html.escape(link)}" style="font-size:15px;font-weight:600;
           color:{COLOR_ACCENT};text-decoration:none;">{html.escape(title)}</a>
        <p class="muted" style="margin:4px 0 0;font-size:12px;color:{COLOR_MUTED};">{html.escape(meta)}</p>
        {summary_html}
      </td>
    </tr>
    """


def render_empty_row(message: str = "Nada de novo relevante hoje.") -> str:
    return f"""
    <tr>
      <td class="border-row muted" style="padding:12px 0;border-bottom:1px solid {COLOR_BORDER};
                 font-size:14px;color:{COLOR_MUTED};font-style:italic;">
        {html.escape(message)}
      </td>
    </tr>
    """


def render_section(icon: str, title: str, rows_html: str) -> str:
    return f"""
    <tr>
      <td style="padding:24px 0 8px;">
        <h2 class="accent" style="margin:0;font-size:17px;font-weight:700;color:{COLOR_ACCENT};">
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


def _add_items(dest: list[dict], seen: set, sent_links: dict[str, str],
               new_items: list[dict], limit: int) -> None:
    """Adiciona itens novos (nao repetidos nem ja enviados) ate o limite."""
    for item in new_items:
        link = item.get("link")
        if not link or link in seen or link in sent_links or len(dest) >= limit:
            continue
        seen.add(link)
        dest.append(item)


def collect_google_news(queries: list[str], sent_links: dict[str, str],
                        seen: set, dest: list[dict], limit: int) -> bool:
    any_ok = False
    for query in queries:
        try:
            results = fetch_recent(query, hours=48, max_items=MAX_ITEMS_PER_SECTION)
            any_ok = True
        except Exception as exc:
            print(f"[aviso] falha ao buscar '{query}': {exc}")
            continue
        _add_items(dest, seen, sent_links, results, limit)
    return any_ok


def collect_news(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    """Noticias: Google News + Hacker News + dev.to, deduplicados."""
    seen: set = set()
    items: list[dict] = []
    limit = MAX_ITEMS_PER_SECTION + 3
    any_ok = collect_google_news(NEWS_QUERIES, sent_links, seen, items, limit)
    for label, fetcher in (
        ("Hacker News", lambda: fetch_recent_stories(hours=48, max_items=3, min_points=100)),
        ("dev.to", lambda: fetch_recent_articles(hours=48, max_items=3)),
    ):
        try:
            _add_items(items, seen, sent_links, fetcher(), limit)
            any_ok = True
        except Exception as exc:
            print(f"[aviso] falha ao buscar {label}: {exc}")
    return items, any_ok


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii").lower()


def collect_estagios_dados(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    """Estagios (e junior) na area de dados: ProgramaThor e Remotar filtrados
    por area/nivel + anuncios de programas de estagio no Google News."""
    seen: set = set()
    items: list[dict] = []
    any_ok = False
    candidates: list[dict] = []
    try:
        jobs = fetch_recent_br_jobs(hours=7 * 24, max_items=40)
        any_ok = True
        candidates += [j for j in jobs
                       if j.get("level") in LEVEL_LABEL
                       and DATA_PATTERN.search(_normalize(j["title"]))]
    except Exception as exc:
        print(f"[aviso] falha ao buscar estagios de dados (ProgramaThor): {exc}")
    try:
        candidates += fetch_data_jobs(hours=7 * 24, max_items=10)
        any_ok = True
    except Exception as exc:
        print(f"[aviso] falha ao buscar estagios de dados (Remotar): {exc}")

    candidates.sort(key=lambda j: (0 if j["level"] == "estagio" else 1,
                                   -j["pub_date"].timestamp()))
    candidates = [{**j, "source": f"{j['source']} · {LEVEL_LABEL[j['level']]}"}
                  for j in candidates]
    _add_items(items, seen, sent_links, candidates, MAX_ITEMS_PER_SECTION)
    if collect_google_news(ESTAGIO_DADOS_QUERIES, sent_links, seen, items, MAX_ITEMS_PER_SECTION):
        any_ok = True
    return items, any_ok


def collect_sigproj(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    """Editais abertos no SIGProj da UFMS. Como o log de dedup e podado apos 7
    dias, um edital que segue aberto reaparece semanalmente (lembrete util)."""
    try:
        editais = fetch_open_editais(max_items=MAX_ITEMS_PER_SECTION)
    except Exception as exc:
        print(f"[aviso] falha ao buscar editais do SIGProj UFMS: {exc}")
        return [], False
    return [e for e in editais if e["link"] not in sent_links], True


def collect_concursos(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    seen: set = set()
    items: list[dict] = []
    any_ok = collect_google_news(CONCURSOS_QUERIES, sent_links, seen, items, MAX_ITEMS_PER_SECTION)
    return items, any_ok


def collect_remoteok(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    try:
        jobs = fetch_recent_jobs(hours=48, max_items=MAX_ITEMS_PER_SECTION)
    except Exception as exc:
        print(f"[aviso] falha ao buscar vagas Remote OK: {exc}")
        return [], False
    items = []
    for job in jobs:
        if job["url"] in sent_links:
            continue
        items.append({
            "title": job["position"],
            "link": job["url"],
            "source": job["company"],
            "pub_date": job["posted"],
            "description": strip_html(job.get("description", "")),
        })
    return items, True


def collect_programathor(sent_links: dict[str, str]) -> tuple[list[dict], bool]:
    try:
        jobs = fetch_recent_br_jobs(hours=72, max_items=MAX_ITEMS_PER_SECTION)
    except Exception as exc:
        print(f"[aviso] falha ao buscar vagas ProgramaThor: {exc}")
        return [], False
    return [j for j in jobs if j["link"] not in sent_links], True


def render_rows(items: list[dict], summaries: dict[str, str], any_ok: bool) -> str:
    if not items:
        if not any_ok:
            return render_empty_row("Nao foi possivel buscar essa categoria hoje (erro temporario).")
        return render_empty_row()
    rows = []
    for it in items:
        meta = f"{it['source']} - {relative_time(it['pub_date'])}"
        summary = summaries.get(it["link"], "") or it.get("description", "")
        rows.append(render_item(it["title"], it["link"], meta, summary))
    return "".join(rows)


def build_body(sent_links: dict[str, str]) -> tuple[str, list[str]]:
    today_label = date.today().strftime("%d/%m/%Y")

    estagios_items, estagios_ok = collect_estagios_dados(sent_links)
    sigproj_items, sigproj_ok = collect_sigproj(sent_links)
    news_items, news_ok = collect_news(sent_links)
    concursos_items, concursos_ok = collect_concursos(sent_links)
    remoteok_items, remoteok_ok = collect_remoteok(sent_links)
    br_items, br_ok = collect_programathor(sent_links)

    # Nao repetir na secao generica do ProgramaThor o que ja esta em destaque
    estagio_links = {it["link"] for it in estagios_items}
    br_items = [j for j in br_items if j["link"] not in estagio_links]

    # Resumos: uma unica chamada pro que so tem titulo (noticias + concursos).
    # Vagas ja trazem descricao/titulo suficiente, nao entram no resumo.
    summaries = enrich_summaries(news_items + concursos_items)

    estagios_section = render_section("🎯", "Estágios em Dados",
                                      render_rows(estagios_items, summaries, estagios_ok))
    sigproj_section = render_section("🎓", "Editais Abertos — SIGProj UFMS",
                                     render_rows(sigproj_items, summaries, sigproj_ok))
    news_section = render_section("📰", "Noticias de Tecnologia",
                                  render_rows(news_items, summaries, news_ok))
    br_jobs_section = render_section("🇧🇷", "Vagas Tech no Brasil (ProgramaThor)",
                                     render_rows(br_items, summaries, br_ok))
    jobs_section = render_section("💼", "Vagas Remotas de TI (Remote OK)",
                                  render_rows(remoteok_items, summaries, remoteok_ok))
    concursos_section = render_section("📋", "Concursos Publicos de TI",
                                       render_rows(concursos_items, summaries, concursos_ok))
    all_included = [it["link"] for it in
                    estagios_items + sigproj_items + news_items
                    + concursos_items + remoteok_items + br_items]

    body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
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
<body style="margin:0;padding:0;background-color:{COLOR_BG};font-family:{FONT_STACK};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               class="card" style="max-width:600px;width:100%;background-color:{COLOR_CARD_BG};
               border-radius:8px;padding:24px 32px;">
          <tr>
            <td style="padding-bottom:16px;border-bottom:3px solid {COLOR_ACCENT};">
              <span class="accent" style="display:inline-block;font-size:28px;font-weight:800;
                     letter-spacing:-1.5px;color:{COLOR_ACCENT};line-height:1;">pbf</span>
              <h1 class="text" style="margin:8px 0 0;font-size:20px;font-weight:800;color:{COLOR_TEXT};">
                Newsletter de Computação
              </h1>
              <p class="muted" style="margin:4px 0 0;font-size:13px;color:{COLOR_MUTED};">
                {today_label} &nbsp;·&nbsp; por PBF
              </p>
            </td>
          </tr>
          {estagios_section}
          {sigproj_section}
          {news_section}
          {br_jobs_section}
          {jobs_section}
          {concursos_section}
          <tr>
            <td style="padding-top:24px;font-size:11px;color:{COLOR_MUTED};">
              Fontes: Google News, Hacker News, dev.to, ProgramaThor, Remotar,
              Remote OK e SIGProj UFMS.
              Gerado automaticamente todo dia.
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
