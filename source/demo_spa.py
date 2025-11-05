"""
Script de demostración para scraping de una SPA (Single Page Application)
usando Selenium.

Este script (opcional) se conecta a la URL del Observatorio BPS,
espera a que un elemento específico (la "caja" de Prestaciones) sea
visible, extrae su texto y lo imprime en la consola.

Requiere:
- selenium (pip install selenium)
- Un WebDriver (ej. chromedriver) compatible con tu versión de Chrome.
"""

# 1. Importaciones de la biblioteca estándar
import time
from typing import List, Tuple

# 2. Importaciones de terceros
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 3. Importaciones locales
# (No hay)


# --- Constantes ---
URL_TARGET: str = "https://observatorio.bps.gub.uy/#/"
WAIT_TIMEOUT: int = 15

# Selector XPath para la caja de "Prestaciones".
# Busca un <h2> con "Prestaciones" y luego el primer <div> con
# la clase "value" que le sigue.
PRESTACIONES_BOX_XPATH: str = "//h2[contains(.,'Prestaciones')]/following::div[contains(@class,'value')][1]"


def setup_driver() -> WebDriver:
    """Configura e inicializa el driver de Chrome en modo headless."""
    opts = Options()
    opts.add_argument("--headless=new")
    driver: WebDriver = webdriver.Chrome(options=opts)
    return driver

def fetch_spa_data(driver: WebDriver, url: str) -> str:
    """
    Navega a la URL de la SPA y extrae el dato de "Prestaciones".

    Args:
        driver (WebDriver): La instancia del driver de Selenium.
        url (str): La URL de la SPA a cargar.

    Returns:
        str: El texto extraído del elemento (ej. "1.234.567").
    """
    driver.get(url)
    
    # Configura el 'WebDriverWait'
    w = WebDriverWait(driver, WAIT_TIMEOUT)
    
    # Define la condición de espera (localizador)
    locator: Tuple[str, str] = (By.XPATH, PRESTACIONES_BOX_XPATH)
    
    print(f"Esperando {WAIT_TIMEOUT}s a que el elemento sea visible en {url}...")
    
    # Espera a que el elemento sea visible
    tile: WebElement = w.until(EC.visibility_of_element_located(locator))
    
    # Devuelve el texto del elemento
    return tile.text.strip()

def main():
    """Punto de entrada principal para el script de demo de la SPA."""
    driver: WebDriver | None = None  # Inicializar por si 'try' falla
    try:
        driver = setup_driver()
        print("Driver de Selenium (Headless Chrome) iniciado.")
        
        prestaciones_valor = fetch_spa_data(driver, URL_TARGET)
        
        print("\n--- Resultado del Scraping (SPA) ---")
        print(f"Prestaciones (valor visible): {prestaciones_valor}")
        print("------------------------------------")
        
    except Exception as e:
        print(f"\nHa ocurrido un error durante la ejecución de Selenium:")
        print(f"{type(e).__name__}: {e}")
        
    finally:
        # Asegura que el driver se cierre SIEMPRE, incluso si hay un error
        if driver:
            print("\nCerrando el driver de Selenium...")
            driver.quit()
            print("Driver cerrado.")

if __name__ == "__main__":
    main()