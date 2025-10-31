# PRACT1-BPS (Web Scraping)
Proyecto de la práctica 1 (M2.851) — Observatorio BPS.

## Estructura
- `source/`: código (scraper + parsers XLS)
- `dataset/`: CSV generados
- `docs/`: memoria y diagrama
- `logs/`: bitácora de ejecución
- `video/`: enlace al video

## Uso rápido

# 1) Entorno
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) Chequeo robots (log informativo)
python -m source.main robots

# 3) Índice (páginas institucionales)
python -m source.main index \
  --pages "https://www.bps.gub.uy/1944/indicadores-de-la-seguridad-social.html" \
          "https://www.bps.gub.uy/bps/observatorio/cuadro.jsp?contentid=12780" \
  --delay 2 --max-pages 3

# 4) Series (reemplaza <URL_XLS_...> por los enlaces reales del índice)
python -m source.main desempleo   --xls-url "<URL_XLS_III_3>"
python -m source.main recaudacion --xls-url "<URL_XLS_II>"
- python -m source.main desempleo --xls-url "https://www.bps.gub.uy/bps/file/23307/1/iii_3_subsidio-por-desempleo.xls" --sheet "III.3.5 Altas Zona" 
- python -m source.main recaudacion --xls-url "https://www.bps.gub.uy/bps/file/23304/1/ii_recaudacion.xls" --sheet "II-0" 

# 5) Validación rápida
python source/validate.py

## Ética y licencias
- No se halló `robots.txt` público en `observatorio.bps.gub.uy` ni `www.bps.gub.uy` (ver `logs/robots.log`).
- Se aplicó *polite crawling*: User-Agent propio, `--delay`, sin login, sin evadir barreras técnicas.
- Fuente de datos: BPS (Indicadores de la Seguridad Social). Este repo publica un **dataset derivado** (metadatos + series tabulares de XLS) bajo **CC-BY 4.0**, citando a la fuente.
