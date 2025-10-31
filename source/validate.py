import pandas as pd, sys, re

def val_index(path):
    df = pd.read_csv(path)
    req = {"capitulo","titulo_corto","tipo_archivo","tamano","fecha_publicacion","url_descarga","url_pagina"}
    missing = req - set(df.columns)
    assert not missing, f"Faltan columnas: {missing}"
    assert df["tipo_archivo"].isin(["pdf","xls"]).all()
    assert df["url_descarga"].str.startswith("http").all()

def val_series(path, req_cols):
    df = pd.read_csv(path)
    assert "fecha" in df.columns
    assert pd.to_datetime(df["fecha"], errors="coerce").notna().all()
    assert set(req_cols) & set(df.columns), "Faltan métricas esperadas"

if __name__ == "__main__":
    val_index("dataset/indicadores_index.csv")
    val_series("dataset/series_desempleo.csv", {"beneficiarios","altas","bajas"})
    val_series("dataset/series_recaudacion.csv", {"recaudacion_total"})
    print("VALIDACIONES OK")
