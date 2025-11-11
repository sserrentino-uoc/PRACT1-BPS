import os
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATA = Path("dataset")
OUTF = Path("results")
FIGS = OUTF / "figs"
TBLS = OUTF / "tables"
OUTF.mkdir(exist_ok=True)
FIGS.mkdir(parents=True, exist_ok=True)
TBLS.mkdir(parents=True, exist_ok=True)

def fmt_int_es(x):
    try:
        return f"{int(round(float(x))):,}".replace(",", ".")
    except Exception:
        return "-"

def fmt_float_es(x, nd=1):
    try:
        s = f"{float(x):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    except Exception:
        return "-"

# --- Carga datos ---
d = pd.read_csv(DATA/"series_desempleo.csv", parse_dates=["fecha"])
r = pd.read_csv(DATA/"series_recaudacion.csv", parse_dates=["fecha"])

# Asegura orden temporal
d = d.sort_values("fecha")
r = r.sort_values("fecha")

# Altas total (por si falta, suma MV+Interior)
if "altas" not in d.columns and {"altas_montevideo","altas_interior"}.issubset(d.columns):
    d["altas"] = d["altas_montevideo"].fillna(0) + d["altas_interior"].fillna(0)

# --- Fig 1: Desempleo - Altas totales ---
plt.figure(figsize=(9,4.5))
plt.plot(d["fecha"], d["altas"], linewidth=2)
plt.title("Subsidio por desempleo – Altas (total)")
plt.xlabel("Fecha")
plt.ylabel("Altas")
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(FIGS/"fig_desempleo_altas.png", dpi=200)
plt.close()

# --- Fig 2: Desempleo - Altas por zona ---
if {"altas_montevideo","altas_interior"}.issubset(d.columns):
    plt.figure(figsize=(9,4.5))
    plt.plot(d["fecha"], d["altas_montevideo"], label="Montevideo", linewidth=1.8)
    plt.plot(d["fecha"], d["altas_interior"], label="Interior", linewidth=1.8)
    plt.legend()
    plt.title("Subsidio por desempleo – Altas por zona")
    plt.xlabel("Fecha")
    plt.ylabel("Altas")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIGS/"fig_desempleo_zonas.png", dpi=200)
    plt.close()

# --- Fig 3: Recaudación (Privados, Públicos, Total) ---
plt.figure(figsize=(9,4.5))
for col in ["recaudacion_privados","recaudacion_publicos","recaudacion_total"]:
    if col in r.columns:
        plt.plot(r["fecha"], r[col], label=col.replace("recaudacion_", "").capitalize(), linewidth=1.8)
plt.legend()
plt.title("Recaudación BPS – Privados / Públicos / Total (mensual)")
plt.xlabel("Fecha")
plt.ylabel("Monto (unidad publicada por BPS)")
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(FIGS/"fig_recaudacion.png", dpi=200)
plt.close()

# --- Resumen último mes + variaciones MoM/YoY ---
def last_variations(df, date_col, val_col):
    df = df[[date_col, val_col]].dropna().sort_values(date_col).copy()
    if df.empty:
        return None
    last = df.iloc[-1]
    dt_last = last[date_col]
    val_last = last[val_col]
    mom = None
    if len(df) >= 2:
        prev = df.iloc[-2][val_col]
        mom = (val_last/prev - 1.0) * 100.0 if prev and pd.notna(prev) else None
    yoy = None
    if len(df) >= 13:
        yoy_prev = df.iloc[-13][val_col]
        yoy = (val_last/yoy_prev - 1.0) * 100.0 if yoy_prev and pd.notna(yoy_prev) else None
    return dt_last, val_last, mom, yoy

rows = []

lv = last_variations(d, "fecha", "altas")
if lv:
    rows.append({
        "serie": "Altas desempleo (total)",
        "fecha": lv[0].date(),
        "valor": fmt_int_es(lv[1]),
        "MoM_%": fmt_float_es(lv[2]) if lv[2] is not None else "-",
        "YoY_%": fmt_float_es(lv[3]) if lv[3] is not None else "-",
    })

for col, label in [("recaudacion_total","Recaudación total"),
                   ("recaudacion_privados","Recaudación privados"),
                   ("recaudacion_publicos","Recaudación públicos")]:
    if col in r.columns:
        lv = last_variations(r, "fecha", col)
        if lv:
            rows.append({
                "serie": label,
                "fecha": lv[0].date(),
                "valor": fmt_int_es(lv[1]),
                "MoM_%": fmt_float_es(lv[2]) if lv[2] is not None else "-",
                "YoY_%": fmt_float_es(lv[3]) if lv[3] is not None else "-",
            })

df_sum = pd.DataFrame(rows)
df_sum.to_csv(TBLS/"summary_latest.csv", index=False)

# -------------------------
#       INDICADORES
# -------------------------
idx_path = DATA / "indicadores_index.csv"
if idx_path.exists():
    idx = pd.read_csv(idx_path)
    # limpieza mínima
    idx["capitulo"] = idx["capitulo"].astype(str).str.strip()
    idx["tipo_archivo"] = idx["tipo_archivo"].astype(str).str.lower().str.strip()
    if "fecha_publicacion" in idx.columns:
        idx["fecha_dt"] = pd.to_datetime(idx["fecha_publicacion"], dayfirst=True, errors="coerce")
    else:
        idx["fecha_dt"] = pd.NaT

    # 1) recursos por capítulo
    cap_counts = (idx.groupby("capitulo")["url_descarga"]
                    .count()
                    .sort_values(ascending=False))
    if not cap_counts.empty:
        plt.figure(figsize=(10,5))
        cap_counts.plot(kind="bar")
        plt.title("Indicadores: recursos por capítulo")
        plt.xlabel("Capítulo")
        plt.ylabel("Nº de recursos")
        plt.tight_layout()
        plt.savefig(FIGS/"fig_indicadores_por_capitulo.png", dpi=200)
        plt.close()

    # 2) distribución por tipo
    type_counts = idx["tipo_archivo"].value_counts()
    if not type_counts.empty:
        plt.figure(figsize=(7,4))
        type_counts.plot(kind="bar")
        plt.title("Indicadores: distribución por tipo de archivo")
        plt.xlabel("Tipo")
        plt.ylabel("Nº de recursos")
        plt.tight_layout()
        plt.savefig(FIGS/"fig_indicadores_tipo.png", dpi=200)
        plt.close()

    # 3) timeline publicaciones por mes
    df_month = idx.dropna(subset=["fecha_dt"]).copy()
    if not df_month.empty:
        df_month["ym"] = df_month["fecha_dt"].dt.to_period("M").dt.to_timestamp()
        timeline = df_month.groupby("ym")["url_descarga"].count()
        if not timeline.empty:
            plt.figure(figsize=(10,4))
            plt.plot(timeline.index, timeline.values, linewidth=2)
            plt.title("Indicadores: publicaciones por mes")
            plt.xlabel("Fecha")
            plt.ylabel("Nº publicaciones")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(FIGS/"fig_publicaciones_tiempo.png", dpi=200)
            plt.close()

    # Top 10 más recientes (para pegar en el snippet)
    top10 = df_month.sort_values("fecha_dt", ascending=False).head(10)[
        ["capitulo","titulo_corto","tipo_archivo","fecha_publicacion","url_descarga"]
    ] if not df_month.empty else pd.DataFrame()

else:
    idx = None
    top10 = pd.DataFrame()

# --- Markdown snippet listo para pegar ---
lines = []
lines.append("## Resultados principales\n")
if not df_sum.empty:
    lines.append("")
    lines.append("| Serie | Fecha | Valor | MoM % | YoY % |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, rrow in df_sum.iterrows():
        lines.append(f"| {rrow['serie']} | {rrow['fecha']} | {rrow['valor']} | {rrow['MoM_%']} | {rrow['YoY_%']} |")
    lines.append("")

lines.append("**Figuras**")
lines.append("")
lines.append("1. Subsidio por desempleo – Altas (total)  \n   ![Altas desempleo](results/figs/fig_desempleo_altas.png)")
if (FIGS/"fig_desempleo_zonas.png").exists():
    lines.append("2. Subsidio por desempleo – Altas por zona  \n   ![Altas por zona](results/figs/fig_desempleo_zonas.png)")
lines.append("3. Recaudación BPS – Privados/Públicos/Total  \n   ![Recaudación](results/figs/fig_recaudacion.png)")

# Añade bloque de Indicadores
if idx_path.exists():
    lines.append("\n## Indicadores (visión general)\n")
    if (FIGS/"fig_indicadores_por_capitulo.png").exists():
        lines.append("1. Recursos por capítulo  \n   ![Por capítulo](results/figs/fig_indicadores_por_capitulo.png)")
    if (FIGS/"fig_indicadores_tipo.png").exists():
        lines.append("2. Distribución por tipo de archivo  \n   ![Por tipo](results/figs/fig_indicadores_tipo.png)")
    if (FIGS/"fig_publicaciones_tiempo.png").exists():
        lines.append("3. Publicaciones por mes  \n   ![Timeline](results/figs/fig_publicaciones_tiempo.png)")
    if not top10.empty:
        lines.append("\n**Top 10 indicadores más recientes**\n")
        lines.append("| Capítulo | Título | Tipo | Fecha | URL |")
        lines.append("|---|---|---|---:|---|")
        for _, row in top10.iterrows():
            cap = str(row["capitulo"])
            tit = str(row["titulo_corto"]) if pd.notna(row["titulo_corto"]) else ""
            typ = str(row["tipo_archivo"])
            fch = str(row["fecha_publicacion"])
            url = str(row["url_descarga"])
            lines.append(f"| {cap} | {tit} | {typ} | {fch} | {url} |")

(Path("results")/"results_snippet.md").write_text("\n".join(lines), encoding="utf-8")

print("OK -> figuras en results/figs/, tablas en results/tables/, snippet en results/results_snippet.md")
