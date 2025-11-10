# Título: Observatorio BPS – Indicadores y Series (Desempleo, Recaudación)

- **Autores**: Sebastian Serrentino Mangino (sserrentino@uoc.edu), Alberto Mochón Paredes (amochon@uoc.edu)  
- **Repositorio**: https://github.com/sserrentino-uoc/PRACT1-BPS  
- **Web origen**: https://observatorio.bps.gub.uy/#/ y páginas institucionales BPS  
- **Dataset (DOI)**: https://doi.org/10.5281/zenodo.17541918  
- **Vídeo**: https://drive.google.com/drive/folders/1WeBU1GibaRapkJ_BqI4K9bRUuO8Dic5F
- **Asignatura**: Tipología y ciclo de vida de los datos
- **Fecha**: 1/11/2025  

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
1.  Indices - URLs
   
    ![Indices](/docs/imagenes/indices_url.png)

3.  Subsidio por desempleo – Altas (total)
   
    ![Indices](/docs/imagenes/altas_subsidio_desempleo.png)

5.  Recaudacion de la Seguridad Social - Privados/Públicos/Total (Total)
   
    ![Recaudacion](/docs/imagenes/recaudacion.png)

7.  Indicadores BPS – BPS en Cifras
   
    ![Recaudación](/docs/imagenes/indicadores_bps_en_cifras.png)
    
**Resultados**
- Ética / robots.txt: robots_check.py registra 404 para robots en dominios consultados → se aplica polite crawling (UA propio, espera ≈2s, reintentos). Evidencia: logs/robots.log.
- Crawl índice: crawl_index.py → dataset/indicadores_index.csv (~272×8 en el ZIP) + trazas en logs/crawl_index.log.
- Series: parse_series.py → dataset/series_desempleo.csv y dataset/series_recaudacion.csv (≈24×4), con _norm_num() y _norm_mes() para homogeneizar números y tiempo. Evidencia adicional: logs/parse_series.log (si presente).
- SPA: demo_spa.py (Selenium + WebDriverWait) captura 21 azulejos del dashboard; salida tabular en dataset/spa_dashboard_data.csv (≈13×2) y trazas en logs/spa_scrape.log.
- Validación: validate.py chequea existencia, encabezados y nulos básicos; evidencias en logs/validate.log (si lo ejecutaste) y verificación manual de CSVs.

# 8. Inspiración

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


## 9. Licencia del dataset
Publicamos el dataset en Zenodo bajo CC0 1.0 (dominio público) para maximizar su reutilización académica y compatibilidad con PRACT2. Se trata de datos públicos y agregados, sin datos personales. Cita sugerida (Zenodo): Serrentino Mangino, S., & Mochón Paredes, A. (2025). Observatorio BPS – Indicadores index + Series (desempleo/recaudación) (v1.0.0). Zenodo. https://doi.org/10.5281/zenodo.17541918

> **TODO Licencia del código**  
> Repositorio bajo `MIT` (confirmar en `LICENSE`).  
> Nota: indicar compatibilidad entre licencia del **código** y licencia del **dataset**.

## 10. Código y retos técnicos
Código en `/source` con CLI (`python -m source.main <subcomando>`).  
Retos: páginas institucionales heterogéneas (HTML/XLS/XLSX), normalización de formatos, distinguir recursos (sniffing de binario/HTML), y una SPA que requiere Selenium (archivo `demo_spa.py` con waits). Se registran logs en `/logs`.

> **TODO Detalle técnico (breve) de soluciones aplicadas**  
> - `_engine_from_ext_or_sniff` (detecta xls/xlsx/html/text por “magic bytes”).  
> - `_read_table_like` con **headers múltiples** y **fallbacks** (`xlrd` manual, `read_html`, BS4, CSV/TSV).  
> - Promoción automática de cabecera por fila con “Fecha”.  
> - Normalización numérica con formato latino (`_to_num`).  
> - Heurística de selección de hoja (**ALTAS > EMISIÓN > PROMEDIO**).  
> - Selección robusta del XLS correcto para **II Recaudación** (sin exigir extensión).  
> - Scraping responsable: User-Agent fijo, sleeps, recorte de probes.

## 10. Dataset y DOI
CSVs disponibles en `/dataset`.
Serrentino Mangino, S., & Mochon Paredes, A. (2025, noviembre 6). Datos estadísticos del Banco de Previsión Social del Uruguay. Zenodo. https://doi.org/10.5281/zenodo.17541918

## 11. Evidencias y reproducibilidad
- **Logs** de scraping: `/logs/*.log` (robots, índice, series, SPA).  
- **Parámetros**: `/source/settings.py` (User-Agent, delays, timeouts).  
- **Requisitos**: `requirements.txt`.  
- **Validación**: `python -m source.main validate` (verifica columnas clave y nulos en los CSV obtenidos).

> **TODO Comandos de reproducción rápida (incluye script)**  
> - `./run_fresh.sh` (repro desde cero).  
> - Salidas esperadas: `dataset/indicadores_index.csv`, `series_desempleo.csv`, `series_recaudacion.csv`, `spa_dashboard_data.csv`.  
> - Captura de pantalla / extracto de logs con **User-Agent** y **“Sleeping …”**.

---

## 12. Tabla de contribuciones (obligatoria)

> **TODO Completar con iniciales y % aproximado por apartado**  
> (Ambos deben aparecer en todos los apartados)

| Apartado | S.S.M. | A.M.P. | Notas |
|---|---:|---:|---|
| 1. Contexto | `TODO` | `TODO` |  |
| 2. Título dataset | `TODO` | `TODO` |  |
| 3. Descripción | `TODO` | `TODO` |  |
| 4. Representación gráfica | `TODO` | `TODO` |  |
| 5. Contenido | `TODO` | `TODO` |  |
| 6. Ética/legal | `TODO` | `TODO` |  |
| 7. Inspiración/Comparativa | `TODO` | `TODO` |  |
| 8. Licencia | `TODO` | `TODO` |  |
| 9. Código/Retos | `TODO` | `TODO` |  |
| 10. Dataset/DOI | `TODO` | `TODO` |  |
| 11. Evidencias/Repro | `TODO` | `TODO` |  |
| Vídeo | `TODO` | `TODO` |  |

> **Firmas**:  
> - Sebastian Serrentino Mangino — `TODO fecha`  
> - Alberto Mochón Paredes — `TODO fecha`
