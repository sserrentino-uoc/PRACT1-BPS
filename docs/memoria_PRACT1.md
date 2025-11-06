# Título: Observatorio BPS – Indicadores y Series (Desempleo, Recaudación)

**Autores**: Sebastian Serrentino Mangino (sserrentino@uoc.edu), Alberto Mochón Paredes (amochon@uoc.edu)  
**Repositorio**: https://github.com/sserrentino-uoc/PRACT1-BPS  
**Web origen**: https://observatorio.bps.gub.uy/#/ y páginas institucionales BPS  
**Dataset (DOI)**: https://doi.org/10.5281/zenodo.17541918  
**Vídeo**: [pendiente – enlace en /video/enlace_video.txt]

## 1. Contexto
El Banco de Previsión Social (BPS) de Uruguay publica indicadores y series relacionadas con la seguridad social. Este proyecto extrae un índice de indicadores y dos series clave (subsidio por desempleo y recaudación), generando un dataset reproducible para análisis posteriores (PRACT2). Se describe la fuente, su fiabilidad institucional y la motivación: disponer de datos limpios y versionados.

## 2. Título del dataset
“Observatorio BPS – Indicadores index + Series: Altas por desempleo / Recaudación (mensual) + Datos Generales”

## 3. Descripción del dataset
Dataset CSVs con:  
- **Índice de indicadores** (`indicadores_index.csv`): catálogo con capítulo, título, tipo de archivo, tamaño, fecha publicación, filename final, URL de descarga y URL de página.  
- **Serie de subsidio por desempleo** (`series_desempleo.csv`): fecha (mensual), altas totales, altas Montevideo, altas Interior.  
- **Serie de recaudación** (`series_recaudacion.csv`): fecha (mensual), recaudación en privados, públicos y total.  
- **KPIs visibles en SPA** (`spa_dashboard_data.csv`): indicador, valor.

Granularidad temporal mensual; unidad y definiciones según BPS (sin datos personales).

## 4. Representación gráfica (pipeline)
![Pipeline de scraping](diagrama_flujo.png)

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

## 6. Propietario y aspectos éticos/legales
Propietario: BPS (Uruguay).  
Actuamos con “scraping responsable”: chequeo de `robots.txt` (ver `/logs/robots.log`), `User-Agent` propio, **rate-limit** (delays), **timeouts**, **reintentos**, y evitamos zonas autenticadas o con captchas. No capturamos datos personales. Uso académico/no comercial. Si `robots.txt` no está disponible (HTTP 404), aplicamos políticas “polite crawling” y monitoreamos carga.

## 7. Inspiración
Trabajos previos del BPS y tableros del Observatorio; el dataset busca facilitar análisis reproducibles (PRACT2) sin depender de la navegación manual por múltiples páginas.

## 8. Licencia del dataset
Publicamos el dataset en Zenodo bajo CC0 1.0 (dominio público) para maximizar su reutilización académica y compatibilidad con PRACT2. Se trata de datos públicos y agregados, sin datos personales. Cita sugerida (Zenodo): Serrentino Mangino, S., & Mochón Paredes, A. (2025). Observatorio BPS – Indicadores index + Series (desempleo/recaudación) (v1.0.0). Zenodo. https://doi.org/10.5281/zenodo.17541918

## 9. Código y retos técnicos
Código en `/source` con CLI (`python -m source.main <subcomando>`).  
Retos: páginas institucionales heterogéneas (HTML/XLS/XLSX), normalización de formatos, distinguir recursos (sniffing de binario/HTML), y una SPA que requiere Selenium (archivo `demo_spa.py` con waits). Se registran logs en `/logs`.

## 10. Dataset y DOI
CSVs disponibles en `/dataset`.
Serrentino Mangino, S., & Mochon Paredes, A. (2025, noviembre 6). Datos estadísticos del Banco de Previsión Social del Uruguay. Zenodo. https://doi.org/10.5281/zenodo.17541918

## 11. Evidencias y reproducibilidad
- **Logs** de scraping: `/logs/*.log` (robots, índice, series, SPA).  
- **Parámetros**: `/source/settings.py` (User-Agent, delays, timeouts).  
- **Requisitos**: `requirements.txt`.  
- **Validación**: `python -m source.main validate` (verifica columnas clave y nulos en los CSV obtenidos).
