# Copyright (c) 2025 Serrentino Mangino, S., & Mochon Paredes, A.
# Licensed under the MIT License. See LICENSE for details.

from typing import List, Tuple, Union, Optional, Any, Dict, Set
from pathlib import Path
import logging

import io
import os
import re
import tempfile
import requests
import pandas as pd
import xlrd
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- Tus otras importaciones ---
from .settings import DEFAULT_UA, REQUEST_TIMEOUT, OUT_DIR
from .utils import make_logger, ensure_dirs

# ===================== Detectores de formato =====================

def _sniff(bytes_buf: bytes):
    """
    Detecta el tipo de contenido (xlsx, xls, html, text) usando "magic bytes".

    Args:
        bytes_buf (bytes): Los primeros bytes del archivo (al menos 8).

    Returns:
        str: Uno de "xlsx", "xls", "html", "text", o "unknown".
    """
    head = bytes_buf[:8]
    if head[:2] == b"PK":
        return "xlsx"
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return "xls"
    if head.lstrip().startswith(b"<"):
        return "html"
    try:
        head.decode("utf-8")
        return "text"
    except Exception:
        return "unknown"

def _engine_from_ext_or_sniff(url: str, bytes_buf: bytes):
    """
    Determina el tipo de archivo ('kind') y el motor de pandas ('engine').

    Primero confía en la extensión (.xls, .xlsx). Si no, usa _sniff()
    para determinar el tipo basado en el contenido.

    Args:
        url (str): La URL de donde se descargó el archivo (para ver extensión).
        bytes_buf (bytes): El contenido del archivo para "sniffing".

    Returns:
        tuple[str | None, str | None]: (kind, engine)
            Ej: ("xlsx", "openpyxl"), ("xls", "xlrd"), ("html", None)
    """
    path = urlparse(url).path.lower()
    kind = None
    if path.endswith(".xlsx"):
        kind = "xlsx"
    elif path.endswith(".xls"):
        kind = "xls"
    sniff = _sniff(bytes_buf)
    if sniff in ("xlsx", "xls", "html", "text"):
        kind = sniff
    if kind == "xlsx":
        return kind, "openpyxl"
    if kind == "xls":
        return kind, "xlrd"
    return kind, None  # html/text -> sin engine de Excel

# ===================== Descarga y helpers =====================

def _download(url, session, logger):
    """
    Descarga el contenido de una URL y devuelve los bytes.

    Lanza una excepción si la petición falla (ej. 404, 500).

    Args:
        url (str): URL a descargar.
        session (requests.Session): Sesión de requests a utilizar.
        logger (logging.Logger): Logger para registrar la descarga.

    Returns:
        bytes: El contenido crudo del archivo.
    """
    r = session.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    logger.info(
        f"Descargado {url} -> {len(r.content)} bytes | "
        f"Content-Type={r.headers.get('Content-Type','')}"
    )
    return r.content  # bytes

def _to_num(series):
    """
    Normaliza una serie a numérico, manejando formatos latinos (ej. "1.234,56").

    Intenta una conversión numérica directa. Si eso aumenta la tasa de NaNs
    (indicando que falló al parsear strings), re-intenta limpiando
    separadores de miles (.), cambiando decimales (,) a (.) y eliminando
    guiones/rayas.

    Args:
        series (pd.Series): Serie de entrada (usualmente de tipo 'object').

    Returns:
        pd.Series: Serie de tipo 'float' o 'int'.
    """
    s_num = pd.to_numeric(series, errors="coerce")
    original_nan_rate = pd.Series(series).isna().mean()
    converted_nan_rate = s_num.isna().mean()

    if converted_nan_rate > original_nan_rate:
        s = (
            pd.Series(series)
            .astype(str)
            .str.replace(r"\u2014|\u2212|–|-", "", regex=True)  # rayas
            .str.replace(r"\.", "", regex=True)                # miles
            .str.replace(",", ".", regex=False)                # decimal
        )
        return pd.to_numeric(s, errors="coerce")
    return s_num

def _norm_mes(df, col_fecha):
    """
    Convierte fechas a periodo mensual (1er día del mes) y elimina filas sin fecha.

    Crea una nueva columna 'fecha' y elimina la `col_fecha` original si
    es diferente.

    Args:
        df (pd.DataFrame): DataFrame con la columna de fecha.
        col_fecha (str): Nombre de la columna que contiene las fechas.

    Returns:
        pd.DataFrame: DataFrame con la columna 'fecha' normalizada y NaNs filtrados.
    """
    df = df.copy()
    s = pd.to_datetime(df[col_fecha], errors="coerce")
    df["fecha"] = s.dt.to_period("M").dt.to_timestamp()
    if col_fecha != "fecha":
        df = df.drop(columns=[col_fecha])
    df = df.dropna(subset=["fecha"])
    return df

def _looks_unnamed_columns(df: pd.DataFrame, threshold: float = 0.9) -> bool: # <-- ¡UMBRAL CAMBIADO!
    """Comprueba si la mayoría de las columnas se llaman 'Unnamed:'"""
    cols = [str(c) for c in df.columns]
    cnt = sum(c.startswith("Unnamed:") or c.strip() == "" for c in cols)
    return (cnt / max(1, len(cols))) >= threshold

def _promote_row_with_fecha_as_header(df: pd.DataFrame, max_scan: int = 20) -> pd.DataFrame | None:
    """
    Busca dentro de las primeras filas una que contenga 'Fecha' (case-insensitive),
    y la usa como encabezado.
    """
    vals = df.astype(object).where(pd.notna(df), "").astype(str)
    for i in range(min(max_scan, len(vals))):
        row = vals.iloc[i].str.strip().str.lower().tolist()
        if any(cell == "fecha" for cell in row):
            new_cols = [c.strip() if c.strip() else f"col_{j}" for j, c in enumerate(vals.iloc[i].tolist())]
            out = df.iloc[i+1:].copy()
            out.columns = new_cols
            out = out.reset_index(drop=True)
            out = out.loc[:, out.notna().mean() > 0.0]
            return out
    return None

def _fix_excel_serial_dates(series: pd.Series) -> pd.Series:
    """
    Convierte una columna de fechas mixta (serial Excel y strings "ene-25").
    """
    s_num = pd.to_numeric(series, errors="coerce")
    dates_from_num = pd.to_datetime(s_num, unit="D", origin="1899-12-30", errors="coerce")

    s_str = series.astype(str).str.strip().str.lower()
    replacements = {
        'ene': 'jan', 'feb': 'feb', 'mar': 'mar', 'abr': 'apr',
        'may': 'may', 'jun': 'jun', 'jul': 'jul', 'ago': 'aug',
        'sep': 'sep', 'oct': 'oct', 'nov': 'nov', 'dic': 'dec'
    }
    for esp, eng in replacements.items():
        s_str = s_str.str.replace(esp, eng, regex=False)
    dates_from_str = pd.to_datetime(s_str, errors="coerce")

    final_dates = dates_from_num.fillna(dates_from_str)
    return final_dates

def _pick_best_series(obj: Any) -> pd.Series:
    """
    Si 'obj' es un DataFrame (p. ej., por etiquetas de columna duplicadas),
    elige la subcolumna con más datos numéricos (menos NaN tras coerción).
    Si es Serie, la devuelve tal cual.
    """
    if isinstance(obj, pd.DataFrame):
        best_i = -1
        best_score = -1
        # iteramos por posición para evitar que obj[c] devuelva otro DF cuando hay duplicados
        for i in range(obj.shape[1]):
            s = pd.to_numeric(obj.iloc[:, i], errors="coerce")
            score = s.notna().sum()
            if score > best_score:
                best_score, best_i = score, i
        return obj.iloc[:, best_i]
    elif isinstance(obj, pd.Series):
        return obj
    # último recurso: intenta convertir a Serie
    return pd.Series(obj)



# ===================== Fallbacks (xlrd, win32) =====================
# (Estas funciones son helpers, no las anidamos)
def _try_xlrd_manual(bytes_buf: bytes, logger, sheet=None):
    """
    (Fallback 1) Lectura manual de .xls usando xlrd directamente.
    Devuelve un DataFrame intentando varias filas como cabecera.
    """

    try:
        # Muchos .xls de BPS están en cp1252
        book = xlrd.open_workbook(file_contents=bytes_buf,
                                  encoding_override="cp1252",
                                  formatting_info=False)
    except Exception as e:
        logger.warning(f"xlrd.open_workbook falló: {type(e).__name__}: {e}")
        return None

    # Selección de hoja
    try:
        if isinstance(sheet, str):
            sh = book.sheet_by_name(sheet)
        else:
            sh = book.sheet_by_index(sheet if isinstance(sheet, int) else 0)
    except Exception as e:
        logger.warning(f"No pude abrir la hoja solicitada: {type(e).__name__}: {e}")
        return None

    # Leer todas las celdas en memoria
    rows = []
    for r in range(sh.nrows):
        row = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            # No convertimos fechas aquí: _fix_excel_serial_dates lo hará después
            row.append(cell.value)
        rows.append(row)

    if not rows or sh.ncols < 2:
        return None

    raw = pd.DataFrame(rows)

    # Intentar promover distintas filas como cabecera
    header_candidates = (7, 6, 5, 4, 0, 1, 2, 3)
    last_err = None
    for hdr in header_candidates:
        if hdr >= len(raw):
            continue
        try:
            header = raw.iloc[hdr].astype(str).str.strip().tolist()
            data = raw.iloc[hdr+1:].reset_index(drop=True).copy()
            data.columns = [h if h else f"col_{i}" for i, h in enumerate(header)]
            # filtra columnas totalmente vacías
            data = data.loc[:, data.notna().mean() > 0.0]
            # ¿Parece tabla útil?
            if data.dropna(how="all").shape[0] > 1 and data.shape[1] >= 2:
                # prueba promoción “Fecha” si las columnas siguen feas
                if _looks_unnamed_columns(data):
                    p = _promote_row_with_fecha_as_header(data)
                    if p is not None and p.dropna(how="all").shape[0] > 1 and p.shape[1] >= 2:
                        logger.info(f"xlrd-manual OK con header={hdr} + promoción Fecha")
                        p.attrs["sheet_name"] = sh.name 
                        return p
                logger.info(f"xlrd-manual OK con header={hdr}")
                data.attrs["sheet_name"] = sh.name
                return data
        except Exception as e:
            last_err = e

    if last_err:
        logger.warning(f"xlrd-manual sin éxito: {type(last_err).__name__}: {last_err}")
    return None

def _try_win32_excel_export(bytes_buf: bytes, logger):
    """
    (Fallback 2) Intenta usar la API COM de Windows para abrir Excel y re-guardar.

    Esto solo funciona en Windows con Excel instalado. Es el último recurso
    para archivos .xls extremadamente corruptos o antiguos.

    Args:
        bytes_buf (bytes): Contenido del archivo Excel.
        logger (logging.Logger): Logger para registrar la actividad.

    Returns:
        pd.DataFrame | None: El DataFrame leído, o None si falla.
    """
    try:
        import win32com.client
        from win32com.client import constants
    except Exception as e:
        logger.info(f"win32com no disponible: {type(e).__name__}: {e}")
        return None
    # ... (resto de la función win32 omitida por brevedad) ...
    # ... (si la tienes, déjala como está) ...
    return None # Asumimos que la tienes, si no, pega tu versión aquí

# ===================== Lector Genérico =====================

def _read_table_like(bytes_buf, kind, engine, logger, sheet=None, header_hint=None):
    """
    Lector genérico y robusto para archivos tipo tabla (Excel, HTML, CSV).

    Prueba múltiples estrategias de lectura y limpieza (ej. probar
    múltiples filas de cabecera) y utiliza fallbacks (xlrd, win32com)
    si la lectura principal de pandas falla.

    Args:
        bytes_buf (bytes): Contenido crudo del archivo.
        kind (str | None): Tipo de archivo detectado (ej. "xlsx", "xls", "html").
        engine (str | None): Motor de pandas sugerido (ej. "openpyxl", "xlrd").
        logger (logging.Logger): Logger para registrar el proceso.
        sheet (str | int | None, optional): Hoja específica a leer.
        header_hint (int | None, optional): Fila (índice 0) que se probará
                                            primero como cabecera.

    Raises:
        RuntimeError: Si no puede leer el contenido como Excel/HTML/CSV.
        ValueError: Si el formato 'kind' es desconocido.

    Returns:
        pd.DataFrame: El DataFrame extraído.
    """
    bio = io.BytesIO(bytes_buf)

    # --- INICIO DE FUNCIONES ANIDADAS ---
    # Estas funciones DEBEN estar DENTRO de _read_table_like
    # para acceder a 'bio', 'engine', 'logger', 'sheet', etc.

    def _try_read_excel(header_hint_internal=None):
        """
        Intenta leer un Excel probando múltiples filas de cabecera.

        Prioritiza el 'header_hint' y luego prueba una lista de
        cabeceras comunes (6, 7, 5, etc.). Filtra DataFrames "inútiles"
        (ej. vacíos o con columnas 'Unnamed:').
        """
        bio.seek(0)
        try:
            xls = pd.ExcelFile(bio, engine=engine)
        except Exception as e:
            logger.warning(f"ExcelFile falló: {type(e).__name__}: {e}")
            return None

        if sheet is not None:
            sheets_to_try = [sheet]    # respeta hoja específica
        else:
            sheets_to_try = list(xls.sheet_names)  # probar todas

            # PRIORIDAD: ALTAS > EMISIÓN > PROMEDIO > resto
            def _sheet_score(name: str) -> int:
                low = str(name).lower()
                if "altas" in low:
                    return 0
                if "emisión" in low or "emision" in low:
                    return 1
                if "promedio" in low:
                    return 2
                return 3

            sheets_to_try = sorted(sheets_to_try, key=_sheet_score)

        if header_hint_internal is not None:
             headers_to_try = (header_hint_internal, 6, 7, 5, 4, 0, 1, 2, 3)
        else:
            headers_to_try = (6, 7, 5, 4, 0, 1, 2, 3) 

        headers_a_probar_final = []
        seen = set()
        for hdr in headers_to_try:
            if hdr not in seen:
                headers_a_probar_final.append(hdr)
                seen.add(hdr)

        last_err = None
        best_df = None
        best_df_sheet = None
        best_score = (-1, -1)   # (n_cols, n_rows_utiles)
        for use_sheet in sheets_to_try:
            for hdr in headers_a_probar_final:
                try:
                    bio.seek(0)
                    df = pd.read_excel(bio, sheet_name=use_sheet, engine=engine, header=hdr)

                    # Limpieza mínima
                    df = df.loc[:, df.notna().mean() > 0.0]  # quita columnas totalmente vacías

                    # Si la cabecera quedó fea, intenta promover una fila con "Fecha"
                    if _looks_unnamed_columns(df):
                        p = _promote_row_with_fecha_as_header(df)
                        if p is not None:
                            df = p

                    rows_ok = df.dropna(how="all").shape[0]
                    cols_ok = df.shape[1]

                    # Criterio de “tabla útil”
                    if cols_ok >= 2 and rows_ok > 1:
                        logger.info(f"Excel OK: hoja={use_sheet} header={hdr} cols={list(df.columns)[:6]}")
                        df.attrs["sheet_name"] = str(use_sheet)
                        return df

                    # Guarda el mejor candidato por si ninguna pasa el umbral fuerte
                    score = (cols_ok, rows_ok)
                    if score > best_score:
                        best_score, best_df = score, df
                        best_df_sheet = use_sheet

                except Exception as e:
                    last_err = e
                    continue

        # Devolver el mejor si supera un umbral mínimo
        if best_df is not None and best_score[0] >= 2 and best_score[1] > 0:
            if best_df_sheet is not None:
                best_df.attrs["sheet_name"] = str(best_df_sheet)
            logger.info(f"Excel débilmente válido (mejor hallado): score={best_score}")
            return best_df

        if last_err:
            logger.warning(f"Excel falló: {type(last_err).__name__}: {last_err}")
       
        return None 

        
    def _try_read_html():
        """Intenta leer como HTML usando pandas.read_html (elige la tabla más ancha)."""
        bio.seek(0)
        try:
            tables = pd.read_html(bio, flavor="bs4")
        except Exception as e:
            logger.warning(f"read_html falló: {type(e).__name__}: {e}")
            return None
        if not tables:
            return None
        # Elige la tabla con más columnas
        df = max(tables, key=lambda t: t.shape[1])
        # Promueve cabecera si quedó 'Unnamed:'
        if _looks_unnamed_columns(df):
            p = _promote_row_with_fecha_as_header(df)
            if p is not None:
                df = p
        if df.dropna(how="all").shape[0] <= 1 or df.shape[1] < 2:
            return None
        return df

    def _try_bs4_table(bytes_buf_local, logger_local):
        """Extrae manualmente la tabla más grande con BeautifulSoup."""
        try:
            soup = BeautifulSoup(bytes_buf_local, "lxml")
        except Exception:
            soup = BeautifulSoup(bytes_buf_local, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return None
        # Elige la tabla con más filas
        table = max(tables, key=lambda t: len(t.find_all("tr")))
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if not rows:
            return None
        header = rows[0]
        data = rows[1:]
        df = pd.DataFrame(data, columns=[c if c else f"col_{i}" for i, c in enumerate(header)])
        if _looks_unnamed_columns(df):
            p = _promote_row_with_fecha_as_header(df)
            if p is not None:
                df = p
        if df.dropna(how="all").shape[0] <= 1 or df.shape[1] < 2:
            return None
        return df

    def _try_read_csv():
        """Prueba como CSV/TSV con separadores comunes."""
        for sep in (";", ",", "\t"):
            bio.seek(0)
            try:
                df = pd.read_csv(bio, sep=sep, engine="python")
                if df.dropna(how="all").shape[0] > 1 and df.shape[1] >= 2:
                    return df
            except Exception:
                pass
        return None

    # --- Ruta principal de _read_table_like ---
    if kind in ("xlsx", "xls"):
        df = _try_read_excel(header_hint) 
        if df is not None:
            return df

        logger.info("Intento fallback xlrd-manual…")
        try:
            df = _try_xlrd_manual(bytes_buf, logger, sheet=sheet)
            if df is not None and df.shape[1] >= 2:
                return df
        except Exception as e:
            logger.warning(f"xlrd-manual falló: {type(e).__name__}: {e}")

        logger.info("Intento fallback Excel-COM…")
        df = _try_win32_excel_export(bytes_buf, logger)
        if df is not None:
            return df
            
        logger.info("Intento fallback HTML…")
        df = _try_read_html()
        if df is not None:
            return df

        logger.info("Intento fallback BS4-table…")
        df = _try_bs4_table(bytes_buf, logger)
        if df is not None:
            return df

        logger.info("Intento fallback CSV/TSV…")
        df = _try_read_csv()
        if df is not None:
            return df

        try:
            tmp = Path(tempfile.gettempdir()) / "parse_fail_dump.bin"
            tmp.write_bytes(bytes_buf)
            logger.warning(f"Dump binario guardado en {tmp} para depuración")
        except Exception:
            pass

        raise RuntimeError("No pude leer el contenido ni como Excel ni como HTML/CSV")

    if kind == "html":
        df = _try_read_html()
        if df is not None:
            return df
        df = _try_bs4_table(bytes_buf, logger)
        if df is not None:
            return df
        # último intento: ¿la página es CSV embebido?
        df = _try_read_csv()
        if df is not None:
            return df
        
        # Dump opcional aquí
        try:
            tmp = Path(tempfile.gettempdir()) / "parse_fail_dump_html.bin"
            tmp.write_bytes(bytes_buf)
            logger.warning(f"Dump HTML guardado en {tmp} para depuración")
        except Exception:
            pass

        raise RuntimeError("HTML no legible como tabla")

    if kind == "text":
        df = _try_read_csv()
        if df is not None:
            return df
        
        try:
            tmp = Path(tempfile.gettempdir()) / "parse_fail_dump_text.bin"
            tmp.write_bytes(bytes_buf)
            logger.warning(f"Dump texto guardado en {tmp} para depuración")
        except Exception:
            pass

        raise RuntimeError("Texto plano sin formato tabular")


    # Fallback cuando 'kind' es None o 'unknown': intentar HTML/CSV igual
    if kind in (None, "unknown"):
        logger.info("Formato 'unknown': pruebo HTML y CSV por si acaso…")
        df = _try_read_html()
        if df is not None:
            return df
        df = _try_bs4_table(bytes_buf, logger)
        if df is not None:
            return df
        df = _try_read_csv()
        if df is not None:
            return df


    raise ValueError("Formato desconocido o no soportado")


# ===================== Parsers específicos =====================

def parse_desempleo(
    xls_url: str,
    out_csv: Path = OUT_DIR / "series_desempleo.csv",
    sheet: Union[str, int, None] = None,
    fecha_col_guess: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> Path:
    """
    Parsea el archivo de "III.3 Subsidio por desempleo".

    Descarga, lee (con fallbacks), limpia, busca la columna de fecha,
    mapea las columnas de métricas (altas, bajas, etc.) y guarda en CSV.

    Args:
        xls_url (str): URL al archivo XLS/XLSX.
        out_csv (Path, optional): Ruta de salida para el CSV.
        sheet (Union[str, int, None], optional): Nombre/índice de la hoja a leer.
        fecha_col_guess (Optional[str], optional): Pista para la columna de fecha.
        logger (Optional[logging.Logger], optional): Logger existente.

    Returns:
        Path: La ruta al archivo CSV generado.
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(out_csv.parent)
    
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        
        # Pasamos la pista del header=7 (Fila 8) para desempleo
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet, header_hint=7)

        # --- Limpieza de columnas ---
        cols_originales = list(df.columns)
        cols_unnamed = df.columns.str.contains(r'^Unnamed: \d+$', na=True)
        cols_totalmente_vacias = df.isna().all()
        columnas_a_mantener = ~ (cols_unnamed | cols_totalmente_vacias)
        df = df.loc[:, columnas_a_mantener]
        logger.info(f"Columnas pre-limpieza: {cols_originales}")
        logger.info(f"Columnas post-limpieza: {list(df.columns)}")

        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        cols_low = {str(c).lower(): c for c in df.columns}

        if _looks_unnamed_columns(df):
            df2 = _promote_row_with_fecha_as_header(df)
            if df2 is not None:
                df = df2
                df = df.rename(columns={c: str(c).strip() for c in df.columns})
                cols_low = {str(c).lower(): c for c in df.columns}


        # --- Encontrar columna de fecha ---
        fecha_col = (
            fecha_col_guess
            or next((cols_low[c] for c in cols_low if "fecha" in c or "mes" in c), None)
        )
        if not fecha_col:
            c0 = list(df.columns)[0]
            if (
                df[c0].astype(str).str.contains(
                    r"(?:\b(202\d|201\d)\b|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)",
                    case=False, regex=True,
                ).mean() > 0.3
            ):
                fecha_col = c0
        if not fecha_col:
            raise ValueError("No encuentro columna de fecha/mes en 'desempleo'")

        # --- Mapeo de columnas ---
        def find_col(patterns: List[str]) -> Optional[str]:
            for p in patterns:
                col_name = next((cols_low[c_low] for c_low in cols_low if re.search(p, c_low)), None)
                if col_name:
                    return col_name
            return None

        sheet_name = str(getattr(df, "attrs", {}).get("sheet_name", "")).lower()
        sheet_hint = (str(sheet).lower() if isinstance(sheet, str) else sheet_name)

        is_altas = "altas" in sheet_hint
        is_emision = ("emisión" in sheet_hint) or ("emision" in sheet_hint)
        is_promedio = "promedio" in sheet_hint
        
        if not (is_altas or is_emision or is_promedio):
            low_cols = [str(c).lower() for c in df.columns]
            if ("montevideo" in low_cols) and ("interior" in low_cols):
                is_altas = True

        out = pd.DataFrame()
        
        # Detecta columnas de zona
        monte_col = next((cols_low[c] for c in cols_low if re.search(r"\bmontevideo\b", c)), None)
        inter_col = next((cols_low[c] for c in cols_low if re.search(r"\binterior\b", c)), None)
        has_zona = bool(monte_col and inter_col)

        if has_zona:
            out["altas_montevideo"] = _to_num(df[monte_col])
            out["altas_interior"]   = _to_num(df[inter_col])

        # Manejar duplicados de 'Fecha' → df[fecha_col] puede ser DataFrame
        _fecha_obj = df[fecha_col]
        if isinstance(_fecha_obj, pd.DataFrame):
            # Elige por POSICIÓN la subcol con menos NaN (evita etiquetas duplicadas)
            na_ratio = _fecha_obj.notna().mean()
            cand_pos = int(na_ratio.to_numpy().argmax())
            _fecha_obj = _fecha_obj.iloc[:, cand_pos]
        # Manejar duplicados de 'Fecha'
        out["fecha"] = _fix_excel_serial_dates(_pick_best_series(df[fecha_col]))

            
        # Lógica específica de 'total_col' para desempleo
        total_col = next((cols_low[c] for c in cols_low if c.strip().lower() == "total"), None)
        if total_col:
            if ("altas" not in out.columns) and (("altas" in sheet_hint) or has_zona):
                out["altas"] = _to_num(df[total_col])
            elif is_emision:
                out["beneficiarios"] = _to_num(df[total_col])
            elif is_promedio:
                out["importe_promedio_total"] = _to_num(df[total_col])

        cand_map: Dict[str, List[str]] = {}
        if is_altas:
            cand_map.update({
                "altas": [r"\baltas?\b"],
                "altas_montevideo": [r"\bmontevideo\b"], 
                "altas_interior": [r"\binterior\b"], 
                "altas_despido": [r"\bdespido\b"], 
                "altas_suspension": [r"\bsuspensi(o|ó)n\b"],
                "altas_fin_contrato": [r"fin.*contrato"],
            })
        elif is_emision:
            cand_map.update({
                "beneficiarios": [r"beneficiari"],
                "altas": [r"\baltas?\b"],
                "bajas": [r"\bbajas?\b"],
            })
        elif is_promedio:
            cand_map.update({
                "importe_promedio_montevideo": [r"\bmontevideo\b"],
                "importe_promedio_interior": [r"\binterior\b"],
                "importe_promedio_total": [r"\btotal\b"],
            })
        else:
            # Fallback genérico si el nombre de la hoja no da pistas
            cand_map.update({
                "beneficiarios": [r"beneficiari"],
                "altas": [r"\baltas?\b"],
                "bajas": [r"\bbajas?\b"],
                "monto_total": [r"\bmonto|\bimporte(?!.*promedio)|\btotal(?!.*promedio)"],
            })
        
        for newcol, pats in cand_map.items():
            if newcol in out.columns:  # No sobrescribir si 'total_col' ya lo pobló
                continue
            src = find_col(pats)
            if src is not None:
                out[newcol] = _to_num(_pick_best_series(df[src]))  
        if "altas" not in out.columns:
            if "altas_montevideo" in out.columns and "altas_interior" in out.columns:
                out["altas"] = out["altas_montevideo"].fillna(0) + out["altas_interior"].fillna(0)
        out = _norm_mes(out, "fecha")

        # --- Validación ---
        metric_cols = {
            "beneficiarios", "altas", "bajas", "monto_total",
            "importe_promedio_total", "altas_montevideo", "altas_interior", "altas_despido"
        }
        if metric_cols.isdisjoint(out.columns):
            logger.warning(f"Columnas detectadas: {list(out.columns)}")
            raise ValueError("No detecté NINGUNA métrica esperada en 'desempleo'")

        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv

def parse_recaudacion(
    xls_url: str,
    out_csv: Path = OUT_DIR / "series_recaudacion.csv",
    sheet: Union[str, int, None] = None,
    fecha_col_guess: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> Path:
    """
    Parsea el archivo de "II. Recaudación".

    Descarga, lee (con fallbacks), limpia, busca la columna de fecha,
    mapea las columnas de métricas (privados, publicos, total) y guarda en CSV.

    Args:
        xls_url (str): URL al archivo XLS/XLSX.
        out_csv (Path, optional): Ruta de salida para el CSV.
        sheet (Union[str, int, None], optional): Nombre/índice de la hoja a leer.
        fecha_col_guess (Optional[str], optional): Pista para la columna de fecha.
        logger (Optional[logging.Logger], optional): Logger existente.

    Returns:
        Path: La ruta al archivo CSV generado.
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(out_csv.parent)
    
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        
        # Pasamos la pista del header=6 (Fila 7) para recaudación
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet, header_hint=6)

        # --- Limpieza de columnas ---
        cols_originales = list(df.columns)
        cols_unnamed = df.columns.str.contains(r'^Unnamed: \d+$', na=True)
        cols_totalmente_vacias = df.isna().all()
        columnas_a_mantener = ~ (cols_unnamed | cols_totalmente_vacias)
        df = df.loc[:, columnas_a_mantener]
        logger.info(f"Columnas pre-limpieza: {cols_originales}")
        logger.info(f"Columnas post-limpieza: {list(df.columns)}")

        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        cols_low = {str(c).lower(): c for c in df.columns}

        # Promover cabecera si la mayoría son 'Unnamed:' (igual que en desempleo)
        if _looks_unnamed_columns(df):
            df2 = _promote_row_with_fecha_as_header(df)
            if df2 is not None:
                df = df2
                df = df.rename(columns={c: str(c).strip() for c in df.columns})
                cols_low = {str(c).lower(): c for c in df.columns}

        # --- Encontrar columna de fecha ---
        fecha_col = (
            fecha_col_guess
            or next((cols_low[c] for c in cols_low if "fecha" in c or "mes" in c), None)
        )
        if not fecha_col:
            c0 = list(df.columns)[0]
            if (
                df[c0].astype(str).str.contains(
                    r"\b(202\d|201\d)\b|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic",
                    case=False, regex=True,
                ).mean() > 0.3
            ):
                fecha_col = c0
        if not fecha_col:
            raise ValueError("No encuentro columna de fecha/mes en 'recaudación'")

        out = pd.DataFrame()
        _fecha_obj = _pick_best_series(df[fecha_col])
        out["fecha"] = _fix_excel_serial_dates(_fecha_obj)

        # --- Mapeo de columnas ---
        def find_col(patterns: List[str]) -> Optional[str]:
            for p in patterns:
                col_name = next((cols_low[c_low] for c_low in cols_low if re.search(p, c_low)), None)
                if col_name:
                    return col_name
            return None

        cand_map: Dict[str, List[str]] = {
            "recaudacion_privados": [r"\bprivados\b"],
            "recaudacion_publicos": [r"\bp(ú|u)blicos\b"],
            "recaudacion_total": [r"\btotal\b", r"\btotal\s+pa[ií]s\b"],  # Total País con/ sin acento
        }

        for newcol, pats in cand_map.items():
            src = find_col(pats)
            if src is not None:
                        out[newcol] = _to_num(_pick_best_series(df[src]))
            else:
                logger.warning(f"No se encontró la columna '{newcol}' (patrones: {pats})")

        out = _norm_mes(out, "fecha")
        
        # --- Validación ---
        required_cols: Set[str] = {"recaudacion_privados", "recaudacion_publicos", "recaudacion_total"}
        
        if not required_cols.issubset(out.columns):
            logger.warning(f"Columnas detectadas: {list(out.columns)}")
            logger.warning(f"Columnas faltantes: {required_cols - set(out.columns)}")
            raise ValueError("No detecté todas las métricas esperadas en 'recaudación' (Privados, Públicos, Total)")
            
        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv