import os
import json
import requests
import time

# --- CONFIGURACIÓN DE SEGURIDAD V4 ---
# Usamos directamente el Token de lectura que me proporcionaste
TMDB_TOKEN = os.environ.get("TMDB_API_KEY")
LANG = "es-ES" 

def obtener_peliculas_tmdb(list_id):
    peliculas = []
    pagina = 1
    total_paginas = 1
    
    # Esta es la llave maestra para la puerta v4
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_TOKEN}"
    }
    
    while pagina <= total_paginas:
        # Usamos la API v4
        url = f"https://api.themoviedb.org/4/list/{list_id}?page={pagina}&language={LANG}"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            # En la v4, las peliculas vienen en 'results'
            peliculas.extend(data.get('results', []))
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

def run():
    print("Iniciando creación de Addons en subcarpetas (API v4)...")
    
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    cat_directores_1 = []
    cat_directores_2 = []
    cat_sagas_premios = []

    for categoria, listas in config.items():
        if categoria == "DIRECTORES I":
            carpeta_base = "directores_1"
            lista_catalogo = cat_directores_1
        elif categoria == "DIRECTORES II":
            carpeta_base = "directores_2"
            lista_catalogo = cat_directores_2
        else:
            carpeta_base = "sagas_premios"
            lista_catalogo = cat_sagas_premios

        stremio_path = os.path.join(carpeta_base, "catalog", "movie")
        os.makedirs(stremio_path, exist_ok=True)

        for list_id, datos in listas.items():
            nombre_lista = datos["nombre"]
            
            # Obtenemos las películas con v4
            raw_movies = obtener_peliculas_tmdb(list_id)
            stremio_metas = [formatear_para_stremio(m) for m in raw_movies if m.get('title')]
            
            # Escudo anti-vacíos: Si la lista está vacía, la ignoramos para no romper Stremio
            if not stremio_metas:
                print(f"⚠️ Omitiendo: {nombre_lista} ({list_id}) - La lista está vacía en TMDB.")
                continue
                
            print(f"✅ Procesando: {nombre_lista} ({list_id}) - {len(stremio_metas)} películas.")
            
            cat_id = f"{categoria.replace(' ', '_').lower()}_{list_id}"
            
            ruta_archivo = os.path.join(stremio_path, f"{cat_id}.json")
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                json.dump({"metas": stremio_metas}, f, ensure_ascii=False, indent=2)
                
            lista_catalogo.append({
                "type": "movie",
                "id": cat_id,
                "name": nombre_lista
            })
            time.sleep(0.5)

    def crear_manifest(carpeta, id_sufijo, nombre, catalogos):
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
        ruta_manifest = os.path.join(carpeta, "manifest.json")
        with open(ruta_manifest, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    crear_manifest("directores_1", "directores1", "Listas personalizadas Directores I", cat_directores_1)
    crear_manifest("directores_2", "directores2", "Listas personalizadas Directores II", cat_directores_2)
    crear_manifest("sagas_premios", "sagaspremios", "Listas personalizadas Sagas y Premios", cat_sagas_premios)
        
    print("¡Proceso finalizado! Los 3 Addons están listos.")

if __name__ == "__main__":
    run()
