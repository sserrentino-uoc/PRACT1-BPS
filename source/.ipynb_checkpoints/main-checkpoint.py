"""
Punto de entrada principal para el proyecto de scraping de la PRACT1.

Este script proporciona una interfaz de línea de comandos (CLI) para
ejecutar las diferentes partes del proyecto:
1. robots: Verifica los archivos robots.txt de los sitios.
2. index: Crawlea el índice de indicadores.
3. desempleo: Parsea un XLS de subsidio por desempleo.
4. recaudacion: Parsea un XLS de recaudación.
"""

import argparse, sys
from .settings import BASE_INDEX_PAGES, DEFAULT_DELAY_SEC
from .robots_check import check_all
from .crawl_index import crawl_index
from .parse_series import parse_desempleo, parse_recaudacion

def main():
    """
    Función principal. 
    
    Parsea los argumentos de la línea de comandos y ejecuta el 
    sub-comando correspondiente (robots, index, desempleo, recaudacion).
    """
    ap = argparse.ArgumentParser(
        prog="PRACT1-BPS",
        description="Herramienta de scraping y parsing para indicadores del BPS."
    )
    # Define el contenedor para los sub-comandos
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
        "--pages", 
        nargs="*", 
        default=BASE_INDEX_PAGES,
        help="Lista de URLs de índice a crawlear."
    )
    p_index.add_argument(
        "--delay", 
        type=float, 
        default=DEFAULT_DELAY_SEC,
        help="Espera (en segundos) entre peticiones."
    )
    p_index.add_argument(
        "--max-pages", 
        type=int, 
        default=10,
        help="Máximo de sub-páginas a explorar por cada página de índice."
    )

    # --- Comando 'desempleo' ---
    p_des = sub.add_parser(
        "desempleo", 
        help="Descarga y parsea XLS de III.3 Subsidio por desempleo"
    )
    p_des.add_argument(
        "--xls-url", 
        required=True, 
        type=str,
        help="URL directa al archivo .xls/.xlsx"
    )
    p_des.add_argument(
        "--sheet", 
        default=None, 
        type=str,
        help="Nombre o índice (base 0) de la hoja a parsear (opcional)."
    )

    # --- Comando 'recaudacion' ---
    p_rec = sub.add_parser(
        "recaudacion", 
        help="Descarga y parsea XLS de II. Recaudación"
    )
    p_rec.add_argument(
        "--xls-url", 
        required=True, 
        type=str,
        help="URL directa al archivo .xls/.xlsx"
    )
    p_rec.add_argument(
        "--sheet", 
        default=None, 
        type=str,
        help="Nombre o índice (base 0) de la hoja a parsear (opcional)."
    )
    
    # Parsea los argumentos de la línea de comandos
    args: argparse.Namespace = ap.parse_args()

    # --- Lógica de Despacho (Dispatch) ---
    # Ejecuta la función correspondiente al comando
    
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

    else:
        # (Aunque con 'required=True', este 'else' no debería alcanzarse)
        ap.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()