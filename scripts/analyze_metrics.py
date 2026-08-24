#!/usr/bin/env python3
"""
Analiza los CSV de metricas de Vercel Web Analytics y escribe el resultado en
weekly_analysis.txt, usando la API de Claude directamente (Messages API) -
mismo patron que analyze_metrics.py de instagram-metrics-bot: sin pasar por
Cowork, para que todo el flujo semanal dependa solo de GitHub Actions.

Pensado para correr como paso dentro de weekly-report.yml, justo antes de
send_weekly_report.py, una vez por semana - lee los CSV que fetch-metrics.yml
ha ido dejando con snapshots diarios durante toda la semana.

Variables de entorno requeridas:
    ANTHROPIC_API_KEY   - API key de Anthropic (console.anthropic.com)

Variables de entorno opcionales:
    ANTHROPIC_MODEL     - modelo a usar (por defecto claude-sonnet-5)
"""

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
TOTALS_CSV = REPO_ROOT / "daily_totals.csv"
BREAKDOWN_CSV = REPO_ROOT / "daily_breakdown.csv"
ANALYSIS_PATH = REPO_ROOT / "weekly_analysis.txt"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Cuantos dias como maximo se mandan en el resumen de totales - de sobra para
# ver tendencia (4 semanas) sin que el prompt crezca sin limite a medida que
# el CSV se acumula (es append-only, solo crece).
MAX_TOTALS_DAYS = 28
# El desglose por dimension solo se manda de la ultima semana - un desglose
# de 4 semanas por 4 dimensiones seria demasiado ruido para un analisis breve.
MAX_BREAKDOWN_DAYS = 7

PROMPT_TEMPLATE = """Eres un analista que le prepara a Miguel Ángel un resumen semanal breve sobre \
el trafico de su web sastrephoto.com, a partir de datos de Vercel Web Analytics. Te paso un resumen \
de visitantes/pageviews por dia (ya procesado, no el CSV en bruto) y un desglose de la ultima semana \
por pagina, procedencia (referrer), pais y tipo de dispositivo.

Aviso importante sobre los datos: Vercel Web Analytics NO mide cuanto tiempo pasa un visitante en \
cada pagina ni tiene datos de sesion - solo visitantes unicos y pageviews, agregados por dimension. \
NUNCA inventes ni menciones "tiempo en pagina", "duracion de sesion" ni nada parecido: esa metrica no \
existe en estos datos. Como aproximacion (dejalo claro si lo usas), pageviews por visitante en una \
pagina puede sugerir que se navega mas dentro de ella, pero no es tiempo real.

Tu tarea: escribir un analisis en español, de 120 a 200 palabras, en PROSA CONTINUA - nada de \
markdown, viñetas, tablas ni encabezados, porque este texto se manda tal cual como mensaje de texto \
por Telegram. Debe sonar como si se lo contaras a Miguel en persona: una frase resumen y luego 3 o 4 \
puntos concretos y utiles.

Cosas que deberias mirar si los datos lo permiten:
- Como ha ido el trafico dia a dia esta semana (subiendo, bajando, estable, con picos o dias flojos) \
- no te limites a comparar el ultimo dia contra el anterior, mira la serie completa si hay datos.
- Que paginas se llevan mas visitas y cuales casi nada - si "/" domina mucho sobre el resto, dilo.
- De donde viene el trafico (referrers): si la mayoria es directo/sin referrer, si destaca alguna red \
social o buscador.
- Cualquier patron que destaque en pais o tipo de dispositivo (movil vs escritorio), solo si es claro.
- Si hay muy pocos datos todavia (pocos dias o pocas visitas) para sacar conclusiones firmes, dilo \
explicitamente en vez de forzar una tendencia con muy poca muestra.

--- visitantes y pageviews por dia (mas antiguo primero) ---
{totals_summary}

--- desglose de la ultima semana por dimension (pagina, procedencia, pais, dispositivo) ---
{breakdown_summary}

Escribe solo el texto del analisis, sin ningun comentario tuyo antes o despues."""


def summarize_totals(path: Path, max_days: int = MAX_TOTALS_DAYS) -> str:
    if not path.exists():
        return "(no existe todavia)"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "(vacio)"
    rows = sorted(rows, key=lambda r: r.get("date_utc", ""))[-max_days:]
    lineas = [f"{r['date_utc']}: {r['visitors']} visitantes, {r['pageviews']} pageviews" for r in rows]
    return "\n".join(lineas)


def summarize_breakdown(path: Path, max_days: int = MAX_BREAKDOWN_DAYS) -> str:
    if not path.exists():
        return "(no existe todavia)"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "(vacio)"

    dias_disponibles = sorted({r.get("date_utc", "") for r in rows})[-max_days:]
    rows = [r for r in rows if r.get("date_utc", "") in dias_disponibles]

    # Agrupa por dimension, sumando visitors/pageviews de cada valor a lo
    # largo de los dias seleccionados (para no repetir un bloque por dia).
    agregados: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        dim = r.get("dimension", "")
        val = r.get("value", "")
        agregados[dim][val][0] += int(r.get("visitors", 0) or 0)
        agregados[dim][val][1] += int(r.get("pageviews", 0) or 0)

    bloques = []
    for dim, valores in agregados.items():
        top = sorted(valores.items(), key=lambda kv: kv[1][0], reverse=True)[:8]
        lineas = [f"  {val}: {v} visitantes, {pv} pageviews" for val, (v, pv) in top]
        bloques.append(f"{dim} (ultimos {len(dias_disponibles)} dias):\n" + "\n".join(lineas))
    return "\n\n".join(bloques)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        sys.exit("Error: falta ANTHROPIC_API_KEY en el entorno.")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5").strip()

    totals_summary = summarize_totals(TOTALS_CSV)
    breakdown_summary = summarize_breakdown(BREAKDOWN_CSV)

    if totals_summary in ("(no existe todavia)", "(vacio)") and breakdown_summary in (
        "(no existe todavia)",
        "(vacio)",
    ):
        sys.exit("Error: no hay CSV que analizar todavia (fetch_metrics.py deberia correr antes que este script).")

    prompt = PROMPT_TEMPLATE.format(totals_summary=totals_summary, breakdown_summary=breakdown_summary)

    print(f"Pidiendo el analisis a {model}...")
    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            # Igual que en el bot de Instagram: margen de tokens de sobra
            # para el bloque de "thinking" antes de la respuesta final.
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    if not resp.ok:
        print(f"Respuesta de la API ({resp.status_code}): {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    texto = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
    if not texto:
        sys.exit(f"Error: la respuesta de la API no traia texto: {data}")

    ANALYSIS_PATH.write_text(texto + "\n", encoding="utf-8")
    print(f"Analisis escrito en {ANALYSIS_PATH.name} ({len(texto.split())} palabras aprox.)")


if __name__ == "__main__":
    main()
