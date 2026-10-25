import unicodedata

import folium
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min, Q
from django.utils.html import escape
from django.utils.translation import gettext as _, ngettext

from .models import Film, Actor, FilmActor, ShootingLocation
from .forms import FilmSearchForm, ActorSearchForm, LocationSearchForm, AdminImportForm, ActorImportForm
from .wikidata_service import fetch_film_data, fetch_actor_data, fetch_actor_films_in_db


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
        [{'label': _('%(country)s (pays)') % {'country': c}, 'value': c} for c in countries]
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


# Tuiles OpenStreetMap France : libres d'accès, sans clé API.
# Pas les serveurs tile.openstreetmap.org : ils bloquent les requêtes sans en-tête Referer,
# et Firefox n'en envoie jamais depuis une page locale (127.0.0.1 / localhost).
# CartoDB, lui, exige désormais une clé API.
MAP_TILES = 'https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png'
MAP_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, '
    'tiles <a href="https://www.openstreetmap.fr">OpenStreetMap France</a>'
)

MARKER_COLORS = [
    'red', 'blue', 'green', 'purple', 'orange', 'darkred',
    'darkblue', 'darkgreen', 'cadetblue', 'darkpurple',
    'pink', 'lightblue', 'lightgreen', 'gray',
]
# Réservée aux lieux où plusieurs films ont été tournés (carte « Films par lieu »)
SHARED_MARKER_COLOR = 'black'
# Teintes réelles des marqueurs Leaflet.awesome-markers, pour que la légende corresponde
MARKER_CSS_COLORS = {
    'red': '#d63e2a', 'blue': '#38aadd', 'green': '#72b026', 'purple': '#d252b9',
    'orange': '#f69730', 'darkred': '#a23336', 'darkblue': '#0067a3', 'darkgreen': '#728224',
    'cadetblue': '#436978', 'darkpurple': '#5b396b', 'pink': '#ff91ea', 'lightblue': '#8adaff',
    'lightgreen': '#bbf970', 'gray': '#575757', 'black': '#303030',
}


def _non_empty(values):
    """Retire les valeurs vides : un ré-import n'efface jamais une donnée déjà en base."""
    return {k: v for k, v in values.items() if v is not None and v != ''}


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

    fmap = folium.Map(location=center, zoom_start=zoom, tiles=MAP_TILES, attr=MAP_ATTRIBUTION)
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


def _film_colors(films):
    """Une couleur de marqueur par film, dans l'ordre de la liste."""
    return {film.id: MARKER_COLORS[i % len(MARKER_COLORS)] for i, film in enumerate(films)}


def _film_label(film):
    year = f" ({film.release_date.year})" if film.release_date else ""
    return f"{escape(film.title)}{year}"


def _add_film_legend(fmap, films, film_colors):
    """Légende en bas à droite de la carte : une pastille de couleur par film."""
    if not films:
        return
    dot = 'display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;'
    entries = [(film_colors[film.id], _film_label(film)) for film in films]
    items = ''.join(
        f'<div style="margin:3px 0">'
        f'<span style="{dot}background:{MARKER_CSS_COLORS.get(color, "#888")}"></span>{label}'
        f'</div>'
        for color, label in entries
    )
    legend_html = (
        '<div style="position:fixed;bottom:30px;right:10px;z-index:1000;'
        'background:white;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 2px 8px rgba(0,0,0,.25);max-width:280px;'
        'max-height:320px;overflow-y:auto;font-size:13px;">'
        f'<strong style="display:block;margin-bottom:6px">{escape(_("Films"))}</strong>'
        + items +
        '</div>'
    )
    fmap.get_root().html.add_child(folium.Element(legend_html))


def _build_actor_map(films_qs, center=None, zoom=3):
    """Carte acteur — une couleur par film + légende HTML."""
    if center is None:
        center = [20, 0]

    fmap = folium.Map(location=center, zoom_start=zoom, tiles=MAP_TILES, attr=MAP_ATTRIBUTION)
    valid_lats, valid_lons = [], []

    film_colors = _film_colors(films_qs)

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
    _add_film_legend(fmap, list(films_qs), film_colors)

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
                error = _("Le film %(id)s n'est pas encore dans la base de données. Utilisez la page d'import pour l'ajouter.") % {'id': wikidata_id}
        elif query:
            films_qs = Film.objects.filter(title__icontains=query)
            if films_qs.exists():
                film = films_qs.first()
            else:
                error = _("Aucun film trouvé pour « %(query)s ». Importez d'abord le film via la page d'import admin.") % {'query': query}

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
        'page_title': _('Carte des lieux de tournage'),
        'active_page': 'film_map',
        'all_films': Film.objects.annotate(n_locations=Count('locations')).order_by('title'),
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
        # Lien depuis la liste « Acteurs en base » : l'identifiant évite toute ambiguïté de nom
        actor_id = request.GET.get('actor_id', '').strip().upper()

        if actor_id or actor_name:
            if actor_id:
                actors_qs = Actor.objects.filter(wikidata_id=actor_id)
            else:
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
                    error = _("Aucun lieu de tournage trouvé pour %(name)s. Vérifiez que ses films ont été importés avec leurs lieux.") % {'name': actor.name}
            else:
                error = _("Acteur « %(name)s » non trouvé dans la base de données. Importez d'abord ses films via la page d'import admin.") % {'name': actor_name or actor_id}

    context = {
        'form': form,
        'actor': actor,
        'films': films,
        'locations': locations,
        'map_html': map_html,
        'error': error,
        'page_title': _("Carte des tournages d'un acteur"),
        'active_page': 'actor_map',
        'all_actors': Actor.objects.annotate(n_films=Count('actor_films')).order_by('name'),
    }
    return render(request, 'locations/actor_map.html', context)


def _all_locations():
    """Lieux distincts en base (un par identifiant Wikidata) avec leur nombre de films, triés par nom."""
    locations = (
        ShootingLocation.objects
        .values('wikidata_id')
        .annotate(name=Min('name'), country=Max('country'), n_films=Count('film', distinct=True))
    )
    # Tri en Python pour ignorer accents et casse (« Écosse » avec les E, pas après Z)
    return sorted(
        locations,
        key=lambda loc: unicodedata.normalize('NFD', loc['name']).encode('ascii', 'ignore').decode().casefold(),
    )


def location_films_view(request):
    form = LocationSearchForm(request.GET or None)
    films = []
    map_html = None
    error = None

    location_id = ''
    if form.is_valid():
        location_name = form.cleaned_data.get('location_name', '').strip()
        # Lien depuis la liste « Lieux en base » : l'identifiant désigne exactement ce lieu
        location_id = request.GET.get('location_id', '').strip().upper()

        if location_id or location_name:
            if location_id:
                lookup = Q(wikidata_id=location_id)
            else:
                lookup = Q(name__icontains=location_name) | Q(country__icontains=location_name)
            sls = (
                ShootingLocation.objects
                .filter(lookup)
                .select_related('film')
                .order_by('name', 'film__title')
            )

            if sls.exists():
                # Films trouvés, du plus récent au plus ancien (même ordre que la carte d'un acteur)
                films = sorted(
                    {sl.film for sl in sls},
                    key=lambda f: (f.release_date is None, -(f.release_date.toordinal() if f.release_date else 0), f.title),
                )

                # Un marqueur par lieu (dédupliqué par wikidata_id), avec les films qui y ont été tournés
                by_location = {}
                for sl in sls:
                    if sl.latitude is not None:
                        by_location.setdefault(sl.wikidata_id, (sl, []))[1].append(sl.film)

                if by_location:
                    # Seuls les films ayant au moins un lieu à eux seuls reçoivent une couleur ;
                    # les autres n'apparaissent que sur des marqueurs partagés et en prennent la couleur
                    own = {loc_films[0].id for _loc, loc_films in by_location.values() if len(loc_films) == 1}
                    film_colors = _film_colors([f for f in films if f.id in own])
                    film_colors.update({f.id: SHARED_MARKER_COLOR for f in films if f.id not in own})
                    fmap = folium.Map(location=[20, 0], zoom_start=4, tiles=MAP_TILES, attr=MAP_ATTRIBUTION)
                    lats, lons = [], []
                    for loc, loc_films in by_location.values():
                        lats.append(loc.latitude)
                        lons.append(loc.longitude)
                        shared = len(loc_films) > 1
                        popup_html = (
                            f'<div style="min-width:160px">'
                            f'<strong>{escape(loc.name)}</strong><br>'
                            f'{escape(loc.country or "")}'
                            + ''.join(f'<br><em>{_film_label(f)}</em>' for f in loc_films) +
                            f'</div>'
                        )
                        tooltip = (
                            ngettext("%(count)d film", "%(count)d films", len(loc_films)) % {'count': len(loc_films)}
                            if shared else loc_films[0].title
                        )
                        folium.Marker(
                            location=[loc.latitude, loc.longitude],
                            popup=folium.Popup(popup_html, max_width=260),
                            tooltip=f"{loc.name} — {tooltip}",
                            icon=folium.Icon(
                                color=SHARED_MARKER_COLOR if shared else film_colors[loc_films[0].id],
                                icon='film', prefix='fa',
                            ),
                        ).add_to(fmap)
                    _fit_map(fmap, lats, lons)
                    _add_film_legend(
                        fmap, [f for f in films if f.id in own] + [f for f in films if f.id not in own], film_colors,
                    )
                    map_html = fmap._repr_html_()
            else:
                error = _("Aucun lieu de tournage trouvé pour « %(name)s ».") % {'name': location_name or location_id}

    context = {
        'form': form,
        'films': films,
        'map_html': map_html,
        'error': error,
        'page_title': _('Films par lieu de tournage'),
        'active_page': 'location_films',
        'all_locations': _all_locations(),
        'location_id': location_id,
    }
    return render(request, 'locations/location_films.html', context)


@login_required
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
                defaults=_non_empty({
                    'name': data['name'],
                    'birth_date': birth_date,
                    'photo_url': data.get('photo_url', ''),
                })
            )
            imported_actor = actor

            # Croiser avec le casting des films déjà en base
            all_film_ids = list(Film.objects.values_list('wikidata_id', flat=True))
            links_checked = True
            try:
                matched_ids = fetch_actor_films_in_db(wikidata_id, all_film_ids)
            except RuntimeError as e:
                matched_ids, links_checked = set(), False
                messages.warning(request, _(
                    "Les films de « %(name)s » n'ont pas pu être vérifiés (%(error)s). Relancez le ré-import plus tard."
                ) % {'name': actor.name, 'error': e})
            links_created = 0
            for film in Film.objects.filter(wikidata_id__in=matched_ids):
                _link, created = FilmActor.objects.get_or_create(film=film, actor=actor)
                if created:
                    links_created += 1

            import_stats = {
                'actor_created': actor_created,
                'films_linked': links_created,
            }
            if actor_created:
                msg = _("Acteur « %(name)s » importé avec succès !") % {'name': actor.name}
            else:
                msg = _("Acteur « %(name)s » mis à jour avec succès !") % {'name': actor.name}
            if links_created:
                msg += " " + ngettext(
                    "%(count)d film en base lié.",
                    "%(count)d films en base liés.",
                    links_created,
                ) % {'count': links_created}
            elif links_checked and not actor.actor_films.exists():
                msg += " " + _("Aucun film en base ne correspond à sa filmographie.")
            messages.success(request, msg)
            form = ActorImportForm()

        except ValueError as e:
            messages.error(request, str(e))
        except RuntimeError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, _("Erreur inattendue : %(error)s") % {'error': e})

    context = {
        'form': form,
        'imported_actor': imported_actor,
        'import_stats': import_stats,
        'page_title': _("Import acteur Wikidata"),
        'active_page': 'actor_import',
        'section': 'back',
        'recent_actors': Actor.objects.order_by('-updated_at', '-id')[:10],
    }
    return render(request, 'locations/actor_import.html', context)


@login_required
def film_delete_view(request, pk):
    if request.method == 'POST':
        film = Film.objects.filter(pk=pk).first()
        if film:
            title = film.title
            film.delete()
            messages.success(request, _("Film « %(title)s » supprimé.") % {'title': title})
    return redirect('admin_import')


@login_required
def actor_delete_view(request, pk):
    if request.method == 'POST':
        actor = Actor.objects.filter(pk=pk).first()
        if actor:
            name = actor.name
            actor.delete()
            messages.success(request, _("Acteur « %(name)s » supprimé.") % {'name': name})
    return redirect('actor_import')


@login_required
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
                defaults=_non_empty({
                    'title': data['title'],
                    'release_date': release_date,
                    'poster_url': data.get('poster_url', ''),
                })
            )
            imported_film = film

            # Save Locations
            locations_saved = 0
            for loc_data in data.get('locations', []):
                ShootingLocation.objects.update_or_create(
                    wikidata_id=loc_data['wikidata_id'],
                    film=film,
                    defaults=_non_empty({
                        'name': loc_data['name'],
                        'latitude': loc_data.get('latitude'),
                        'longitude': loc_data.get('longitude'),
                        'country': loc_data.get('country', ''),
                    })
                )
                locations_saved += 1

            # Croiser le casting Wikidata avec les acteurs déjà en base
            actors_linked = 0
            cast_ids = data.get('cast_ids', set())
            if cast_ids:
                matching_actors = Actor.objects.filter(wikidata_id__in=cast_ids)
                for actor in matching_actors:
                    _link, created = FilmActor.objects.get_or_create(film=film, actor=actor)
                    if created:
                        actors_linked += 1

            import_stats = {
                'film_created': film_created,
                'locations': locations_saved,
                'actors_linked': actors_linked,
            }

            if film_created:
                msg = _("Film « %(title)s » importé avec succès !") % {'title': film.title}
            else:
                msg = _("Film « %(title)s » mis à jour avec succès !") % {'title': film.title}
            msg += " " + ngettext(
                "%(count)d lieu enregistré.",
                "%(count)d lieux enregistrés.",
                locations_saved,
            ) % {'count': locations_saved}
            if actors_linked:
                msg += " " + ngettext(
                    "%(count)d acteur déjà en base lié automatiquement.",
                    "%(count)d acteurs déjà en base liés automatiquement.",
                    actors_linked,
                ) % {'count': actors_linked}
            messages.success(request, msg)
            form = AdminImportForm()

        except ValueError as e:
            messages.error(request, str(e))
        except RuntimeError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, _("Erreur inattendue lors de l'import : %(error)s") % {'error': e})

    context = {
        'form': form,
        'imported_film': imported_film,
        'import_stats': import_stats,
        'page_title': _("Import de données Wikidata"),
        'active_page': 'admin_import',
        'section': 'back',
        'recent_films': Film.objects.order_by('-updated_at', '-created_at')[:10],
    }
    return render(request, 'locations/admin_import.html', context)
