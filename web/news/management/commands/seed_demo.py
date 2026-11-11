import os

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from news.models import Feed, FollowUpQuestion

FEEDS = [
    {
        "title": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "site_url": "https://www.bbc.com/news/world",
        "category": "World",
        "description": "Global headlines from the BBC World desk.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "site_url": "https://www.npr.org",
        "category": "General",
        "description": "US and world coverage with a public-radio voice.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "site_url": "https://www.theverge.com",
        "category": "Tech",
        "description": "Gadgets, platforms, and internet culture.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "site_url": "https://arstechnica.com",
        "category": "Tech",
        "description": "Deep tech reporting and analysis.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "Nature News",
        "url": "https://www.nature.com/nature.rss",
        "site_url": "https://www.nature.com/news",
        "category": "Science",
        "description": "Research news from Nature.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "The Guardian Technology",
        "url": "https://www.theguardian.com/uk/technology/rss",
        "site_url": "https://www.theguardian.com/uk/technology",
        "category": "Tech",
        "description": "Technology desk from The Guardian.",
        "kind": Feed.SourceKind.CURATED,
    },
    {
        "title": "Associated Press Top News",
        "url": "https://rsshub.app/apnews/topics/apf-topnews",
        "site_url": "https://apnews.com",
        "category": "World",
        "description": "Wire-style top stories (demo catalog entry).",
        "kind": Feed.SourceKind.RECOMMENDED,
    },
]

# Retired from the catalog; deactivate on re-seed so existing DBs drop them.
RETIRED_FEED_URLS = ("https://hnrss.org/frontpage",)

QUESTIONS = [
    "Which topics should almost always surface in your brief?",
    "What kinds of stories do you want filtered out aggressively?",
    "Do you prefer deep analysis, short wire updates, or a mix?",
    "Any regions or beats you care about more than the global average?",
    "How technical should tech coverage be for you?",
]


class Command(BaseCommand):
    help = "Seed curated/recommended feeds and follow-up questions."

    def handle(self, *args, **options):
        site_domain = os.environ.get("SITE_DOMAIN", "127.0.0.1:8000")
        Site.objects.update_or_create(
            id=1,
            defaults={"domain": site_domain, "name": "Noise to Signal"},
        )
        self.stdout.write(f"Site domain set to {site_domain}")

        for data in FEEDS:
            feed, created = Feed.objects.update_or_create(
                url=data["url"],
                defaults={
                    "title": data["title"],
                    "site_url": data["site_url"],
                    "category": data["category"],
                    "description": data["description"],
                    "kind": data["kind"],
                    "is_active": True,
                    "owner": None,
                },
            )
            self.stdout.write(f"{'Created' if created else 'Updated'} feed: {feed.title}")

        retired = Feed.objects.filter(url__in=RETIRED_FEED_URLS, is_active=True)
        for feed in retired:
            feed.is_active = False
            feed.save(update_fields=["is_active"])
            self.stdout.write(f"Deactivated retired feed: {feed.title}")

        for order, prompt in enumerate(QUESTIONS):
            FollowUpQuestion.objects.update_or_create(
                prompt=prompt,
                defaults={"sort_order": order, "is_active": True},
            )

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
