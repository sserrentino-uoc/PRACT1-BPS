# Copyright (c) 2025 Serrentino Mangino, S., & Mochon Paredes, A.
# Licensed under the MIT License. See LICENSE for details.

"""
Crawler del índice de indicadores.

Este módulo se encarga de:
1. Descargar las páginas de índice (HTML).
2. Parsear el HTML para encontrar enlaces a archivos (PDF, XLS).
3. Extraer metadatos de la página (Capítulo, Título, Fecha, Tamaño visible).
4. Enriquecer los metadatos consultando el servidor (HEAD/GET Range)
   para obtener el tamaño real y el nombre de archivo del header.
5. Resolver y unificar el tamaño del archivo.
6. Guardar todos los resultados en un archivo CSV.
"""

import re, csv, requests
import email.utils as eut
from urllib.parse import urlsplit, unquote
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime

from .settings import DEFAULT_UA, REQUEST_TIMEOUT, DEFAULT_DELAY_SEC, BASE_INDEX_PAGES, OUT_DIR
from .utils import make_logger, ensure_dirs, abs_url, clean_whitespace, polite_sleep, text2num


ROMAN_TITLE_RE = re.compile(r"\b([IVX]+(?:\.\d+)?)\s+([^\(\|·\-\n]{3,120})", re.I)
SIZE_RE = re.compile(r"\b(\d+(?:[\.,]\d+)?\s*(?:KB|MB|B))\b", re.I)
DATE_RE = re.compile(r"(Última\s+modificación|Fecha\s+de\s+publicación)\s*[:\-]\s*(\d{2}/\d{2}/\d{4})", re.I)
EXT_RE = re.compile(r"\.(pdf|xlsx?)\b", re.I)
FILENAME_QUOTED_RE = re.compile(r'filename="([^"]+)"', re.I)
FILENAME_UNQUOTED_RE = re.compile(r'filename=([^;]+)', re.I)
FILENAME_STAR_RE = re.compile(r"filename\*\s*=\s*([^']*)'[^']*'(.+)", re.I)  # RFC 5987



RANGE_RE = re.compile(r"bytes\s+\d+-\d+\/(\d+)", re.I)

def _parse_content_disposition(cd: str) -> str:
    """
    Devuelve el 'filename' del header Content-Disposition si existe.
    Soporta 'filename=' (comillas) y 'filename*=' (RFC 5987).

    Args:
        cd (Optional[str]): El valor del header Content-Disposition.

    Returns:
        str: El nombre de archivo extraído, o "" si no se encuentra.
    """
    if not cd:
        return ""
    # Soporta filename* (RFC5987) y filename=
    parts = cd.split(";")
    out = ""
    for p in parts:
        p = p.strip()
        if p.lower().startswith("filename*="):
            # filename*=UTF-8''nombre.pdf
            try:
                _, v = p.split("=", 1)
                encoding, _, fname = v.partition("''")
                out = unquote(fname)
                break
            except Exception:
                pass
        elif p.lower().startswith("filename="):
            out = p.split("=", 1)[1].strip().strip('"').strip("'")
            break
    return out

def _is_clean_1024(n: int) -> bool:
    """Comprueba si un número es un múltiplo "limpio" de 1024 (ej. 512.0 KB)."""
    return n % 1024 == 0 or (abs(n - round(n/1024)*1024) <= 512)

def _human_bytes(n) -> str:
    """Convierte bytes (int) a un string legible (KB, MB)."""
    if not n:
        return ""
    n = int(n)
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"

def resolve_size(row: dict) -> dict:
    """
    Resuelve el tamaño final ('tamano_bytes') basado en las fuentes disponibles.
    Prioridad: Servidor (server) > Página (page) > Aproximado (aprox).
    Maneja la heurística de tamaños "redondeados" (ej. 512 KB).
    """
    def as_int(x):
        try:
            return int(float(x))
        except Exception:
            return None

    server = as_int(row.get("size_bytes_server"))
    page   = as_int(row.get("size_bytes_page"))
    aprox  = as_int(row.get("tamano_bytes_aprox"))

    chosen = None
    if server and page:
        diff = abs(server - page) / max(server, page)
        if diff <= 0.03:
            if _is_clean_1024(page) and not _is_clean_1024(server):
                chosen = page
            elif _is_clean_1024(server) and not _is_clean_1024(page):
                chosen = server
            else:
                chosen = max(server, page)
        else:
            chosen = server
    elif server:
        chosen = server
    elif page:
        chosen = page
    else:
        chosen = aprox

    row["tamano_bytes"]    = chosen or ""
    row["tamano_resuelto"] = _human_bytes(chosen)
    return row

def _filename_from_url(u: str) -> str:
    """Extrae el nombre de archivo de la URL (ej. .../archivo.pdf)."""
    try:
        path = urlsplit(u).path or ""
        base = path.rsplit("/", 1)[-1]
        return unquote(base) or ""
    except Exception:
        return ""

def _try_head_or_range(session: requests.Session, url: str, timeout: int) -> tuple[int|None, str]:
    """
    Intenta obtener tamaño y filename del servidor:
    1) HEAD → Content-Length y Content-Disposition
    2) GET Range: bytes=0-0 → Content-Range (más seguro que bajar todo)
    """
    size = None
    fname = ""
    try:
        rh = session.head(url, allow_redirects=True, timeout=timeout)
        # Algunos servidores devuelven Content-Length y/o Content-Disposition
        cl = rh.headers.get("Content-Length")
        if cl and cl.isdigit():
            size = int(cl)
        cd = rh.headers.get("Content-Disposition", "")
        fname = _parse_content_disposition(cd) or fname
    except Exception:
        pass

    if size is None:
        try:
            rg = session.get(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
                             stream=True, allow_redirects=True, timeout=timeout)
            cr = rg.headers.get("Content-Range", "")
            m = RANGE_RE.search(cr)
            if m:
                size = int(m.group(1))
            # Algunos servers devuelven CD en el 206
            cd = rg.headers.get("Content-Disposition", "")
            if cd and not fname:
                fname = _parse_content_disposition(cd)
        except Exception:
            pass

    return size, fname

def _decode_rfc5987(value: str) -> str:
    """
    Decodifica filename*=charset''urlenc (RFC 5987).
    """
    try:
        m = FILENAME_STAR_RE.search(value)
        if not m: 
            return ""
        charset, enc = m.group(1) or "utf-8", m.group(2)
        return _up.unquote(enc, encoding=charset or "utf-8", errors="replace")
    except Exception:
        return ""

def _filename_from_headers(headers) -> str:
    """
    Intenta extraer el nombre de archivo desde Content-Disposition.
    Soporta filename*= (RFC 5987) y filename="...".
    """
    cd = headers.get("Content-Disposition") or headers.get("content-disposition")
    if not cd:
        return ""
    # filename*=
    fn = _decode_rfc5987(cd)
    if fn:
        return fn.strip()
    # filename="..."
    m = FILENAME_QUOTED_RE.search(cd)
    if m:
        return m.group(1).strip()
    # filename=sin comillas
    m = FILENAME_UNQUOTED_RE.search(cd)
    if m:
        return m.group(1).strip().strip("'")
    return ""

def _filename_from_url(u: str) -> str:
    """
    Extrae el nombre de archivo de la ruta de una URL.

    Toma el último segmento de la ruta (ej. 'archivo.pdf' de
    'https://sitio.com/path/archivo.pdf') y lo decodifica (unquote).

    Args:
        u (str): La URL completa.

    Returns:
        str: El nombre de archivo extraído de la URL, o "" si falla.
    """
    try:
        path = urlsplit(u).path or ""
        base = path.rsplit("/", 1)[-1]
        return unquote(base) or ""
    except Exception:
        return ""

def _filename_from_cd(cd: str) -> str:
    """
    Extrae el nombre de archivo de un string Content-Disposition.

    Busca patrones 'filename*=' (RFC 5987) o 'filename="..."'.

    Nota: Esta es una de varias funciones en el archivo que intentan
    parsear este header. '_parse_content_disposition' es más completa.

    Args:
        cd (str): El string completo del header Content-Disposition.

    Returns:
        str: El nombre de archivo encontrado, o "" si no se encuentra.
    """
    if not cd:
        return ""
    # RFC 5987: filename*=UTF-8''...
    m = re.search(r"filename\*=(?:UTF-8''|)([^;]+)", cd, re.I)
    if m:
        return unquote(m.group(1)).strip(' "')
    # filename="..."
    m = re.search(r'filename="?([^";]+)"?', cd, re.I)
    return m.group(1).strip() if m else ""
    
def _content_length_from_headers(headers) -> int | None:
    """
    Lee Content-Length si existe y es numérico.
    """
    cl = headers.get("Content-Length") or headers.get("content-length")
    if not cl:
        return None
    try:
        return int(cl)
    except Exception:
        return None

def _probe_head_for_meta(session, url: str, timeout: float):
    """
    HEAD para sacar tamaño/nombre sin descargar cuerpo.
    Algunos servers bloquean HEAD → entonces devolvemos {}.
    """
    try:
        r = session.head(url, allow_redirects=True, timeout=timeout)
        # Algunos proxies devuelven 405/403 a HEAD
        if r.status_code >= 400:
            return {}
        size = _content_length_from_headers(r.headers)
        fname = _filename_from_headers(r.headers)
        return {"size_bytes_server": size, "filename_header": fname}
    except Exception:
        return {}

def _probe_range_for_size(session, url: str, timeout: float):
    """
    GET parcial con Range: bytes=0-0. Si el server soporta rangos (206),
    Content-Range trae el total: 'bytes 0-0/12345' → 12345.
    """
    try:
        r = session.get(url, headers={"Range": "bytes=0-0"},
                        allow_redirects=True, timeout=timeout, stream=True)
        # Si responde 206 es buena señal; si 200 puede no soportar rangos.
        cr = r.headers.get("Content-Range") or r.headers.get("content-range")
        if cr:
            # formato: bytes start-end/total
            m = re.search(r"/\s*(\d+)\s*$", cr)
            if m:
                return {"size_bytes_server": int(m.group(1))}
        # fallback: si vino Content-Length en 200 (a veces lo incluyen igual)
        size = _content_length_from_headers(r.headers)
        if size:
            return {"size_bytes_server": size}
        return {}
    except Exception:
        return {}

def augment_with_remote_meta(session, url: str, timeout=30):
    """
    Obtiene metadatos (tamaño, nombre de archivo) del servidor.
    
    Intenta HEAD (Content-Length / Content-Disposition).
    Si no hay tamaño, prueba un GET con Range: bytes=0-0 y lee Content-Range.

    Args:
        session (requests.Session): Sesión de requests.
        url (str): URL del archivo a probar.
        timeout (int): Timeout para las peticiones.

    Returns:
        Dict[str, Any]: Un diccionario con:
            - "size_bytes_server" (int | None)
            - "filename_header" (str)
            - "filename_final" (str)
    """
    size_server, fname_hdr = None, ""

    try:
        # 1) HEAD
        rh = session.head(url, allow_redirects=True, timeout=timeout)
        rh.raise_for_status()

        cl = rh.headers.get("Content-Length")
        if cl and cl.isdigit():
            size_server = int(cl)

        fname_hdr = _filename_from_cd(rh.headers.get("Content-Disposition", ""))

        # 2) Si no hay Content-Length, probamos GET con Range: 0-0
        if size_server is None:
            rg = session.get(
                url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                allow_redirects=True,
                timeout=timeout,
            )
            # Puede devolver 206 Partial Content con "Content-Range: bytes 0-0/123456"
            cr = rg.headers.get("Content-Range", "")
            m = re.search(r"/(\d+)$", cr)
            if m:
                size_server = int(m.group(1))
    except Exception:
        # No interrumpimos el flujo si falla
        pass

    filename_url = _filename_from_url(url)
    filename_final = fname_hdr or filename_url

    return {
        "size_bytes_server": size_server,
        "filename_header": fname_hdr,
        "filename_final": filename_final,
    }


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
    """
    Convierte un string de tamaño (ej. "1.2 MB") a bytes.

    Nota: Esta función es muy similar a 'text2num' de utils.py.

    Args:
        tam_text (str): El string de tamaño (ej. "512 KB", "1,2 MB").

    Returns:
        int | None: El número de bytes, o None si no se pudo parsear.
    """
    if not tam_text: return None
    txt = tam_text.replace(",", ".").strip().upper()
    m = re.search(r"([\d\.]+)\s*(KB|MB|B)", txt)
    if not m: return None
    n, unit = float(m.group(1)), m.group(2)
    if unit == "MB": return int(n * 1024 * 1024)
    if unit == "KB": return int(n * 1024)
    return int(n)

def _clean_spaces(s: str) -> str:
    """
    Limpia el exceso de espacios en blanco de un string.

    Nota: Esta función es idéntica a 'clean_whitespace' de utils.py.

    Args:
        s (str): El string a limpiar.

    Returns:
        str: El string limpio.
    """
    return re.sub(r"\s+", " ", s or "").strip()

def _near_block(a):
    """
    Encuentra el texto "contextual" más cercano al ancla <a>.
    El mejor contexto suele estar en el padre <li>, <div>, o fila <tr>.
    """
    for tag in ("li","div","td","tr","p","article","section"):
        p = a.find_parent(tag)
        if p: 
            return p.get_text(" ", strip=True)
    # fallback a toda la página si no hay padres “semánticos”
    return a.find_parent().get_text(" ", strip=True)

def parse_index_page(page_url, html, rows, logger):
    """
    Parsea el HTML de una página de índice y extrae todos los enlaces
    a PDF/XLS, junto con sus metadatos contextuales.

    Modifica la lista 'rows' in-place.
    """
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("a[href]")
    total_links = 0
    kept_links = 0

    for a in anchors:
        row = {}  # ← asegura que exista aunque algo falle más arriba

        href = a.get("href") or ""
        mext = EXT_RE.search(href)
        if not mext:
            continue
        total_links += 1

        tipo_raw = mext.group(1).lower()
        tipo = "xls" if tipo_raw.startswith("xls") else "pdf"
        href_abs = urljoin(page_url, href)

        link_text  = _clean_spaces(" ".join(a.stripped_strings))
        block_text = _clean_spaces(_near_block(a))
        context = f"{link_text} | {block_text}"

        # ===== tamaño visible en la página (texto) → bytes (page)
        size_text = a.get("title") or a.get("data-size") or ""
        if not size_text:
            msize = SIZE_RE.search(context)
            size_text = msize.group(1) if msize else ""
        size_bytes_page = _text2bytes(size_text)

        # ===== fecha
        mfecha = DATE_RE.search(context)
        fecha_publicacion = mfecha.group(2) if mfecha else ""

        # ===== capítulo / título
        mcap = ROMAN_TITLE_RE.search(context)
        cap_num = mcap.group(1).strip() if mcap else ""
        tit_corto = mcap.group(2).strip() if mcap else ""

        if not cap_num or not tit_corto:
            try:
                idx = html.find(href)
                s = max(0, idx - 600)
                snippet = _clean_spaces(html[s:idx])
                mcap2 = ROMAN_TITLE_RE.search(snippet)
                if mcap2:
                    cap_num   = cap_num   or mcap2.group(1).strip()
                    tit_corto = tit_corto or mcap2.group(2).strip()
            except Exception:
                pass

        cap_num = _prefer_cap_by_href(cap_num, href)

        # construir row una sola vez
        row = {
            "capitulo": cap_num,
            "titulo_corto": tit_corto,
            "tipo_archivo": tipo,
            "tamano": size_text,                 # texto crudo visible
            "size_bytes_page": size_bytes_page,  # bytes parseados del texto
            "tamano_bytes_aprox": _text2bytes(size_text) or "",
            "fecha_publicacion": fecha_publicacion,
            "url_descarga": href_abs,
            "url_pagina": page_url,
            "size_bytes_server": "",             # se completa luego
            "filename_header": "",               # se completa luego
            "filename_url": _filename_from_url(href_abs),
            "filename_final": ""                 # se completa luego
        }

        if row["url_descarga"] and row["tipo_archivo"] in {"pdf", "xls"}:
            rows.append(row)
            kept_links += 1
        else:
            # No referenciar 'row' si no estamos seguros de que tenga todo
            logger.warning(
                "Descartado (incompleto): tipo=%s url=%s size_text=%s",
                tipo, href_abs, size_text
            )

    logger.info("Página %s: %d enlaces PDF/XLS encontrados, %d válidos",
                page_url, total_links, kept_links)

def scrape_index_page(session, page_url: str, logger):
    """
    Descarga y parsea una página de índice para extraer enlaces PDF/XLS.

    Nota: Esta función es casi idéntica a 'parse_index_page' pero
    descarga el contenido ella misma en lugar de recibirlo.

    Args:
        session (requests.Session): La sesión de requests para descargar.
        page_url (str): La URL de la página de índice a crawlear.
        logger (logging.Logger): El logger para registrar eventos.

    Returns:
        List[Dict[str, Any]]: Una lista de diccionarios (filas) con
                              los metadatos extraídos.
    """
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

# === consulta al servidor para tamaño y filename ===
def _head_size_and_name(session, url: str, timeout):
    """
    Devuelve (size_bytes_server, filename_header). Intenta HEAD y si no hay
    Content-Length, prueba GET con Range: bytes=0-0 para leer Content-Range.
    """
    size_server, fname_hdr = None, ""
    try:
        r = session.head(url, allow_redirects=True, timeout=timeout)
        r.raise_for_status()
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit():
            size_server = int(cl)
        fname_hdr = _filename_from_cd(r.headers.get("Content-Disposition", ""))

        if size_server is None:
            # Algunos servidores no informan en HEAD; probamos Range:
            r2 = session.get(url, headers={"Range": "bytes=0-0"},
                             stream=True, allow_redirects=True, timeout=timeout)
            cr = r2.headers.get("Content-Range", "")
            m = re.search(r"/(\d+)$", cr)
            if m:
                size_server = int(m.group(1))
    except Exception:
        pass
    return size_server, fname_hdr

def crawl_index(pages=None, out_csv=f"{OUT_DIR}/indicadores_index.csv",
                delay=DEFAULT_DELAY_SEC, max_pages=10, log_dir="logs"):
    """
    Orquesta el proceso completo de crawling de índice.

    1. Descarga las páginas de índice.
    2. Parsea los enlaces y metadatos de la página.
    3. Enriquece los metadatos con peticiones HEAD/Range.
    4. Resuelve el tamaño final y de-duplica.
    5. Escribe el archivo 'indicadores_index.csv'.

    Args:
        pages (Optional[List[str]], optional): Lista de URLs de índice.
            Usa BASE_INDEX_PAGES de settings si es None.
        out_csv (Path, optional): Ruta de salida del CSV.
        delay (float, optional): Pausa entre descargas de páginas.
        max_pages (int, optional): Límite de páginas de índice a descargar.
        log_dir (Path, optional): Directorio para guardar logs.

    Returns:
        Path: La ruta al archivo CSV generado.
    """
    ensure_dirs(OUT_DIR, log_dir)
    logger = make_logger(log_dir, "crawl_index")
    pages = pages or BASE_INDEX_PAGES
    rows = []
    n = 0

    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        logger.info(f"User-Agent en uso: {DEFAULT_UA}")  # ← evidencia en logs

        # ==== 1) CRAWL PÁGINAS ====
        for page_url in pages:
            if n >= max_pages:
                break
            try:
                r = s.get(page_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
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

        # ==== 2) ENRIQUECER METADATOS REMOTOS (HEAD / Range) ====
        # Elegimos filas que no tengan size de servidor; limitamos para no castigar el sitio
        to_probe = []
        for i, row in enumerate(rows):
            # Si no hay tamaño server, intentamos; filename_url casi siempre está
            if not row.get("size_bytes_server"):
                to_probe.append(i)

        MAX_PROBES = 200
        if len(to_probe) > MAX_PROBES:
            logger.info(f"Reduciendo probes de {len(to_probe)} a {MAX_PROBES} para ser amables.")
            to_probe = to_probe[:MAX_PROBES]

        meta_cache = {}
        for i in to_probe:
            url = rows[i].get("url_descarga")
            if not url:
                continue
            if url not in meta_cache:
                meta_cache[url] = augment_with_remote_meta(s, url, timeout=REQUEST_TIMEOUT)
                polite_sleep(0.2, logger)  # mini-delay entre probes
            meta = meta_cache[url] or {}

            # Completar campos remotos
            if meta.get("size_bytes_server") is not None:
                rows[i]["size_bytes_server"] = meta["size_bytes_server"]
            if meta.get("filename_header"):
                rows[i]["filename_header"] = meta["filename_header"]

            # filename_final: header > url
            rows[i]["filename_final"] = meta.get("filename_final") or rows[i].get("filename_url", "")
        
        for r in rows:
            resolve_size(r)

        # ==== 3) DEDUP ====
        seen = set()
        out = []
        for row in rows:
            k = row.get("url_descarga", "")
            if not k or k in seen:
                continue
            seen.add(k)

            # Asegurar filename_final
            row["filename_final"] = row.get("filename_final") or row.get("filename_url") or ""

            # ==== 4) TAMAÑO UNIFICADO ====
            # Prioridad: size_bytes_server > size_bytes_page > tamano_bytes_aprox
            size_server = row.get("size_bytes_server")
            size_page   = row.get("size_bytes_page")
            size_aprox  = row.get("tamano_bytes_aprox")

            # Normalizar a enteros o None
            size_server = int(size_server) if str(size_server).isdigit() else None
            size_page   = int(size_page) if str(size_page).isdigit() else None
            try:
                size_aprox = int(size_aprox) if str(size_aprox).isdigit() else None
            except Exception:
                size_aprox = None

            unificado = size_server or size_page or size_aprox
            row["tamano_bytes"] = unificado or ""
            row["tamano_resuelto"] = _human_bytes(unificado) if unificado else ""

            out.append(row)

    # ==== 5) CSV ====
    hdr = [
        "capitulo", "titulo_corto", "tipo_archivo",
        "tamano_resuelto",        # ← humano de 'tamano_bytes'
        "fecha_publicacion",
        "filename_final",
        "url_descarga", "url_pagina"
    ]

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