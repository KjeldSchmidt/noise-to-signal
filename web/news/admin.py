from django.contrib import admin

from news.admin_ops import patch_admin_urls
from news.models import (
    Article,
    Feed,
    FeedMute,
    FollowUpAnswer,
    FollowUpQuestion,
    LocationOfInterest,
    RelevanceFeedback,
    StoryThread,
    Subscription,
    Theme,
)

patch_admin_urls()


@admin.register(Feed)
class FeedAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "kind", "is_active", "owner")
    list_filter = ("kind", "category", "is_active")
    search_fields = ("title", "url", "description")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "feed", "created_at")
    list_filter = ("feed",)


@admin.register(FeedMute)
class FeedMuteAdmin(admin.ModelAdmin):
    list_display = ("user", "feed", "created_at")
    list_filter = ("feed",)


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("slug", "label", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "label")
    prepopulated_fields = {"slug": ("label",)}


@admin.register(LocationOfInterest)
class LocationOfInterestAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "user",
        "geo_level",
        "country_code",
        "admin1",
        "locality",
        "latitude",
        "longitude",
        "created_at",
    )
    list_filter = ("geo_level", "country_code")
    search_fields = ("label", "admin1", "locality")


@admin.register(StoryThread)
class StoryThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "last_published_at", "updated_at")
    search_fields = ("label",)
    change_list_template = "admin/news/storythread_change_list.html"


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "feed",
        "published_at",
        "geo_level",
        "place_label",
        "story_thread",
        "embedding_model",
    )
    list_filter = ("feed", "geo_level", "embedding_model")
    search_fields = ("title", "summary", "place_label")
    filter_horizontal = ("themes",)
    raw_id_fields = ("story_thread", "near_duplicate_of")
    change_list_template = "admin/news/article_change_list.html"


@admin.register(RelevanceFeedback)
class RelevanceFeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "article", "verdict", "created_at")
    list_filter = ("verdict",)


@admin.register(FollowUpQuestion)
class FollowUpQuestionAdmin(admin.ModelAdmin):
    list_display = ("prompt", "sort_order", "is_active")


@admin.register(FollowUpAnswer)
class FollowUpAnswerAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "updated_at")
