#!/usr/bin/env python3
"""
Bot de metricas de Vercel Web Analytics (sastrephoto.com).

Pensado para ejecutarse a diario desde GitHub Actions (ver fetch-metrics.yml),
mismo patron que el bot de metricas de Instagram (instagram-metrics-bot):
cada ejecucion pide a la API de Vercel los datos del DIA ANTERIOR completo
(00:00 a 24:00 UTC) y anade filas nuevas a dos CSV append-only:

  1. daily_totals.csv     - una fila por dia: visitantes y pageviews totales.
  2. daily_breakdown.csv  - una fila por dia y valor, para cuatro dimensiones:
                             pagina (route), de donde vienen (referrerHostname),
                             pais (country) y tipo de dispositivo (deviceType).

Se pide el dia anterior (no "las ultimas 24h" relativas al momento de
ejecucion) para que cada fila represente un dia natural completo y no un
trozo de dos dias distintos segun a que hora corra el cron.

Aviso importante: Vercel Web Analytics NO registra cuanto tiempo pasa un
visitante en cada pagina (no hay metrica de "time on page" ni de sesion) -
solo visitantes y pageviews, agregados por dimension. El "breakdown" por
pagina (route) es lo mas parecido a "donde se quedan mas": la pagina con mas
pageviews por visitante es la que mas se repite dentro de una misma visita,
pero no es una medida de tiempo real. analyze_metrics.py tiene instrucciones
explicitas de no inventar datos de tiempo en pagina.

Variables de entorno requeridas (configuradas como GitHub Actions Secrets):
    VERCEL_TOKEN        - Vercel Access Token (Settings -> Tokens), scope
                           Full Account o al equipo que tiene el proyecto.
    VERCEL_TEAM_ID       - ID del team de Vercel (empieza por "team_").
    VERCEL_PROJECT_ID    - ID del proyecto (empieza por "prj_").

Variables de entorno opcionales:
    BREAKDOWN_LIMIT      - cuantos valores top guardar por dimension y dia
                            (por defecto 10; el resto se agrupa en "Others"
                            del lado de la API, y no se guarda aqui).
"""

import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
TOTALS_CSV = REPO_ROOT / "daily_totals.csv"
BREAKDOWN_CSV = REPO_ROOT / "daily_breakdown.csv"

API_BASE = "https://api.vercel.com/v1/query/web-analytics"

TOTALS_CSV_HEADER = ["date_utc", "visitors", "pageviews"]
BREAKDOWN_CSV_HEADER = ["date_utc", "dimension", "value", "visitors", "pageviews"]

# dimension de la API de Vercel -> nombre que guardamos en el CSV (mismo
# nombre, aqui solo para tener la lista en un sitio).
DIMENSIONS = ["route", "referrerHostname", "country", "deviceType"]


def _get(path: str, token: str, params: dict) -> dict:
    resp = requests.get(
        f"{API_BASE}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if not resp.ok:
        print(f"  Respuesta de la API ({resp.status_code}): {resp.text}")
    resp.raise_for_status()
    return resp.json()


def append_csv_rows(path: Path, header: list[str], rows: list[list]):
    if not rows:
        return
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(header)
        writer.writerows(rows)


def fetch_totals(team_id: str, project_id: str, token: str, since: str, until: str) -> tuple[int, int]:
    data = _get(
        "visits/count",
        token,
        {"teamId": team_id, "projectId": project_id, "since": since, "until": until},
    ).get("data", {})
    return data.get("visitors", 0), data.get("pageviews", 0)


def fetch_breakdown(
    team_id: str, project_id: str, token: str, since: str, until: str, dimension: str, limit: int
) -> list[dict]:
    body = _get(
        "visits/aggregate",
        token,
        {
            "teamId": team_id,
            "projectId": project_id,
            "since": since,
            "until": until,
            "by": dimension,
            "limit": limit,
        },
    )
    return body.get("data", [])


def main():
    token = os.environ.get("VERCEL_TOKEN", "").strip()
    team_id = os.environ.get("VERCEL_TEAM_ID", "").strip()
    project_id = os.environ.get("VERCEL_PROJECT_ID", "").strip()
    if not token or not team_id or not project_id:
        sys.exit("Error: faltan VERCEL_TOKEN, VERCEL_TEAM_ID o VERCEL_PROJECT_ID en el entorno.")

    limit = int(os.environ.get("BREAKDOWN_LIMIT", "10"))

    # Dia anterior completo en UTC (si el cron corre a las 04:00 UTC de hoy,
    # pedimos el dia de ayer, ya cerrado del todo).
    today_utc = datetime.now(timezone.utc).date()
    target_day = today_utc - timedelta(days=1)
    since = target_day.isoformat()
    until = (target_day + timedelta(days=1)).isoformat()
    date_label = since

    print(f"Pidiendo metricas de Vercel Web Analytics para {date_label} (UTC)...")

    visitors, pageviews = fetch_totals(team_id, project_id, token, since, until)
    append_csv_rows(TOTALS_CSV, TOTALS_CSV_HEADER, [[date_label, visitors, pageviews]])
    print(f"  Totales del dia: {visitors} visitantes, {pageviews} pageviews")

    breakdown_rows = []
    for dimension in DIMENSIONS:
        print(f"  Desglose por {dimension}...")
        try:
            entries = fetch_breakdown(team_id, project_id, token, since, until, dimension, limit)
        except requests.RequestException as exc:
            print(f"  Aviso: no se pudo pedir el desglose por {dimension}: {exc}")
            continue
        for entry in entries:
            value = entry.get(dimension, "") or "(directo/desconocido)"
            breakdown_rows.append(
                [date_label, dimension, value, entry.get("visitors", 0), entry.get("pageviews", 0)]
            )

    append_csv_rows(BREAKDOWN_CSV, BREAKDOWN_CSV_HEADER, breakdown_rows)
    print(f"  {len(breakdown_rows)} filas anadidas a {BREAKDOWN_CSV.name}")


if __name__ == "__main__":
    main()
