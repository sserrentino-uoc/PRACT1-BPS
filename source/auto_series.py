# source/auto_series.py
import re
import pandas as pd
from .parse_series import parse_desempleo, parse_recaudacion

CSV_PATH = "dataset/indicadores_index.csv"

def run_auto():
    # Carga índice
    idx = pd.read_csv(CSV_PATH)

    # Normalizaciones
    idx["tipo_archivo"] = idx["tipo_archivo"].astype(str).str.lower()
    idx["capitulo"] = idx["capitulo"].astype(str).str.strip()
    idx["cap_low"] = idx["capitulo"].str.lower()
    if "filename_final" in idx.columns:
        idx["file_low"] = idx["filename_final"].astype(str).str.lower()
    else:
        idx["file_low"] = ""

    # Fechas
    idx["fecha_dt"] = pd.to_datetime(idx["fecha_publicacion"], dayfirst=True, errors="coerce")

    # Solo Excel (para III.3)
    excel = idx[idx["tipo_archivo"].isin(["xls", "xlsx"])].copy()

    # ----------------------------
    #   III.3 - Subsidio desempleo
    # ----------------------------
    mask_des = (
        excel["cap_low"].str.startswith("iii.3") |
        excel["file_low"].str.contains(r"\biii[_\.]3\b|desempleo", regex=True)
    )
    des_cand = excel[mask_des].copy().sort_values(["fecha_dt", "url_descarga"], ascending=[False, False])
    if not des_cand.empty:
        des_url = des_cand.iloc[0]["url_descarga"]
        # sheet=None: el lector elige Altas/Emisión/Promedio
        parse_desempleo(des_url, sheet=None)
    else:
        print("WARNING: No encontré XLS de 'III.3 Subsidio por desempleo' en el índice.")

    # ----------------------------
    #   II - Recaudación (robusto, sin exigir extensión)
    # ----------------------------
    df_all = idx.copy()

    # Asegura 'file_low' también aquí (por si no viene en el CSV)
    if "filename_final" in df_all.columns:
        df_all["file_low"] = df_all["filename_final"].astype(str).str.lower()
    else:
        df_all["file_low"] = ""

    def _norm(s):
        s = (str(s) if pd.notna(s) else "").strip().lower()
        return (s.replace("í", "i").replace("ó", "o")
                 .replace("ú", "u").replace("á", "a").replace("é", "e"))

    # Normaliza campos texto y crea un campo de búsqueda combinado
    df_all["cap_low"] = df_all["capitulo"].astype(str).map(_norm)
    df_all["file_low"] = df_all["file_low"].astype(str).map(_norm)
    df_all["url_low"]  = df_all["url_descarga"].astype(str).str.lower()
    df_all["search_text"] = (
        df_all["cap_low"] + " " + df_all["file_low"] + " " + df_all["url_low"]
    )

    # Evita el warning de grupos capturados: usa no-capturantes
    pat_cap_ii   = r"(?:^|\b)ii(?:\.|[\s\-:])"
    # Términos típicos que aparecen en título/archivo/URL
    pat_terms    = r"\brecaudacion\b|\bringresos?\b|\baportes?\b|\bcontribuciones?\b"

    # Filtro principal: “II …” + términos de recaudación
    rec_cand = df_all[
        df_all["search_text"].str.contains(pat_cap_ii, regex=True, na=False) &
        df_all["search_text"].str.contains(pat_terms,   regex=True, na=False)
    ].copy()

    # Fallback 1: términos sin exigir “II …” (evita III.*)
    if rec_cand.empty:
        rec_cand = df_all[
            df_all["search_text"].str.contains(pat_terms, regex=True, na=False) &
            (~df_all["cap_low"].str.startswith("iii", na=False))
        ].copy()

    # Fallback 2: lo último con “II …” aunque no aparezcan términos (lo validará el parser)
    if rec_cand.empty:
        rec_cand = df_all[
            df_all["search_text"].str.contains(pat_cap_ii, regex=True, na=False)
        ].copy()

    # Ordena por fecha (si existe) y URL
    if "fecha_dt" in rec_cand.columns:
        rec_cand = rec_cand.sort_values(["fecha_dt", "url_descarga"], ascending=[False, False])
    else:
        rec_cand = rec_cand.sort_values(["url_descarga"], ascending=False)

    if not rec_cand.empty:
        rec_url = rec_cand.iloc[0]["url_descarga"]
        print("Recaudación ->", rec_cand.iloc[0]["capitulo"], rec_url)
        parse_recaudacion(rec_url, sheet=None)
    else:
        print("WARNING: No encontré 'II Recaudación'. Muestras útiles:")
        m = df_all[df_all["search_text"].str.contains(r"recaud|ingres|aporte|contribu", regex=True, na=False)]
        print(m[["capitulo","url_descarga"]].head(10).to_string(index=False))
        n = df_all[df_all["search_text"].str.contains(pat_cap_ii, regex=True, na=False)]
        print("\nPrimeros con 'II':")
        print(n[["capitulo","url_descarga"]].head(10).to_string(index=False))
