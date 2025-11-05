import requests
from requests.exceptions import RequestException
from typing import List, Union
from pathlib import Path

from .settings import DEFAULT_UA, REQUEST_TIMEOUT, LOG_DIR
from .utils import make_logger

TARGETS: List[str] = [
    "https://observatorio.bps.gub.uy/robots.txt",
    "https://www.bps.gub.uy/robots.txt",
    "https://bps.gub.uy/robots.txt",
]

def check_all(log_dir: Union[str, Path] = LOG_DIR) -> None:
    """
    Verifica los archivos robots.txt de los dominios objetivo (TARGETS).

    Intenta primero una petición HEAD. Si falla (ej. 405, 4xx) o tiene éxito (200),
    realiza un GET para descargar y mostrar una vista previa del contenido
    si es de tipo texto.

    Registra toda la actividad en un archivo 'robots.log'.

    Args:
        log_dir (Union[str, Path], optional): Directorio para guardar los logs.
            Por defecto, usa el LOG_DIR de settings.py.
    """
    logger = make_logger(log_dir, "robots")
    
    for url in TARGETS:
        try:
            h = requests.head(url, headers={"User-Agent": DEFAULT_UA},
                              timeout=REQUEST_TIMEOUT, allow_redirects=True)
            code = h.status_code
            logger.info(f"[HEAD] {url} -> {code}")

            # Lógica 'if' simplificada para evitar duplicación de código (DRY)
            if (code == 405 or code >= 400) or (code == 200):
                r = requests.get(url, headers={"User-Agent": DEFAULT_UA},
                                   timeout=REQUEST_TIMEOUT)
                
                content_type = r.headers.get('Content-Type', '')
                logger.info(f"[GET ] {url} -> {r.status_code} {content_type}")
                
                if r.ok and "text" in content_type:
                    preview = "\n".join(r.text.splitlines()[:10])
                    logger.info(f"--- robots.txt preview ---\n{preview}\n--- end ---")
        
        # Usar una excepción específica en lugar de 'Exception'
        except RequestException as e:
            logger.warning(f"[ERR ] {url} -> {e}")
            
    logger.info("Si no hay robots.txt público, se aplica 'polite crawling' por defecto.")