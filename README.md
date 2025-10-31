# PRACT1-BPS (Web Scraping)
Proyecto de la práctica 1 (M2.851) — Observatorio BPS.

## Estructura
- `source/`: código (scraper + parsers XLS)
- `dataset/`: CSV generados
- `docs/`: memoria y diagrama
- `logs/`: bitácora de ejecución
- `video/`: enlace al video

## Uso rápido
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m source.main robots
python -m source.main index --delay 2.0 --max-pages 3
# Luego usar URLs XLS de III.3 e II para:
# python -m source.main desempleo --xls-url "<URL_XLS_III_3>"
# python -m source.main recaudacion --xls-url "<URL_XLS_II>"