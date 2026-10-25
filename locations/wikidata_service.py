"""
Service for fetching film and actor data from Wikidata.

Les imports passent par l'API Wikibase (wbgetentities) plutôt que par le point
SPARQL query.wikidata.org, beaucoup plus sujet aux limitations de débit (HTTP 429).
"""
import logging
import time
from urllib.parse import quote

import requests
from SPARQLWrapper import SPARQLWrapper, JSON
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "FilmLocationsApp/1.0 (Django educational project)"
LABEL_LANGUAGES = ("fr", "en")
COMMONS_FILE_URL = "http://commons.wikimedia.org/wiki/Special:FilePath/"
API_BATCH_SIZE = 50  # maximum d'identifiants par appel wbgetentities
MAX_RETRIES = 2  # nouveaux essais après un HTTP 429
MAX_RETRY_WAIT = 30  # secondes d'attente maximum demandées par Retry-After


# --- API Wikibase -----------------------------------------------------------

def _get_entities(ids, props="labels|claims", timeout=30):
    """Récupère des entités Wikidata par lots de 50. Retourne {id: entité}."""
    ids = list(dict.fromkeys(ids))
    entities = {}
    for start in range(0, len(ids), API_BATCH_SIZE):
        params = {
            "action": "wbgetentities",
            "ids": "|".join(ids[start:start + API_BATCH_SIZE]),
            "props": props,
            "languages": "|".join(LABEL_LANGUAGES),
            "format": "json",
        }
        for attempt in range(MAX_RETRIES + 1):
            response = requests.get(API_ENDPOINT, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if response.status_code != 429 or attempt == MAX_RETRIES:
                break
            # Wikidata indique combien de temps attendre ; au-delà du plafond, on abandonne
            wait = int(response.headers.get("Retry-After", "5") or 5)
            if wait > MAX_RETRY_WAIT:
                break
            logger.warning(f"Wikidata rate limit (429), nouvel essai dans {wait}s")
            time.sleep(wait)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("info", payload["error"]))
        entities.update(payload.get("entities", {}))
    return entities


def _get_entity(wikidata_id, props="labels|claims"):
    """Récupère une seule entité ; lève ValueError si elle n'existe pas."""
    try:
        entity = _get_entities([wikidata_id], props=props).get(wikidata_id)
    except Exception as e:
        logger.error(f"Wikidata API call failed for {wikidata_id}: {e}")
        raise RuntimeError(
            _("Impossible de récupérer les données pour %(id)s : %(error)s") % {'id': wikidata_id, 'error': e}
        )
    if not entity or "missing" in entity:
        raise ValueError(_("Aucun résultat trouvé pour %(id)s. Vérifiez l'identifiant Wikidata.") % {'id': wikidata_id})
    return entity


def _label(entity):
    """Libellé en français, à défaut en anglais."""
    labels = entity.get("labels", {})
    for lang in LABEL_LANGUAGES:
        if lang in labels:
            return labels[lang]["value"]
    return None


def _truthy_values(entity, prop):
    """
    Valeurs « vraies » d'une propriété, comme wdt: en SPARQL :
    rang préféré s'il existe, sinon rang normal ; jamais le rang déprécié.
    """
    statements = [
        s for s in entity.get("claims", {}).get(prop, [])
        if s.get("rank") != "deprecated" and s["mainsnak"].get("snaktype") == "value"
    ]
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    return [s["mainsnak"]["datavalue"]["value"] for s in (preferred or statements)]


def _entity_ids(entity, prop):
    return [value["id"] for value in _truthy_values(entity, prop)]


def _earliest_date(entity, prop):
    """Date la plus ancienne au format YYYY-MM-DD ; mois ou jour inconnus deviennent 01, comme en SPARQL."""
    dates = [
        value["time"].lstrip("+")[:10].replace("-00", "-01")  # ex. "+1975-06-00T00:00:00Z"
        for value in _truthy_values(entity, prop)
    ]
    return min(dates) if dates else None


def _commons_url(entity, *props):
    """URL Commons du premier fichier trouvé (même format que l'ancien import SPARQL)."""
    for prop in props:
        files = _truthy_values(entity, prop)
        if files:
            return COMMONS_FILE_URL + quote(files[0], safe="")
    return ""


# --- Films ------------------------------------------------------------------

def fetch_film_data(wikidata_id):
    """
    Fetch film data from Wikidata: title, release date, poster and
    filming locations (with coordinates and country).

    Returns a dict with keys:
        - title (str)
        - release_date (str or None, ISO format YYYY-MM-DD)
        - poster_url (str)
        - locations (list of dicts: wikidata_id, name, latitude, longitude, country)
        - cast_ids (set of actor wikidata_ids, P161)
    """
    film = _get_entity(wikidata_id)

    film_title = _label(film)
    if film_title is None:
        raise ValueError(
            _("Titre non trouvé pour %(id)s. Cet identifiant n'est peut-être pas un film.") % {'id': wikidata_id}
        )

    # Lieux de tournage (P915), puis leurs pays (P17) : deux appels groupés au plus
    location_ids = _entity_ids(film, "P915")
    try:
        location_entities = _get_entities(location_ids) if location_ids else {}
        country_ids = {
            ids[0]
            for entity in location_entities.values()
            if (ids := _entity_ids(entity, "P17"))
        }
        country_entities = _get_entities(country_ids, props="labels") if country_ids else {}
    except Exception as e:
        logger.error(f"Wikidata API call failed for locations of {wikidata_id}: {e}")
        raise RuntimeError(
            _("Impossible de récupérer les données pour %(id)s : %(error)s") % {'id': wikidata_id, 'error': e}
        )

    locations = []
    for loc_id in location_ids:
        entity = location_entities.get(loc_id, {})
        coords = _truthy_values(entity, "P625")
        countries = _entity_ids(entity, "P17")
        if countries:
            country = _label(country_entities.get(countries[0], {})) or ""
        elif _truthy_values(entity, "P297"):
            # Le lieu est lui-même un pays (code ISO 3166-1) : il n'a pas de P17
            country = _label(entity) or ""
        else:
            country = ""
        locations.append({
            "wikidata_id": loc_id,
            "name": _label(entity) or loc_id,
            "latitude": coords[0]["latitude"] if coords else None,
            "longitude": coords[0]["longitude"] if coords else None,
            "country": country,
        })

    with_coords = sum(1 for l in locations if l["latitude"] is not None)
    logger.info(f"{wikidata_id}: {len(locations)} lieu(x) dont {with_coords} avec coordonnées GPS")

    return {
        "title": film_title,
        "release_date": _earliest_date(film, "P577"),
        "poster_url": _commons_url(film, "P18", "P154"),
        "locations": locations,
        "cast_ids": set(_entity_ids(film, "P161")),
    }


# --- Acteurs ----------------------------------------------------------------

def fetch_actor_data(wikidata_id):
    """
    Fetch actor metadata only: name, birth date, photo.
    La correspondance avec les films se fait séparément via fetch_actor_films_in_db().

    Returns a dict: name, birth_date, photo_url.
    """
    actor = _get_entity(wikidata_id)

    actor_name = _label(actor)
    if actor_name is None:
        raise ValueError(_("Acteur non trouvé pour %(id)s.") % {'id': wikidata_id})

    logger.info(f"{wikidata_id}: acteur '{actor_name}'")
    return {
        "name": actor_name,
        "birth_date": _earliest_date(actor, "P569"),
        "photo_url": _commons_url(actor, "P18"),
    }


def fetch_actor_films_in_db(actor_wikidata_id, film_wikidata_ids):
    """
    Parmi une liste de film_wikidata_ids (déjà en base), retourne ceux
    où l'acteur apparaît dans le casting Wikidata (P161).
    On lit le casting des films connus plutôt que la filmographie de l'acteur :
    le coût dépend du nombre de films en base, pas de sa carrière.
    """
    if not film_wikidata_ids:
        return set()

    try:
        films = _get_entities(film_wikidata_ids, props="claims")
    except Exception as e:
        logger.warning(f"fetch_actor_films_in_db failed for {actor_wikidata_id}: {e}")
        raise RuntimeError(str(e))

    matched = {
        film_id for film_id, entity in films.items()
        if actor_wikidata_id in _entity_ids(entity, "P161")
    }
    logger.info(
        f"{actor_wikidata_id}: {len(matched)}/{len(film_wikidata_ids)} "
        "film(s) en base avec cet acteur"
    )
    return matched


# --- Recherche (SPARQL) -------------------------------------------------------

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
