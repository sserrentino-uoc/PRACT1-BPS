# source/auto_series.py
import csv
import datetime as dt
from .parse_series import parse_desempleo, parse_recaudacion

CSV_PATH = "dataset/indicadores_index.csv"

def _pick_latest(prefix: str, tipo: str = "xls"):
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    cand = [r for r in rows if r["capitulo"].startswith(prefix) and r["tipo_archivo"]==tipo]
    if not cand:
        return None
    cand.sort(key=lambda r: dt.datetime.strptime(r["fecha_publicacion"], "%d/%m/%Y"), reverse=True)
    return cand[0]["url_descarga"]

def run_auto():
    des_url = _pick_latest("III.3")
    rec_url = _pick_latest("II")
    if des_url:
        parse_desempleo(des_url, sheet=0)
    if rec_url:
        parse_recaudacion(rec_url, sheet=0)
