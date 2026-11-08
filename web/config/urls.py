from django.contrib import admin
from django.urls import include, path

from config.views import health

urlpatterns = [
    path("health", health, name="health"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/internal/", include("news.api_urls")),
    path("", include("news.urls")),
]
