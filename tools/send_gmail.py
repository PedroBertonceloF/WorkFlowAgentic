"""
Envia um e-mail via Gmail API usando OAuth.

Uso:
    python send_gmail.py --to dest@example.com --subject "Assunto" --body-file corpo.txt
    python send_gmail.py --subject "Assunto" --body-file corpo.html --html

Se --to for omitido, usa RECIPIENT_EMAIL do .env.

Duas formas de autenticacao:
- Local (credentials.json / token.json): na primeira execucao abre o
  navegador para autorizar o app (escopo gmail.send) e salva o token em
  token.json para as proximas execucoes.
- CI/GitHub Actions (env vars): se GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET e
  GMAIL_REFRESH_TOKEN estiverem definidos, usa essas credenciais direto, sem
  tocar em nenhum arquivo local.
"""

import argparse
import base64
import os
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

load_dotenv(BASE_DIR / ".env")


def get_credentials() -> Credentials:
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def send_email(to: str, subject: str, body: str, html: bool = False) -> dict:
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    mime_type = "html" if html else "plain"
    message = MIMEText(body, mime_type, "utf-8")
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent


def main():
    parser = argparse.ArgumentParser(description="Envia e-mail via Gmail API")
    parser.add_argument("--to", default=os.getenv("RECIPIENT_EMAIL"), help="Destinatario")
    parser.add_argument("--subject", required=True, help="Assunto do e-mail")
    parser.add_argument("--body-file", required=True, help="Arquivo com o corpo do e-mail")
    parser.add_argument("--html", action="store_true", help="Trata o corpo como HTML")
    args = parser.parse_args()

    if not args.to:
        raise SystemExit("Destinatario nao informado (--to ou RECIPIENT_EMAIL no .env)")

    body = Path(args.body_file).read_text(encoding="utf-8")
    result = send_email(args.to, args.subject, body, html=args.html)
    print(f"Enviado. Message ID: {result.get('id')}")


if __name__ == "__main__":
    main()
