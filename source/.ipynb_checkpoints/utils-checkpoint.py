import os, time, logging, re
import urllib.parse as up
from bs4 import BeautifulSoup

def ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)

def make_logger(log_dir, name="run"):
    ensure_dirs(log_dir)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt); sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

def polite_sleep(seconds, logger=None):
    if logger: logger.info(f"Sleeping {seconds:.1f}s")
    time.sleep(seconds)

def abs_url(base, href):
    if not href: return None
    href = href.strip()
    if href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    return up.urljoin(base, href)

def text2num(s):
    # “952 KB”, “1,2 MB” -> bytes aprox (opcional)
    if not s: return None
    m = re.search(r"([\d\.,]+)\s*(KB|MB|B)", s, re.I)
    if not m: return None
    val = float(m.group(1).replace(".", "").replace(",", "."))
    unit = m.group(2).upper()
    mult = {"B":1, "KB":1024, "MB":1024*1024}[unit]
    return int(val*mult)

def clean_whitespace(s):
    return re.sub(r"\s+", " ", s or "").strip()

def soup_select_text(soup, css, default=""):
    el = soup.select_one(css)
    return clean_whitespace(el.get_text(" ", strip=True) if el else default)
