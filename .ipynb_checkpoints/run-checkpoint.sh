# Para correr:
# chmod +x run.sh
# ./run.sh

# 1) Ruta del proyecto 
PROJ="$HOME/Tipologia/PRACT1-BPS"
cd "$PROJ"

# 2) Entorno limpio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel

# 3) Dependencias 
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
else
  # mínimo necesario por si no hay requirements.txt
  pip install pandas requests beautifulsoup4 lxml xlrd openpyxl
fi

# 4) Limpieza de salidas anteriores
rm -f dataset/indicadores_index.csv \
      dataset/series_desempleo.csv \
      dataset/series_recaudacion.csv
mkdir -p logs dataset

# 5) Construir índice (descubre y lista todas las fuentes)
python -m source.main index

# 6) Auto (elige los últimos XLS correctos y parsea)
python -m source.main auto

# 7) Validaciones
python -m source.main validate

# 8) Comprobaciones rápidas
echo "---- HEAD dataset/indicadores_index.csv"
head -n 5 dataset/indicadores_index.csv || true
echo "---- HEAD dataset/series_desempleo.csv"
head -n 5 dataset/series_desempleo.csv || true
echo "---- HEAD dataset/series_recaudacion.csv"
head -n 5 dataset/series_recaudacion.csv || true

# 9) Esquema mínimo esperado (nombres pueden variar, pero debe haber 'fecha' en ambos)
python - <<'PY'
import pandas as pd, sys
ok = True
try:
    d = pd.read_csv("dataset/series_desempleo.csv")
    assert "fecha" in d.columns and len(d) > 0
except Exception as e:
    ok = False; print("Desempleo KO:", e, file=sys.stderr)

try:
    r = pd.read_csv("dataset/series_recaudacion.csv")
    assert "fecha" in r.columns and len(r) > 0
except Exception as e:
    ok = False; print("Recaudación KO:", e, file=sys.stderr)

sys.exit(0 if ok else 1)
PY

echo "Repro completa OK"
