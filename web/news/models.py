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
        help_text="Set for custom feeds owned by a single user.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "title"]

    def __str__(self) -> str:
        return self.title


class Subscription(TimeStampedModel):
    """Legacy opt-in rows; superseded by FeedMute (catalog is on by default)."""

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


class FeedMute(TimeStampedModel):
    """Opt-out: catalog (and custom) feeds are enabled unless muted."""

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

    label = models.CharField(max_length=300, blank=True)
    centroid = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    last_published_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-last_published_at"]

    def __str__(self) -> str:
        return self.label or f"Thread {self.pk}"


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


class FollowUpQuestion(TimeStampedModel):
    """Catalog of taste-discovery questions (seeded / placeholder AI)."""

    prompt = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.prompt[:80]


class FollowUpAnswer(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followup_answers",
    )
    question = models.ForeignKey(
        FollowUpQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    answer = models.TextField()

    class Meta:
        unique_together = ("user", "question")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user} / Q{self.question_id}"
