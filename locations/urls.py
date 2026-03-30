from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('film-map/', views.film_map_view, name='film_map'),
    path('actor-map/', views.actor_map_view, name='actor_map'),
    path('location-films/', views.location_films_view, name='location_films'),
    path('admin-import/', views.admin_import_view, name='admin_import'),
    path('actor-import/', views.actor_import_view, name='actor_import'),
    path('film-delete/<int:pk>/', views.film_delete_view, name='film_delete'),
    path('actor-delete/<int:pk>/', views.actor_delete_view, name='actor_delete'),
    path('film-autocomplete/', views.film_autocomplete, name='film_autocomplete'),
    path('actor-autocomplete/', views.actor_autocomplete, name='actor_autocomplete'),
    path('location-autocomplete/', views.location_autocomplete, name='location_autocomplete'),
]
