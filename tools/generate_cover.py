"""
Gera a "capa" duotone da edicao via Kie.ai (opcional).

API assincrona da Kie.ai (unified Jobs API):
  1. POST {BASE}/api/v1/jobs/createTask  -> devolve data.taskId
  2. GET  {BASE}/api/v1/jobs/recordInfo?taskId=...  (poll ate state=success)
     -> data.resultJson = '{"resultUrls": ["https://..."]}'

Tudo opcional e com degradacao graciosa: sem KIE_API_KEY, ou se a geracao
falhar/estourar o tempo, devolve None e o e-mail usa a faixa duotone em CSS.
O modelo e configuravel por KIE_MODEL (default abaixo), pra ajustar sem mexer
no codigo caso o nome mude no marketplace da Kie.ai.

Uso:
    from generate_cover import generate_cover
    url = generate_cover("Engenharia de Software ganha forca com IA")  # ou None
"""

import json
import os
import time
import urllib.request

BASE_URL = os.getenv("KIE_BASE_URL", "https://api.kie.ai")
DEFAULT_MODEL = "google/nano-banana"
POLL_TIMEOUT_S = 90
POLL_INTERVAL_S = 4

# Prompt travado na identidade PBF: duotone navy + off-white, abstrato, SEM
# texto e SEM rostos, pra nunca competir com o conteudo nem parecer "arte de IA".
PROMPT_TEMPLATE = (
    "Minimalist abstract horizontal banner, wide 3:1 aspect ratio. Strict two-color "
    "duotone palette: deep navy (#1a3a5f) and off-white (#f7f7f7), with subtle sage "
    "(#687d6a) accents only. Flat geometric shapes evoking data flow, circuit traces "
    "and grids, editorial and calm. No text, no letters, no logos, no faces. Theme: {theme}."
)


def _post(url: str, api_key: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _get(url: str, api_key: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _extract_url(record: dict) -> str:
    """Procura a URL da imagem em formatos comuns de resposta da Kie.ai."""
    data = record.get("data", record) or {}
    result_json = data.get("resultJson") or data.get("result_json")
    if isinstance(result_json, str) and result_json.strip():
        try:
            result_json = json.loads(result_json)
        except json.JSONDecodeError:
            result_json = {}
    if isinstance(result_json, dict):
        for key in ("resultUrls", "result_urls", "imageUrls", "urls"):
            urls = result_json.get(key)
            if isinstance(urls, list) and urls:
                return urls[0]
        for key in ("resultUrl", "imageUrl", "url"):
            if isinstance(result_json.get(key), str):
                return result_json[key]
    return ""


def generate_cover(theme: str) -> str | None:
    api_key = os.getenv("KIE_API_KEY")
    if not api_key:
        return None
    model = os.getenv("KIE_MODEL") or DEFAULT_MODEL
    prompt = PROMPT_TEMPLATE.format(theme=theme.strip() or "software and computing")

    try:
        created = _post(f"{BASE_URL}/api/v1/jobs/createTask", api_key, {
            "model": model,
            "input": {"prompt": prompt, "image_size": "3:2", "output_format": "png"},
        })
    except Exception as exc:
        print(f"[cover] falha ao criar tarefa Kie.ai, usando fallback CSS: {exc}")
        return None

    task_id = (created.get("data") or {}).get("taskId") or (created.get("data") or {}).get("task_id")
    if not task_id:
        print(f"[cover] resposta sem taskId ({created.get('msg') or created}); fallback CSS.")
        return None

    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)
        try:
            record = _get(f"{BASE_URL}/api/v1/jobs/recordInfo?taskId={task_id}", api_key)
        except Exception as exc:
            print(f"[cover] falha no poll Kie.ai: {exc}")
            return None
        data = record.get("data") or {}
        state = str(data.get("state") or data.get("status") or "").lower()
        if state in ("success", "succeeded", "completed", "2"):
            url = _extract_url(record)
            if url:
                print(f"[cover] capa gerada: {url}")
                return url
            print("[cover] tarefa concluida sem URL; fallback CSS.")
            return None
        if state in ("fail", "failed", "error", "3"):
            print(f"[cover] geracao falhou ({data.get('failMsg') or 'sem detalhe'}); fallback CSS.")
            return None
    print("[cover] timeout aguardando a capa; fallback CSS.")
    return None


if __name__ == "__main__":
    print(generate_cover("inteligencia artificial e engenharia de software"))
