import os

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from news.models import Feed, FollowUpQuestion

# Catalog rows are also applied by migration 0012 for deploy envs.
# Keep FEEDS in sync with news/migrations/0012_seed_multilingual_catalog_feeds.py.
FEEDS = [
    {
        "title": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "site_url": "https://www.bbc.com/news/world",
        "category": "World",
        "description": "Global headlines from the BBC World desk.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "site_url": "https://www.npr.org",
        "category": "General",
        "description": "US and world coverage with a public-radio voice.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "site_url": "https://www.theverge.com",
        "category": "Tech",
        "description": "Gadgets, platforms, and internet culture.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "site_url": "https://arstechnica.com",
        "category": "Tech",
        "description": "Deep tech reporting and analysis.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "Nature News",
        "url": "https://www.nature.com/nature.rss",
        "site_url": "https://www.nature.com/news",
        "category": "Science",
        "description": "Research news from Nature.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "The Guardian Technology",
        "url": "https://www.theguardian.com/uk/technology/rss",
        "site_url": "https://www.theguardian.com/uk/technology",
        "category": "Tech",
        "description": "Technology desk from The Guardian.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "Associated Press Top News",
        "url": "https://rsshub.app/apnews/topics/apf-topnews",
        "site_url": "https://apnews.com",
        "category": "World",
        "description": "Wire-style top stories (demo catalog entry).",
        "kind": Feed.SourceKind.RECOMMENDED,
        "language": "en",
    },
    {
        "title": "Le Monde",
        "url": "https://www.lemonde.fr/rss/une.xml",
        "site_url": "https://www.lemonde.fr",
        "category": "World",
        "description": "French front-page headlines from Le Monde.",
        "kind": Feed.SourceKind.CURATED,
        "language": "fr",
    },
    {
        "title": "Franceinfo",
        "url": "https://www.francetvinfo.fr/titres.rss",
        "site_url": "https://www.francetvinfo.fr",
        "category": "World",
        "description": "Top titles from Franceinfo.",
        "kind": Feed.SourceKind.CURATED,
        "language": "fr",
    },
    {
        "title": "Tagesschau",
        "url": "https://www.tagesschau.de/index~rss2.xml",
        "site_url": "https://www.tagesschau.de",
        "category": "World",
        "description": "German public-broadcasting top stories from ARD.",
        "kind": Feed.SourceKind.CURATED,
        "language": "de",
    },
    {
        "title": "Spiegel Schlagzeilen",
        "url": "https://www.spiegel.de/schlagzeilen/index.rss",
        "site_url": "https://www.spiegel.de",
        "category": "World",
        "description": "German headlines from Der Spiegel.",
        "kind": Feed.SourceKind.CURATED,
        "language": "de",
    },
    {
        "title": "AllAfrica Latest",
        "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "site_url": "https://allafrica.com",
        "category": "World",
        "description": "Aggregated Africa headlines from AllAfrica.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "site_url": "https://www.aljazeera.com",
        "category": "World",
        "description": "Middle East and world coverage from Al Jazeera English.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
    },
    {
        "title": "South China Morning Post",
        "url": "https://www.scmp.com/rss/91/feed/",
        "site_url": "https://www.scmp.com",
        "category": "World",
        "description": "Asia and world coverage from the SCMP.",
        "kind": Feed.SourceKind.CURATED,
        "language": "en",
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
                    "language": data["language"],
                    "is_active": True,
                    "owner": None,
                },
            )
            self.stdout.write(f"{'Created' if created else 'Updated'} feed: {feed.title}")

        retired = Feed.objects.filter(url__in=RETIRED_FEED_URLS, is_active=True)
        for feed in retired:
            feed.is_active = False
            feed.save(update_fields=["is_active", "updated_at"])
            self.stdout.write(f"Deactivated retired feed: {feed.title}")

        for i, prompt in enumerate(QUESTIONS):
            FollowUpQuestion.objects.update_or_create(
                prompt=prompt,
                defaults={"sort_order": i, "is_active": True},
            )
        self.stdout.write(f"Seeded {len(QUESTIONS)} follow-up questions.")
