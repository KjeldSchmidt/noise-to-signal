from django.conf import settings
from django.db import models
from pgvector.django import VectorField

EMBEDDING_DIMENSIONS = 1024


class Feed(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "title"]

    def __str__(self) -> str:
        return self.title


class Subscription(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "feed")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} → {self.feed}"


class FeedMute(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "feed")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} muted {self.feed}"


class LocationOfInterest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations_of_interest",
    )
    label = models.CharField(max_length=200)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label", "id"]

    def __str__(self) -> str:
        return self.label


class StoryThread(models.Model):
    """Online cluster of articles covering the same evolving event."""

    label = models.CharField(max_length=300, blank=True)
    centroid = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    last_published_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_published_at"]

    def __str__(self) -> str:
        return self.label or f"Thread {self.pk}"


class Article(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedding_model = models.CharField(max_length=80, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)
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

    class Meta:
        ordering = ["-published_at"]
        unique_together = ("feed", "url")

    def __str__(self) -> str:
        return self.title


class RelevanceFeedback(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "article")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user}: {self.article} → {self.verdict}"


class FollowUpQuestion(models.Model):
    """Catalog of taste-discovery questions (seeded / placeholder AI)."""

    prompt = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.prompt[:80]


class FollowUpAnswer(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "question")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user} / Q{self.question_id}"
