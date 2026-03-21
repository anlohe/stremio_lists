import os
import json
import requests
import time

# --- CONFIGURACIÓN DE SEGURIDAD ---
# Coge la API Key que guardamos en los Secrets de GitHub
API_KEY = os.environ.get('TMDB_API_KEY')
BASE_URL = "https://api.themoviedb.org/3"
# Forzamos idioma español y país España para mejores metadatos
LANG = "es-ES" 

# --- CONFIGURACIÓN DE LA PRUEBA (Temporal, luego irá en config.json) ---
# Hemos elegido dos listas públicas existentes para la prueba:
# 1. Una de Director (Tarantino) -> irá a DIRECTORES I
# 2. Una de Saga (Star Wars) -> irá a SAGAS
LISTAS_PRUEBA = [
    {"id": "8239066", "carpeta": "DIRECTORES I", "nombre_archivo": "tarantino", "nombre_catalogo": "Quentin Tarantino"},
    {"id": "10",      "carpeta": "SAGAS",        "nombre_archivo": "star_wars", "nombre_catalogo": "Saga Star Wars"}
]

# --- FUNCIONES DEL MOTOR ---

def obtener_peliculas_tmdb(list_id):
    """Se conecta a TMDB, maneja paginación (>20) y trae info en español."""
    peliculas = []
    pagina = 1
    total_paginas = 1
    
    while pagina <= total_paginas:
        # Construimos la URL de petición a la API v3 de TMDB
        url = f"{BASE_URL}/list/{list_id}?api_key={API_KEY}&language={LANG}&page={pagina}"
        try:
            response = requests.get(url)
            response.raise_for_status() # Lanza error si la conexión falla
            data = response.json()
            
            # Guardamos los resultados de esta página
            peliculas.extend(data.get('items', []))
            
            # Actualizamos el total de páginas para saber si hay que seguir
            total_paginas = data.get('total_pages', 1)
            pagina += 1
            
            # Pequeña pausa de seguridad para no saturar la API de TMDB
            if total_paginas > 1: time.sleep(0.2)
            
        except Exception as e:
            print(f"Error descargando lista {list_id}: {e}")
            break
            
    return peliculas

def formatear_para_stremio(tmdb_movie):
    """Convierte el formato de TMDB al formato JSON que entiende Stremio."""
    # Creamos el ID único de Stremio (ej: tt1234567 o tmdb:123)
    # Usamos imdb_id si existe, si no, usamos el id de tmdb
    stremio_id = tmdb_movie.get('imdb_id')
    if not stremio_id:
        stremio_id = f"tmdb:{tmdb_movie.get('id')}"

    # Construimos la URL de la carátula original de TMDB
    poster_path = tmdb_movie.get('poster_path')
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    return {
        "id": stremio_id,
        "type": "movie", # Por ahora asumimos que son películas
        "name": tmdb_movie.get('title') or tmdb_movie.get('original_title'),
        "poster": poster_url,
        "description": tmdb_movie.get('overview', 'Sin descripción en español.')
    }

# --- PROCESO PRINCIPAL ---

def run():
    print("Iniciando actualización de listas...")
    
    if not API_KEY:
        print("ERROR: No se encontró la TMDB_API_KEY en los Secrets.")
        return

    # Lista para guardar los catálogos que formarán el Manifest final
    catalogos_manifest = []

    for lista in LISTAS_PRUEBA:
        print(f"Procesando: {lista['nombre_catalogo']} ({lista['id']}) en {lista['carpeta']}...")
        
        # 1. Crear la carpeta si no existe (ej: DIRECTORES I)
        if not os.path.exists(lista['carpeta']):
            os.makedirs(lista['carpeta'])
            
        # 2. Descargar películas de TMDB (en español, sin límite de 20)
        raw_movies = obtener_peliculas_tmdb(lista['id'])
        print(f"  - Encontradas {len(raw_movies)} películas.")
        
        # 3. Traducir al formato Stremio (JSON plano optimizado)
        stremio_metas = [formatear_para_stremio(m) for m in raw_movies if m.get('title')]
        
        # 4. Crear el JSON final de la lista (ej: DIRECTORES I/tarantino.json)
        json_final = {
            "metas": stremio_metas
        }
        
        ruta_archivo = os.path.join(lista['carpeta'], f"{lista['nombre_archivo']}.json")
        with open(ruta_archivo, 'w', encoding='utf-8') as f:
            json.dump(json_final, f, ensure_ascii=False, indent=2)
            
        # 5. Añadir info a la lista para generar el Manifest final
        # Creamos un ID de catálogo único para Stremio: carpeta_archivo
        catalog_id = f"{lista['carpeta'].replace(' ', '_').lower()}_{lista['nombre_archivo']}"
        catalogos_manifest.append({
            "type": "movie",
            "id": catalog_id,
            "name": f"{lista['nombre_catalogo']} ({lista['carpeta']})"
        })

    # --- GENERAR EL MANIFEST.JSON FINAL ---
    # Este archivo es el que vincula todo con Stremio
    manifest = {
        "id": "com.anlohe.tmdb.listas.estaticas",
        "version": "1.0.0",
        "name": "Mis Listas TMDB Estáticas",
        "description": "Listas de TMDB en español, rápidas y sin errores de Empty.",
        "resources": ["catalog"],
        "types": ["movie"],
        "idPrefixes": ["tt", "tmdb:"],
        "catalogs": catalogos_manifest
    }
    
    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        
    print("Proceso finalizado. manifest.json generado.")

if __name__ == "__main__":
    run()
