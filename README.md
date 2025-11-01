# PRACT1-BPS (Web Scraping)
**Materia - M2.851 - Tipología y ciclo de vida de los datos - Aula 4**
**Proyecto de la práctica 1 -  — Observatorio BPS.**
**Última actualización:** 2025-10-31

## Integrantes
- Sebastian Serrentino Mangino (Seba) – <colocar email UOC>
- Alberto Mochon Paredes – <colocar email UOC>


## Estructura del repositorio
```
.
├─ source/                 # Código del scraper (CLI con subcomandos)
│  ├─ main.py              # Punto de entrada: `python -m source.main <cmd>`
│  ├─ crawl_index.py       # Descubrimiento/filtrado de enlaces
│  ├─ parse_series.py      # Descarga y parsing de tablas (HTML/XLS(X))
│  ├─ robots_check.py      # Verificación y registro de robots.txt
│  ├─ settings.py          # Parámetros (UA, delays, timeouts, rutas)
│  └─ utils.py             # Utilidades comunes
├─ dataset/                # CSV listos para PRACT2 (y para Zenodo)
├─ logs/                   # Logs de ejecución (robots, index, descargas)
├─ docs/
│  ├─ memoria_PRACT1.md    # Memoria con 11 apartados (ver más abajo)
│  └─ tabla_contribuciones.csv  # Matriz de contribución por integrante
├─ requirements.txt
├─ README.md
└─ video/
   └─ enlace_video.txt     # URL al vídeo (≤ 10 min)
```

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

## Zenodo (DOI)
- **Depósito**: sube los CSV de `/dataset` y el `README.md` a un **nuevo registro** de Zenodo.
- **DOI**: copia aquí el DOI final: `10.5281/zenodo.xxxxxx` y añádelo a la **memoria** y al encabezado del vídeo.
- **Licencia sugerida del dataset**: CC BY 4.0 u ODbL, según el origen/mezcla.

## Vídeo (≤10 min)
- Incluir una demo corta: `robots → index → (desempleo|recaudacion|asignacion) → dataset → Zenodo`.
- Ambos integrantes deben aparecer en algún momento.
- Coloca el enlace en `video/enlace_video.txt` y en la **memoria**.

## Ética y licencias
- No se halló `robots.txt` público en `observatorio.bps.gub.uy` ni `www.bps.gub.uy` (ver `logs/robots.log`).
- Se aplicó *polite crawling*: User-Agent propio, `--delay`, sin login, sin evadir barreras técnicas.
- Fuente de datos: BPS (Indicadores de la Seguridad Social). Este repo publica un **dataset derivado** (metadatos + series tabulares de XLS) bajo **CC-BY 4.0**, citando a la fuente.

## Buenas prácticas implementadas
- **User‑Agent propio**, **retardos** configurables, **timeouts** y **reintentos** exponenciales.
- **Respeto de robots.txt** y registro explícito en logs.
- **Modularidad** del código y **comentarios** concisos.
- **Limitaciones conocidas**: algunos servidores bloquean `HEAD`; se usa fallback GET controlado. Páginas con iframes/JS pueden requerir estrategia alternativa.

## Créditos / Propiedad intelectual
- Autoría del código: integrantes.
- Terceros: mencionar bibliografía, documentación y paquetes utilizados (licencias). Detallar en la **memoria**.
