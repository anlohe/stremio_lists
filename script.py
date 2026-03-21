import os
import json
import requests
import time

# --- CONFIGURACIÓN DE SEGURIDAD ---
API_KEY = os.environ.get('TMDB_API_KEY')
BASE_URL = "https://api.themoviedb.org/3"
LANG = "es-ES" 

# --- FUNCIONES DEL MOTOR ---
def obtener_peliculas_tmdb(list_id):
    peliculas = []
    pagina = 1
    total_paginas = 1
    
    while pagina <= total_paginas:
        url = f"{BASE_URL}/list/{list_id}?api_key={API_KEY}&language={LANG}&page={pagina}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            peliculas.extend(data.get('items', []))
            total_paginas = data.get('total_pages', 1)
            pagina += 1
            if total_paginas > 1: 
                time.sleep(0.2) # Pausa interna entre páginas de una misma lista
        except Exception as e:
            print(f"Error descargando lista {list_id}: {e}")
            break
            
    return peliculas

def formatear_para_stremio(tmdb_movie):
    stremio_id = tmdb_movie.get('imdb_id')
    if not stremio_id:
        stremio_id = f"tmdb:{tmdb_movie.get('id')}"

    poster_path = tmdb_movie.get('poster_path')
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

    return {
        "id": stremio_id,
        "type": "movie",
        "name": tmdb_movie.get('title') or tmdb_movie.get('original_title'),
        "poster": poster_url,
        "description": tmdb_movie.get('overview', 'Sin descripción en español.')
    }

# --- PROCESO PRINCIPAL ---
def run():
    print("Iniciando actualización masiva de listas desde config.json...")
    
    if not API_KEY:
        print("ERROR: No se encontró la TMDB_API_KEY en los Secrets.")
        return

    # Leer el archivo config.json del usuario
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error leyendo config.json: {e}")
        return

    catalogos_manifest = []

    # Crear la estructura de carpetas estricta que exige Stremio
    stremio_path = os.path.join("catalog", "movie")
    os.makedirs(stremio_path, exist_ok=True)

    for categoria, listas in config.items():
        for list_id, nombre_lista in listas.items():
            print(f"Procesando: {nombre_lista} ({list_id}) en {categoria}...")
            
            raw_movies = obtener_peliculas_tmdb(list_id)
            print(f"  - Encontradas {len(raw_movies)} películas.")
            
            stremio_metas = [formatear_para_stremio(m) for m in raw_movies if m.get('title')]
            
            # Crear un ID único para la lista (ej: directores_i_8640008)
            cat_id = f"{categoria.replace(' ', '_').lower()}_{list_id}"
            
            # Guardar el JSON en la ruta estricta que lee Stremio
            ruta_archivo = os.path.join(stremio_path, f"{cat_id}.json")
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                json.dump({"metas": stremio_metas}, f, ensure_ascii=False, indent=2)
                
            catalogos_manifest.append({
                "type": "movie",
                "id": cat_id,
                "name": f"{nombre_lista} ({categoria})"
            })
            
            # --- LA PAUSA SALVAVIDAS PARA TMDB ---
            # Esperamos medio segundo antes de pedir la siguiente lista al servidor
            time.sleep(0.5) 

    # Generar el manifest final
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
        
    print("Proceso finalizado con éxito.")

if __name__ == "__main__":
    run()
