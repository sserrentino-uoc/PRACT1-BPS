import requests
from .settings import DEFAULT_UA, REQUEST_TIMEOUT
from .utils import make_logger

TARGETS = [
    "https://observatorio.bps.gub.uy/robots.txt",
    "https://www.bps.gub.uy/robots.txt",
    "https://bps.gub.uy/robots.txt",
]

def check_all(log_dir="logs"):
    logger = make_logger(log_dir, "robots")
    for url in TARGETS:
        try:
            h = requests.head(url, headers={"User-Agent": DEFAULT_UA},
                              timeout=REQUEST_TIMEOUT, allow_redirects=True)
            code = h.status_code
            logger.info(f"[HEAD] {url} -> {code}")
            if code == 405 or code >= 400:
                r = requests.get(url, headers={"User-Agent": DEFAULT_UA},
                                 timeout=REQUEST_TIMEOUT)
                logger.info(f"[GET ] {url} -> {r.status_code} {r.headers.get('Content-Type','')}")
                if r.ok and "text" in r.headers.get("Content-Type",""):
                    preview = "\n".join(r.text.splitlines()[:10])
                    logger.info(f"--- robots.txt preview ---\n{preview}\n--- end ---")
            elif code == 200:
                r = requests.get(url, headers={"User-Agent": DEFAULT_UA},
                                 timeout=REQUEST_TIMEOUT)
                logger.info(f"[GET ] {url} -> {r.status_code} {r.headers.get('Content-Type','')}")
                if r.ok and "text" in r.headers.get("Content-Type",""):
                    preview = "\n".join(r.text.splitlines()[:10])
                    logger.info(f"--- robots.txt preview ---\n{preview}\n--- end ---")
        except Exception as e:
            logger.warning(f"[ERR ] {url} -> {e}")
    logger.info("Si no hay robots.txt público, se aplica 'polite crawling' por defecto.")