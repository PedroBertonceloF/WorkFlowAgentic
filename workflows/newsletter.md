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
- **Notícias**: Google News RSS (`tools/fetch_google_news.py`) + Hacker News
  via API Algolia (`tools/fetch_hackernews.py`, filtra por pontuação mínima) +
  dev.to via API pública (`tools/fetch_devto.py`, já traz descrição). Todas
  gratuitas, sem API key, filtram itens das últimas 48h.
- **Concursos**: Google News RSS (`tools/fetch_google_news.py`).
- **Vagas remotas (internacional)**: API pública do Remote OK
  (`tools/fetch_remoteok_jobs.py`) — filtra por tags relevantes de tech, 48h.
- **Vagas tech no Brasil**: RSS do ProgramaThor
  (`tools/fetch_programathor.py`) — prioriza estágio/júnior/pleno pela tag de
  senioridade no título, últimas 72h. Foi a fonte gratuita e confiável de
  vagas BR que faltava (Indeed BR descontinuou RSS; Vagas.com/Catho/Gupy não
  expõem RSS público útil).

## Resumos (IA opcional, com fallback determinístico)
`tools/summarize.py` gera um resumo de 1 linha em PT-BR para itens que só têm
título (Google News e Hacker News não trazem descrição):
- **Com `GEMINI_API_KEY`**: uma única chamada em lote ao Gemini
  (`gemini-2.5-flash`, tier gratuito), com grounding do Google Search para
  resumir de forma factual. Mesmo padrão de cliente do `aquaia-ufms`.
- **Sem chave / se o Gemini falhar**: busca a `og:description` /
  `<meta name="description">` da página como fallback. Links do Google News
  redirecionam por JS e não expõem meta útil, então nesses casos o item sai só
  com título (como antes). Nenhuma falha de resumo cancela o e-mail.

## Melhorias futuras (não implementadas ainda)
- Curadoria/ranking semântico por IA (hoje a IA só resume, não prioriza).
- Seguir o redirect do Google News para pegar a URL real e resumir com base no
  texto do artigo (hoje o resumo desses itens depende do grounding do Gemini).

## Passo a passo (executado pelo tool, não por um agente)

1. `python tools/build_newsletter.py`
   - Carrega `data/sent_links.json` (log de links já enviados nos últimos 7
     dias) e descarta itens repetidos das buscas.
   - Busca as 3 categorias e escreve:
     - `.tmp/newsletter_<YYYY-MM-DD>.html` (corpo, HTML formatado)
     - `.tmp/newsletter_subject.txt` (assunto)
   - Se uma categoria não tiver nada relevante no dia (ou tudo já foi
     enviado antes), escreve "Nada de novo relevante hoje" em vez de
     inventar conteúdo. Se uma busca falhar (rede/timeout), essa categoria
     mostra "Não foi possível buscar essa categoria hoje" e o resto do
     e-mail segue normalmente — uma falha parcial nunca cancela o envio.
   - Título de cada item é um link clicável (a URL não aparece no corpo),
     com fonte + tempo relativo ("há X horas") como metadado, e um resumo
     curto pras vagas (Remote OK fornece descrição; Google News RSS não).
   - Atualiza `data/sent_links.json` com os links incluídos nesta edição
     (e remove entradas com mais de 7 dias).

2. `python tools/send_gmail.py --subject "$(cat .tmp/newsletter_subject.txt)" --body-file .tmp/newsletter_<data>.html --html`
   - Local: usa `credentials.json` + `token.json` (OAuth interativo na
     primeira vez).
   - GitHub Actions: usa os secrets `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
     `GMAIL_REFRESH_TOKEN` diretamente (sem tocar em arquivo local).

3. Se `data/sent_links.json` mudou, o Action commita e dá push desse
   arquivo de volta pro repositório (usando `GITHUB_TOKEN`, permissão
   `contents: write` declarada no próprio workflow).

## Tools usados
- `tools/fetch_google_news.py` — busca RSS (notícias, concursos)
- `tools/fetch_hackernews.py` — busca stories no HN (API Algolia)
- `tools/fetch_devto.py` — busca artigos no dev.to (API pública)
- `tools/fetch_remoteok_jobs.py` — busca vagas remotas internacionais (API)
- `tools/fetch_programathor.py` — busca vagas tech no Brasil (RSS)
- `tools/summarize.py` — resumos (Gemini opcional + fallback meta-descrição)
- `tools/dedup_log.py` — carrega/atualiza/poda o log de links já enviados
- `tools/build_newsletter.py` — monta o corpo do e-mail
- `tools/send_gmail.py` — envio via Gmail API

## Design
Identidade PBF (ver `.claude/LOGO.png`), regra 60-30-10: fundo off-white
`#F7F7F7`, tinta/links navy `#1A3A5F`, hairlines support-blue `#AABCCF`,
metadados em accent-grey `#687D6A`. Cabeçalho com wordmark "pbf" + título
"Newsletter de Computação", seções com ícone + título navy, itens com título
linkado + fonte/tempo + resumo. Fonte Poppins (via `<style>`) com fallback de
sistema. Suporta dark mode via `prefers-color-scheme`.

## Tratamento de erros
- Se uma busca falhar (rede/timeout), não travar o workflow inteiro — a
  seção correspondente fica marcada como indisponível, as outras seguem
  normalmente e o e-mail é enviado do mesmo jeito.
- Se o envio falhar, o GitHub Actions marca o run como failed — checar em
  https://github.com/PedroBertonceloF/WorkFlowAgentic/actions
- Se o commit do log de dedup falhar por permissão, checar Settings →
  Actions → General → Workflow permissions → "Read and write permissions"
  (o workflow já declara `permissions: contents: write`, mas uma política
  de organização pode sobrescrever isso).
- Se o refresh token expirar/for revogado, é preciso gerar um novo
  `token.json` localmente (rodando `send_gmail.py` sem env vars, que reabre o
  fluxo OAuth no navegador) e atualizar o secret `GMAIL_REFRESH_TOKEN` no
  GitHub.

## Notas / aprendizados
- O app OAuth (`newsletter-501317`): recomendado publicar (Google Auth
  Platform → Público-alvo → "Publicar app") pra eliminar o risco de
  expiração do refresh token por ficar em modo de teste. Se ainda estiver
  em modo teste e o Action começar a falhar com erro de auth, esse é o
  primeiro lugar a checar.
- Credenciais (`credentials.json`, `token.json`, `.env`) NUNCA vão para o
  git — ficam só no `.gitignore` local. No GitHub Actions, os mesmos valores
  vivem como Repository Secrets (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
  `GMAIL_REFRESH_TOKEN`, `RECIPIENT_EMAIL`), criptografados pelo GitHub.
- `GEMINI_API_KEY` (opcional): habilita os resumos por IA. É gratuito
  (Google AI Studio) e roda em 1 chamada/dia, bem dentro do tier grátis. Sem
  ele, o newsletter usa o fallback de meta-descrição. `GEMINI_MODEL` é
  opcional (default `gemini-2.5-flash`).
- Descartamos a ideia inicial de usar uma cloud routine do Claude Code
  (`/schedule`) porque exigiria comitar as credenciais do Gmail num
  repositório para o agente de nuvem acessar — GitHub Actions com secrets
  criptografados resolve o mesmo problema (roda sem o PC ligado) sem esse
  risco.
