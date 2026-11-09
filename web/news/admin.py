from django.contrib import admin

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
)


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


@admin.register(LocationOfInterest)
class LocationOfInterestAdmin(admin.ModelAdmin):
    list_display = ("label", "user", "latitude", "longitude", "created_at")
    search_fields = ("label",)


@admin.register(StoryThread)
class StoryThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "last_published_at", "updated_at")
    search_fields = ("label",)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "feed",
        "published_at",
        "story_thread",
        "embedding_model",
    )
    list_filter = ("feed", "embedding_model")
    search_fields = ("title", "summary")
    raw_id_fields = ("story_thread", "near_duplicate_of")


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
