"""
Monta o corpo HTML da newsletter diaria ("Boletim Dev") combinando varias
fontes (Google News, Hacker News, dev.to, ProgramaThor, Remote OK), com
resumos opcionais por IA e capa gerada pela Kie.ai. Escreve o resultado em
.tmp/newsletter_<data>.html (corpo) e .tmp/newsletter_subject.txt (assunto).

Design: identidade PBF (ver .claude/LOGO.png). Feito pra sobreviver ao Gmail
(que ignora web-fonts e boa parte do CSS): tipografia editorial Georgia +
rotulos monoespacados + corpo sans, tudo com fontes de sistema. Nenhuma falha
de fonte/imagem/rede cancela o e-mail.

Uso:
    python build_newsletter.py
"""

import html
import re
from datetime import date, datetime, timezone
from pathlib import Path

from dedup_log import load_sent_links, mark_sent, prune_old, save_sent_links
from fetch_devto import fetch_recent_articles
from fetch_google_news import fetch_recent
from fetch_hackernews import fetch_recent_stories
from fetch_programathor import fetch_recent_br_jobs
from fetch_remoteok_jobs import fetch_recent_jobs
from generate_cover import generate_cover
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

# Identidade visual PBF (ver .claude/LOGO.png) + regra 60-30-10 do ColorSheet:
# 60% fundo off-white, 30% tinta navy, 10% destaque sage.
BRAND_NAVY = "#1a3a5f"     # primaria / destaque (headers, links)
SUPPORT_BLUE = "#aabccf"   # secundaria (hairlines)
OFF_WHITE = "#f7f7f7"      # fundo
SAGE = "#687d6a"           # apoio / "ao vivo, novo" (accent grey esverdeado)

COLOR_BG = OFF_WHITE
COLOR_CARD_BG = "#ffffff"
COLOR_TEXT = "#1f2d3d"     # navy suavizado, legivel pra corpo
COLOR_MUTED = "#6b7787"    # cinza-azulado pra metadados
COLOR_ACCENT = BRAND_NAVY
COLOR_BORDER = SUPPORT_BLUE
CHIP_BG = "#eef2f6"        # tinte navy bem clara pros chips
SAGE_BG = "#e9eeea"        # tinte sage pros selos de estagio/junior

# Fontes: escolhidas pra renderizar bem no Gmail SEM web-font externa.
FONT_DISPLAY = "Georgia,'Times New Roman',serif"                        # manchetes
FONT_MONO = "SFMono-Regular,Consolas,Menlo,'Liberation Mono',monospace"  # rotulos/dados
FONT_BODY = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"  # corpo
FONT_BRAND = "'Poppins',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"  # wordmark

WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


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
        return f"ha {hours}h"
    days = hours // 24
    return f"ha {days} dia{'s' if days != 1 else ''}"


def short_source(source: str) -> str:
    """Encurta a fonte pra caber num chip: 'Hacker News (121 pts)' -> 'hacker news'."""
    return re.split(r"\s+[-(]", source or "")[0].strip().lower() or "fonte"


def mono_chip(text: str) -> str:
    return (
        f'<span class="chip" style="font-family:{FONT_MONO};font-size:11px;'
        f'letter-spacing:.3px;color:{COLOR_ACCENT};background:{CHIP_BG};'
        f'padding:2px 7px;border-radius:3px;white-space:nowrap;">{html.escape(text)}</span>'
    )


def seniority_badge(level: str) -> str:
    labels = {"estagio": "estágio", "junior": "jr", "pleno": "pleno", "senior": "sr"}
    lab = labels.get(level, level)
    highlight = level in ("estagio", "junior")
    color = SAGE if highlight else COLOR_MUTED
    bg = SAGE_BG if highlight else CHIP_BG
    return (
        f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:700;'
        f'letter-spacing:.3px;color:{color};background:{bg};padding:2px 7px;'
        f'border-radius:3px;white-space:nowrap;">[ {html.escape(lab)} ]</span>'
    )


def render_entry(it: dict, summary: str = "") -> str:
    badge = (seniority_badge(it["level"]) + " ") if it.get("level") else ""
    meta = (
        f'{mono_chip(short_source(it["source"]))} '
        f'<span class="muted" style="font-size:12px;color:{COLOR_MUTED};">'
        f'· {relative_time(it["pub_date"])}</span>'
    )
    summary_html = (
        f'<p class="text" style="margin:6px 0 0;font-size:14px;line-height:1.55;'
        f'color:{COLOR_TEXT};">{html.escape(summary)}</p>'
        if summary else ""
    )
    return f"""
    <tr>
      <td class="border-row" style="padding:14px 0;border-bottom:1px solid {COLOR_BORDER};">
        <a class="text" href="{html.escape(it['link'])}" style="font-family:{FONT_DISPLAY};
           font-size:16px;line-height:1.35;font-weight:700;color:{COLOR_TEXT};
           text-decoration:none;">{badge}{html.escape(it['title'])}</a>
        <div style="margin-top:7px;">{meta}</div>
        {summary_html}
      </td>
    </tr>
    """


def render_empty_row(message: str = "Nada de novo relevante hoje.") -> str:
    return f"""
    <tr>
      <td class="border-row muted" style="padding:14px 0;border-bottom:1px solid {COLOR_BORDER};
                 font-family:{FONT_MONO};font-size:13px;color:{COLOR_MUTED};">
        // {html.escape(message)}
      </td>
    </tr>
    """


def render_section(label: str, count: int, rows_html: str) -> str:
    return f"""
    <tr>
      <td style="padding:30px 0 6px;border-bottom:2px solid {COLOR_ACCENT};">
        <span class="accent" style="font-family:{FONT_MONO};font-size:12px;font-weight:700;
              letter-spacing:2.5px;text-transform:uppercase;color:{COLOR_ACCENT};">{html.escape(label)}</span>
        <span class="muted" style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};">
              &nbsp;[{count:02d}]</span>
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


def render_rows(items: list[dict], summaries: dict[str, str], any_ok: bool) -> str:
    if not items:
        if not any_ok:
            return render_empty_row("nao foi possivel buscar essa categoria hoje.")
        return render_empty_row()
    rows = [render_entry(it, summaries.get(it["link"], "") or it.get("description", "")) for it in items]
    return "".join(rows)


def render_cover(url: str | None) -> str:
    if url:
        return f"""
    <tr>
      <td style="padding:16px 0 0;">
        <img src="{html.escape(url)}" width="536" alt="Boletim Dev — capa da edição"
             style="display:block;width:100%;max-width:536px;height:auto;border-radius:6px;">
      </td>
    </tr>"""
    # Fallback sem imagem: faixa duotone (cor solida + gradiente onde suportado).
    return f"""
    <tr>
      <td style="padding:16px 0 0;">
        <div style="height:110px;border-radius:6px;background-color:{BRAND_NAVY};
             background-image:linear-gradient(115deg,{BRAND_NAVY} 0%,{BRAND_NAVY} 55%,{SAGE} 120%);"></div>
      </td>
    </tr>"""


def render_highlight(it: dict, summary: str) -> str:
    summary_html = (
        f'<p class="text" style="margin:10px 0 0;font-size:15px;line-height:1.6;'
        f'color:{COLOR_TEXT};">{html.escape(summary)}</p>'
        if summary else ""
    )
    return f"""
    <tr>
      <td style="padding:22px 0 4px;">
        <span style="font-family:{FONT_MONO};font-size:12px;font-weight:700;letter-spacing:1.5px;
              text-transform:uppercase;color:{SAGE};">&rsaquo; destaque do dia</span>
        <a class="text" href="{html.escape(it['link'])}" style="display:block;margin-top:10px;
           font-family:{FONT_DISPLAY};font-size:23px;line-height:1.25;font-weight:700;
           color:{COLOR_TEXT};text-decoration:none;">{html.escape(it['title'])}</a>
        {summary_html}
        <div style="margin-top:10px;">fonte: {mono_chip(short_source(it['source']))}
          <span class="muted" style="font-size:12px;color:{COLOR_MUTED};">· {relative_time(it['pub_date'])}</span>
        </div>
      </td>
    </tr>"""


def _add_items(dest, seen, sent_links, new_items, limit):
    for item in new_items:
        link = item.get("link")
        if not link or link in seen or link in sent_links or len(dest) >= limit:
            continue
        seen.add(link)
        dest.append(item)


def collect_google_news(queries, sent_links, seen, dest, limit) -> bool:
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


def collect_news(sent_links):
    seen, items = set(), []
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


def collect_concursos(sent_links):
    seen, items = set(), []
    any_ok = collect_google_news(CONCURSOS_QUERIES, sent_links, seen, items, MAX_ITEMS_PER_SECTION)
    return items, any_ok


def collect_remoteok(sent_links):
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


def collect_programathor(sent_links):
    try:
        jobs = fetch_recent_br_jobs(hours=72, max_items=MAX_ITEMS_PER_SECTION)
    except Exception as exc:
        print(f"[aviso] falha ao buscar vagas ProgramaThor: {exc}")
        return [], False
    return [j for j in jobs if j["link"] not in sent_links], True


def build_body(sent_links: dict[str, str]) -> tuple[str, list[str]]:
    today = date.today()
    today_label = today.strftime("%d/%m/%Y")
    weekday = WEEKDAYS_PT[today.weekday()]

    news_items, news_ok = collect_news(sent_links)
    concursos_items, concursos_ok = collect_concursos(sent_links)
    remoteok_items, remoteok_ok = collect_remoteok(sent_links)
    br_items, br_ok = collect_programathor(sent_links)

    # Resumos numa unica chamada (noticias + concursos, que so tem titulo).
    summaries = enrich_summaries(news_items + concursos_items)

    # Destaque = primeira noticia; o resto vai pra secao NOTICIAS.
    highlight = news_items[0] if news_items else None
    rest_news = news_items[1:] if highlight else news_items
    cover_theme = highlight["title"] if highlight else "tecnologia e computacao"
    cover_url = generate_cover(cover_theme)

    n_vagas = len(br_items) + len(remoteok_items)
    stamp = f"build {today.isoformat()} · {weekday} · {len(news_items)} historias · {n_vagas} vagas · {len(concursos_items)} concursos"

    highlight_block = render_highlight(highlight, summaries.get(highlight["link"], "")) if highlight else ""
    news_section = render_section("Noticias", len(rest_news), render_rows(rest_news, summaries, news_ok))
    br_section = render_section("Vagas Tech Brasil", len(br_items), render_rows(br_items, summaries, br_ok))
    remote_section = render_section("Vagas Remotas", len(remoteok_items), render_rows(remoteok_items, summaries, remoteok_ok))
    concursos_section = render_section("Concursos TI", len(concursos_items), render_rows(concursos_items, summaries, concursos_ok))

    all_included = [it["link"] for it in news_items + concursos_items + remoteok_items + br_items]

    body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;800&display=swap');
  body {{ background-color: {COLOR_BG}; }}
  .card {{ background-color: {COLOR_CARD_BG}; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background-color: #0f2233 !important; }}
    .card {{ background-color: #16293b !important; }}
    .text {{ color: {OFF_WHITE} !important; }}
    .muted {{ color: {SUPPORT_BLUE} !important; }}
    .accent {{ color: {SUPPORT_BLUE} !important; }}
    .border-row {{ border-color: #2a4055 !important; }}
    .chip {{ color: {SUPPORT_BLUE} !important; background: #21374d !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{COLOR_BG};font-family:{FONT_BODY};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               class="card" style="max-width:600px;width:100%;background-color:{COLOR_CARD_BG};
               border-radius:10px;padding:26px 32px 30px;">
          <tr>
            <td style="padding-bottom:16px;border-bottom:3px solid {COLOR_ACCENT};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family:{FONT_BRAND};font-size:26px;font-weight:800;
                      letter-spacing:-1px;color:{COLOR_ACCENT};line-height:1;">pbf<span
                      class="muted" style="font-family:{FONT_MONO};font-size:14px;font-weight:400;
                      color:{COLOR_MUTED};letter-spacing:0;"> ///</span></td>
                  <td align="right" style="font-family:{FONT_MONO};font-size:12px;color:{SAGE};
                      font-weight:700;letter-spacing:.5px;">&#9679; no ar</td>
                </tr>
              </table>
              <div class="text" style="font-family:{FONT_DISPLAY};font-size:27px;font-weight:700;
                   color:{COLOR_TEXT};margin-top:12px;letter-spacing:.3px;">Boletim Dev</div>
              <div class="muted" style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};
                   margin-top:5px;">{stamp}</div>
            </td>
          </tr>
          {render_cover(cover_url)}
          {highlight_block}
          {news_section}
          {br_section}
          {remote_section}
          {concursos_section}
          <tr>
            <td style="padding-top:26px;">
              <div class="muted" style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};
                   line-height:1.7;border-top:1px solid {COLOR_BORDER};padding-top:14px;">
                — gerado automaticamente · pbf@ufms<br>
                fontes: google news · hacker news · dev.to · programathor · remote ok
              </div>
            </td>
          </tr>
        </table>
        <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_MUTED};padding:12px 0 0;">
          {today_label}
        </div>
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
    subject_path.write_text(
        f"Boletim Dev · PBF — {today.strftime('%d/%m/%Y')}", encoding="utf-8"
    )

    sent_links = mark_sent(sent_links, included_links, today)
    save_sent_links(sent_links)

    print(f"Corpo escrito em {body_path}")


if __name__ == "__main__":
    main()
