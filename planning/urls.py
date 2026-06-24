from django.urls import path

from . import views

app_name = "planning"
urlpatterns = [
    path("dienstplan/", views.schedule, name="schedule"),
    path("mitarbeiter/", views.mitarbeiter_liste, name="mitarbeiter_liste"),
    path("mitarbeiter/neu/", views.mitarbeiter_neu, name="mitarbeiter_neu"),
    path("mitarbeiter/<int:pk>/", views.mitarbeiter_detail, name="mitarbeiter_detail"),
    path(
        "mitarbeiter/<int:pk>/bearbeiten/",
        views.mitarbeiter_bearbeiten,
        name="mitarbeiter_bearbeiten",
    ),
]
