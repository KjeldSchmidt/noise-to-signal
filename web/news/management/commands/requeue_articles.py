from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

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
            "--since-hours",
            type=int,
            default=None,
            help="Only articles published within the last N hours.",
        )
        parser.add_argument(
            "--enriched-before-hours",
            type=int,
            default=None,
            help=(
                "Only articles never enriched or last enriched more than N hours ago "
                "(skips a recent test requeue)."
            ),
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

        since_hours = options.get("since_hours")
        if since_hours is not None and since_hours < 1:
            raise CommandError("--since-hours must be >= 1")
        enriched_before_hours = options.get("enriched_before_hours")
        if enriched_before_hours is not None and enriched_before_hours < 1:
            raise CommandError("--enriched-before-hours must be >= 1")

        try:
            qs = articles_for_requeue(
                all_articles=bool(options["all"]),
                unthreaded=bool(options["unthreaded"]),
                ids=ids,
                since_hours=since_hours,
                enriched_before_hours=enriched_before_hours,
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
            self.style.SUCCESS(f"Enqueued {result['enqueued']} / {result['count']} message(s).")
        )
