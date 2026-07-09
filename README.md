# 📬 WorkFlowAgentic

Agente que monta e envia, **todo dia às 12h**, uma newsletter de tecnologia por e-mail — sem depender de nenhuma máquina ligada. Roda inteiramente em **GitHub Actions** (cron), com IA para resumir as notícias e um fallback determinístico para nunca falhar o envio.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="GitHub Actions" src="https://img.shields.io/badge/GitHub_Actions-cron-2088FF?logo=githubactions&logoColor=white">
  <img alt="Gmail API" src="https://img.shields.io/badge/Gmail_API-OAuth2-EA4335?logo=gmail&logoColor=white">
  <img alt="Gemini" src="https://img.shields.io/badge/Gemini-resumo_por_IA-8E75B2?logo=googlegemini&logoColor=white">
</p>

## O que ele faz

Toda edição da newsletter combina cinco fontes em quatro seções:

| Seção | Fonte |
|---|---|
| 📰 Notícias de Tecnologia | Google News RSS, Hacker News, dev.to |
| 🇧🇷 Vagas Tech no Brasil | ProgramaThor |
| 💼 Vagas Remotas de TI | Remote OK |
| 📋 Concursos Públicos de TI | Google News RSS |

- **Deduplicação com janela de 7 dias** — cada link enviado fica registrado em `data/sent_links.json`; o workflow só considera itens das últimas 48h e nunca repete o que já foi mandado.
- **Resumo por IA (opcional)** — se `GEMINI_API_KEY` estiver configurada, os títulos são resumidos em lote via Gemini; sem a chave, o pipeline cai automaticamente para um resumo determinístico (meta-descrição da página) e continua funcionando normalmente.
- **E-mail responsivo com dark mode** — HTML gerado com CSS inline e `prefers-color-scheme`, pensado pra renderizar bem em qualquer cliente de e-mail.
- **Resiliente por seção** — se uma fonte falhar (ex: RSS fora do ar), as demais seções continuam sendo geradas normalmente.

## Arquitetura

```
tools/
├── fetch_google_news.py     # RSS: notícias + concursos
├── fetch_hackernews.py      # Hacker News (score mínimo configurável)
├── fetch_devto.py           # dev.to
├── fetch_remoteok_jobs.py   # Remote OK
├── fetch_programathor.py    # vagas tech no Brasil
├── dedup_log.py             # janela de 7 dias, persistida em data/sent_links.json
├── summarize.py             # resumo em lote via Gemini + fallback determinístico
├── build_newsletter.py      # monta o HTML final (orquestra tudo acima)
└── send_gmail.py            # envia via Gmail API (OAuth2)

.github/workflows/newsletter.yml   # cron diário (16:00 UTC / 12:00 América/Cuiabá)
```

O workflow roda `build_newsletter.py` → `send_gmail.py`, e ao final commita de volta o `data/sent_links.json` atualizado (`[skip ci]`, evitando loop).

## Rodando localmente

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha RECIPIENT_EMAIL e as credenciais do Gmail
python tools/build_newsletter.py   # gera .tmp/newsletter_<data>.html
python tools/send_gmail.py --subject "..." --body-file .tmp/newsletter_<data>.html --html
```

Na primeira execução local, o fluxo OAuth do Gmail abre o navegador para gerar `credentials.json`/`token.json` (nunca commitados — estão no `.gitignore`).

## Segredos

Em produção (GitHub Actions), nenhuma credencial fica no código: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GEMINI_API_KEY` e `RECIPIENT_EMAIL` são todos **Repository Secrets** criptografados, injetados só em tempo de execução (ver `.github/workflows/newsletter.yml`).

## Autor

[Pedro Bertoncelo](https://github.com/PedroBertonceloF) — Ciência da Computação (UFMS)
