#!/usr/bin/env python3
"""
Manda el analisis semanal de trafico (weekly_analysis.txt) por Telegram, como
mensaje de texto - version simplificada, solo texto, del bot de audio de
instagram-metrics-bot (send_weekly_audio.py). El reporte de Vercel es breve
a proposito, asi que no hace falta convertirlo a audio ni mandar grafico;
si mas adelante quieres eso tambien, se puede anadir siguiendo el mismo
patron que send_weekly_chart.py del bot de Instagram.

Pensado para ejecutarse desde GitHub Actions, en weekly-report.yml, justo
despues de analyze_metrics.py (necesita que el analisis ya este escrito en
el repo antes de correr).

Para no reenviar el mismo texto si el workflow se ejecuta mas de una vez
antes de que haya analisis nuevo, se guarda un hash del ultimo texto enviado
en `.last_sent_analysis_hash` y se compara en cada ejecucion.

Variables de entorno requeridas (GitHub Actions Secrets):
    TELEGRAM_BOT_TOKEN   - token del bot de Telegram (el mismo que tts-telegram-bot
                            e instagram-metrics-bot)
    TELEGRAM_CHAT_ID     - chat_id al que mandar el reporte
"""

import hashlib
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_PATH = REPO_ROOT / "weekly_analysis.txt"
HASH_MARKER_PATH = REPO_ROOT / ".last_sent_analysis_hash"

HEADER = "📊 Reporte semanal de sastrephoto.com (Vercel Analytics)\n\n"


def send_text_telegram(texto: str, token: str, chat_id: str):
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": texto[:4096]},
        timeout=30,
    )
    if not resp.ok:
        print(f"Respuesta de Telegram ({resp.status_code}): {resp.text}")
    resp.raise_for_status()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        sys.exit("Error: faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el entorno.")

    if not ANALYSIS_PATH.exists():
        print(f"No existe {ANALYSIS_PATH.name} todavia - nada que mandar. Saliendo sin error.")
        return

    texto = ANALYSIS_PATH.read_text(encoding="utf-8").strip()
    if not texto:
        print(f"{ANALYSIS_PATH.name} esta vacio - nada que mandar.")
        return

    texto_hash = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    hash_anterior = HASH_MARKER_PATH.read_text(encoding="utf-8").strip() if HASH_MARKER_PATH.exists() else ""
    if texto_hash == hash_anterior:
        print("El analisis no ha cambiado desde el ultimo envio - no se manda un reporte duplicado.")
        return

    print("Mandando el reporte por Telegram...")
    send_text_telegram(HEADER + texto, token, chat_id)
    print("Enviado correctamente.")

    HASH_MARKER_PATH.write_text(texto_hash, encoding="utf-8")


if __name__ == "__main__":
    main()
