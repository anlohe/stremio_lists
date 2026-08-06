import os
import json
import requests
import time
import regex

# --- CONFIGURACIÓN DE SEGURIDAD V4 ---
TMDB_TOKEN = os.environ.get("TMDB_API_KEY")
LANG = "es-ES"

NON_LATIN = regex.compile(
    r'[\p{Script=Cyrillic}\p{Script=Arabic}\p{Script=Han}\p{Script=Hiragana}'
    r'\p{Script=Katakana}\p{Script=Hangul}\p{Script=Devanagari}\p{Script=Thai}'
    r'\p{Script=Hebrew}\p{Script=Greek}\p{Script=Tamil}\p{Script=Bengali}'
    r'\p{Script=Telugu}\p{Script=Malayalam}\p{Script=Georgian}\p{Script=Armenian}]'
)

def obtener_overrides_titulos():
    WORKER_URL = os.environ.get("WORKER_URL")
    ADMIN_KEY = os.environ.get("ADMIN_KEY")
    try:
        r = requests.get(f"{WORKER_URL}/overrides-titulos?key={ADMIN_KEY}")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Aviso: no se pudieron cargar overrides de titulos: {e}")
        return {}

OVERRIDES_TITULOS = obtener_overrides_titulos()

def resolver_titulo(item, media_type):
    """
    Resuelve el título de una película o serie.
    - Para películas: usa 'title' y 'original_title'
    - Para series: usa 'name' y 'original_name'
    """
    if media_type == "series":  # Stremio espera "series", pero TMDB devuelve "tv" en media_type
        titulo = item.get('name') or item.get('original_name') or ""
        original = item.get('original_name') or ""
        endpoint = "tv"
    else:
        titulo = item.get('title') or item.get('original_title') or ""
        original = item.get('original_title') or ""
        endpoint = "movie"

    if not NON_LATIN.search(titulo):
        return titulo

    tmdb_id = item.get('id')
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_TOKEN}"
    }
    try:
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?append_to_response=translations"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        translations = data.get('translations', {}).get('translations', [])
        # Buscar traducción al inglés
        en = None
        for t in translations:
            if t.get('iso_639_1') == 'en':
                if endpoint == "tv":
                    en = t.get('data', {}).get('name')
                else:
                    en = t.get('data', {}).get('title')
                break
        if en and not NON_LATIN.search(en):
            return en
    except Exception as e:
        print(f"Aviso: no se pudo traducir título de {tmdb_id} ({endpoint}): {e}")

    if original and not NON_LATIN.search(original):
        return original

    return titulo

def obtener_items_tmdb(list_id):
    """
    Descarga los items de una lista TMDB v4 (películas o series).
    Devuelve la lista de items sin modificar.
    """
    items = []
    pagina = 1
    total_paginas = 1

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_TOKEN}"
    }

    while pagina <= total_paginas:
        url = f"https://api.themoviedb.org/4/list/{list_id}?page={pagina}&language={LANG}"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            items.extend(data.get('results', []))
            total_paginas = data.get('total_pages', 1)
            pagina += 1
            if total_paginas > 1:
                time.sleep(0.2)
        except Exception as e:
            print(f"Error descargando lista {list_id}: {e}")
            break
    return items

def formatear_para_stremio(item, media_type):
    """
    Convierte un item de TMDB (movie o tv) al formato de Stremio.
    media_type debe ser "movie" o "series" (el mismo que declaramos en config.json).
    """
    # ID: si tiene imdb_id, usarlo; si no, tmdb:...
    imdb = item.get('imdb_id')
    if imdb:
        stremio_id = imdb
    else:
        stremio_id = f"tmdb:{item.get('id')}"

    poster_path = item.get('poster_path')
    MI_WORKER = "http://127.0.0.1:8888"  # Cambia esto si tu worker tiene otra URL
    poster_url = f"{MI_WORKER}/t/p/w500{poster_path}" if poster_path else None

    # Obtener el título según el tipo
    if media_type == "series":
        nombre_base = item.get('name') or item.get('original_name') or ""
    else:
        nombre_base = item.get('title') or item.get('original_title') or ""

    # Aplicar override si existe
    nombre_final = OVERRIDES_TITULOS.get(str(item.get('id')), resolver_titulo(item, media_type))

    return {
        "id": stremio_id,
        "type": media_type,  # "movie" o "series"
        "name": nombre_final,
        "poster": poster_url,
        "description": item.get('overview', 'Sin descripción en español.')
    }

def run():
    print("Iniciando creación de Addons en subcarpetas (API v4)...")

    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    cat_directores_1 = []
    cat_directores_2 = []
    cat_sagas_premios = []
    cat_anos = []

    for categoria, listas in config.items():
        # Determinar carpeta base y lista de catálogo
        if categoria == "DIRECTORES I":
            carpeta_base = "directores_1"
            lista_catalogo = cat_directores_1
        elif categoria == "DIRECTORES II":
            carpeta_base = "directores_2"
            lista_catalogo = cat_directores_2
        elif categoria == "ANOS":
            carpeta_base = "anos"
            lista_catalogo = cat_anos
        else:  # SAGAS, PREMIOS, etc.
            carpeta_base = "sagas_premios"
            lista_catalogo = cat_sagas_premios

        # Recorremos cada lista dentro de la categoría
        for list_id, datos in listas.items():
            nombre_lista = datos["nombre"]
            # Determinar el tipo de contenido (movie o series)
            # Si no tiene campo "tipo", asumimos "movie" (compatibilidad hacia atrás)
            tipo_esperado = datos.get("tipo", "movie")

            # -------- CORRECCIÓN BUG 1 --------
            # La carpeta de destino debe ser 'catalog/movie' o 'catalog/series'
            # según el tipo de la lista, y se crea dentro del bucle.
            stremio_path = os.path.join(carpeta_base, "catalog", tipo_esperado)
            os.makedirs(stremio_path, exist_ok=True)
            # ---------------------------------

            # Descargar items
            raw_items = obtener_items_tmdb(list_id)

            stremio_metas = []
            for item in raw_items:
                # -------- CORRECCIÓN BUG 2 --------
                # Ignoramos el media_type que devuelve TMDB ("tv") y usamos
                # siempre el tipo declarado en config.json ("series").
                media_type = tipo_esperado
                # ---------------------------------

                # Si el item no tiene título, lo saltamos (según el tipo)
                if media_type == "series":
                    if not item.get('name') and not item.get('original_name'):
                        continue
                else:
                    if not item.get('title') and not item.get('original_title'):
                        continue

                stremio_metas.append(formatear_para_stremio(item, media_type))

            print(f"✅ Procesando: {nombre_lista} ({list_id}) - {len(stremio_metas)} items.")

            # cat_id: usamos el ID de la lista para mantener el patrón esperado por el userscript
            cat_id = f"{categoria.replace(' ', '_').lower()}_{list_id}"

            ruta_archivo = os.path.join(stremio_path, f"{cat_id}.json")
            with open(ruta_archivo, 'w', encoding='utf-8') as f:
                json.dump({"metas": stremio_metas}, f, ensure_ascii=False, indent=2)

            # Añadir al catálogo correspondiente (usamos el tipo esperado)
            lista_catalogo.append({
                "type": tipo_esperado,
                "id": cat_id,
                "name": nombre_lista
            })
            time.sleep(0.5)

    def crear_manifest(carpeta, id_sufijo, nombre, catalogos, tipos=None):
        if tipos is None:
            tipos = ["movie"]
        manifest = {
            "id": f"com.anlohe.tmdb.{id_sufijo}",
            "version": "1.0.2",
            "name": nombre,
            "description": f"Colección de {nombre} extraídas de TMDB.",
            "resources": ["catalog"],
            "types": tipos,
            "idPrefixes": ["tt", "tmdb:"],
            "catalogs": catalogos
        }
        ruta_manifest = os.path.join(carpeta, "manifest.json")
        with open(ruta_manifest, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Crear manifests
    crear_manifest("directores_1", "directores1", "Listas personalizadas Directores I", cat_directores_1)
    crear_manifest("directores_2", "directores2", "Listas personalizadas Directores II", cat_directores_2)
    crear_manifest("sagas_premios", "sagaspremios", "Listas personalizadas Sagas y Premios", cat_sagas_premios)
    # Para años, permitimos ambos tipos
    crear_manifest("anos", "anos", "Listas personalizadas por Año", cat_anos, tipos=["movie", "series"])

    print("¡Proceso finalizado! Los 4 Addons están listos.")

if __name__ == "__main__":
    run()
