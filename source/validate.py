# Copyright (c) 2025 Serrentino Mangino, S., & Mochon Paredes, A.
# Licensed under the MIT License. See LICENSE for details.

import pandas as pd
import sys
import logging
from typing import Set

# Configurar un logger simple para mostrar los mensajes de validación
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def val_index(path: str) -> bool:
    """
    Valida el archivo de índice (index).

    Comprueba que:
    1. Contiene todas las columnas requeridas.
    2. No hay valores nulos en 'tipo_archivo' y 'url_descarga'.
    3. 'tipo_archivo' solo contiene 'pdf' o 'xls' (insensible a mayúsculas).
    4. 'url_descarga' comienza con 'http'.

    Args:
        path (str): Ruta al archivo CSV.

    Returns:
        bool: True si la validación pasa.
    
    Raises:
        AssertionError: Si alguna validación falla.
    """
    try:
        df = pd.read_csv(path)
        
        # 1. Validación de columnas
        req = {"capitulo", "titulo_corto", "tipo_archivo", "tamano_resuelto", 
               "fecha_publicacion", "filename_final", "url_descarga", "url_pagina"}
        missing = req - set(df.columns)
        assert not missing, f"Faltan columnas: {missing}"

        # 2. Validación de nulos
        assert df["tipo_archivo"].notna().all(), "Columna 'tipo_archivo' contiene valores nulos"
        assert df["url_descarga"].notna().all(), "Columna 'url_descarga' contiene valores nulos"

        # 3. Validación de 'tipo_archivo' (case-insensitive)
        assert df["tipo_archivo"].str.lower().isin(["pdf", "xls"]).all(), \
            f"Valores inválidos en 'tipo_archivo'. Se encontraron: {set(df['tipo_archivo'].str.lower().unique()) - {'pdf', 'xls'}}"

        # 4. Validación de 'url_descarga'
        assert df["url_descarga"].str.startswith("http").all(), "No todas las 'url_descarga' comienzan con 'http'"
        
        logging.info(f"✔ Validación OK: {path}")
        return True
    
    except AssertionError as e:
        logging.error(f"FAIL: {path} | {e}")
        return False
    except FileNotFoundError:
        logging.error(f"FAIL: {path} | Archivo no encontrado.")
        return False
    except Exception as e:
        logging.error(f"FAIL: {path} | Error inesperado: {e}")
        return False

def val_series(path: str, req_cols: Set[str]) -> bool:
    """
    Valida un archivo de serie temporal.

    Comprueba que:
    1. Existe la columna 'fecha'.
    2. Todos los valores de 'fecha' son fechas válidas.
    3. Contiene TODAS las columnas de métricas especificadas en req_cols.

    Args:
        path (str): Ruta al archivo CSV.
        req_cols (Set[str]): Un conjunto de nombres de columnas de métricas
                             que DEBEN estar presentes.

    Returns:
        bool: True si la validación pasa.

    Raises:
        AssertionError: Si alguna validación falla.
    """
    try:
        df = pd.read_csv(path)
        
        # 1. Validación de columna 'fecha'
        assert "fecha" in df.columns, "Falta la columna 'fecha'"
        
        # 2. Validación de formato de 'fecha'
        assert pd.to_datetime(df["fecha"], errors="coerce").notna().all(), "La columna 'fecha' contiene valores inválidos o nulos"
        
        # 3. Validación de métricas (Lógica corregida)
        # Comprueba que TODAS las columnas requeridas existan
        missing_metrics = req_cols - set(df.columns)
        assert not missing_metrics, f"Faltan métricas: {missing_metrics}"
        
        logging.info(f"✔ Validación OK: {path}")
        return True

    except AssertionError as e:
        logging.error(f"FAIL: {path} | {e}")
        return False
    except FileNotFoundError:
        logging.error(f"FAIL: {path} | Archivo no encontrado.")
        return False
    except Exception as e:
        logging.error(f"FAIL: {path} | Error inesperado: {e}")
        return False

def val_spa(path: str, req_indicadores: Set[str]) -> bool:
    """
    Valida el archivo de datos del dashboard de la SPA.

    Comprueba que:
    1. El archivo existe y usa codificación UTF-8.
    2. Contiene las columnas 'indicador' y 'valor'.
    3. No hay valores nulos en ninguna de esas columnas.
    4. Contiene todos los indicadores clave (filas) de 'req_indicadores'.

    Args:
        path (str): Ruta al archivo CSV.
        req_indicadores (Set[str]): Un conjunto de strings de los
                                    indicadores que DEBEN estar presentes.

    Returns:
        bool: True si la validación pasa.
    
    Raises:
        AssertionError: Si alguna validación falla.
    """
    try:
        # Forzamos la lectura en UTF-8, ya que así es como lo guarda demo_spa.py
        df = pd.read_csv(path, encoding="utf-8")
        
        # 1. Validación de columnas
        req_cols = {"indicador", "valor"}
        missing_cols = req_cols - set(df.columns)
        assert not missing_cols, f"Faltan columnas: {missing_cols}"

        # 2. Validación de nulos
        assert df["indicador"].notna().all(), "Columna 'indicador' contiene valores nulos"
        assert df["valor"].notna().all(), "Columna 'valor' contiene valores nulos"

        # 3. Validación de indicadores clave (filas)
        # (Usamos los nombres correctos con tildes, ya que leemos en UTF-8)
        indicadores_en_archivo = set(df["indicador"])
        missing_indicadores = req_indicadores - indicadores_en_archivo
        assert not missing_indicadores, f"Faltan indicadores clave (filas): {missing_indicadores}"
        
        logging.info(f"✔ Validación OK: {path}")
        return True

    except AssertionError as e:
        logging.error(f"FAIL: {path} | {e}")
        return False
    except FileNotFoundError:
        logging.error(f"FAIL: {path} | Archivo no encontrado.")
        return False
    except Exception as e:
        logging.error(f"FAIL: {path} | Error inesperado: {e}")
        return False

def main():
    """
    Ejecuta todas las validaciones y reporta los resultados.
    """
    logging.info("--- Iniciando validaciones ---")
    
    # Definir rutas
    path_index = "dataset/indicadores_index.csv"
    path_desempleo = "dataset/series_desempleo.csv"
    path_recaudacion = "dataset/series_recaudacion.csv"
    path_spa = "dataset/spa_dashboard_data.csv" 

    # Definir métricas/indicadores requeridos para cada archivo
    # (Tus datos de ejemplo mostraron 'RecaudaciÃ³n' por un problema
    # de encoding en la consola, pero el archivo CSV se guarda en UTF-8,
    # por lo que aquí usamos los nombres correctos con tildes).
    
    desempleo_cols_req = {"altas", "altas_montevideo", "altas_interior"}
    recaudacion_cols_req = {"recaudacion_privados", "recaudacion_publicos", "recaudacion_total"}
    spa_indicadores_req = {
        "Prestaciones", "Jubilaciones", "Recaudación", 
        "Empresas", "Régimen general"
    }
    # Ejecutamos las validaciones
    results = [
        val_index(path_index),
        val_series(path_desempleo, desempleo_cols_req),
        val_series(path_recaudacion, recaudacion_cols_req),
        val_spa(path_spa, spa_indicadores_req)  
    ]
    
    logging.info("--- Validaciones terminadas ---")
    
    if all(results):
        logging.info("✔✔✔ TODAS LAS VALIDACIONES PASARON ✔✔✔")
    else:
        failed_count = results.count(False)
        total_count = len(results)
        logging.error(f"✘✘✘ Han fallado {failed_count} de {total_count} validaciones. ✘✘✘")
        sys.exit(1) 

if __name__ == "__main__":
    main()