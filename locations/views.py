import folium
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q

from .models import Film, Actor, FilmActor, ShootingLocation
from .forms import FilmSearchForm, ActorSearchForm, LocationSearchForm, AdminImportForm, ActorImportForm
from .wikidata_service import fetch_film_data, fetch_actor_data, fetch_film_cast_ids, fetch_actor_films_in_db


def location_autocomplete(request):
    q = request.GET.get('q', '').strip()
    from django.http import JsonResponse
    if len(q) < 2:
        return JsonResponse([], safe=False)

    names = (
        ShootingLocation.objects
        .filter(name__icontains=q)
        .values_list('name', flat=True)
        .distinct().order_by('name')[:8]
    )
    countries = (
        ShootingLocation.objects
        .filter(country__icontains=q)
        .exclude(country='')
        .values_list('country', flat=True)
        .distinct().order_by('country')[:5]
    )
    results = (
        [{'label': n, 'value': n} for n in names] +
        [{'label': f'{c} (pays)', 'value': c} for c in countries]
    )
    return JsonResponse(results, safe=False)


def actor_autocomplete(request):
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        actors = Actor.objects.filter(name__icontains=q).order_by('name')[:10]
        results = [{'name': a.name} for a in actors]
    from django.http import JsonResponse
    return JsonResponse(results, safe=False)


def film_autocomplete(request):
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        films = Film.objects.filter(title__icontains=q).order_by('title')[:10]
        results = [{'title': f.title, 'wikidata_id': f.wikidata_id} for f in films]
    from django.http import JsonResponse
    return JsonResponse(results, safe=False)


def home_view(request):
    return redirect('film_map')


MARKER_COLORS = [
    'red', 'blue', 'green', 'purple', 'orange', 'darkred',
    'darkblue', 'darkgreen', 'cadetblue', 'darkpurple',
    'pink', 'lightblue', 'lightgreen', 'gray', 'black',
]


def _fit_map(fmap, valid_lats, valid_lons):
    if not valid_lats:
        return
    fmap.location = [sum(valid_lats) / len(valid_lats), sum(valid_lons) / len(valid_lons)]
    if len(valid_lats) > 1:
        fmap.fit_bounds([
            [min(valid_lats), min(valid_lons)],
            [max(valid_lats), max(valid_lons)],
        ])


def _build_map(locations_qs, center=None, zoom=4):
    """Carte simple (film unique) — tous les marqueurs en rouge."""
    if center is None:
        center = [20, 0]

    fmap = folium.Map(location=center, zoom_start=zoom, tiles='CartoDB positron')
    valid_lats, valid_lons = [], []

    for loc in locations_qs:
        if loc.latitude is None or loc.longitude is None:
            continue
        valid_lats.append(loc.latitude)
        valid_lons.append(loc.longitude)
        popup_html = (
            f'<div style="min-width:150px">'
            f'<strong>{loc.name}</strong><br>'
            f'<em>{loc.film.title}</em><br>'
            f'{loc.country or ""}'
            f'</div>'
        )
        folium.Marker(
            location=[loc.latitude, loc.longitude],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{loc.name} — {loc.film.title}",
            icon=folium.Icon(color='red', icon='film', prefix='fa'),
        ).add_to(fmap)

    _fit_map(fmap, valid_lats, valid_lons)
    return fmap


def _build_actor_map(films_qs, center=None, zoom=3):
    """Carte acteur — une couleur par film + légende HTML."""
    if center is None:
        center = [20, 0]

    fmap = folium.Map(location=center, zoom_start=zoom, tiles='CartoDB positron')
    valid_lats, valid_lons = [], []

    # Attribuer une couleur à chaque film
    film_colors = {
        film.id: MARKER_COLORS[i % len(MARKER_COLORS)]
        for i, film in enumerate(films_qs)
    }

    for film in films_qs:
        color = film_colors[film.id]
        for loc in film.locations.all():
            if loc.latitude is None or loc.longitude is None:
                continue
            valid_lats.append(loc.latitude)
            valid_lons.append(loc.longitude)
            popup_html = (
                f'<div style="min-width:160px">'
                f'<strong>{loc.name}</strong><br>'
                f'<span style="color:#555"><em>{film.title}</em></span><br>'
                f'{loc.country or ""}'
                f'</div>'
            )
            folium.Marker(
                location=[loc.latitude, loc.longitude],
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f"{loc.name} — {film.title}",
                icon=folium.Icon(color=color, icon='film', prefix='fa'),
            ).add_to(fmap)

    _fit_map(fmap, valid_lats, valid_lons)

    # Légende
    if film_colors:
        dot = (
            'display:inline-block;width:12px;height:12px;'
            'border-radius:50%;margin-right:6px;'
        )
        items = []
        for film in films_qs:
            color = film_colors[film.id]
            # Correspondance couleur Folium → couleur CSS
            css_colors = {
                'red': '#d63031', 'blue': '#0984e3', 'green': '#00b894',
                'purple': '#6c5ce7', 'orange': '#e17055', 'darkred': '#922b21',
                'darkblue': '#1a5276', 'darkgreen': '#1e8449', 'cadetblue': '#5dade2',
                'darkpurple': '#7d3c98', 'pink': '#fd79a8', 'lightblue': '#74b9ff',
                'lightgreen': '#55efc4', 'gray': '#636e72', 'black': '#2d3436',
            }
            css = css_colors.get(color, '#888')
            year = f" ({film.release_date.year})" if film.release_date else ""
            items.append(
                f'<div style="margin:3px 0">'
                f'<span style="{dot}background:{css}"></span>'
                f'{film.title}{year}'
                f'</div>'
            )
        legend_html = (
            '<div style="position:fixed;bottom:30px;right:10px;z-index:1000;'
            'background:white;padding:12px 16px;border-radius:8px;'
            'box-shadow:0 2px 8px rgba(0,0,0,.25);max-width:280px;'
            'max-height:320px;overflow-y:auto;font-size:13px;">'
            '<strong style="display:block;margin-bottom:6px">Films</strong>'
            + ''.join(items) +
            '</div>'
        )
        fmap.get_root().html.add_child(folium.Element(legend_html))

    return fmap


def film_map_view(request):
    form = FilmSearchForm(request.GET or None)
    film = None
    map_html = None
    locations = []
    error = None

    if form.is_valid():
        wikidata_id = form.cleaned_data.get('wikidata_id', '').strip().upper()
        query = form.cleaned_data.get('query', '').strip()

        if wikidata_id:
            try:
                film = Film.objects.get(wikidata_id=wikidata_id)
            except Film.DoesNotExist:
                error = f"Le film {wikidata_id} n'est pas encore dans la base de données. Utilisez la page d'import pour l'ajouter."
        elif query:
            films_qs = Film.objects.filter(title__icontains=query)
            if films_qs.exists():
                film = films_qs.first()
            else:
                error = f"Aucun film trouvé pour '{query}'. Importez d'abord le film via la page d'import admin."

        if film:
            locations = film.locations.all()
            fmap = _build_map(locations)
            map_html = fmap._repr_html_()

    context = {
        'form': form,
        'film': film,
        'locations': locations,
        'map_html': map_html,
        'error': error,
        'page_title': 'Carte des lieux de tournage',
        'active_page': 'film_map',
    }
    return render(request, 'locations/film_map.html', context)


def actor_map_view(request):
    form = ActorSearchForm(request.GET or None)
    actor = None
    map_html = None
    locations = []
    films = []
    error = None

    if form.is_valid():
        actor_name = form.cleaned_data.get('actor_name', '').strip()

        if actor_name:
            actors_qs = Actor.objects.filter(name__icontains=actor_name)
            if actors_qs.exists():
                actor = actors_qs.first()
                film_ids = FilmActor.objects.filter(actor=actor).values_list('film_id', flat=True)
                films = Film.objects.filter(id__in=film_ids)
                locations = ShootingLocation.objects.filter(film__in=films).select_related('film')

                films_with_locs = films.filter(locations__latitude__isnull=False).distinct()
                if films_with_locs.exists():
                    fmap = _build_actor_map(films_with_locs)
                    map_html = fmap._repr_html_()
                else:
                    error = f"Aucun lieu de tournage trouvé pour {actor.name}. Vérifiez que ses films ont été importés avec leurs lieux."
            else:
                error = f"Acteur '{actor_name}' non trouvé dans la base de données. Importez d'abord ses films via la page d'import admin."

    context = {
        'form': form,
        'actor': actor,
        'films': films,
        'locations': locations,
        'map_html': map_html,
        'error': error,
        'page_title': "Carte des tournages d'un acteur",
        'active_page': 'actor_map',
    }
    return render(request, 'locations/actor_map.html', context)


def location_films_view(request):
    form = LocationSearchForm(request.GET or None)
    rows = []       # list of (shooting_location, film) for the table
    map_html = None
    error = None

    if form.is_valid():
        location_name = form.cleaned_data.get('location_name', '').strip()

        if location_name:
            sls = (
                ShootingLocation.objects
                .filter(
                    Q(name__icontains=location_name) |
                    Q(country__icontains=location_name)
                )
                .select_related('film')
                .order_by('name', 'film__title')
            )

            if sls.exists():
                rows = [(sl, sl.film) for sl in sls]

                # Carte : un marqueur par lieu (dédupliqué par wikidata_id)
                seen = set()
                map_locs = []
                for sl in sls:
                    if sl.wikidata_id not in seen and sl.latitude is not None:
                        seen.add(sl.wikidata_id)
                        map_locs.append(sl)

                if map_locs:
                    fmap = folium.Map(location=[20, 0], zoom_start=4, tiles='CartoDB positron')
                    lats, lons = [], []
                    for loc in map_locs:
                        lats.append(loc.latitude)
                        lons.append(loc.longitude)
                        popup_html = (
                            f'<div style="min-width:150px">'
                            f'<strong>{loc.name}</strong><br>'
                            f'{loc.country or ""}'
                            f'</div>'
                        )
                        folium.Marker(
                            location=[loc.latitude, loc.longitude],
                            popup=folium.Popup(popup_html, max_width=220),
                            tooltip=loc.name,
                            icon=folium.Icon(color='green', icon='map-marker', prefix='fa'),
                        ).add_to(fmap)
                    _fit_map(fmap, lats, lons)
                    map_html = fmap._repr_html_()
            else:
                error = f"Aucun lieu de tournage trouvé pour '{location_name}'."

    context = {
        'form': form,
        'rows': rows,
        'map_html': map_html,
        'error': error,
        'page_title': 'Films par lieu de tournage',
        'active_page': 'location_films',
    }
    return render(request, 'locations/location_films.html', context)


def actor_import_view(request):
    form = ActorImportForm(request.POST or None)
    imported_actor = None
    import_stats = {}

    if request.method == 'POST' and form.is_valid():
        wikidata_id = form.cleaned_data['wikidata_id']
        try:
            data = fetch_actor_data(wikidata_id)

            birth_date = None
            if data.get('birth_date'):
                try:
                    from datetime import date
                    parts = data['birth_date'].split('-')
                    if len(parts) == 3:
                        birth_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    elif len(parts) == 1:
                        birth_date = date(int(parts[0]), 1, 1)
                except (ValueError, IndexError):
                    pass

            actor, actor_created = Actor.objects.update_or_create(
                wikidata_id=wikidata_id,
                defaults={
                    'name': data['name'],
                    'birth_date': birth_date,
                    'photo_url': data.get('photo_url', ''),
                }
            )
            imported_actor = actor

            # Croiser avec les films en base via VALUES (requête ciblée)
            all_film_ids = list(Film.objects.values_list('wikidata_id', flat=True))
            matched_ids = fetch_actor_films_in_db(wikidata_id, all_film_ids)
            links_created = 0
            for film in Film.objects.filter(wikidata_id__in=matched_ids):
                _, created = FilmActor.objects.get_or_create(film=film, actor=actor)
                if created:
                    links_created += 1

            import_stats = {
                'actor_created': actor_created,
                'films_linked': links_created,
            }
            action = "importé" if actor_created else "mis à jour"
            msg = f"Acteur '{actor.name}' {action} avec succès !"
            if links_created:
                msg += f" {links_created} film(s) en base liés."
            else:
                msg += " Aucun film en base ne correspond à sa filmographie."
            messages.success(request, msg)
            form = ActorImportForm()

        except ValueError as e:
            messages.error(request, str(e))
        except RuntimeError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur inattendue : {e}")

    context = {
        'form': form,
        'imported_actor': imported_actor,
        'import_stats': import_stats,
        'page_title': "Import acteur Wikidata",
        'active_page': 'actor_import',
        'recent_actors': Actor.objects.order_by('-id')[:10],
    }
    return render(request, 'locations/actor_import.html', context)


def film_delete_view(request, pk):
    if request.method == 'POST':
        film = Film.objects.filter(pk=pk).first()
        if film:
            title = film.title
            film.delete()
            messages.success(request, f"Film '{title}' supprimé.")
    return redirect('admin_import')


def actor_delete_view(request, pk):
    if request.method == 'POST':
        actor = Actor.objects.filter(pk=pk).first()
        if actor:
            name = actor.name
            actor.delete()
            messages.success(request, f"Acteur '{name}' supprimé.")
    return redirect('actor_import')


def admin_import_view(request):
    form = AdminImportForm(request.POST or None)
    imported_film = None
    import_stats = {}

    if request.method == 'POST' and form.is_valid():
        wikidata_id = form.cleaned_data['wikidata_id']

        try:
            data = fetch_film_data(wikidata_id)

            # Parse release date
            release_date = None
            if data.get('release_date'):
                try:
                    from datetime import date
                    parts = data['release_date'].split('-')
                    if len(parts) == 3:
                        release_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    elif len(parts) == 1:
                        release_date = date(int(parts[0]), 1, 1)
                except (ValueError, IndexError):
                    pass

            # Save or update Film
            film, film_created = Film.objects.update_or_create(
                wikidata_id=wikidata_id,
                defaults={
                    'title': data['title'],
                    'release_date': release_date,
                    'poster_url': data.get('poster_url', ''),
                }
            )
            imported_film = film

            # Save Locations
            locations_saved = 0
            for loc_data in data.get('locations', []):
                ShootingLocation.objects.update_or_create(
                    wikidata_id=loc_data['wikidata_id'],
                    film=film,
                    defaults={
                        'name': loc_data['name'],
                        'latitude': loc_data.get('latitude'),
                        'longitude': loc_data.get('longitude'),
                        'country': loc_data.get('country', ''),
                    }
                )
                locations_saved += 1

            # Croiser le casting Wikidata avec les acteurs déjà en base
            actors_linked = 0
            cast_ids = fetch_film_cast_ids(wikidata_id)
            if cast_ids:
                matching_actors = Actor.objects.filter(wikidata_id__in=cast_ids)
                for actor in matching_actors:
                    _, created = FilmActor.objects.get_or_create(film=film, actor=actor)
                    if created:
                        actors_linked += 1

            import_stats = {
                'film_created': film_created,
                'locations': locations_saved,
                'actors_linked': actors_linked,
            }

            action = "importé" if film_created else "mis à jour"
            msg = f"Film '{film.title}' {action} avec succès ! {locations_saved} lieu(x) enregistré(s)."
            if actors_linked:
                msg += f" {actors_linked} acteur(s) déjà en base liés automatiquement."
            messages.success(request, msg)
            form = AdminImportForm()

        except ValueError as e:
            messages.error(request, str(e))
        except RuntimeError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erreur inattendue lors de l'import: {e}")

    context = {
        'form': form,
        'imported_film': imported_film,
        'import_stats': import_stats,
        'page_title': "Import de données Wikidata",
        'active_page': 'admin_import',
        'recent_films': Film.objects.order_by('-created_at')[:10],
    }
    return render(request, 'locations/admin_import.html', context)
