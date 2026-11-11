from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from n2s_api import FeedItem

from news.models import Article
from news.sqs import enqueue_feed_items


class Command(BaseCommand):
    help = (
        "Enqueue selected articles to FEED_ITEMS_QUEUE_URL for full news_parser "
        "re-enrich. Does not clear story threads unless --clear-threads."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Requeue every article.",
        )
        parser.add_argument(
            "--unthreaded",
            action="store_true",
            help="Only articles with no story_thread.",
        )
        parser.add_argument(
            "--ids",
            type=str,
            default="",
            help="Comma-separated article primary keys.",
        )
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="Only articles with published_at >= this ISO datetime.",
        )
        parser.add_argument(
            "--clear-threads",
            action="store_true",
            help=(
                "Clear story_thread (and near_duplicate_of) on selected rows "
                "before enqueue so assign_story_thread can run again after enrich."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print count only; do not enqueue or clear.",
        )

    def handle(self, *args, **options):
        qs = Article.objects.all().order_by("id")
        selected = False
        if options["all"]:
            selected = True
        if options["unthreaded"]:
            qs = qs.filter(story_thread__isnull=True)
            selected = True
        ids_raw = (options["ids"] or "").strip()
        if ids_raw:
            try:
                ids = [int(x.strip()) for x in ids_raw.split(",") if x.strip()]
            except ValueError as exc:
                raise CommandError("--ids must be comma-separated integers") from exc
            qs = qs.filter(id__in=ids)
            selected = True
        since_raw = (options["since"] or "").strip()
        if since_raw:
            since = parse_datetime(since_raw)
            if since is None:
                raise CommandError("--since must be an ISO datetime")
            qs = qs.filter(published_at__gte=since)
            selected = True
        if not selected:
            raise CommandError("Select articles with --all, --unthreaded, --ids, and/or --since")

        articles = list(qs.select_related("feed"))
        if options["dry_run"]:
            self.stdout.write(f"Would requeue {len(articles)} article(s).")
            return

        if options["clear_threads"]:
            cleared = Article.objects.filter(
                id__in=[a.id for a in articles]
            ).update(story_thread_id=None, near_duplicate_of_id=None)
            self.stdout.write(f"Cleared threads on {cleared} article(s).")

        items: list[FeedItem] = []
        for article in articles:
            published = article.published_at.isoformat() if article.published_at else ""
            items.append(
                FeedItem(
                    feed_id=article.feed_id,
                    id=str(article.id),
                    link=article.url,
                    title=article.title,
                    description=article.summary or "",
                    published_at=published,
                    thumbnail=article.image_url or "",
                )
            )
        sent = enqueue_feed_items(items)
        self.stdout.write(self.style.SUCCESS(f"Enqueued {sent} / {len(items)} message(s)."))
