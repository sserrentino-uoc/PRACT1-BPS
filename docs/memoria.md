# Título: Observatorio BPS – Indicadores y Series (Desempleo, Recaudación)

- **Autores**: Sebastian Serrentino Mangino (sserrentino@uoc.edu), Alberto Mochón Paredes (amochon@uoc.edu)  
- **Repositorio**: https://github.com/sserrentino-uoc/PRACT1-BPS  
- **Web origen**: https://observatorio.bps.gub.uy/#/ y páginas institucionales BPS  
- **Dataset (DOI)**: https://doi.org/10.5281/zenodo.17541918  
- **Vídeo**: https://drive.google.com/drive/folders/1WeBU1GibaRapkJ_BqI4K9bRUuO8Dic5F
- **Asignatura**: Tipología y ciclo de vida de los datos
- **Fecha**: 10/11/2025  

## 1. Contexto
El Banco de Previsión Social (BPS) de Uruguay publica indicadores y series relacionadas con la seguridad social. Este proyecto extrae un índice de indicadores y dos series clave (subsidio por desempleo y recaudación), generando un dataset reproducible para análisis posteriores (PRACT2). Se describe la fuente, su fiabilidad institucional y la motivación: disponer de datos limpios y versionados.

## 2. Título del dataset
“Observatorio BPS – Indicadores y Series (Desempleo, Recaudación)”

## 3. Descripción del dataset
Dataset CSVs con:  
- **Índice de indicadores** (`indicadores_index.csv`): catálogo con capítulo, título, tipo de archivo, tamaño, fecha publicación, filename final, URL de descarga y URL de página.  
- **Serie de subsidio por desempleo** (`series_desempleo.csv`): fecha (mensual), altas totales, altas Montevideo, altas Interior.  
- **Serie de recaudación** (`series_recaudacion.csv`): fecha (mensual), recaudación en privados, públicos y total.  
- **KPIs visibles en SPA** (`spa_dashboard_data.csv`): indicador, valor.

Granularidad temporal mensual; unidad y definiciones según BPS (sin datos personales).

> **TODO Periodo temporal**  
> - `series_desempleo.csv`: **Periodo** = `YYYY-MM … YYYY-MM` (según la última ejecución).  
> - `series_recaudacion.csv`: **Periodo** = `YYYY-MM … YYYY-MM` (según la última ejecución).  
> - `indicadores_index.csv`: **Corte** = fecha de rastreo `YYYY-MM-DD`.

## 4. Representación gráfica (pipeline)
![Pipeline de scraping](/docs/imagenes/diagrama_flujo.png)

**Flujo**: Descubrimiento/índice (HTML) → Descarga tablas (HTML/XLS/XLSX) → Limpieza/normalización → CSVs finales → Publicación Zenodo.

## 5. Contenido (diccionario de datos)

**Periodo temporal (exacto)**
- `/dataset/series_desempleo.csv`: 2023-08-01 – 2025-07-01 (mensual, inclusive).
- `/dataset/series_recaudacion.csv`: 2023-05-01 – 2025-04-01 (mensual, inclusive).
- `/dataset/spa_dashboard_data.csv`: 
   - Naturaleza: snapshot de KPIs del dashboard SPA del Observatorio (no es serie temporal).
   - Período: no aplica. Los valores corresponden al instante de captura.
   - Evidencia: timestamp de captura registrado en `logs/spa_scrape.log`.
   - Fuente: https://observatorio.bps.gub.uy/#/
  
**indicadores_index.csv**  
- `capitulo` (str) — agrupador temático del indicador  
- `titulo_corto` (str) — resumen del indicador  
- `tipo_archivo` (str) — tipo de recurso (html/xls/xlsx/pdf)  
- `tamano_resuelto` (str) — tamaño detectado (cuando está disponible)  
- `fecha_publicacion` (str|date) — fecha publicada por BPS  
- `filename_final` (str) — nombre de archivo estandarizado  
- `url_descarga` (str) — URL directa del recurso  
- `url_pagina` (str) — URL de la página que contiene el indicador

**series_desempleo.csv**  
- `fecha` (YYYY-MM) — período  
- `altas` (int) — altas total  
- `altas_montevideo` (int) — altas en Montevideo  
- `altas_interior` (int) — altas en el interior

**series_recaudacion.csv**  
- `fecha` (YYYY-MM) — período  
- `recaudacion_privados` (float) — monto privados  
- `recaudacion_publicos` (float) — monto públicos  
- `recaudacion_total` (float) — monto total (control de suma)

**spa_dashboard_data.csv**  
- `indicador` (str) — nombre visible en el dashboard SPA  
- `valor` (float|str) — valor parseado

## 6. Resultados principales

**Figuras**
Indices - URLs
   
   ![Indices](/docs/imagenes/indices_url.png)

Subsidio por desempleo – Altas (total)
   
   ![Indices](/docs/imagenes/altas_subsidio_desempleo.png)

Recaudacion de la Seguridad Social - Privados/Públicos/Total (Total)
   
   ![Recaudacion](/docs/imagenes/recaudacion.png)

Indicadores BPS – BPS en Cifras
   
   ![Recaudación](/docs/imagenes/indicadores_bps_en_cifras.png)
    
**Resultados**
- Ética / robots.txt: robots_check.py registra 404 para robots en dominios consultados → se aplica polite crawling (UA propio, espera ≈2s, reintentos). Evidencia: logs/robots.log.
- Crawl índice: crawl_index.py → dataset/indicadores_index.csv (~272×8 en el ZIP) + trazas en logs/crawl_index.log.
- Series: parse_series.py → dataset/series_desempleo.csv y dataset/series_recaudacion.csv (≈24×4), con _norm_num() y _norm_mes() para homogeneizar números y tiempo. Evidencia adicional: logs/parse_series.log (si presente).
- SPA: demo_spa.py (Selenium + WebDriverWait) captura 21 azulejos del dashboard; salida tabular en dataset/spa_dashboard_data.csv (≈13×2) y trazas en logs/spa_scrape.log.
- Validación: validate.py chequea existencia, encabezados y nulos básicos; evidencias en logs/validate.log (si lo ejecutaste) y verificación manual de CSVs.

# 7. Inspiración

El proyecto se inspira en los **tableros públicos del Observatorio del BPS**, especialmente en los apartados *“Indicadores de la Seguridad Social”* y *“Series históricas”*, donde se presentan métricas agregadas sobre empleo, recaudación y prestaciones.  
Estos tableros constituyen una valiosa fuente de información, pero **su consulta es manual** y la descarga de datos requiere navegar por múltiples páginas o archivos Excel heterogéneos.  

**Trabajos previos del BPS** —como los informes *“Indicadores de la Seguridad Social”* y los tableros *Power BI* del Observatorio— ofrecen visualizaciones interactivas, pero **no publican datasets normalizados ni reproducibles**. Tampoco incluyen metadatos técnicos, licencias explícitas ni versiones históricas de los indicadores.  

El **dataset generado en PRACT1-BPS** aporta una capa intermedia que **facilita el análisis reproducible** y la integración automatizada para futuras prácticas (por ejemplo, **PRACT2**, dedicada a análisis estadístico o visualización).  
Su principal contribución es el **flujo automatizado y documentado de recolección** (Python + Selenium + BeautifulSoup + validaciones), que transforma información semiestructurada en **CSV abiertos y estandarizados**, acompañados de **logs y DOI** para trazabilidad.  

**Comparativa breve con los trabajos previos:**

| Aspecto | Tableros del Observatorio BPS | PRACT1-BPS |
|----------|-------------------------------|-------------|
| **Acceso** | Navegación manual, interfaz web | Automatizado (scripts Python) |
| **Formato de datos** | Visualizaciones o Excel heterogéneos | CSV homogéneos y reproducibles |
| **Licencia** | No especificada | CC0 1.0 Universal |
| **Reproducibilidad** | Limitada | Completa (scripts, logs, DOI) |
| **Trazabilidad** | Parcial (sin versiones históricas) | Total (logs + versionado Zenodo) |

**Aportes clave:**
- Automatización completa del flujo de recolección y normalización.  
- Publicación con metadatos, licencias y DOI (cumplimiento FAIR).  
- Disponibilidad de archivos CSV abiertos, listos para análisis reproducibles en PRACT2.  

**Limitaciones actuales:**
- Cobertura inicial acotada a **dos series históricas (desempleo y recaudación)**.  
- Dependencia del **layout actual del sitio institucional**: un rediseño podría requerir ajustes en los selectores de scraping.  
- El proyecto no incluye análisis de contenido, sino preparación y documentación de datos (según el alcance de la PRACT1).


## 8. Licencias
El dataset se publica en Zenodo (v1.0.0) con DOI 10.5281/zenodo.17541918 bajo licencia CC0 1.0 Universal, a fin de maximizar su reutilización académica y garantizar compatibilidad con PRACT2.
Dado que se trata de datos públicos y agregados provenientes de un organismo oficial (BPS) y sin información personal, la licencia CC0 elimina fricciones de uso y citación.
La cita sugerida se encuentra en la propia ficha de Zenodo junto al DOI.
Una copia local del dataset se conserva en /dataset.
En el [README](/README.md) se detalla la política de licencias: Datos → CC0 1.0 / Código → MIT.

## 9. Código y retos técnicos
Código en `/source` con CLI (`python -m source.main <subcomando>`).  
Retos: páginas institucionales heterogéneas (HTML/XLS/XLSX), normalización de formatos, distinguir recursos (sniffing de binario/HTML), y una SPA que requiere Selenium (archivo `demo_spa.py` con waits). Se registran logs en `/logs`.

Renderizado asíncrono (SPA): elementos del dashboard tardaban en estar presentes en el DOM.
Solución: WebDriverWait con condiciones explícitas (p. ej., presence_of_element_located) + try/except para TimeoutException. Se ajustaron locators a selectores estables (clases/atributos) y se registraron los tiempos en spa_scrape.log.

Heterogeneidad en XLS institucionales: números con separadores regionales y meses en formatos mixtos.
Solución: funciones _norm_num() y _norm_mes() en parse_series.py para armonizar valores y obtener columnas anio/mes estandarizadas.

Falta de robots.txt formal (404): riesgo de ambigüedad de permisos.
Solución: polite crawling explícito (UA propio, DEFAULT_DELAY_SEC, MAX_RETRIES, REQUEST_TIMEOUT en settings.py) + registro exhaustivo en robots.log y documentación en memoria.

## 10. Dataset y DOI
CSVs disponibles en `/dataset`.
Serrentino Mangino, S., & Mochon Paredes, A. (2025, noviembre 6). Datos estadísticos del Banco de Previsión Social del Uruguay. Zenodo. https://doi.org/10.5281/zenodo.17541918

## 11. Evidencias y reproducibilidad

Esta sección documenta **cómo reproducir** la extracción y **qué evidencias** quedan guardadas automáticamente. No se duplica información ya descrita en otros archivos; donde aplica, se referencia.

---

## 11.1 Artefactos y evidencias

- **Logs de scraping**: `logs/*.log`  
  (p. ej., `robots.log`, `crawl_index.log`, `parse_series.log`, `spa_scrape.log`). Contienen timestamps, `User-Agent` efectivo, pausas (*Sleeping/backoff*) y errores.
- **Parámetros**: `source/settings.py`  
  (`DEFAULT_UA`, `DEFAULT_DELAY_SEC`, `REQUEST_TIMEOUT`, `MAX_RETRIES`, rutas `OUT_DIR`, `LOG_DIR`). *Ver ese archivo para valores exactos.*
- **Dependencias**: `requirements.txt`. *Ver archivo para versiones exactas.*
- **Datasets generados** (`OUT_DIR = dataset/`):  
  - `dataset/indicadores_index.csv`  
  - `dataset/series_desempleo.csv`  
  - `dataset/series_recaudacion.csv`  
  - `dataset/spa_dashboard_data.csv`
- **Resultados de figuras y tablas**:  
  - Figuras: `results/figs/*.png`  
  - Tablas: `results/tables/*.csv`  
  - Resumen: `results/results_snippet.md`
- **Documento principal**: `docs/memoria.md` (este archivo).

## 11.2 Resultado y evidencias

**Respeto de robots y “polite crawling”**

```text
2025-10-30 20:23:38,045 [INFO] [HEAD] https://observatorio.bps.gub.uy/robots.txt -> 404
2025-10-30 20:23:38,114 [INFO] [GET ] https://observatorio.bps.gub.uy/robots.txt -> 404 text/html; charset=iso-8859-1
2025-10-30 20:23:38,186 [INFO] [HEAD] https://www.bps.gub.uy/robots.txt -> 404
2025-10-30 20:23:38,234 [INFO] [GET ] https://www.bps.gub.uy/robots.txt -> 404 text/html; charset=iso-8859-1
2025-10-30 20:23:38,306 [INFO] [HEAD] https://bps.gub.uy/robots.txt -> 404
2025-10-30 20:23:38,368 [INFO] [GET ] https://bps.gub.uy/robots.txt -> 404 text/html; charset=iso-8859-1
2025-10-30 20:23:38,370 [INFO] Si no hay robots.txt público, se aplica 'polite crawling' por defecto.
Rate-limit y espera deliberada (delays)
```

**líneas reales con Sleeping (rate-limit)**
```text
2025-10-30 20:24:18,460 [INFO] Sleeping 2.0s
2025-10-30 20:26:25,927 [INFO] GET https://www.bps.gub.uy/1944/indicadores-de-la-seguridad-social.html -> 200
2025-10-30 20:26:26,056 [INFO] Sleeping 2.0s
2025-10-30 20:26:28,098 [INFO] GET https://www.bps.gub.uy/bps/estadisticas/cuadro.jsp?cuadro=2 -> 200
2025-10-30 20:26:28,154 [INFO] Sleeping 2.0s
2025-10-30 20:26:30,479 [INFO] GET https://www.bps.gub.uy/bps/observatorio/cuadro.jsp?contentid=12780 -> 200
2025-10-30 20:26:30,704 [INFO] Sleeping 2.0s
User-Agent (configurado en el código)
```
**User-Agent configurado**
UOC-PRACT1/1.0 (sserrentino@uoc.edu)
Definido en source/settings.py como DEFAULT_UA, usado en las solicitudes HTTP.

**Evidencia del scraping de SPA (dashboard Observatorio)**

```text
2025-11-05 21:17:38,044 [INFO] Esperando 30s a que los azulejos sean visibles en https://observatorio.bps.gub.uy/#/...
2025-11-05 21:17:38,850 [INFO] Encontrados 21 azulejos de datos. Extrayendo...
2025-11-05 21:17:39,714 [INFO] --- Resultados del Scraping (SPA) ---
```

---

## 11.2 Preparación del entorno

Véase el [README](/README.md) 

---

## 12. Tabla de contribuciones (obligatoria)

| Apartado | S.S.M. | A.M.P. | Notas |
|---|---:|---:|---|
| 1. Investigación previa | `70%` | `30%` | - |
| 2. Redacción de las respuestas | `20%` | `80%` | - |
| 3. Desarrollo del código | `80%` | `20%` | - |
| 4. Participación en el vídeo | `50%` | `50%` | - |

**Firmas**:  
- Sebastian Serrentino Mangino (S.S.M.)
- Alberto Mochón Paredes (A.M.P.)
