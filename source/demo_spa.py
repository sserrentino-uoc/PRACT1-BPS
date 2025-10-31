# demo_spa.py (opcional, solo para el video)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

opts = Options()
opts.add_argument("--headless=new")
driver = webdriver.Chrome(options=opts)
driver.get("https://observatorio.bps.gub.uy/#/")
w = WebDriverWait(driver, 15)
# ejemplo: caja grande "Prestaciones" (ajusta el selector si cambia el DOM)
tile = w.until(EC.visibility_of_element_located((By.XPATH, "//h2[contains(.,'Prestaciones')]/following::div[contains(@class,'value')][1]")))
print("Prestaciones (valor visible):", tile.text)
driver.quit()