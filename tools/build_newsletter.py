"""
Monta o corpo da newsletter diaria combinando 3 categorias de busca
(noticias, vagas, concursos) via Google News RSS e escreve o resultado em
.tmp/newsletter_<data>.txt (corpo) e .tmp/newsletter_subject.txt (assunto).

Uso:
    python build_newsletter.py
"""

from datetime import date
from pathlib import Path

from fetch_google_news import fetch_recent
from fetch_remoteok_jobs import fetch_recent_jobs

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = BASE_DIR / ".tmp"

NEWS_QUERIES = [
    "tecnologia inteligencia artificial noticia",
    "software engenharia noticia Brasil",
]
CONCURSOS_QUERIES = [
    "concurso publico TI analista de sistemas",
    "concurso publico tecnologia da informacao edital",
]


def format_section(title: str, queries: list[str]) -> str:
    seen_links = set()
    lines = [f"## {title}", ""]
    found_any = False
    for query in queries:
        for item in fetch_recent(query, hours=48, max_items=6):
            if item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            found_any = True
            lines.append(f"- {item['title']} ({item['source']})")
            lines.append(f"  {item['link']}")
    if not found_any:
        lines.append("Nada de novo relevante hoje.")
    lines.append("")
    return "\n".join(lines)


def format_jobs_section() -> str:
    lines = ["## Vagas Remotas de TI (Remote OK)", ""]
    jobs = fetch_recent_jobs(hours=48, max_items=8)
    if not jobs:
        lines.append("Nada de novo relevante hoje.")
    for job in jobs:
        lines.append(f"- {job['position']} @ {job['company']}")
        lines.append(f"  {job['url']}")
    lines.append("")
    return "\n".join(lines)


def build_body() -> str:
    parts = [f"Newsletter Computacao - {date.today().strftime('%d/%m/%Y')}", ""]
    parts.append(format_section("Noticias de Tecnologia/Computacao", NEWS_QUERIES))
    parts.append(format_jobs_section())
    parts.append(format_section("Concursos Publicos de TI", CONCURSOS_QUERIES))
    return "\n".join(parts)


def main():
    TMP_DIR.mkdir(exist_ok=True)
    body = build_body()
    today = date.today().isoformat()
    body_path = TMP_DIR / f"newsletter_{today}.txt"
    subject_path = TMP_DIR / "newsletter_subject.txt"

    body_path.write_text(body, encoding="utf-8")
    subject_path.write_text(
        f"Newsletter Computacao - {date.today().strftime('%d/%m/%Y')}", encoding="utf-8"
    )
    print(f"Corpo escrito em {body_path}")


if __name__ == "__main__":
    main()
