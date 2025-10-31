import io
import os
import re
import tempfile
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .settings import DEFAULT_UA, REQUEST_TIMEOUT, OUT_DIR
from .utils import make_logger, ensure_dirs

# ===================== Detectores de formato =====================

def _sniff(bytes_buf: bytes):
    """Detecta tipo de contenido por magic bytes / firma."""
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
    """Devuelve ('xlsx'|'xls'|'html'|'text', 'openpyxl'|'xlrd'|None)."""
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
    r = session.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    logger.info(
        f"Descargado {url} -> {len(r.content)} bytes | "
        f"Content-Type={r.headers.get('Content-Type','')}"
    )
    return r.content  # bytes

def _to_num(series):
    """
    Normaliza números con formato latino o mixto.
    Si ya es numérico, lo deja como está.
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

# ===================== Fallbacks (xlrd, win32) =====================
# (Estas funciones son helpers, no las anidamos)
def _try_xlrd_manual(bytes_buf: bytes, logger, sheet=None):
    try:
        import xlrd  # requiere xlrd==2.0.1
    except Exception as e:
        logger.warning(f"xlrd no disponible: {type(e).__name__}: {e}")
        return None
    # ... (resto de la función xlrd omitida por brevedad) ...
    # ... (si la tienes, déjala como está) ...
    return None # Asumimos que la tienes, si no, pega tu versión aquí

def _try_win32_excel_export(bytes_buf: bytes, logger):
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
    Devuelve un DataFrame 'df' leíble desde Excel, HTML o CSV.
    Acepta un 'header_hint' (int) para probar esa fila de header primero.
    """
    bio = io.BytesIO(bytes_buf)

    # --- INICIO DE FUNCIONES ANIDADAS ---
    # Estas funciones DEBEN estar DENTRO de _read_table_like
    # para acceder a 'bio', 'engine', 'logger', 'sheet', etc.

    def _try_read_excel(header_hint_internal=None):
        bio.seek(0)
        try:
            xls = pd.ExcelFile(bio, engine=engine)
        except Exception as e:
            logger.warning(f"ExcelFile falló: {type(e).__name__}: {e}")
            return None

        sheets = xls.sheet_names
        use_sheet = sheet if sheet is not None else sheets[0]
        
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
        
        for hdr in headers_a_probar_final:
            try:
                bio.seek(0)
                df = pd.read_excel(bio, sheet_name=use_sheet, engine=engine, header=hdr)
                
                # Comprobación de que el DataFrame es útil Y NO ES BASURA
                if (
                    df.shape[1] >= 2 
                    and df.dropna(how="all").shape[0] > 1
                    and not _looks_unnamed_columns(df)  # <-- La corrección clave
                ):
                    logger.info(f"Excel OK: hoja={use_sheet} header={hdr} cols={list(df.columns)[:6]}")
                    return df
            except Exception as e:
                last_err = e
        
        if last_err:
            logger.warning(f"Excel falló: {type(last_err).__name__ if hasattr(last_err,'__class__') else 'Error'}: {last_err}")
        
        return None
        
    def _try_read_html():
        # (Pega tu función _try_read_html aquí, indentada)
        pass

    def _try_bs4_table(bytes_buf_local, logger_local):
        # (Pega tu función _try_bs4_table aquí, indentada)
        pass

    def _try_read_csv():
        # (Pega tu función _try_read_csv aquí, indentada)
        pass
    
    # --- FIN DE FUNCIONES ANIDADAS ---


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

        raise RuntimeError("No pude leer el contenido ni como Excel ni como HTML/CSV")

    if kind == "html":
        # (Pega tu lógica para kind=="html" aquí)
        pass

    if kind == "text":
        # (Pega tu lógica para kind=="text" aquí)
        pass

    # (Pega tu lógica de fallback final aquí)
    # ...

    raise ValueError("Formato desconocido o no soportado")


# ===================== Parsers específicos =====================

def parse_desempleo(xls_url, out_csv=f"{OUT_DIR}/series_desempleo.csv",
                      sheet=None, fecha_col_guess=None, logger=None):
    """
    III.3 Subsidio por desempleo
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(OUT_DIR)
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        
        # Pasamos la pista del header=7 (Fila 8) para desempleo
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet, header_hint=7)

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

        fecha_col = (
            fecha_col_guess
            or next((cols_low[c] for c in cols_low if "fecha" in c or "mes" in c), None)
        )
        if not fecha_col:
            c0 = list(df.columns)[0]
            if (
                df[c0]
                .astype(str)
                .str.contains(
                    r"(?:\b(202\d|201\d)\b|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)",
                    case=False,
                    regex=True,
                )
                .mean()
                > 0.3
            ):
                fecha_col = c0
        if not fecha_col:
            raise ValueError("No encuentro columna de fecha/mes en 'desempleo'")

        def find_col(patterns):
            for p in patterns:
                col_name = next((cols_low[c_low] for c_low in cols_low if re.search(p, c_low)), None)
                if col_name:
                    return col_name
            return None

        sheet_hint = (str(sheet).lower() if isinstance(sheet, str) else "")
        is_altas     = "altas" in sheet_hint
        is_emision   = ("emisión" in sheet_hint) or ("emision" in sheet_hint)
        is_promedio  = "promedio" in sheet_hint
        
        out = pd.DataFrame()
        out["fecha"] = _fix_excel_serial_dates(df[fecha_col])
        
        total_col = next((cols_low[c] for c in cols_low if c.strip().lower() == "total"), None)
        if total_col:
            if is_altas:
                out["altas"] = _to_num(df[total_col])
            elif is_emision:
                out["beneficiarios"] = _to_num(df[total_col])
            elif is_promedio:
                out["importe_promedio_total"] = _to_num(df[total_col])
        
        cand_map = {}
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
            cand_map.update({
                "beneficiarios": [r"beneficiari"],
                "altas": [r"\baltas?\b"],
                "bajas": [r"\bbajas?\b"],
                "monto_total": [r"\bmonto|\bimporte(?!.*promedio)|\btotal(?!.*promedio)"],
            })
        
        for newcol, pats in cand_map.items():
            if newcol in out.columns:
                continue
            src = find_col(pats)
            if src is not None:
                out[newcol] = _to_num(df[src])
        
        out = _norm_mes(out, "fecha")

        metric_cols = {
            "beneficiarios", "altas", "bajas", "monto_total",
            "importe_promedio_total", "altas_montevideo", "altas_despido"
        }
        if metric_cols.isdisjoint(out.columns):
            logger.warning(f"Columnas detectadas: {list(out.columns)}")
            raise ValueError("No detecté métricas esperadas en 'desempleo'")

        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv

def parse_recaudacion(xls_url, out_csv=f"{OUT_DIR}/series_recaudacion.csv",
                        sheet=None, fecha_col_guess=None, logger=None):
    """
    II. Recaudación
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(OUT_DIR)
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        
        # Pasamos la pista del header=6 (Fila 7) para recaudación
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet, header_hint=6)

        cols_originales = list(df.columns)
        cols_unnamed = df.columns.str.contains(r'^Unnamed: \d+$', na=True)
        cols_totalmente_vacias = df.isna().all()
        columnas_a_mantener = ~ (cols_unnamed | cols_totalmente_vacias)
        df = df.loc[:, columnas_a_mantener]
        logger.info(f"Columnas pre-limpieza: {cols_originales}")
        logger.info(f"Columnas post-limpieza: {list(df.columns)}")

        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        cols_low = {str(c).lower(): c for c in df.columns}

        fecha_col = (
            fecha_col_guess
            or next((cols_low[c] for c in cols_low if "fecha" in c or "mes" in c), None)
        )
        if not fecha_col:
            c0 = list(df.columns)[0]
            if (
                df[c0]
                .astype(str)
                .str.contains(
                    r"\b(202\d|201\d)\b|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic",
                    case=False,
                    regex=True,
                )
                .mean()
                > 0.3
            ):
                fecha_col = c0
        if not fecha_col:
            raise ValueError("No encuentro columna de fecha/mes en 'recaudación'")

        out = pd.DataFrame()
        out["fecha"] = _fix_excel_serial_dates(df[fecha_col])

        def find_col(patterns):
            for p in patterns:
                col_name = next((cols_low[c_low] for c_low in cols_low if re.search(p, c_low)), None)
                if col_name:
                    return col_name
            return None

        cand_map = {
            "recaudacion_privados": [r"\bprivados\b"],
            "recaudacion_publicos": [r"\bp(ú|u)blicos\b"],
            "recaudacion_total": [r"\btotal\b"],
        }

        for newcol, pats in cand_map.items():
            src = find_col(pats)
            if src is not None:
                out[newcol] = _to_num(df[src])
            else:
                logger.warning(f"No se encontró la columna '{newcol}' (patrones: {pats})")

        out = _norm_mes(out, "fecha")
        
        required_cols = {"recaudacion_privados", "recaudacion_publicos", "recaudacion_total"}
        
        if not required_cols.issubset(out.columns):
            logger.warning(f"Columnas detectadas: {list(out.columns)}")
            logger.warning(f"Columnas faltantes: {required_cols - set(out.columns)}")
            raise ValueError("No detecté todas las métricas esperadas en 'recaudación' (Privados, Públicos, Total)")
            
        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv