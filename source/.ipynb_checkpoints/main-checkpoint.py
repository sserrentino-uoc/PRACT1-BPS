import argparse, sys
from .settings import BASE_INDEX_PAGES, DEFAULT_DELAY_SEC
from .robots_check import check_all
from .crawl_index import crawl_index
from .parse_series import parse_desempleo, parse_recaudacion

def main():
    ap = argparse.ArgumentParser(prog="PRACT1-BPS")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_robots = sub.add_parser("robots", help="Verifica robots.txt en hosts relevantes")

    p_index = sub.add_parser("index", help="Crawlea el índice y genera indicadores_index.csv")
    p_index.add_argument("--pages", nargs="*", default=BASE_INDEX_PAGES)
    p_index.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC)
    p_index.add_argument("--max-pages", type=int, default=10)

    p_des = sub.add_parser("desempleo", help="Descarga y parsea XLS de III.3 Subsidio por desempleo")
    p_des.add_argument("--xls-url", required=True)
    p_des.add_argument("--sheet", default=None)

    p_rec = sub.add_parser("recaudacion", help="Descarga y parsea XLS de II. Recaudación")
    p_rec.add_argument("--xls-url", required=True)
    p_rec.add_argument("--sheet", default=None)

    args = ap.parse_args()

    if args.cmd == "robots":
        check_all()
    elif args.cmd == "index":
        crawl_index(pages=args.pages, delay=args.delay, max_pages=args.max_pages)
    elif args.cmd == "desempleo":
        parse_desempleo(args.xls_url, sheet=args.sheet)
    elif args.cmd == "recaudacion":
        parse_recaudacion(args.xls_url, sheet=args.sheet)
    else:
        ap.print_help(); sys.exit(1)

if __name__ == "__main__":
    main()