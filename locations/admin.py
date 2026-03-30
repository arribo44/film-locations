from django.contrib import admin
from .models import Film, Actor, FilmActor, ShootingLocation


class ShootingLocationInline(admin.TabularInline):
    model = ShootingLocation
    extra = 0
    fields = ('name', 'wikidata_id', 'country', 'latitude', 'longitude')


class FilmActorInline(admin.TabularInline):
    model = FilmActor
    extra = 0
    raw_id_fields = ('actor',)


@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    list_display = ('title', 'wikidata_id', 'release_date', 'created_at')
    search_fields = ('title', 'wikidata_id')
    list_filter = ('release_date',)
    inlines = [FilmActorInline, ShootingLocationInline]


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ('name', 'wikidata_id', 'birth_date')
    search_fields = ('name', 'wikidata_id')


@admin.register(ShootingLocation)
class ShootingLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'film', 'country', 'latitude', 'longitude', 'wikidata_id')
    search_fields = ('name', 'country', 'film__title')
    list_filter = ('country',)
    raw_id_fields = ('film',)


@admin.register(FilmActor)
class FilmActorAdmin(admin.ModelAdmin):
    list_display = ('film', 'actor')
    search_fields = ('film__title', 'actor__name')
    raw_id_fields = ('film', 'actor')
