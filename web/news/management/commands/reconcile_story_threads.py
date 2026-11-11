from django.core.management.base import BaseCommand

from news.services.threading import reconcile_story_threads


class Command(BaseCommand):
    help = (
        "No-AI repair: dissolve singleton threads, then soft-pair / join "
        "unthreaded articles that already have embeddings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max unthreaded articles to consider (oldest first).",
        )

    def handle(self, *args, **options):
        stats = reconcile_story_threads(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                "singletons_cleared={singletons_cleared} "
                "threads_deleted={threads_deleted} "
                "unthreaded_considered={unthreaded_considered} "
                "newly_threaded={newly_threaded}".format(**stats)
            )
        )
