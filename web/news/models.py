from django.conf import settings
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField

EMBEDDING_DIMENSIONS = 1024


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GeoLevel(models.TextChoices):
    GLOBAL = "global", "Global"
    COUNTRY = "country", "Country"
    ADMIN1 = "admin1", "Region / state"
    LOCALITY = "locality", "City / locality"


class EnrichmentStatus(models.TextChoices):
    OK = "ok", "OK"
    DEGRADED = "degraded", "Degraded"


class ImpactTier(models.TextChoices):
    COMMERCIAL = "commercial", "Commercial"
    EPHEMERAL = "ephemeral", "Ephemeral"
    NOTABLE = "notable", "Notable"
    MAJOR = "major", "Major"


class Language(TimeStampedModel):
    """ISO 639-1 content-language catalog (en/fr/de product set + und)."""

    code = models.CharField(max_length=8, primary_key=True)
    name = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.name


class Feed(TimeStampedModel):
    class SourceKind(models.TextChoices):
        CURATED = "curated", "Curated catalog"
        CUSTOM = "custom", "User-added"
        RECOMMENDED = "recommended", "Recommended"

    title = models.CharField(max_length=200)
    url = models.URLField(unique=True)
    site_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True, db_index=True)
    kind = models.CharField(
        max_length=20,
        choices=SourceKind.choices,
        default=SourceKind.CURATED,
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="custom_feeds",
        help_text="Optional first-adder metadata for custom feeds.",
    )
    language = models.ForeignKey(
        Language,
        to_field="code",
        db_column="language",
        on_delete=models.PROTECT,
        related_name="feeds",
        default="en",
        help_text="ISO 639-1 content language (e.g. en, fr, de). Use und when unknown.",
    )
    is_active = models.BooleanField(default=True)
    http_etag = models.CharField(
        max_length=255,
        blank=True,
        help_text="Last ETag from the RSS origin for conditional GET.",
    )
    http_last_modified = models.CharField(
        max_length=64,
        blank=True,
        help_text="Last Last-Modified header from the RSS origin for conditional GET.",
    )

    class Meta:
        ordering = ["category", "title"]

    def __str__(self) -> str:
        return self.title


class Subscription(TimeStampedModel):
    """Opt-in for custom (non-catalog) feeds. Catalog enablement uses FeedMute instead."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    feed = models.ForeignKey(
        Feed,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )

    class Meta:
        unique_together = ("user", "feed")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} → {self.feed}"


class UserOnboarding(TimeStampedModel):
    """Tracks whether the post-signup preference wizard has been finished or skipped."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        state = "done" if self.completed_at else "pending"
        return f"{self.user_id} onboarding ({state})"


class UserContentLanguage(TimeStampedModel):
    """Languages the user wants in briefs/stories (read-side filter on Feed.language)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_languages",
    )
    language = models.ForeignKey(
        Language,
        to_field="code",
        db_column="language",
        on_delete=models.PROTECT,
        related_name="user_preferences",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary language for UI chrome and story title/summary selection.",
    )

    class Meta:
        unique_together = ("user", "language")
        ordering = ["language"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_primary=True),
                name="uniq_user_primary_content_language",
            )
        ]

    def __str__(self) -> str:
        suffix = " (primary)" if self.is_primary else ""
        return f"{self.user} → {self.language.code}{suffix}"


class FeedMute(TimeStampedModel):
    """Opt-out: catalog feeds are enabled unless muted."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_mutes",
    )
    feed = models.ForeignKey(
        Feed,
        on_delete=models.CASCADE,
        related_name="mutes",
    )

    class Meta:
        unique_together = ("user", "feed")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} muted {self.feed}"


class Theme(TimeStampedModel):
    """Curated allowlist of article themes (not freestyle tags)."""

    slug = models.SlugField(max_length=64, unique=True)
    label = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self) -> str:
        return self.label


class ThemeSuggestion(TimeStampedModel):
    """Rejected free-form theme ideas from extract (promotion candidates)."""

    raw = models.SlugField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_example_title = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-count", "raw"]

    def __str__(self) -> str:
        return f"{self.raw} ({self.count})"


class LocationOfInterest(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations_of_interest",
    )
    label = models.CharField(max_length=200)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    admin1 = models.CharField(max_length=120, blank=True, db_index=True)
    locality = models.CharField(max_length=120, blank=True, db_index=True)
    geo_level = models.CharField(
        max_length=20,
        choices=GeoLevel.choices,
        default=GeoLevel.LOCALITY,
        blank=True,
    )

    class Meta:
        ordering = ["label", "id"]

    def __str__(self) -> str:
        return self.label


class StoryThread(TimeStampedModel):
    """Online cluster of articles covering the same evolving event."""

    label = models.CharField(
        max_length=300,
        blank=True,
        help_text="English mirror of the en localization (bootstrap + summarizer).",
    )
    centroid = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    last_published_at = models.DateTimeField(db_index=True)
    summary = models.TextField(
        blank=True,
        help_text="English mirror of the en localization AI digest.",
    )
    summarized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When localizations were last generated (6h throttle on refresh).",
    )

    class Meta:
        ordering = ["-last_published_at"]

    def __str__(self) -> str:
        return self.label or f"Thread {self.pk}"


class StoryThreadLocalization(TimeStampedModel):
    """Per-language display title and AI digest for a story thread."""

    story_thread = models.ForeignKey(
        StoryThread,
        on_delete=models.CASCADE,
        related_name="localizations",
    )
    language = models.ForeignKey(
        Language,
        to_field="code",
        db_column="language",
        on_delete=models.PROTECT,
        related_name="thread_localizations",
    )
    label = models.CharField(max_length=300, blank=True)
    summary = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story_thread", "language"],
                name="uniq_storythreadlocalization_thread_lang",
            )
        ]
        ordering = ["language_id", "id"]

    def __str__(self) -> str:
        return f"thread {self.story_thread_id} [{self.language.code}]"


class Article(TimeStampedModel):
    feed = models.ForeignKey(
        Feed,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    title = models.CharField(max_length=300)
    url = models.URLField()
    summary = models.TextField(blank=True)
    image_url = models.URLField(blank=True, max_length=1000)
    published_at = models.DateTimeField()
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedding_model = models.CharField(max_length=80, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)
    enrichment_status = models.CharField(
        max_length=20,
        choices=EnrichmentStatus.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="ok = extract succeeded; degraded = extract ok but geocode failed.",
    )
    extract_model = models.CharField(
        max_length=120,
        blank=True,
        help_text="Bedrock/LangChain model id used for place/theme extract.",
    )
    enriched_at = models.DateTimeField(null=True, blank=True)
    story_thread = models.ForeignKey(
        StoryThread,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
    )
    near_duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="near_duplicates",
    )
    geo_level = models.CharField(
        max_length=20,
        choices=GeoLevel.choices,
        default=GeoLevel.GLOBAL,
        db_index=True,
    )
    place_label = models.CharField(max_length=200, blank=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    admin1 = models.CharField(max_length=120, blank=True, db_index=True)
    locality = models.CharField(max_length=120, blank=True, db_index=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    geo_confidence = models.FloatField(null=True, blank=True)
    story_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Short generic event name from extract (e.g. Spanish Rail Crash).",
    )
    impact_tier = models.CharField(
        max_length=20,
        choices=ImpactTier.choices,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "User-agnostic lasting importance from extract "
            "(commercial / ephemeral / notable / major)."
        ),
    )
    impact_rationale = models.CharField(
        max_length=160,
        blank=True,
        help_text="Short extract rationale for impact_tier (admin debug).",
    )
    themes = models.ManyToManyField(Theme, blank=True, related_name="articles")

    class Meta:
        ordering = ["-published_at"]
        unique_together = ("feed", "url")

    def __str__(self) -> str:
        return self.title


class RelevanceFeedback(TimeStampedModel):
    class Verdict(models.TextChoices):
        RELEVANT = "relevant", "Relevant"
        NOT_RELEVANT = "not_relevant", "Not relevant"
        SKIP = "skip", "Skip"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="relevance_feedback",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    verdict = models.CharField(max_length=20, choices=Verdict.choices)

    class Meta:
        unique_together = ("user", "article")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user}: {self.article} → {self.verdict}"


class UserThemeAffinity(TimeStampedModel):
    """Per-user more/less counts for curated themes (log-damped in ranking)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="theme_affinities",
    )
    theme = models.ForeignKey(
        Theme,
        on_delete=models.CASCADE,
        related_name="user_affinities",
    )
    more_count = models.PositiveIntegerField(default=0)
    less_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "theme"],
                name="uniq_userthemeaffinity_user_theme",
            )
        ]
        ordering = ["theme__sort_order", "theme__slug"]

    def __str__(self) -> str:
        return f"{self.user_id} {self.theme_id} +{self.more_count}/-{self.less_count}"


class UserBrief(TimeStampedModel):
    """One personalized brief run for a user (async worker fills items)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="briefs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    ready_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="userbrief_user_created_idx"),
        ]

    def __str__(self) -> str:
        return f"brief {self.pk} user={self.user_id} {self.status}"


class UserBriefItem(TimeStampedModel):
    """Ranked article or story-thread slot inside a ready UserBrief."""

    brief = models.ForeignKey(
        UserBrief,
        on_delete=models.CASCADE,
        related_name="items",
    )
    article = models.ForeignKey(
        Article,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="brief_items",
    )
    story_thread = models.ForeignKey(
        StoryThread,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="brief_items",
    )
    rank = models.PositiveIntegerField()
    score = models.FloatField(default=0.0)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["rank", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(article_id__isnull=False, story_thread_id__isnull=True)
                    | models.Q(article_id__isnull=True, story_thread_id__isnull=False)
                ),
                name="userbriefitem_article_xor_thread",
            ),
            models.UniqueConstraint(
                fields=["brief", "article"],
                condition=models.Q(article_id__isnull=False),
                name="uniq_userbriefitem_brief_article",
            ),
            models.UniqueConstraint(
                fields=["brief", "story_thread"],
                condition=models.Q(story_thread_id__isnull=False),
                name="uniq_userbriefitem_brief_thread",
            ),
            models.UniqueConstraint(
                fields=["brief", "rank"],
                name="uniq_userbriefitem_brief_rank",
            ),
        ]

    def __str__(self) -> str:
        if self.story_thread_id:
            return f"brief {self.brief_id} #{self.rank} thread={self.story_thread_id}"
        return f"brief {self.brief_id} #{self.rank} article={self.article_id}"


class ChatRateLimitBucket(TimeStampedModel):
    """Per-user chat rate-limit counters shared across Lambda instances via RDS."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_rate_limit_buckets",
    )
    bucket_key = models.CharField(max_length=32, db_index=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "bucket_key", "window_start"],
                name="uniq_chat_rate_limit_bucket",
            )
        ]
        indexes = [
            models.Index(fields=["window_start"], name="chat_rl_window_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.bucket_key}@{self.window_start}={self.count}"
