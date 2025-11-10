# PRACT1-BPS (Web Scraping)
**Materia - M2.851 - Tipología y ciclo de vida de los datos - Aula 4**
**Proyecto de la práctica 1 -  — Observatorio BPS.**
**Última actualización:** 2025-10-31

## Integrantes
- Sebastian Serrentino Mangino – sserrentino@uoc.edu
- Alberto Mochon Paredes – amochon@uoc.edu


## Estructura del repositorio
```
.
├─ source/                 # Código del scrapper (CLI con subcomandos)
│  ├─ main.py              # Punto de entrada: `python -m source.main <cmd>`
│  ├─ crawl_index.py       # Descubrimiento/filtrado de enlaces
│  ├─ parse_series.py      # Descarga y parsing de tablas (HTML/XLS(X))
│  ├─ robots_check.py      # Verificación y registro de robots.txt
│  ├─ settings.py          # Parámetros (UA, delays, timeouts, rutas)
│  ├─ utils.py             # Utilidades comunes
│  └─ demo_spa.py          # Demostración para scraping de una SPA
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

# 1.1) Navegador Chrome y Driver

- Este script está configurado para buscar estos archivos en las siguientes rutas (modificar source/demo_spa.py si se instalan en otro lugar):
    - Driver: C:\chrome-testing\chromedriver-win64\chromedriver.exe
    - Navegador: C:\chrome-testing\chrome-win64\chrome.exe
    - Fuente Chrome Driver:= https://storage.googleapis.com/chrome-for-testing-public/142.0.7444.61/win64/chromedriver-win64.zip
    - Fuente Chrome:= https://storage.googleapis.com/chrome-for-testing-public/142.0.7444.61/win64/chrome-win64.zip

# 2) Chequeo robots (log informativo), verifica los archivos robots.txt de los dominios objetivo (TARGETS).
python -m source.main robots

# 3) Índice (páginas institucionales)
python -m source.main index --pages "https://www.bps.gub.uy/1944/indicadores-de-la-seguridad-social.html" "https://www.bps.gub.uy/bps/observatorio/cuadro.jsp?contentid=12780" --delay 2 --max-pages 3

# 4) Series (Se deben reemplazar las url's por los enlaces reales del índice)
- python -m source.main desempleo|recaudacion --xls-url "enlace_real" --sheet "nombre_hoja"
    - python -m source.main desempleo --xls-url "https://www.bps.gub.uy/bps/file/23307/1/iii_3_subsidio-por-desempleo.xls" --sheet "III.3.5 Altas Zona" 
    - python -m source.main recaudacion --xls-url "https://www.bps.gub.uy/bps/file/23304/1/ii_recaudacion.xls" --sheet "II-0" 

# 5) Demostracion de SPA (captura de KPIs visibles)
- python -m source.main spa 
- 
# 6) Validación rápida de los datos obtenidos por scrapping
- python -m source.main validate 
    - Si todo esta ok debe recibir el mensaje: "INFO: ✔✔✔ TODAS LAS VALIDACIONES PASARON ✔✔✔" 

## Vídeo (≤10 min)
- Incluir una demo corta: `robots → index → (desempleo|recaudacion|asignacion) → dataset → Zenodo`.
- Ambos integrantes deben aparecer en algún momento.
- Coloca el enlace en `video/enlace_video.txt` y en la **memoria**.

## Ética y licencias
- No se halló `robots.txt` público en `observatorio.bps.gub.uy` ni `www.bps.gub.uy` (ver `logs/robots.log`).
- Se aplicó *polite crawling*: User-Agent propio, `--delay`, sin login, sin evadir barreras técnicas.
- Fuente de datos: BPS (Indicadores de la Seguridad Social). Este repo publica un **dataset derivado** (metadatos + series tabulares de XLS) bajo **CC-1.0**, citando a la fuente.

## Buenas prácticas implementadas
- **User‑Agent propio**, **retardos** configurables, **timeouts** y **reintentos** exponenciales.
- **Respeto de robots.txt** y registro explícito en logs.
- **Modularidad** del código y **comentarios** concisos.
- **Limitaciones conocidas**: algunos servidores bloquean `HEAD`; se usa fallback GET controlado. Páginas con iframes/JS pueden requerir estrategia alternativa.

## Créditos / Propiedad intelectual
- Autoría del código: integrantes.
- Terceros: mencionar bibliografía, documentación y paquetes utilizados (licencias). Detallar en la **memoria**.

## Licencia
- **DOI**: Serrentino Mangino, S., & Mochon Paredes, A. (2025, octubre 30). Datos estadísticos del Banco de Previsión Social del Uruguay. 
- **Datos** (`/dataset` y depósito Zenodo): **CC0 1.0** (dominio público). Se agradece citar el DOI: https://doi.org/10.5281/zenodo.17541918  
- **Código** (`/source`): **MIT**.  Detalles en [`LICENSE.md`](./LICENSE.md).

