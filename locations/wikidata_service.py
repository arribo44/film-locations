"""
Service for querying Wikidata via SPARQL to fetch film and actor data.
"""
import logging
from SPARQLWrapper import SPARQLWrapper, JSON

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "FilmLocationsApp/1.0 (Django educational project)"


def get_sparql_wrapper():
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)
    sparql.setReturnFormat(JSON)
    return sparql


def _run_query(query, timeout=30):
    sparql = get_sparql_wrapper()
    sparql.setTimeout(timeout)
    sparql.setQuery(query)
    return sparql.query().convert().get("results", {}).get("bindings", [])


def fetch_film_data(wikidata_id):
    """
    Fetch film data from Wikidata including title, release date,
    filming locations (with coordinates), and cast members.

    Returns a dict with keys:
        - title (str)
        - release_date (str or None, ISO format YYYY-MM-DD)
        - poster_url (str)
        - locations (list of dicts: wikidata_id, name, latitude, longitude, country)
        - actors (list of dicts: wikidata_id, name, birth_date, photo_url)
    """
    # --- Query 1 : film metadata + filming locations with coordinates ---
    query_locations = f"""
    SELECT DISTINCT
      ?filmLabel
      ?releaseDate
      ?posterUrl
      ?logoUrl
      ?location
      ?locationLabel
      ?lat
      ?lon
      ?countryLabel
    WHERE {{
      BIND(wd:{wikidata_id} AS ?film)

      OPTIONAL {{ ?film wdt:P577 ?releaseDate . }}
      OPTIONAL {{ ?film wdt:P18 ?posterUrl . }}
      OPTIONAL {{ ?film wdt:P154 ?logoUrl . }}

      OPTIONAL {{
        ?film wdt:P915 ?location .
        OPTIONAL {{
          ?location p:P625 ?coordStmt .
          ?coordStmt psv:P625 ?coordNode .
          ?coordNode wikibase:geoLatitude ?lat .
          ?coordNode wikibase:geoLongitude ?lon .
        }}
        OPTIONAL {{ ?location wdt:P17 ?country . }}
      }}

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
    }}
    LIMIT 300
    """

    try:
        loc_bindings = _run_query(query_locations)
    except Exception as e:
        logger.error(f"SPARQL query failed for {wikidata_id}: {e}")
        raise RuntimeError(f"Impossible de récupérer les données pour {wikidata_id}: {e}")

    if not loc_bindings:
        raise ValueError(
            f"Aucun résultat trouvé pour {wikidata_id}. "
            "Vérifiez l'identifiant Wikidata."
        )

    return _parse_results(wikidata_id, loc_bindings)


def _parse_results(wikidata_id, loc_bindings):
    film_title = None
    release_date = None
    poster_url = ""
    locations = {}

    for row in loc_bindings:
        if film_title is None and "filmLabel" in row:
            film_title = row["filmLabel"]["value"]

        if "releaseDate" in row:
            date_str = row["releaseDate"]["value"][:10]
            if release_date is None or date_str < release_date:
                release_date = date_str

        if not poster_url and "posterUrl" in row:
            poster_url = row["posterUrl"]["value"]
        if not poster_url and "logoUrl" in row:
            poster_url = row["logoUrl"]["value"]

        if "location" in row:
            loc_id = row["location"]["value"].split("/")[-1]
            if loc_id not in locations:
                locations[loc_id] = {
                    "wikidata_id": loc_id,
                    "name": row.get("locationLabel", {}).get("value", loc_id),
                    "latitude": None,
                    "longitude": None,
                    "country": row.get("countryLabel", {}).get("value", ""),
                }
            loc = locations[loc_id]
            if loc["latitude"] is None and "lat" in row:
                try:
                    loc["latitude"] = float(row["lat"]["value"])
                    loc["longitude"] = float(row["lon"]["value"])
                except (ValueError, KeyError):
                    pass

    if film_title is None:
        raise ValueError(
            f"Titre non trouvé pour {wikidata_id}. "
            "Cet identifiant n'est peut-être pas un film."
        )

    loc_list = list(locations.values())
    with_coords = sum(1 for l in loc_list if l["latitude"] is not None)
    logger.info(f"{wikidata_id}: {len(loc_list)} lieu(x) dont {with_coords} avec coordonnées GPS")

    return {
        "title": film_title,
        "release_date": release_date,
        "poster_url": poster_url,
        "locations": loc_list,
    }


def fetch_film_cast_ids(wikidata_id):
    """
    Retourne l'ensemble des wikidata_id des acteurs du film.
    Requête légère : uniquement les identifiants, pas les labels.
    """
    query = f"""
    SELECT DISTINCT ?actor WHERE {{
      BIND(wd:{wikidata_id} AS ?film)
      ?film wdt:P161 ?actor .
    }}
    """
    try:
        bindings = _run_query(query)
        return {row["actor"]["value"].split("/")[-1] for row in bindings}
    except Exception as e:
        logger.error(f"fetch_film_cast_ids failed for {wikidata_id}: {e}")
        return set()


def fetch_actor_data(wikidata_id):
    """
    Fetch actor metadata only: name, birth date, photo.
    La correspondance avec les films se fait séparément via fetch_actor_films_in_db().

    Returns a dict: name, birth_date, photo_url.
    """
    query = f"""
    SELECT DISTINCT ?actorLabel ?birthDate ?photoUrl WHERE {{
      BIND(wd:{wikidata_id} AS ?actor)
      OPTIONAL {{ ?actor wdt:P569 ?birthDate . }}
      OPTIONAL {{ ?actor wdt:P18 ?photoUrl . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
    }}
    LIMIT 5
    """
    try:
        bindings = _run_query(query, timeout=15)
    except Exception as e:
        logger.error(f"Actor meta query failed for {wikidata_id}: {e}")
        raise RuntimeError(f"Impossible de récupérer les données pour {wikidata_id}: {e}")

    if not bindings:
        raise ValueError(f"Aucun résultat trouvé pour {wikidata_id}. Vérifiez l'identifiant Wikidata.")

    actor_name = None
    birth_date = None
    photo_url = ""
    for row in bindings:
        if actor_name is None and "actorLabel" in row:
            actor_name = row["actorLabel"]["value"]
        if birth_date is None and "birthDate" in row:
            birth_date = row["birthDate"]["value"][:10]
        if not photo_url and "photoUrl" in row:
            photo_url = row["photoUrl"]["value"]

    if actor_name is None:
        raise ValueError(f"Acteur non trouvé pour {wikidata_id}.")

    logger.info(f"{wikidata_id}: acteur '{actor_name}'")
    return {"name": actor_name, "birth_date": birth_date, "photo_url": photo_url}


def fetch_actor_films_in_db(actor_wikidata_id, film_wikidata_ids):
    """
    Parmi une liste de film_wikidata_ids (déjà en base), retourne ceux
    où l'acteur apparaît dans le casting Wikidata.
    Utilise VALUES pour limiter la recherche aux films connus — toujours rapide
    quelle que soit la filmographie totale de l'acteur.
    """
    if not film_wikidata_ids:
        return set()

    values = " ".join(f"wd:{fid}" for fid in film_wikidata_ids)
    query = f"""
    SELECT DISTINCT ?film WHERE {{
      VALUES ?film {{ {values} }}
      ?film wdt:P161 wd:{actor_wikidata_id} .
    }}
    """
    try:
        bindings = _run_query(query, timeout=30)
        matched = {row["film"]["value"].split("/")[-1] for row in bindings}
        logger.info(
            f"{actor_wikidata_id}: {len(matched)}/{len(film_wikidata_ids)} "
            "film(s) en base avec cet acteur"
        )
        return matched
    except Exception as e:
        logger.warning(f"fetch_actor_films_in_db failed for {actor_wikidata_id}: {e}")
        return set()


def search_actor_on_wikidata(actor_name):
    """Search for an actor on Wikidata by name."""
    query = f"""
    SELECT DISTINCT ?actor ?actorLabel WHERE {{
      ?actor wdt:P31 wd:Q5 ;
             wdt:P106 ?occupation .
      VALUES ?occupation {{ wd:Q33999 wd:Q10800557 wd:Q2526255 }}
      ?actor rdfs:label ?label .
      FILTER(LANG(?label) IN ("fr", "en"))
      FILTER(CONTAINS(LCASE(?label), LCASE("{actor_name}")))
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
    }}
    LIMIT 10
    """
    try:
        bindings = _run_query(query)
        return [
            {
                "wikidata_id": row["actor"]["value"].split("/")[-1],
                "name": row.get("actorLabel", {}).get("value", ""),
            }
            for row in bindings
        ]
    except Exception as e:
        logger.error(f"Actor search failed for '{actor_name}': {e}")
        return []
