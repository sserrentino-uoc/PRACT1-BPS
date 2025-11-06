"""
Script de demostración para scraping de una SPA (Single Page Application)
usando Selenium.

... (resto de tu docstring de módulo) ...
"""

# 1. Importaciones de la biblioteca estándar
import time
import csv
import logging  # <-- AÑADIDO: Para type hints
from typing import List, Tuple, Dict
from pathlib import Path

# 2. Importaciones de terceros
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# 3. Importaciones locales
from .settings import OUT_DIR, LOG_DIR  # <-- AÑADIDO LOG_DIR
from .utils import ensure_dirs, make_logger  # <-- AÑADIDO make_logger


# --- Constantes ---
URL_TARGET: str = "https://observatorio.bps.gub.uy/#/"
WAIT_TIMEOUT: int = 30
ALL_TILES_XPATH: str = "//div[contains(@class,'card-dashboard')]"
TITLE_REL_XPATH: str = ".//h4[contains(@class,'card-title')]"
VALUE_REL_XPATH: str = ".//h5"
CHROME_DRIVER_PATH = r"C:\chrome-testing\chromedriver-win64\chromedriver.exe"
CHROME_BROWSER_PATH = r"C:\chrome-testing\chrome.exe"


def setup_driver() -> WebDriver:
    """
    Configura e inicializa el driver de Chrome
    usando las rutas manuales de Chrome for Testing.
    """
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.binary_location = CHROME_BROWSER_PATH
    service = Service(executable_path=CHROME_DRIVER_PATH)
    driver: WebDriver = webdriver.Chrome(service=service, options=opts)
    return driver

def fetch_all_tiles(driver: WebDriver, url: str, logger: logging.Logger) -> Dict[str, str]:
    """
    Navega a la URL de la SPA y extrae los datos de TODOS los azulejos.
    """
    driver.get(url)
    
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    locator: Tuple[str, str] = (By.XPATH, ALL_TILES_XPATH)
    
    logger.info(f"Esperando {WAIT_TIMEOUT}s a que los azulejos sean visibles en {url}...")
    wait.until(EC.visibility_of_element_located(locator))
    
    tiles: List[WebElement] = driver.find_elements(By.XPATH, ALL_TILES_XPATH)
    logger.info(f"Encontrados {len(tiles)} azulejos de datos. Extrayendo...")
    
    resultados: Dict[str, str] = {}
    
    for tile in tiles:
        try:
            titulo = tile.find_element(By.XPATH, TITLE_REL_XPATH).text.strip()
            valor_raw = tile.find_element(By.XPATH, VALUE_REL_XPATH).text.strip()
            
            if titulo and valor_raw:
                titulo_limpio = titulo.replace("*", "").strip()
                partes_valor = valor_raw.split(" ")
                
                valor_limpio = ""
                if len(partes_valor) > 0:
                    if partes_valor[0] == "$":
                        valor_limpio = partes_valor[1] if len(partes_valor) > 1 else "$"
                    else:
                        valor_limpio = partes_valor[0]
                
                if titulo_limpio and valor_limpio:
                    resultados[titulo_limpio] = valor_limpio

        except Exception as e:
            # Ignorar "azulejos" que no tienen título o valor
            pass 
            
    return resultados

def scrape_spa_dashboard():
    """
    Punto de entrada principal:
    1. Configura el logger y los directorios.
    2. Inicia el driver de Selenium.
    3. Extrae los datos de la SPA.
    4. Guarda los datos en un archivo CSV.
    """
    # --- 1. Configuración de Logger y Archivos ---
    ensure_dirs(OUT_DIR, LOG_DIR)
    logger = make_logger(LOG_DIR, "spa_scrape")  # <-- AÑADIDO
    output_path = OUT_DIR / "spa_dashboard_data.csv"

    driver: WebDriver | None = None
    try:
        # --- 2. Ejecución de Selenium ---
        driver = setup_driver()
        logger.info("Driver de Selenium (Chrome) iniciado.")
        
        todos_los_datos = fetch_all_tiles(driver, URL_TARGET, logger) # <-- Pasa el logger
        
        logger.info("--- Resultados del Scraping (SPA) ---")
        
        if not todos_los_datos:
            logger.warning("No se extrajeron datos.")
            logger.info("---------------------------------------")
            return

        # --- 3. Escritura de CSV ---
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["indicador", "valor"])
            
            for titulo, valor in todos_los_datos.items():
                logger.info(f"- {titulo}: {valor}") # <-- REEMPLAZA PRINT
                writer.writerow([titulo, valor])
        
        logger.info("---------------------------------------")
        logger.info(f"¡Éxito! Datos guardados en {output_path}")
        
    except Exception as e:
        # Usa logger.error para excepciones
        logger.error(f"Ha ocurrido un error durante la ejecución de Selenium:")
        logger.error(f"{type(e).__name__}: {e}")
        
    finally:
        if driver:
            logger.info("Cerrando el driver de Selenium...")
            driver.quit()
            logger.info("Driver cerrado.")

# ----- EL SCRIPT AÚN PUEDE EJECUTARSE SOLO -----
if __name__ == "__main__":
    scrape_spa_dashboard()