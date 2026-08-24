#!/usr/bin/env python3
"""
Manda el analisis semanal de trafico (weekly_analysis.txt) por Telegram: el
texto completo (sendMessage) y el mismo texto convertido a audio con
edge-tts (sendAudio) - mismo patron que send_weekly_audio.py de
instagram-metrics-bot, reutilizando la misma voz por defecto.

Pensado para ejecutarse desde GitHub Actions, en weekly-report.yml, justo
despues de analyze_metrics.py (necesita que el analisis ya este escrito en
el repo antes de correr).

Para no reenviar el mismo texto/audio si el workflow se ejecuta mas de una
vez antes de que haya analisis nuevo, se guarda un hash del ultimo texto
enviado en `.last_sent_analysis_hash` y se compara en cada ejecucion (un
solo hash para los dos envios: si el texto no cambio, tampoco cambia el
audio que saldria de el).

Variables de entorno requeridas (GitHub Actions Secrets):
    TELEGRAM_BOT_TOKEN   - token del bot de Telegram (el mismo que tts-telegram-bot
                            e instagram-metrics-bot)
    TELEGRAM_CHAT_ID     - chat_id al que mandar el reporte

Variables de entorno opcionales:
    TTS_VOICE            - voz de edge-tts (por defecto es-ES-AlvaroNeural,
                            la misma que usa tts-telegram-bot por defecto)
"""

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import edge_tts
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


def send_audio_telegram(audio_path: str, token: str, chat_id: str):
    with open(audio_path, "rb") as audio:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendAudio",
            data={"chat_id": chat_id, "title": "Reporte semanal de sastrephoto.com"},
            files={"audio": audio},
            timeout=60,
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

    print("Mandando el texto por Telegram...")
    send_text_telegram(HEADER + texto, token, chat_id)

    voz = os.environ.get("TTS_VOICE", "es-ES-AlvaroNeural")
    print(f"Generando audio con la voz {voz}...")

    ruta_audio = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            ruta_audio = tmp.name

        import asyncio

        async def generar():
            communicate = edge_tts.Communicate(texto, voz)
            await communicate.save(ruta_audio)

        asyncio.run(generar())

        print("Mandando el audio por Telegram...")
        send_audio_telegram(ruta_audio, token, chat_id)
        print("Enviado correctamente (texto + audio).")
    finally:
        if ruta_audio and os.path.exists(ruta_audio):
            os.remove(ruta_audio)

    HASH_MARKER_PATH.write_text(texto_hash, encoding="utf-8")


if __name__ == "__main__":
    main()
