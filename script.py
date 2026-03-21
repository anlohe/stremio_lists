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
                time.sleep(0.2)
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

    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error leyendo config.json: {e}")
        return

    # Listas separadas para cada addon
    cat_directores_1 = []
    cat_directores_2 = []
    cat_sagas_premios = []

    stremio_path = os.path.join("catalog", "movie")
    os.makedirs(stremio_path, exist_ok=True)

    for categoria, listas in config.items():
        for list_id, datos in listas.items():
            nombre_lista = datos["nombre"]
            print(f"Procesando: {nombre_lista} ({list_id}) en {categoria}...")
            
            raw_movies = obtener_peliculas_tmdb(list_id)
            print(f"  - Encontradas {len(raw_movies)} películas.")
            
            stremio_metas = [formatear_para_stremio(m) for m in raw_movies if m.get('title')]
            
            cat_id = f"{categoria.replace(' ', '_').lower()}_{list_id}"
            
            ruta_archivo = os.path.join(stremio_path, f"{cat_id}.json")
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                json.dump({"metas": stremio_metas}, f, ensure_ascii=False, indent=2)
                
            catalogo_obj = {
                "type": "movie",
                "id": cat_id,
                "name": f"{nombre_lista}"
            }
            
            # Repartir los catalogos en su addon correspondiente
            if categoria == "DIRECTORES I":
                cat_directores_1.append(catalogo_obj)
            elif categoria == "DIRECTORES II":
                cat_directores_2.append(catalogo_obj)
            elif categoria in ["SAGAS", "PREMIOS"]:
                cat_sagas_premios.append(catalogo_obj)
            
            time.sleep(0.5) 

    # Función para crear los manifests individuales
    def crear_manifest(id_sufijo, nombre, catalogos, nombre_archivo):
        manifest = {
            "id": f"com.anlohe.tmdb.{id_sufijo}",
            "version": "1.0.0",
            "name": nombre,
            "description": f"Colección de {nombre} extraídas de TMDB.",
            "resources": ["catalog"],
            "types": ["movie"],
            "idPrefixes": ["tt", "tmdb:"],
            "catalogs": catalogos
        }
        with open(nombre_archivo, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Crear los 3 archivos manifest
    crear_manifest("directores1", "Listas personalizadas Directores I", cat_directores_1, "manifest_directores_1.json")
    crear_manifest("directores2", "Listas personalizadas Directores II", cat_directores_2, "manifest_directores_2.json")
    crear_manifest("sagaspremios", "Listas personalizadas Sagas y Premios", cat_sagas_premios, "manifest_sagas_premios.json")
        
    print("Proceso finalizado con éxito. Se han generado 3 manifiestos.")

if __name__ == "__main__":
    run()
