from django.urls import path

from news import api

urlpatterns = [
    path("feeds/", api.list_feeds, name="internal_list_feeds"),
    path("themes/", api.list_themes, name="internal_list_themes"),
    path("geocode/search/", api.geocode_search, name="internal_geocode_search"),
    path("feed-items/", api.ingest_feed_items, name="internal_ingest_feed_items"),
    path("articles/", api.upsert_article, name="internal_upsert_article"),
]
