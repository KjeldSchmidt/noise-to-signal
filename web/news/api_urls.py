from django.urls import path

from news import api

urlpatterns = [
    path("feeds/", api.list_feeds, name="internal_list_feeds"),
    path("feed-items/", api.ingest_feed_items, name="internal_ingest_feed_items"),
    path("articles/", api.upsert_article, name="internal_upsert_article"),
]
