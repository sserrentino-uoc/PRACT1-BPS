import os, time, logging, re
import urllib.parse as up
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry

def ensure_dirs(*paths):
    """
    Asegura que uno o más directorios existan, creándolos si es necesario.
    
    Utiliza `os.makedirs(..., exist_ok=True)` para evitar errores si
    el directorio ya existe.

    Args:
        *paths (str): Una secuencia de rutas de directorio a crear.
    """
    for p in paths:
        os.makedirs(p, exist_ok=True)

def make_logger(log_dir: str, name: str = "run") -> logging.Logger:
    """
    Configura y devuelve un logger que escribe en un archivo y en la consola.

    Asegura que el directorio de logs exista antes de crear el archivo.

    Args:
        log_dir (str): Directorio donde se guardará el archivo .log.
        name (str, optional): Nombre del logger y del archivo .log. 
                              Defaults to "run".

    Returns:
        logging.Logger: La instancia del logger configurado.
    """
    ensure_dirs(log_dir)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    sh = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

def polite_sleep(seconds: float | int, logger: logging.Logger | None = None) -> None:
    """
    Realiza una pausa (sleep) e informa opcionalmente a un logger.

    Args:
        seconds (float | int): Número de segundos para pausar la ejecución.
        logger (logging.Logger | None, optional): Logger para registrar el
                                                  mensaje de espera. Defaults to None.
    """
    if logger: 
        logger.info(f"Sleeping {seconds:.1f}s")
    time.sleep(seconds)

def abs_url(base: str, href: str | None) -> str | None:
    """
    Convierte un enlace (href) relativo en una URL absoluta.

    Filtra enlaces nulos, vacíos, anclas (#) y llamadas javascript.

    Args:
        base (str): La URL base de la página (ej. "https://www.dominio.com").
        href (str | None): El atributo href extraído (ej. "/pagina.html").

    Returns:
        str | None: La URL absoluta (ej. "https://www.dominio.com/pagina.html")
                    o None si el href no es un enlace válido.
    """
    if not href: return None
    href = href.strip()
    if href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    return up.urljoin(base, href)

def text2num(s: str | None) -> int | None:
    """
    Convierte un string de tamaño de archivo (ej. "1,2 MB") a bytes.

    Maneja unidades B, KB, y MB, e ignora mayúsculas/minúsculas.
    Acepta ',' como separador decimal y '.' como separador de miles.

    Args:
        s (str | None): El string a convertir.

    Returns:
        int | None: El número de bytes aproximado, o None si no se pudo parsear.
    """
    if not s: return None
    m = re.search(r"([\d\.,]+)\s*(KB|MB|B)", s, re.I)
    if not m: return None
    val = float(m.group(1).replace(".", "").replace(",", "."))
    unit = m.group(2).upper()
    mult = {"B": 1, "KB": 1024, "MB": 1024 * 1024}[unit]
    return int(val*mult)

def clean_whitespace(s: str | None) -> str:
    """
    Limpia el exceso de espacios en blanco de un string.

    Reemplaza todas las secuencias de espacios (incluyendo saltos de línea,
    tabulaciones, etc.) por un solo espacio y elimina los espacios
    al inicio y al final.

    Args:
        s (str | None): El string a limpiar.

    Returns:
        str: El string limpio. Devuelve "" si la entrada es None.
    """
    return re.sub(r"\s+", " ", s or "").strip()

def soup_select_text(soup: BeautifulSoup, css: str, default: str = "") -> str:
    """
    Extrae y limpia el texto de un elemento usando un selector CSS.

    Utiliza `soup.select_one()` para encontrar el primer elemento que
    coincida con el selector y devuelve su texto limpio.

    Args:
        soup (BeautifulSoup): El objeto BeautifulSoup parseado.
        css (str): El selector CSS para encontrar el elemento.
        default (str, optional): Valor a devolver si no se encuentra
                                 el elemento. Defaults to "".

    Returns:
        str: El texto limpio del elemento, o el valor `default`.
    """
    el = soup.select_one(css)
    return clean_whitespace(el.get_text(" ", strip=True) if el else default)

def build_session(ua: str, timeout: int = 20, total: int = 5, backoff: float = 0.8) -> requests.Session:
    """
    Construye una sesión de `requests` robusta con reintentos y timeout.

    Configura la sesión con un User-Agent, una estrategia de reintentos
    (Retry) para códigos de error comunes (429, 5xx) y un timeout
    por defecto para todas las peticiones.

    Args:
        ua (str): El string User-Agent a utilizar.
        timeout (int, optional): Timeout en segundos para las peticiones.
                                 Defaults to 20.
        total (int, optional): Número total de reintentos. Defaults to 5.
        backoff (float, optional): Factor de backoff para los reintentos.
                                   Defaults to 0.8.

    Returns:
        requests.Session: La instancia de la sesión configurada.
    """
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