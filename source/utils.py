import os, time, logging, re
import urllib.parse as up
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry

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

def build_session(ua: str, timeout: int = 20, total: int = 5, backoff: float = 0.8) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua})
    retries = Retry(total=total, backoff_factor=backoff, status_forcelist=[429,500,502,503,504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    # wrap timeout
    orig = s.request
    def _req(method, url, **kw):
        kw.setdefault("timeout", timeout)
        return orig(method, url, **kw)
    s.request = _req
    return s

