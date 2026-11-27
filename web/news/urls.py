from django.urls import path

from news import views, views_onboarding

urlpatterns = [
    path("", views.landing, name="landing"),
    path("privacy/", views.privacy, name="privacy"),
    path("oauth/popup-done/", views.oauth_popup_done, name="oauth_popup_done"),
    path("onboarding/", views_onboarding.onboarding_entry, name="onboarding"),
    path(
        "onboarding/languages/",
        views_onboarding.onboarding_languages,
        name="onboarding_languages",
    ),
    path(
        "onboarding/places/",
        views_onboarding.onboarding_places,
        name="onboarding_places",
    ),
    path(
        "onboarding/themes/",
        views_onboarding.onboarding_themes,
        name="onboarding_themes",
    ),
    path("brief/", views.brief, name="brief"),
    path("brief/<int:brief_id>/status/", views.brief_status, name="brief_status"),
    path("stories/", views.stories, name="stories"),
    path(
        "stories/threads/<int:thread_id>/",
        views.story_thread,
        name="story_thread",
    ),
    path("settings/", views.settings_page, name="settings"),
    path(
        "settings/preferences/",
        views.stored_preferences,
        name="stored_preferences",
    ),
    path(
        "settings/preferences/memory/delete/",
        views.delete_stored_memory,
        name="delete_stored_memory",
    ),
    path(
        "settings/preferences/theme/delete/",
        views.delete_theme_leaning,
        name="delete_theme_leaning",
    ),
    path("feeds/<int:feed_id>/mute/", views.mute_feed, name="mute_feed"),
    path("feeds/<int:feed_id>/unmute/", views.unmute_feed, name="unmute_feed"),
    path(
        "feeds/<int:feed_id>/unsubscribe/",
        views.unsubscribe_feed,
        name="unsubscribe_feed",
    ),
    path("locations/geocode/reverse/", views.geocode_reverse, name="geocode_reverse"),
    path("locations/geocode/search/", views.geocode_search, name="geocode_search"),
    path(
        "locations/<int:location_id>/delete/",
        views.delete_location,
        name="delete_location",
    ),
    path("articles/<int:article_id>/feedback/", views.feedback, name="feedback"),
    path(
        "articles/<int:article_id>/theme-affinity/",
        views.theme_affinity,
        name="theme_affinity",
    ),
    path("chat/", views.chat, name="chat"),
]
