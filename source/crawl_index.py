import re, csv, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from .settings import DEFAULT_UA, REQUEST_TIMEOUT, DEFAULT_DELAY_SEC, BASE_INDEX_PAGES, OUT_DIR
from .utils import make_logger, ensure_dirs, abs_url, clean_whitespace, polite_sleep, text2num
from datetime import datetime

ROMAN_TITLE_RE = re.compile(r"\b([IVX]+(?:\.\d+)?)\s+([^\(\|·\-\n]{3,120})", re.I)
SIZE_RE = re.compile(r"\b(\d+(?:[\.,]\d+)?\s*(?:KB|MB|B))\b", re.I)
DATE_RE = re.compile(r"(Última\s+modificación|Fecha\s+de\s+publicación)\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", re.I)
EXT_RE = re.compile(r"\.(pdf|xlsx?)\b", re.I)


# === NUEVOS HELPERS (pegarlos junto a los demás helpers del módulo) ===
def _roman_from_href(href: str) -> str:
    """
    Intenta deducir el capítulo (I, II, III.3, etc.) a partir del nombre del archivo.
    Cubre variantes como 'iii_3_', 'iii.3_', 'ii_recaudacion', 'i.-ingresos', etc.
    """
    if not href:
        return ""
    name = href.split("/")[-1].lower()
    # normalizar separadores y puntos sueltos
    name = re.sub(r"[^a-z0-9]+", "_", name)
    # casos con subcapítulo tipo iii_3_...
    m = re.search(r"\b([ivx]+)_(\d+)_", name)
    if m:
        return f"{m.group(1).upper()}.{m.group(2)}"
    # casos iii_ , ii_ , v_ ...
    m = re.search(r"\b([ivx]+)_", name)
    if m:
        return m.group(1).upper()
    # casos '2_' usados como II
    m = re.search(r"\b([1-5])_", name)
    if m:
        return ["","I","II","III","IV","V"][int(m.group(1))]
    return ""

def _prefer_cap_by_href(cap_num: str, href: str) -> str:
    """
    Si el capítulo del contexto está vacío o es inconsistente con el que
    se deduce por archivo, toma el del archivo.
    """
    cap_from_file = _roman_from_href(href)
    if not cap_num:
        return cap_from_file
    if cap_from_file and cap_from_file != cap_num:
        return cap_from_file
    return cap_num

def _text2bytes(tam_text: str) -> int | None:
    if not tam_text: return None
    txt = tam_text.replace(",", ".").strip().upper()
    m = re.search(r"([\d\.]+)\s*(KB|MB|B)", txt)
    if not m: return None
    n, unit = float(m.group(1)), m.group(2)
    if unit == "MB": return int(n * 1024 * 1024)
    if unit == "KB": return int(n * 1024)
    return int(n)

def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _near_block(a):
    # el mejor contexto suele estar en el padre <li>, <div>, o fila de tabla
    for tag in ("li","div","td","tr","p","article","section"):
        p = a.find_parent(tag)
        if p: 
            return p.get_text(" ", strip=True)
    # fallback a toda la página si no hay padres “semánticos”
    return a.find_parent().get_text(" ", strip=True)

def parse_index_page(page_url, html, rows, logger):
    """
    Analiza la página y agrega a 'rows' una fila por cada enlace PDF/XLS/XLSX.
    - Corrige acentos (si venían mal en 'html', ya los recibimos bien desde crawl_index).
    - Extrae capítulo/título desde contexto y reconcilia el capítulo con el nombre del archivo.
    """
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("a[href]")
    total_links = 0
    kept_links = 0

    for a in anchors:
        href = a.get("href") or ""
        mext = EXT_RE.search(href)
        if not mext:
            continue
        total_links += 1

        tipo_raw = mext.group(1).lower()               # pdf | xls | xlsx
        tipo = "xls" if tipo_raw.startswith("xls") else "pdf"
        href_abs = urljoin(page_url, href)

        # Contexto cercano
        link_text  = _clean_spaces(" ".join(a.stripped_strings))
        block_text = _clean_spaces(_near_block(a))
        context = f"{link_text} | {block_text}"

        # Tamaño
        size_text = a.get("title") or a.get("data-size") or ""
        if not size_text:
            msize = SIZE_RE.search(context)
            size_text = msize.group(1) if msize else ""

        # Fecha
        mfecha = DATE_RE.search(context)
        fecha_publicacion = mfecha.group(2) if mfecha else ""

        # Capítulo/Título desde contexto
        mcap = ROMAN_TITLE_RE.search(context)
        cap_num = mcap.group(1).strip() if mcap else ""
        tit_corto = mcap.group(2).strip() if mcap else ""

        # Plan B: buscar antes del href bruto
        if not cap_num or not tit_corto:
            try:
                idx = html.find(href)
                s = max(0, idx - 600)
                snippet = _clean_spaces(html[s:idx])
                mcap2 = ROMAN_TITLE_RE.search(snippet)
                if mcap2:
                    cap_num  = cap_num  or mcap2.group(1).strip()
                    tit_corto = tit_corto or mcap2.group(2).strip()
            except Exception:
                pass

        # *** Reconciliación: si el archivo indica otro capítulo, usar el del archivo
        cap_num = _prefer_cap_by_href(cap_num, href)

        row = {
            "capitulo": cap_num,
            "titulo_corto": tit_corto,
            "tipo_archivo": tipo,
            "tamano": size_text,
            "tamano_bytes_aprox": _text2bytes(size_text) or "",
            "fecha_publicacion": fecha_publicacion,
            "url_descarga": href_abs,
            "url_pagina": page_url,
        }

        if row["url_descarga"] and row["tipo_archivo"] in {"pdf", "xls"}:
            rows.append(row)
            kept_links += 1
        else:
            logger.warning("Descartado (incompleto): %s", row)

    logger.info("Página %s: %d enlaces PDF/XLS encontrados, %d válidos",
                page_url, total_links, kept_links)


def scrape_index_page(session, page_url: str, logger):
    out_rows = []
    r = session.get(page_url, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "lxml")

    anchors = soup.select("a[href]")
    total_links = 0
    kept_links = 0

    for a in anchors:
        href = a.get("href") or ""
        mext = EXT_RE.search(href)
        if not mext:
            continue  # sólo PDF/XLS/XLSX
        total_links += 1

        tipo = mext.group(1).lower()  # 'pdf', 'xls' o 'xlsx'
        href_abs = urljoin(page_url, href)

        link_text = _clean_spaces(" ".join(a.stripped_strings))
        block_text = _clean_spaces(_near_block(a))
        context = f"{link_text} | {block_text}"

        # tamaño (si aparece en el título/data-size o en el texto del bloque)
        size_text = a.get("title") or a.get("data-size") or ""
        if not size_text:
            msize = SIZE_RE.search(context)
            size_text = msize.group(1) if msize else ""

        # fecha de publicación / última modificación (DD/MM/AAAA)
        mfecha = DATE_RE.search(context)
        fecha_publicacion = mfecha.group(2) if mfecha else ""

        # capítulo y título corto (ROMAN + texto)
        mcap = ROMAN_TITLE_RE.search(context)
        cap_num = mcap.group(1).strip() if mcap else ""
        tit_corto = mcap.group(2).strip() if mcap else ""

        # si no pudimos extraer cap/título, intenta mirar 200 chars antes del link en el HTML bruto
        if not cap_num or not tit_corto:
            try:
                idx = html.find(href)  # posición aproximada
                s = max(0, idx - 600)
                snippet = _clean_spaces(html[s:idx])
                mcap2 = ROMAN_TITLE_RE.search(snippet)
                if mcap2:
                    cap_num = cap_num or mcap2.group(1).strip()
                    tit_corto = tit_corto or mcap2.group(2).strip()
            except Exception:
                pass

        # fila
        row = {
            "capitulo": cap_num,
            "titulo_corto": tit_corto,
            "tipo_archivo": "xls" if tipo.startswith("xls") else "pdf",
            "tamano": size_text,
            "tamano_bytes_aprox": _text2bytes(size_text) or "",
            "fecha_publicacion": fecha_publicacion,  # DD/MM/AAAA original
            "url_descarga": href_abs,
            "url_pagina": page_url,
        }

        # criterio mínimo para no dejar el CSV vacío por “falso positivo”:
        if row["url_descarga"] and row["tipo_archivo"] in {"pdf","xls"}:
            out_rows.append(row)
            kept_links += 1
        else:
            logger.warning("Descartado (incompleto): %s", row)

    logger.info("Página %s: %d enlaces PDF/XLS encontrados, %d válidos",
                page_url, total_links, kept_links)
    return out_rows

def crawl_index(pages=None, out_csv=f"{OUT_DIR}/indicadores_index.csv",
                delay=DEFAULT_DELAY_SEC, max_pages=10, log_dir="logs"):
    """
    Itera por las páginas de índice, usa parse_index_page(),
    deduplica por url_descarga y escribe el CSV sólo si hay filas.
    Además corrige la codificación del HTML (acentos) usando apparent_encoding.
    """
    ensure_dirs(OUT_DIR, log_dir)
    logger = make_logger(log_dir, "crawl_index")
    pages = pages or BASE_INDEX_PAGES
    rows = []
    n = 0

    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        for page_url in pages:
            if n >= max_pages:
                break
            try:
                r = s.get(page_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                # forzar codificación correcta para evitar 'reciÃ©n'
                try:
                    r.encoding = r.apparent_encoding or r.encoding
                except Exception:
                    pass
                r.raise_for_status()
                logger.info(f"GET {page_url} -> {r.status_code}")
                parse_index_page(page_url, r.text, rows, logger)
            except Exception as e:
                logger.warning(f"Fallo en {page_url}: {e}")
            n += 1
            polite_sleep(delay, logger)

    # De-duplicar por url_descarga
    seen = set()
    out = []
    for row in rows:
        k = row.get("url_descarga", "")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(row)

    hdr = ["capitulo", "titulo_corto", "tipo_archivo", "tamano", "tamano_bytes_aprox",
           "fecha_publicacion", "url_descarga", "url_pagina"]

    if not out:
        logger.warning("No se extrajeron filas de índice. CSV NO se escribirá para evitar un archivo vacío.")
        return out_csv

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in hdr})

    logger.info(f"Escribí {len(out)} filas en {out_csv}")
    return out_csv
