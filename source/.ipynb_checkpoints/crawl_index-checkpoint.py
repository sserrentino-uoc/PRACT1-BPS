import re, csv, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .settings import DEFAULT_UA, REQUEST_TIMEOUT, DEFAULT_DELAY_SEC, BASE_INDEX_PAGES, OUT_DIR
from .utils import make_logger, ensure_dirs, abs_url, clean_whitespace, polite_sleep, text2num

def parse_index_page(page_url, html, rows, logger):
    soup = BeautifulSoup(html, "lxml")

    # --- A) Páginas "1944/indicadores..." (tarjetas) -------------------------
    # Busco enlaces a PDF/XLS dentro de bloques "tarjeta" genéricos
    items = soup.select(".item, .card, .fila, .contenedor, li, tr, section, article, div")
    logger.info(f"Bloques candidatos detectados: {len(items)} (fase A)")
    for it in items:
        block_text = clean_whitespace(it.get_text(" ", strip=True))
        # Capítulo/subcapítulo tipo "III.3 Subsidio por desempleo"
        m_cap = re.search(r"\b([IVX]+\.\d*\s*[^\|·\-]{3,120})", block_text)
        capitulo = m_cap.group(1) if m_cap else ""
        # Fecha "Última modificación" o "Fecha de publicación"
        m_fecha = re.search(r"(Última\s+modificación|Fecha\s+de\s+publicación)\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", block_text, re.I)
        fecha = m_fecha.group(2) if m_fecha else ""

        for a in it.select('a[href$=".pdf"], a[href$=".xls"], a[href$=".xlsx"]'):
            href = abs_url(page_url, a.get("href")); 
            if not href: 
                continue
            txt = clean_whitespace(a.get_text(" ", strip=True))
            size_text = a.get("title") or a.get("data-size") or txt
            tipo = "pdf" if href.lower().endswith(".pdf") else "xls"
            rows.append({
                "capitulo": capitulo or "",
                "titulo_corto": "",
                "tipo_archivo": tipo,
                "tamano": size_text,
                "tamano_bytes_aprox": text2num(size_text),
                "fecha_publicacion": fecha,
                "url_descarga": href,
                "url_pagina": page_url
            })

    # --- B) Páginas "cuadro.jsp" (índice tabular oficial) --------------------
    if "cuadro.jsp" in page_url:
        # En algunos "cuadro.jsp" no hay clases reconocibles; tomamos todos los <a> a PDF/XLS
        links = soup.select('a[href$=".pdf"], a[href$=".xls"], a[href$=".xlsx"]')
        logger.info(f"Enlaces directos a ficheros en cuadro.jsp: {len(links)} (fase B)")
        for a in links:
            href = abs_url(page_url, a.get("href"))
            if not href:
                continue
            # Busco contexto cercano para inferir capítulo y fecha
            wrap = a.find_parent(["li","tr","td","div","section","article"]) or a
            ctx = clean_whitespace(wrap.get_text(" ", strip=True))
            m_cap = re.search(r"\b([IVX]+\.\d*\s*[^\|·\-]{3,120})", ctx)
            capitulo = m_cap.group(1) if m_cap else ""

            m_fecha = re.search(r"(Última\s+modificación|Fecha\s+de\s+publicación)\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", ctx, re.I)
            fecha = m_fecha.group(2) if m_fecha else ""

            txt = clean_whitespace(a.get_text(" ", strip=True))
            size_text = a.get("title") or a.get("data-size") or txt
            tipo = "pdf" if href.lower().endswith(".pdf") else "xls"

            rows.append({
                "capitulo": capitulo or "",
                "titulo_corto": "",
                "tipo_archivo": tipo,
                "tamano": size_text,
                "tamano_bytes_aprox": text2num(size_text),
                "fecha_publicacion": fecha,
                "url_descarga": href,
                "url_pagina": page_url
            })

def parse_index_page_old(page_url, html, rows, logger):
    soup = BeautifulSoup(html, "lxml")

    # Heurística de selectores (ajusta a la estructura real del índice):
    # 1) Tarjetas o filas con título/capítulo, fecha, tipo y enlaces.
    # Buscamos bloques con botones "Descargar PDF/EXCEL" y metadata.
    items = soup.select(".item, .card, .fila, .contenedor, li, tr")
    logger.info(f"Bloques candidatos detectados: {len(items)}")

    for it in items:
        block_text = clean_whitespace(it.get_text(" ", strip=True))
        # Capítulo/subcapítulo (ej.: “III.3 Subsidio por desempleo”)
        m_cap = re.search(r"\b([IVX]+\.\d*\s*[^\|·\-]{3,80})", block_text)
        capitulo = m_cap.group(1) if m_cap else ""

        # Fecha de publicación/última modificación
        m_fecha = re.search(r"(Última\s+modificación|Fecha\s+de\s+publicación)\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", block_text, re.I)
        fecha = m_fecha.group(2) if m_fecha else ""

        # Enlaces de descarga PDF/XLS + tamaño
        for a in it.select("a[href]"):
            href = abs_url(page_url, a.get("href"))
            if not href: continue
            low = href.lower()
            if low.endswith(".pdf") or low.endswith(".xls") or low.endswith(".xlsx"):
                tipo = "pdf" if low.endswith(".pdf") else "xls"
                # Intentar leer el texto del enlace p/ tamaño “952 KB”
                atext = clean_whitespace(a.get_text(" ", strip=True))
                # A veces el tamaño está en el hermano/siguiente
                size_text = a.get("data-size") or a.get("title") or atext
                # Guardamos fila
                rows.append({
                    "capitulo": capitulo or "",
                    "titulo_corto": "",  # si hubiera un h3/h4 específico lo puedes capturar arriba
                    "tipo_archivo": tipo,
                    "tamano": size_text,
                    "tamano_bytes_aprox": text2num(size_text),
                    "fecha_publicacion": fecha,
                    "url_descarga": href,
                    "url_pagina": page_url
                })

def crawl_index(pages=None, out_csv=f"{OUT_DIR}/indicadores_index.csv",
                delay=DEFAULT_DELAY_SEC, max_pages=10, log_dir="logs"):
    ensure_dirs(OUT_DIR, log_dir)
    logger = make_logger(log_dir, "crawl_index")
    pages = pages or BASE_INDEX_PAGES
    rows = []
    n = 0
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        for page_url in pages:
            if n >= max_pages: break
            try:
                r = s.get(page_url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                logger.info(f"GET {page_url} -> {r.status_code}")
                parse_index_page(page_url, r.text, rows, logger)
            except Exception as e:
                logger.warning(f"Fallo en {page_url}: {e}")
            n += 1
            polite_sleep(delay, logger)

    # De-duplicar por (url_descarga)
    seen = set(); out = []
    for row in rows:
        k = row["url_descarga"]
        if k in seen: continue
        seen.add(k); out.append(row)

    # Persistir CSV
    hdr = ["capitulo","titulo_corto","tipo_archivo","tamano","tamano_bytes_aprox",
           "fecha_publicacion","url_descarga","url_pagina"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        for r in out: w.writerow(r)
    logger.info(f"Escribí {len(out)} filas en {out_csv}")
    return out_csv