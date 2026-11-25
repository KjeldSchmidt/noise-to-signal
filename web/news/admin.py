from django.contrib import admin

from news.admin_ops import patch_admin_site
from news.models import (
    Article,
    ChatRateLimitBucket,
    Feed,
    FeedMute,
    LocationOfInterest,
    RelevanceFeedback,
    StoryThread,
    Subscription,
    Theme,
    ThemeSuggestion,
    UserBrief,
    UserBriefItem,
    UserContentLanguage,
    UserThemeAffinity,
)

patch_admin_site()


@admin.register(Feed)
class FeedAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "kind", "language", "is_active", "owner")
    list_filter = ("kind", "category", "language", "is_active")
    search_fields = ("title", "url", "description")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "feed", "created_at")
    list_filter = ("feed",)


@admin.register(UserContentLanguage)
class UserContentLanguageAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "created_at")
    list_filter = ("language",)
    search_fields = ("user__username", "user__email", "language")


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


@admin.register(ThemeSuggestion)
class ThemeSuggestionAdmin(admin.ModelAdmin):
    list_display = ("raw", "count", "last_seen_at", "last_example_title")
    search_fields = ("raw", "last_example_title")
    readonly_fields = ("raw", "count", "last_seen_at", "last_example_title")
    ordering = ("-count", "raw")


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
        "impact_tier",
        "geo_level",
        "place_label",
        "story_thread",
        "enrichment_status",
        "extract_model",
        "embedding_model",
        "enriched_at",
    )
    list_filter = (
        "feed",
        "impact_tier",
        "geo_level",
        "enrichment_status",
        "embedding_model",
    )
    search_fields = (
        "title",
        "summary",
        "place_label",
        "extract_model",
        "impact_rationale",
    )
    readonly_fields = ("impact_rationale",)
    filter_horizontal = ("themes",)
    raw_id_fields = ("story_thread", "near_duplicate_of")
    change_list_template = "admin/news/article_change_list.html"


@admin.register(RelevanceFeedback)
class RelevanceFeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "article", "verdict", "created_at")
    list_filter = ("verdict",)


@admin.register(UserThemeAffinity)
class UserThemeAffinityAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "more_count", "less_count", "updated_at")
    list_filter = ("theme",)
    search_fields = ("user__username", "user__email", "theme__slug", "theme__label")
    raw_id_fields = ("user", "theme")


class UserBriefItemInline(admin.TabularInline):
    model = UserBriefItem
    extra = 0
    raw_id_fields = ("article",)
    ordering = ("rank",)


@admin.register(UserBrief)
class UserBriefAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "ready_at", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "error")
    raw_id_fields = ("user",)
    inlines = (UserBriefItemInline,)


@admin.register(UserBriefItem)
class UserBriefItemAdmin(admin.ModelAdmin):
    list_display = ("brief", "rank", "article", "score", "created_at")
    list_filter = ("brief__status",)
    search_fields = ("reason", "article__title")
    raw_id_fields = ("brief", "article")


@admin.register(ChatRateLimitBucket)
class ChatRateLimitBucketAdmin(admin.ModelAdmin):
    list_display = ("user", "bucket_key", "window_start", "count", "updated_at")
    list_filter = ("bucket_key",)
    search_fields = ("user__username", "user__email", "bucket_key")
    raw_id_fields = ("user",)
