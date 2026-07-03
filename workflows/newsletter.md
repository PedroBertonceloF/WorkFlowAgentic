# Workflow: Newsletter Diária de Computação

## Objetivo
Todo dia, montar e enviar por e-mail um resumo com:
1. Notícias importantes da área de computação/tecnologia
2. Vagas remotas de tecnologia (Remote OK)
3. Concursos públicos relacionados a TI/computação

Destinatário: `pedroberto2005@gmail.com` (default em `.env` -> `RECIPIENT_EMAIL`,
ou secret `RECIPIENT_EMAIL` no GitHub Actions).

## Como roda
Este workflow é 100% determinístico (sem IA no loop) — nenhuma chamada a LLM é
necessária em tempo de execução. Isso permite rodar de graça no GitHub
Actions, todo dia, mesmo sem o computador do usuário ligado.

Execução automática: `.github/workflows/newsletter.yml`, cron diário às
16:00 UTC (12:00 horário de Cuiabá/Brasil).

## Fontes de conteúdo
- **Notícias e concursos**: Google News RSS (`tools/fetch_google_news.py`) —
  busca gratuita, sem API key, filtra itens das últimas 48h.
- **Vagas**: API pública do Remote OK (`tools/fetch_remoteok_jobs.py`) —
  filtra por tags relevantes de tech (dev, engineer, python, javascript,
  junior, etc.), últimas 48h. Nota: são vagas remotas/internacionais, não
  especificamente estágios no Brasil — não achamos fonte gratuita de RSS
  para vagas de estágio brasileiras (Indeed BR descontinuou RSS). Se
  aparecer uma fonte melhor no futuro, trocar aqui.

## Melhorias futuras (não implementadas ainda)
- Resumo real para notícias/concursos: Google News RSS não fornece
  snippet/descrição, só título. Daria pra visitar cada link e extrair a
  meta-descrição da página, mas é mais lento/frágil (cada site é
  diferente, pode bloquear scraping) — avaliar se vale a pena depois.

## Passo a passo (executado pelo tool, não por um agente)

1. `python tools/build_newsletter.py`
   - Busca as 3 categorias e escreve:
     - `.tmp/newsletter_<YYYY-MM-DD>.html` (corpo, HTML formatado)
     - `.tmp/newsletter_subject.txt` (assunto)
   - Se uma categoria não tiver nada relevante no dia, escreve "Nada de novo
     relevante hoje" em vez de inventar conteúdo.
   - Título de cada item é um link clicável (a URL não aparece no corpo),
     com fonte + tempo relativo ("há X horas") como metadado, e um resumo
     curto pras vagas (Remote OK fornece descrição; Google News RSS não).

2. `python tools/send_gmail.py --subject "$(cat .tmp/newsletter_subject.txt)" --body-file .tmp/newsletter_<data>.html --html`
   - Local: usa `credentials.json` + `token.json` (OAuth interativo na
     primeira vez).
   - GitHub Actions: usa os secrets `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
     `GMAIL_REFRESH_TOKEN` diretamente (sem tocar em arquivo local).

## Tools usados
- `tools/fetch_google_news.py` — busca RSS (notícias, concursos)
- `tools/fetch_remoteok_jobs.py` — busca API (vagas)
- `tools/build_newsletter.py` — monta o corpo do e-mail
- `tools/send_gmail.py` — envio via Gmail API

## Tratamento de erros
- Se uma busca falhar (rede/timeout), não travar o workflow inteiro — a
  seção correspondente fica vazia/marcada, as outras seguem normalmente.
- Se o envio falhar, o GitHub Actions marca o run como failed — checar em
  https://github.com/PedroBertonceloF/WorkFlowAgent/actions
- Se o refresh token expirar/for revogado, é preciso gerar um novo
  `token.json` localmente (rodando `send_gmail.py` sem env vars, que reabre o
  fluxo OAuth no navegador) e atualizar o secret `GMAIL_REFRESH_TOKEN` no
  GitHub.

## Notas / aprendizados
- O app OAuth (`newsletter-501317`) está em modo de teste no Google Cloud.
  Nesse modo, o Google pode expirar o refresh token em ~7 dias de
  inatividade da app em modo teste — como o Actions roda todo dia, o token é
  usado com frequência, então na prática deve continuar valendo. Se um dia o
  Action começar a falhar com erro de auth, o problema mais provável é esse:
  ou "Publicar" o app na tela de consentimento OAuth (remove o limite),
  ou gerar um novo refresh token.
- Credenciais (`credentials.json`, `token.json`, `.env`) NUNCA vão para o
  git — ficam só no `.gitignore` local. No GitHub Actions, os mesmos valores
  vivem como Repository Secrets (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
  `GMAIL_REFRESH_TOKEN`, `RECIPIENT_EMAIL`), criptografados pelo GitHub.
- Descartamos a ideia inicial de usar uma cloud routine do Claude Code
  (`/schedule`) porque exigiria comitar as credenciais do Gmail num
  repositório para o agente de nuvem acessar — GitHub Actions com secrets
  criptografados resolve o mesmo problema (roda sem o PC ligado) sem esse
  risco.
