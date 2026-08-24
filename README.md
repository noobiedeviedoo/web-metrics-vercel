# Bot de metricas de Vercel Analytics (sastrephoto.com)

## Objetivo

Cada dia, pide a la API de Vercel Web Analytics los datos de trafico de
sastrephoto.com (visitantes, pageviews, paginas mas vistas, de donde viene el
trafico, pais, tipo de dispositivo) del dia anterior, y los guarda en dos CSV
dentro de este mismo repo — un snapshot diario, igual que hace
`instagram-metrics-bot` con las metricas de Instagram. Con ese historico,
Claude (o cualquier otra herramienta) puede leer la evolucion en el tiempo.
Una vez a la semana se manda un analisis breve por Telegram, usando el mismo
bot de texto (`tts-telegram-bot`) que ya usa el bot de Instagram.

Es un proyecto independiente del frontend (`sastrephotoweb-frontend`) y del
bot de Instagram a proposito — cada uno con su propio repo, su propio cron y
sus propios secrets, para que un fallo en uno no afecte a los demas.

**Aviso importante sobre los datos:** Vercel Web Analytics no mide cuanto
tiempo pasa un visitante en cada pagina ni tiene datos de sesion — solo
visitantes unicos y pageviews, agregados por dimension (pagina, procedencia,
pais, dispositivo). No hay forma de saber "en que paginas se quedan mas
tiempo" con esta fuente de datos; lo mas cercano es ver que paginas se llevan
mas pageviews.

## Arquitectura

**Entorno:** GitHub Actions (gratuito, sin mantenimiento, no depende de que
tengas el ordenador encendido) — igual que los otros bots.

**Frecuencia:** cron diario, 04:00 UTC (`.github/workflows/fetch-metrics.yml`)
para la recogida de metricas del dia anterior. El reporte (analisis breve por
texto) se manda una vez a la semana, lunes 06:30 UTC
(`.github/workflows/weekly-report.yml`). Puedes cambiar cualquiera de los dos
crons o lanzarlos a mano desde la pestana Actions de GitHub
(`workflow_dispatch`).

**Datos guardados:**
- `daily_totals.csv` — una fila por dia: visitantes y pageviews totales.
- `daily_breakdown.csv` — una fila por dia y valor, para cuatro dimensiones:
  `route` (pagina), `referrerHostname` (de donde viene el trafico), `country`
  y `deviceType`. Por defecto los 10 valores top de cada dimension y dia (el
  resto lo agrupa la propia API de Vercel en "Others" y no se guarda).

Ambos CSV son de solo-anadir (append-only), con `merge=union` en
`.gitattributes` para que nunca haya conflictos de git si se ejecuta mas de
una vez seguida.

## Puesta en marcha (pasos que tienes que hacer tu)

### 1. Crear el repositorio en GitHub

Esta carpeta todavia no tiene `git init`. Dentro de la carpeta:

```
git init
git add .
git commit -m "Bot de metricas de Vercel: version inicial"
```

Crea un repositorio vacio en GitHub (puede ser privado) y anade el remoto:

```
git remote add origin <URL-de-tu-repo>
git branch -M main
git push -u origin main
```

### 2. Crear un Access Token de Vercel

En Vercel: click en tu avatar (arriba a la derecha, cuenta personal, no el
team) → **Settings** → **Tokens** → **Create Token**.

- **Scope:** elige **Full Account** (o el team `MASG's projects` si te deja
  elegir uno concreto) — no lo limites a un solo proyecto, o volveremos a
  tener el problema que tuvimos con el conector de Claude.
- **Expiration:** ponle una fecha lejana (p.ej. 1 año) y apunta cuando toca
  renovarlo, porque GitHub Actions no te va a avisar solo.

Copia el token — solo se muestra una vez.

### 3. Configurar los Secrets del repo

En GitHub: **Settings → Secrets and variables → Actions → New repository
secret**. Anade:

- `VERCEL_TOKEN` — el token que acabas de crear.
- `VERCEL_TEAM_ID` — `team_A9hufkzbUQpzx0s7KZKhLkzY` (el ID del team `MASG's
  projects`).
- `VERCEL_PROJECT_ID` — `prj_SmOB27Y5ji7wlipmOlNFrUcCmHFy` (el ID del proyecto
  `sastrephotoweb-frontend`).
- `ANTHROPIC_API_KEY` — puedes reutilizar la misma que ya creaste para
  `instagram-metrics-bot`, o crear una nueva en
  [console.anthropic.com](https://console.anthropic.com/settings/keys). Coste:
  una llamada semanal a un par de CSV pequeños, del orden de centimos al mes.
- `TELEGRAM_BOT_TOKEN` — el token de tu bot `tts-telegram-bot` (el mismo que
  tienes en `BOTS/tts-telegram-bot/.env` y que ya usa `instagram-metrics-bot`).
- `TELEGRAM_CHAT_ID` — tu chat_id de Telegram (el mismo que ya usas en los
  otros bots).

### 4. Primera ejecucion manual

Pestana **Actions** del repo → **Recoger metricas de Vercel Analytics
(programado)** → **Run workflow**. Revisa el log: deberia decirte cuantos
visitantes/pageviews encontro para el dia anterior y cuantas filas anadio al
desglose.

Espera a que este workflow haya corrido al menos un par de dias (para tener
algo de historico) antes de lanzar a mano **Mandar reporte semanal de Vercel
Analytics (Telegram)** — si lo lanzas con muy pocos datos, el analisis de
Claude lo va a decir explicitamente en vez de inventar una tendencia.

## ¿Y si quiero pedirte un analisis fuera de la rutina semanal?

Puedo leer `daily_totals.csv` y `daily_breakdown.csv` cuando quieras, en
cualquier conversacion normal con Claude, y darte un analisis al momento — no
hace falta esperar al lunes.

## Estructura del repo

```
vercel-metrics-bot/
├── scripts/
│   ├── fetch_metrics.py       # Pide metricas del dia anterior y las anade a los CSV
│   ├── analyze_metrics.py     # Le pasa los CSV a la API de Claude y escribe weekly_analysis.txt
│   └── send_weekly_report.py  # Manda weekly_analysis.txt por Telegram (texto)
├── .github/workflows/
│   ├── fetch-metrics.yml      # Cron diario: solo actualiza los CSV (snapshot del dia)
│   └── weekly-report.yml      # Cron semanal: genera el analisis y lo manda por Telegram
├── daily_totals.csv           # Se crea solo en la primera ejecucion
├── daily_breakdown.csv        # Se crea solo en la primera ejecucion
├── weekly_analysis.txt        # Lo escribe analyze_metrics.py cada semana
├── .last_sent_analysis_hash   # Lo escribe weekly-report.yml, evita duplicar el envio
├── requirements.txt
├── .env.example
├── .gitattributes
└── .gitignore
```
