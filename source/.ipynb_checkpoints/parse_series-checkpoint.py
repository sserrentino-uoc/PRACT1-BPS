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
    # XLSX (zip)
    if head[:2] == b"PK":
        return "xlsx"
    # XLS OLE2/BIFF (Compound File Binary Format)
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return "xls"
    # HTML (muy probable si comienza con '<')
    if head.lstrip().startswith(b"<"):
        return "html"
    # Texto (CSV/TSV) heurístico
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
    # si la extensión engaña, usamos sniff:
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
    
    # 1. Intentar convertir a numérico directamente
    s_num = pd.to_numeric(series, errors="coerce")

    # 2. Comprobar si la conversión directa tuvo éxito
    # Comparamos la proporción de NaNs (vacíos) antes y después.
    # Si la tasa de NaNs aumentó, es que eran strings que hay que limpiar.
    original_nan_rate = pd.Series(series).isna().mean()
    converted_nan_rate = s_num.isna().mean()

    # Si la conversión falló (más NaNs que antes), aplicamos la limpieza
    if converted_nan_rate > original_nan_rate:
        
        # Este es tu bloque de código original, que ahora SÓLO
        # se ejecutará para strings que lo necesiten.
        s = (
            pd.Series(series)
            .astype(str)
            .str.replace(r"\u2014|\u2212|–|-", "", regex=True)  # rayas
            .str.replace(r"\.", "", regex=True)                # miles
            .str.replace(",", ".", regex=False)                # decimal
        )
        return pd.to_numeric(s, errors="coerce")

    # Si la conversión directa funcionó, devolver ese resultado
    return s_num

def _norm_mes(df, col_fecha):
    """
    Convierte fechas a periodo mensual (1er día del mes) y elimina filas sin fecha.
    Soporta el caso col_fecha == 'fecha' sin tirar KeyError.
    """
    df = df.copy()
    s = pd.to_datetime(df[col_fecha], errors="coerce")
    df["fecha"] = s.dt.to_period("M").dt.to_timestamp()

    # Si la columna de origen NO es 'fecha', la puedo eliminar
    if col_fecha != "fecha":
        df = df.drop(columns=[col_fecha])

    # Quitar filas sin fecha válida
    df = df.dropna(subset=["fecha"])
    return df

def _looks_unnamed_columns(df: pd.DataFrame, threshold: float = 0.6) -> bool:
    cols = [str(c) for c in df.columns]
    cnt = sum(c.startswith("Unnamed:") or c.strip() == "" for c in cols)
    return (cnt / max(1, len(cols))) >= threshold

def _promote_row_with_fecha_as_header(df: pd.DataFrame, max_scan: int = 20) -> pd.DataFrame | None:
    """
    Busca dentro de las primeras filas una que contenga 'Fecha' (case-insensitive),
    y la usa como encabezado. Devuelve un nuevo DataFrame o None si no encontró.
    """
    # trabajamos sobre valores string para inspección
    vals = df.astype(object).where(pd.notna(df), "").astype(str)
    for i in range(min(max_scan, len(vals))):
        row = vals.iloc[i].str.strip().str.lower().tolist()
        if any(cell == "fecha" for cell in row):
            # nueva cabecera
            new_cols = [c.strip() if c.strip() else f"col_{j}" for j, c in enumerate(vals.iloc[i].tolist())]
            out = df.iloc[i+1:].copy()
            out.columns = new_cols
            out = out.reset_index(drop=True)
            # limpieza básica: quitar columnas totalmente vacías
            out = out.loc[:, out.notna().mean() > 0.0]
            return out
    return None


def _fix_excel_serial_dates(series: pd.Series) -> pd.Series:
    """
    Si la mayoría parecen seriales de Excel, convierte.
    Si no, limpia strings (ene, feb, ...) y convierte.
    """
    
    # 1. Intentar como serial de Excel (números como 45139.0)
    #    (Usamos una copia limpia con strip por si acaso)
    s_cleaned_for_num = series.astype(str).str.strip()
    s_num = pd.to_numeric(s_cleaned_for_num, errors="coerce")
    
    if s_num.notna().mean() > 0.7 and s_num.between(35000, 60000).mean() > 0.7:
        # CASO 1: Eran números seriales
        return pd.to_datetime(s_num, unit="D", origin="1899-12-30", errors="coerce")

    # 2. Son strings (ej. "ene-23", "ago-25 ")
    # Limpiar (strip), poner en minúsculas y REEMPLAZAR
    
    s_str = series.astype(str).str.strip().str.lower()

    # Diccionario de "traducción"
    replacements = {
        'ene': 'jan', 'feb': 'feb', 'mar': 'mar', 'abr': 'apr',
        'may': 'may', 'jun': 'jun', 'jul': 'jul', 'ago': 'aug',
        'sep': 'sep', 'oct': 'oct', 'nov': 'nov', 'dic': 'dec'
    }

    # Aplicar todos los reemplazos
    for esp, eng in replacements.items():
        s_str = s_str.str.replace(esp, eng, regex=False)

    return pd.to_datetime(s_str, errors="coerce")
    

# ===================== Fallback XLS binario manual (xlrd) =====================

def _try_xlrd_manual(bytes_buf: bytes, logger, sheet=None):
    """
    Fallback para XLS binarios 'raros': usa xlrd directamente y arma un DataFrame.
    Heurística de encabezado: fila con más strings y >=2 columnas no vacías.
    """
    try:
        import xlrd  # requiere xlrd==2.0.1
    except Exception as e:
        logger.warning(f"xlrd no disponible: {type(e).__name__}: {e}")
        return None

    book = xlrd.open_workbook(file_contents=bytes_buf, on_demand=True)
    sheet_names = book.sheet_names()
    if not sheet_names:
        return None
    use_sheet = sheet if (sheet is not None and sheet in sheet_names) else sheet_names[0]
    sh = book.sheet_by_name(use_sheet)

    rows = []
    for r in range(sh.nrows):
        row_vals = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                try:
                    import datetime
                    dt_tuple = xlrd.xldate_as_tuple(cell.value, book.datemode)
                    row_vals.append(datetime.datetime(*dt_tuple))
                except Exception:
                    row_vals.append(cell.value)
            else:
                row_vals.append(cell.value)
        rows.append(row_vals)

    if not rows:
        return None

    # Heurística de encabezado
    best_header_idx = 0
    best_score = -1
    for i, row in enumerate(rows[:30]):  # inspeccionamos primeras 30 filas
        non_empty = sum(1 for x in row if (str(x).strip() != "" and x is not None))
        str_count = sum(1 for x in row if isinstance(x, str) and x.strip() != "")
        score = str_count + non_empty
        if non_empty >= 2 and score > best_score:
            best_score = score
            best_header_idx = i

    header = [str(x).strip() if str(x).strip() else f"col_{j}" for j, x in enumerate(rows[best_header_idx])]
    data_rows = rows[best_header_idx + 1 :]
    df = pd.DataFrame(data_rows, columns=header)
    df = df.dropna(how="all")
    df = df.loc[:, df.notna().mean() > 0.0]  # quita columnas totalmente vacías
    if df.shape[1] < 2 or df.dropna(how="all").shape[0] < 1:
        return None
    logger.info(f"xlrd-manual OK: hoja={use_sheet} header_row={best_header_idx} cols={list(df.columns)[:6]}")
    return df

# ===================== Fallback Excel vía COM (Windows + Excel) =====================

def _try_win32_excel_export(bytes_buf: bytes, logger):
    """
    Fallback usando Microsoft Excel vía COM (pywin32) para abrir el binario y exportar a CSV.
    Intenta reparar archivos dañados (CorruptLoad=1). Devuelve un DataFrame o None.
    """
    try:
        import win32com.client  # pip install pywin32
        from win32com.client import constants  # noqa: F401
    except Exception as e:
        logger.info(f"win32com no disponible: {type(e).__name__}: {e}")
        return None

    tmpdir = tempfile.mkdtemp(prefix="bps_xls_")
    xls_path = os.path.join(tmpdir, "input.xls")
    csv_path = os.path.join(tmpdir, "output.csv")
    try:
        with open(xls_path, "wb") as f:
            f.write(bytes_buf)

        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        # CorruptLoad=1 -> xlRepairFile
        wb = excel.Workbooks.Open(xls_path, UpdateLinks=0, ReadOnly=True, CorruptLoad=1)
        # 6 = xlCSV (ANSI). Si tu Excel soporta UTF-8, podés usar 62 (xlCSVUTF8).
        wb.SaveAs(csv_path, FileFormat=6)
        wb.Close(SaveChanges=False)
        excel.Quit()

        df = pd.read_csv(csv_path, engine="python")
        if df.shape[0] >= 1 and df.shape[1] >= 1:
            logger.info(f"win32com Excel export OK: shape={df.shape} cols={list(df.columns)[:6]}")
            return df
    except Exception as e:
        logger.warning(f"win32com export falló: {type(e).__name__}: {e}")
        return None
    finally:
        try:
            if os.path.exists(csv_path): os.remove(csv_path)
            if os.path.exists(xls_path): os.remove(xls_path)
            os.rmdir(tmpdir)
        except Exception:
            pass

    return None

# ===================== Lectores genéricos =====================

def _read_table_like(bytes_buf, kind, engine, logger, sheet=None):
    """
    Devuelve un DataFrame 'df' leíble desde:
    - Excel real (xlsx/xls)
    - HTML con tablas
    - Texto (CSV/TSV)

    Estrategia:
      * Si parece Excel: intento Excel (varios headers). Si falla, xlrd-manual, luego Excel-COM, HTML, BS4 y CSV.
      * Si parece HTML: read_html (lxml) y si falla, BS4-table.
      * Si parece texto: CSV con autodetección y separadores comunes.
    """
    bio = io.BytesIO(bytes_buf)

    def _try_read_excel():
        bio.seek(0)
        try:
            xls = pd.ExcelFile(bio, engine=engine)
        except Exception as e:
            logger.warning(f"ExcelFile falló: {type(e).__name__}: {e}")
            return None

        sheets = xls.sheet_names
        use_sheet = sheet if sheet is not None else sheets[0]
        last_err = None
        headers_a_probar = (7, 6, 5, 4, 0, 1, 2, 3) 

        last_err = None
        for hdr in headers_a_probar:  # <--- ¡LÍNEA MODIFICADA!
            try:
                bio.seek(0)
                df = pd.read_excel(bio, sheet_name=use_sheet, engine=engine, header=hdr)
                if df.shape[1] >= 2 and df.dropna(how="all").shape[0] > 1:
                    logger.info(f"Excel OK: hoja={use_sheet} header={hdr} cols={list(df.columns)[:6]}")
                    return df
            except Exception as e:
                last_err = e
        if last_err:
            logger.warning(f"Excel falló: {type[last_err].__name__ if hasattr(last_err,'__class__') else 'Error'}: {last_err}")
        return None

    def _try_read_html():
        # 1) intentar con lxml directo desde bytes
        try:
            bio.seek(0)
            tables = pd.read_html(bio)  # usa lxml si está instalado
        except Exception:
            tables = None

        # 2) si falla, intentar decodificando a texto con utf-8 y latin1
        if tables is None:
            for enc in ("utf-8", "latin1"):
                try:
                    bio.seek(0)
                    html_txt = bio.read().decode(enc, errors="replace")
                    tables = pd.read_html(io.StringIO(html_txt))
                    break
                except Exception:
                    continue

        if tables is None:
            logger.warning("HTML falló: no pude parsear tablas con lxml/html5lib")
            return None

        logger.info(f"HTML: {len(tables)} tablas detectadas")
        # Heurística: preferimos tabla con 'mes'/'fecha'; si no, la 1ª con >=2 columnas
        best = None
        for t in tables:
            if t.shape[1] >= 2:
                low = [str(c).lower() for c in t.columns]
                if any(("mes" in c or "fecha" in c) for c in low):
                    return t
                best = best or t
        return best

    def _try_bs4_table(bytes_buf_local, logger_local):
        """
        Fallback extra: parsear HTML 'irregular' con BeautifulSoup + lxml y
        reconstruir DataFrame de la primera <table> con al menos 2 columnas.
        """
        try:
            html = bytes_buf_local.decode("utf-8", errors="replace")
        except Exception:
            try:
                html = bytes_buf_local.decode("latin1", errors="replace")
            except Exception as e:
                logger_local.warning(f"BS4 decode falló: {type(e).__name__}: {e}")
                return None

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        if not table:
            logger_local.warning("BS4: no encontré <table> en el contenido")
            return None

        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            rows.append([c.get_text(strip=True) for c in cells])

        # limpiar filas vacías
        rows = [r for r in rows if any(val.strip() for val in r)]
        if not rows or len(rows[0]) < 2:
            logger_local.warning("BS4: tabla encontrada pero no tiene >=2 columnas utilizables")
            return None

        # Heurística de encabezado: si la primera fila parece header (th) o si la segunda es más 'numérica'
        trs = table.find_all("tr")
        use_header = 0
        if trs and trs[0].find("th"):
            use_header = 0
        elif len(rows) >= 2:
            nums_row1 = sum(bool(re.search(r"\d", x)) for x in rows[0])
            nums_row2 = sum(bool(re.search(r"\d", x)) for x in rows[1])
            use_header = 0 if nums_row1 < nums_row2 else 1

        header = rows[use_header]
        data = rows[use_header + 1 :]
        df_local = pd.DataFrame(data, columns=[h if h else f"col_{i}" for i, h in enumerate(header)])
        logger_local.info(f"BS4: tabla reconstruida shape={df_local.shape} cols={list(df_local.columns)[:6]}")
        return df_local

    def _try_read_csv():
        # 0) autodetección de separador
        try:
            bio.seek(0)
            df = pd.read_csv(bio, sep=None, engine="python")
            if df.shape[1] >= 2:
                logger.info(f"Texto: autodetect sep cols={list(df.columns)[:6]}")
                return df
        except Exception:
            pass
        # 1) separadores comunes
        for sep in (";", ",", "\t", "|"):
            try:
                bio.seek(0)
                df = pd.read_csv(bio, sep=sep, engine="python")
                if df.shape[1] >= 2:
                    logger.info(f"Texto: sep='{sep}' cols={list(df.columns)[:6]}")
                    return df
            except Exception:
                continue
        return None

    # Ruta principal según “kind”
    if kind in ("xlsx", "xls"):
        df = _try_read_excel()
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
        df = _try_read_html()
        if df is None:
            logger.info("HTML falló, pruebo BS4-table…")
            df = _try_bs4_table(bytes_buf, logger)
        if df is not None:
            return df
        logger.info("HTML/BS4 falló, pruebo CSV/TSV…")
        df = _try_read_csv()
        if df is not None:
            return df
        raise RuntimeError("No pude parsear las tablas HTML")

    if kind == "text":
        df = _try_read_csv()
        if df is not None:
            return df
        logger.warning("Texto: intenté ; , \\t | y falló")
        raise ValueError("No pude parsear el texto como CSV/TSV")

    # Último recurso: intenta HTML, BS4 y CSV sin mirar 'kind'
    logger.info("Kind desconocido, pruebo HTML y CSV…")
    df = _try_read_html()
    if df is None:
        logger.info("HTML falló, pruebo BS4-table…")
        df = _try_bs4_table(bytes_buf, logger)
    if df is not None:
        return df
    df = _try_read_csv()
    if df is not None:
        return df

    raise ValueError("Formato desconocido o no soportado")

# ===================== Parsers específicos =====================
def parse_desempleo(xls_url, out_csv=f"{OUT_DIR}/series_desempleo.csv",
                     sheet=None, fecha_col_guess=None, logger=None):
    """
    III.3 Subsidio por desempleo:
    Detecta columnas por patrones: fecha/mes, beneficiarios, altas, bajas, (monto_total).
    Soporta xlsx/xls reales, HTML-tabla y CSV disfrazado.
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(OUT_DIR)
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet)

        # --- INICIO DE NUEVA LIMPIEZA ---
        # 1. Guardamos los nombres originales para el log
        cols_originales = list(df.columns)
        
        # 2. Eliminamos columnas que se llamen 'Unnamed: ...' Y estén vacías
        #    (usamos 'na=True' para que 'str.contains' funcione aunque haya NaNs)
        cols_unnamed = df.columns.str.contains(r'^Unnamed: \d+$', na=True)
        
        # 3. También eliminamos columnas que no sean 'Unnamed' pero estén 100% vacías
        cols_totalmente_vacias = df.isna().all()
        
        # 4. Seleccionamos las columnas que NO queremos eliminar
        columnas_a_mantener = ~ (cols_unnamed | cols_totalmente_vacias)
        df = df.loc[:, columnas_a_mantener]
        
        logger.info(f"Columnas pre-limpieza: {cols_originales}")
        logger.info(f"Columnas post-limpieza: {list(df.columns)}")
        # --- FIN DE NUEVA LIMPIEZA ---

        # normalización de encabezados
        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        cols_low = {str(c).lower(): c for c in df.columns}

        # Si el header es pobre (muchos Unnamed), intentamos promover la fila con 'Fecha'
        if _looks_unnamed_columns(df):
            df2 = _promote_row_with_fecha_as_header(df)
            if df2 is not None:
                df = df2
                df = df.rename(columns={c: str(c).strip() for c in df.columns})
                cols_low = {str(c).lower(): c for c in df.columns}

        # fecha/mes
        fecha_col = (
            fecha_col_guess
            or next((cols_low[c] for c in cols_low if "fecha" in c or "mes" in c), None)
        )
        if not fecha_col:
            # intento adicional: si la primera columna parece fecha/mes
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

        # --- 4. Helper 'find_col' definido una sola vez ---
        def find_col(patterns):
            """Busca en cols_low la primera columna que coincida con una lista de patrones regex."""
            for p in patterns:
                # c_low es la clave (ej. "total")
                # cols_low[c_low] es el valor (ej. "Total ")
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
        
        # Mapear la columna "Total" primero, ya que es la más fiable según el contexto
        # Usamos .lower() para ser robustos
        total_col = next((cols_low[c] for c in cols_low if c.strip().lower() == "total"), None)
        if total_col:
            if is_altas:
                out["altas"] = _to_num(df[total_col])
            elif is_emision:
                out["beneficiarios"] = _to_num(df[total_col])
            elif is_promedio:
                # en hojas de promedio, 'Total' es un importe promedio
                out["importe_promedio_total"] = _to_num(df[total_col])
            # else: si no hay hint, 'Total' se buscará después con el cand_map genérico
        
        # Construir cand_map (mapa de candidatos) según el tipo de hoja
        cand_map = {}
        if is_altas:
            # --- 3. Lógica refinada para 'is_altas' ---
            cand_map.update({
                "altas": [r"\baltas?\b"], # Si no se encontró como "Total"
                # Para 'Altas Zona'
                "altas_montevideo": [r"\bmontevideo\b"], 
                "altas_interior": [r"\binterior\b"], 
                # Para 'Altas Causal'
                "altas_despido": [r"\bdespido\b"], 
                "altas_suspension": [r"\bsuspensi(o|ó)n\b"],
                "altas_fin_contrato": [r"fin.*contrato"],
                # (agregar más causales si se desea)
            })
        elif is_emision:
            cand_map.update({
                "beneficiarios": [r"beneficiari"],
                "altas": [r"\baltas?\b"], # si existiera otra columna de altas
                "bajas": [r"\bbajas?\b"],
            })
        elif is_promedio:
            # en “Promedio…” sólo buscamos importes
            cand_map.update({
                "importe_promedio_montevideo": [r"\bmontevideo\b"],
                "importe_promedio_interior": [r"\binterior\b"],
                "importe_promedio_total": [r"\btotal\b"], # Si no se encontró antes
            })
        else:
            # fallback genérico si no hay hint en el nombre de la hoja
            cand_map.update({
                "beneficiarios": [r"beneficiari"],
                "altas": [r"\baltas?\b"],
                "bajas": [r"\bbajas?\b"],
                # Este regex es clave: busca monto/importe/total pero NO si dice "promedio"
                "monto_total": [r"\bmonto|\bimporte(?!.*promedio)|\btotal(?!.*promedio)"],
            })
        
        # Aplicar cand_map sin pisar lo ya seteado desde 'total_col'
        for newcol, pats in cand_map.items():
            if newcol in out.columns:
                continue  # Ya fue asignada (ej. 'altas' desde 'total_col')
            
            src = find_col(pats) # Usamos el helper
            if src is not None:
                out[newcol] = _to_num(df[src])
        
        out = _norm_mes(out, "fecha")

        # --- 2. ELIMINADO todo el bloque duplicado que estaba aquí ---
        # (El bloque desde el segundo `cand_map = { ... }` 
        #  hasta el segundo `out = _norm_mes(out, "fecha")` fue removido)

        # --- 5. Validación final actualizada ---
        # requisito mínimo: al menos una métrica de interés
        metric_cols = {
            "beneficiarios", "altas", "bajas", "monto_total",
            "importe_promedio_total", "altas_montevideo", "altas_despido"
        }
        # .isdisjoint() devuelve True si NO hay elementos en común
        if metric_cols.isdisjoint(out.columns):
            logger.warning(f"Columnas detectadas: {list(out.columns)}")
            raise ValueError("No detecté métricas esperadas en 'desempleo'")

        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv

def parse_recaudacion(xls_url, out_csv=f"{OUT_DIR}/series_recaudacion.csv",
                      sheet=None, fecha_col_guess=None, logger=None):
    """
    II. Recaudación:
    Detecta fecha y recaudación total (+ posibles subcomponentes).
    Soporta xlsx/xls reales, HTML-tabla y CSV disfrazado.
    """
    logger = logger or make_logger("logs", "parse_series")
    ensure_dirs(OUT_DIR)
    with requests.Session() as s:
        s.headers.update({"User-Agent": DEFAULT_UA})
        bytes_buf = _download(xls_url, s, logger)
        kind, engine = _engine_from_ext_or_sniff(xls_url, bytes_buf)
        logger.info(f"Detección de formato: kind={kind} engine={engine}")
        df = _read_table_like(bytes_buf, kind, engine, logger, sheet=sheet)

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

        # recaudación total (varias denominaciones)
        total = next(
            (
                cols_low[c]
                for c in cols_low
                if ("recaud" in c and "total" in c)
                or re.search(r"\brecaud(aci[oó]n)?\b", c)
            ),
            None,
        )
        if total:
            out["recaudacion_total"] = _to_num(df[total])

        # subcomponentes (si existieran)
        def maybe_add(key, pat):
            col = next((cols_low[c] for c in cols_low if re.search(pat, c)), None)
            if col:
                out[key] = _to_num(df[col])

        maybe_add("aportes_reparto", r"(reparto|aporte).*recaud")
        maybe_add("otros", r"(otros|varios|divers).*recaud")

        out = _norm_mes(out, "fecha")
        if "recaudacion_total" not in out.columns:
            logger.info(f"Columnas detectadas: {list(out.columns)}")
            raise ValueError("No detecté columna de recaudación total")
        out.to_csv(out_csv, index=False)
        logger.info(f"Escribí {len(out)} filas en {out_csv}")
        return out_csv
