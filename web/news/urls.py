from django.urls import path

from news import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("oauth/popup-done/", views.oauth_popup_done, name="oauth_popup_done"),
    path("brief/", views.brief, name="brief"),
    path("stories/", views.stories, name="stories"),
    path("settings/", views.settings_page, name="settings"),
    path("feeds/<int:feed_id>/mute/", views.mute_feed, name="mute_feed"),
    path("feeds/<int:feed_id>/unmute/", views.unmute_feed, name="unmute_feed"),
    path("locations/geocode/reverse/", views.geocode_reverse, name="geocode_reverse"),
    path("locations/geocode/search/", views.geocode_search, name="geocode_search"),
    path(
        "locations/<int:location_id>/delete/",
        views.delete_location,
        name="delete_location",
    ),
    path("articles/<int:article_id>/feedback/", views.feedback, name="feedback"),
    path("followups/", views.followups, name="followups"),
    path(
        "followups/<int:question_id>/answer/",
        views.answer_followup,
        name="answer_followup",
    ),
]
