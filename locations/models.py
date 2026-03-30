from django.db import models


class Film(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=500)
    release_date = models.DateField(null=True, blank=True)
    poster_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Film'
        verbose_name_plural = 'Films'
        ordering = ['-release_date']


class Actor(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=300)
    birth_date = models.DateField(null=True, blank=True)
    photo_url = models.URLField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Acteur'
        verbose_name_plural = 'Acteurs'
        ordering = ['name']


class FilmActor(models.Model):
    film = models.ForeignKey(Film, on_delete=models.CASCADE, related_name='film_actors')
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE, related_name='actor_films')

    def __str__(self):
        return f"{self.actor.name} dans {self.film.title}"

    class Meta:
        unique_together = ('film', 'actor')
        verbose_name = 'Film-Acteur'
        verbose_name_plural = 'Films-Acteurs'


class ShootingLocation(models.Model):
    wikidata_id = models.CharField(max_length=20)
    name = models.CharField(max_length=500)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    country = models.CharField(max_length=200, blank=True)
    film = models.ForeignKey(Film, on_delete=models.CASCADE, related_name='locations')

    def __str__(self):
        return f"{self.name} ({self.film.title})"

    class Meta:
        unique_together = ('wikidata_id', 'film')
        verbose_name = 'Lieu de tournage'
        verbose_name_plural = 'Lieux de tournage'
