from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from news.services.requeue import articles_for_requeue, requeue_articles


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
        ids_raw = (options["ids"] or "").strip()
        ids: list[int] | None = None
        if ids_raw:
            try:
                ids = [int(x.strip()) for x in ids_raw.split(",") if x.strip()]
            except ValueError as exc:
                raise CommandError("--ids must be comma-separated integers") from exc

        since = None
        since_raw = (options["since"] or "").strip()
        if since_raw:
            since = parse_datetime(since_raw)
            if since is None:
                raise CommandError("--since must be an ISO datetime")

        try:
            qs = articles_for_requeue(
                all_articles=bool(options["all"]),
                unthreaded=bool(options["unthreaded"]),
                ids=ids,
                since=since,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        result = requeue_articles(
            qs,
            clear_threads=bool(options["clear_threads"]),
            dry_run=bool(options["dry_run"]),
        )
        if options["dry_run"]:
            self.stdout.write(f"Would requeue {result['count']} article(s).")
            return
        if result["cleared"]:
            self.stdout.write(f"Cleared threads on {result['cleared']} article(s).")
        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued {result['enqueued']} / {result['count']} message(s)."
            )
        )
