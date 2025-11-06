# Copyright (c) 2025 Serrentino Mangino, S., & Mochon Paredes, A.
# Licensed under the MIT License. See LICENSE for details.

"""
Punto de entrada principal para el proyecto de scraping del BPS.
... (resto de tu docstring de módulo) ...
"""

# 1. Importaciones de la biblioteca estándar
import argparse
import sys

# 3. Importaciones locales (de tu proyecto)
from .settings import BASE_INDEX_PAGES, DEFAULT_DELAY_SEC
from .robots_check import check_all
from .crawl_index import crawl_index
from .parse_series import parse_desempleo, parse_recaudacion
from .demo_spa import scrape_spa_dashboard
from .auto_series import run_auto
# --- 1. AÑADE LA IMPORTACIÓN DE VALIDATE ---
from .validate import main as validate_main  # Renombramos 'main' a 'validate_main'

def main() -> None:
    """
    Función principal. 
    Parsea los argumentos de la línea de comandos y ejecuta el 
    sub-comando correspondiente.
    """
    ap = argparse.ArgumentParser(
        prog="PRACT1-BPS",
        description="Herramienta de scraping y parsing para indicadores del BPS."
    )
    
    sub = ap.add_subparsers(
        dest="cmd", 
        required=True,
        help="Comando a ejecutar"
    )

    # --- Comando 'robots' ---
    p_robots = sub.add_parser(
        "robots", 
        help="Verifica robots.txt en hosts relevantes"
    )

    # --- Comando 'index' ---
    p_index = sub.add_parser(
        "index", 
        help="Crawlea el índice y genera indicadores_index.csv"
    )
    p_index.add_argument(
        "--pages", nargs="*", default=BASE_INDEX_PAGES,
        help="Lista de URLs de índice a crawlear."
    )
    p_index.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_SEC,
        help="Espera (en segundos) entre peticiones."
    )
    p_index.add_argument(
        "--max-pages", type=int, default=10,
        help="Máximo de sub-páginas a explorar por cada página de índice."
    )

    # --- Comando 'desempleo' ---
    p_des = sub.add_parser(
        "desempleo", 
        help="Descarga y parsea XLS de III.3 Subsidio por desempleo"
    )
    p_des.add_argument(
        "--xls-url", required=True, type=str,
        help="URL directa al archivo .xls/.xlsx"
    )
    p_des.add_argument(
        "--sheet", default=None, type=str,
        help="Nombre o índice (base 0) de la hoja a parsear (opcional)."
    )

    # --- Comando 'recaudacion' ---
    p_rec = sub.add_parser(
        "recaudacion", 
        help="Descarga y parsea XLS de II. Recaudación"
    )
    p_rec.add_argument(
        "--xls-url", required=True, type=str,
        help="URL directa al archivo .xls/.xlsx"
    )
    p_rec.add_argument(
        "--sheet", default=None, type=str,
        help="Nombre o índice (base 0) de la hoja a parsear (opcional)."
    )
    
    # --- Comando 'spa' ---
    p_spa = sub.add_parser(
        "spa",
        help="Extrae datos del dashboard principal de la SPA (Observatorio)"
    )
    
    # --- Comando 'auto' ---
    p_auto = sub.add_parser(
        "auto",
        help="Lee dataset/indicadores_index.csv y ejecuta desempleo+recaudación con el último XLS por capítulo."
    )

    # --- 2. AÑADE EL SUB-COMANDO 'validate' ---
    p_val = sub.add_parser(
        "validate",
        help="Valida que todos los archivos CSV generados sean correctos."
    )
    
    
    # Parsea los argumentos de la línea de comandos
    args: argparse.Namespace = ap.parse_args()

    # --- Lógica de Despacho (Dispatch) ---
    
    if args.cmd == "robots":
        check_all()
        
    elif args.cmd == "index":
        crawl_index(
            pages=args.pages, 
            delay=args.delay, 
            max_pages=args.max_pages
        )
    
    elif args.cmd == "desempleo":
        parse_desempleo(args.xls_url, sheet=args.sheet)

    elif args.cmd == "recaudacion":
        parse_recaudacion(args.xls_url, sheet=args.sheet)
        
    elif args.cmd == "spa":
        scrape_spa_dashboard()
        
    elif args.cmd == "auto":
        run_auto()

    # --- 3. AÑADE LA LLAMADA A LA FUNCIÓN DE VALIDACIÓN ---
    elif args.cmd == "validate":
        validate_main()

    else:
        ap.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()