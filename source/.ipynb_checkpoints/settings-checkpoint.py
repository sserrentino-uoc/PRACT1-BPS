# Copyright (c) 2025 Serrentino Mangino, S., & Mochon Paredes, A.
# Licensed under the MIT License. See LICENSE for details.

from pathlib import Path  # <-- 1. Importar

# (Necesitarías importar 'list' de 'typing' solo si usas Python < 3.9)
# from typing import List 

DEFAULT_UA: str = "UOC-PRACT1/1.0 (sserrentino@uoc.edu)"
REQUEST_TIMEOUT: int = 20
DEFAULT_DELAY_SEC: float = 2.0
MAX_RETRIES: int = 3
BASE_SEED_SPA: str = "https://observatorio.bps.gub.uy/#/"

# Página institucional (índice y cuadro) — se completa al ejecutar:
# En Python 3.9+ puedes usar list[str]. 
# En Python < 3.9, usa List[str] (importado de typing)
BASE_INDEX_PAGES: list[str] = [
    "https://www.bps.gub.uy/1944/indicadores-de-la-seguridad-social.html",
    "https://www.bps.gub.uy/bps/estadisticas/cuadro.jsp?cuadro=2",
    "https://www.bps.gub.uy/bps/observatorio/cuadro.jsp?contentid=12780",
]

OUT_DIR: Path = Path("dataset") 
LOG_DIR: Path = Path("logs") 