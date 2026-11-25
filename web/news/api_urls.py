from django.urls import path

from news import api

urlpatterns = [
    path("feeds/", api.list_feeds, name="internal_list_feeds"),
    path("feeds/poll-state/", api.update_feed_poll_state, name="internal_feed_poll_state"),
    path("themes/", api.list_themes, name="internal_list_themes"),
    path("geocode/search/", api.geocode_search, name="internal_geocode_search"),
    path("feed-items/", api.ingest_feed_items, name="internal_ingest_feed_items"),
    path("articles/search/", api.search_articles, name="internal_search_articles"),
    path(
        "articles/embeddings/",
        api.export_article_embeddings,
        name="internal_export_article_embeddings",
    ),
    path("articles/", api.upsert_article, name="internal_upsert_article"),
    path(
        "briefs/users/<int:user_id>/context/",
        api.brief_user_context,
        name="internal_brief_user_context",
    ),
    path("briefs/complete/", api.complete_brief, name="internal_complete_brief"),
    path(
        "story-threads/<int:thread_id>/summary-context/",
        api.story_thread_summary_context,
        name="internal_story_thread_summary_context",
    ),
    path(
        "story-threads/summary/",
        api.update_story_thread_summary,
        name="internal_update_story_thread_summary",
    ),
]
