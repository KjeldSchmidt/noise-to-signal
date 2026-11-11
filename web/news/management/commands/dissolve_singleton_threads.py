from django.core.management.base import BaseCommand

from news.services.threading import dissolve_singleton_threads


class Command(BaseCommand):
    help = (
        "Clear story_thread on articles that are the sole member of a thread, "
        "then delete empty/singleton StoryThread rows."
    )

    def handle(self, *args, **options):
        cleared, deleted = dissolve_singleton_threads()
        self.stdout.write(
            self.style.SUCCESS(f"Cleared {cleared} article(s); deleted {deleted} thread(s).")
        )
