import os
from datetime import timedelta

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.utils import timezone

from news.models import Article, Feed, FollowUpQuestion


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
        "title": "Hacker News Front Page",
        "url": "https://hnrss.org/frontpage",
        "site_url": "https://news.ycombinator.com",
        "category": "Tech",
        "description": "What builders are upvoting today.",
        "kind": Feed.SourceKind.RECOMMENDED,
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

ARTICLES = {
    "BBC World": [
        ("European leaders meet on trade pact", "Diplomats signal progress after late-night talks in Brussels."),
        ("Flooding displaces thousands after coastal storm", "Emergency services expand shelters along the shoreline."),
        ("New climate report warns of faster ice loss", "Researchers say polar melt is outpacing earlier models."),
    ],
    "NPR News": [
        ("City budgets face pressure from housing costs", "Mayors push for zoning reforms ahead of spring sessions."),
        ("Public radio explores the future of local news", "Stations experiment with memberships and newsletters."),
        ("Health officials update guidance on seasonal illness", "Clinics prepare for a busier than usual outpatient season."),
    ],
    "The Verge": [
        ("A quieter phone launch still moves the market", "Mid-range hardware and AI features share the spotlight."),
        ("Streaming apps rewrite their home screens again", "Personalization teams chase lower churn with denser rails."),
        ("E-bike makers race to simplify urban commuting", "Battery swaps and safer frames headline spring catalogs."),
    ],
    "Ars Technica": [
        ("Why open weights still matter for enterprise AI", "Procurement teams weigh auditability against hosted APIs."),
        ("Chipmakers outline the next packaging leap", "Yield and thermals remain the hard constraints."),
        ("Security researchers detail a novel supply-chain path", "Maintainers urge signed builds and narrower trust roots."),
    ],
    "Nature News": [
        ("Gene therapy trial shows durable response", "Early patients remain stable a year after dosing."),
        ("Ocean sensors map microplastic hotspots", "Citizen science fleets add coastal resolution."),
        ("Lab-grown cartilage clears a regulatory hurdle", "Clinicians eye sports-injury applications first."),
    ],
    "The Guardian Technology": [
        ("Regulators scrutinize dark-pattern checkout flows", "Consumer groups want clearer cancellation paths."),
        ("Workers organize around AI workload spikes", "Unions ask for transparency on productivity metrics."),
        ("Europe debates messaging interoperability timelines", "Vendors argue over encryption and metadata boundaries."),
    ],
    "Hacker News Front Page": [
        ("Show HN: a tiny offline RSS reader", "Single binary, keyboard-first, no account required."),
        ("Lessons from running Postgres on free tiers", "Connection pooling and migrations still bite."),
        ("Ask HN: how do you filter news without doomscrolling?", "Readers share keyword lists and morning rituals."),
    ],
    "Associated Press Top News": [
        ("Markets open mixed after overnight futures dip", "Energy and retail stocks pull in opposite directions."),
        ("Transport strike slows morning commute", "Officials urge remote work where possible."),
        ("Talks resume on regional infrastructure funding", "Bridges and broadband top the draft agenda."),
    ],
}

QUESTIONS = [
    "Which topics should almost always surface in your brief?",
    "What kinds of stories do you want filtered out aggressively?",
    "Do you prefer deep analysis, short wire updates, or a mix?",
    "Any regions or beats you care about more than the global average?",
    "How technical should tech coverage be for you?",
]


class Command(BaseCommand):
    help = "Seed curated feeds, placeholder articles, and follow-up questions."

    def handle(self, *args, **options):
        now = timezone.now()
        feed_map: dict[str, Feed] = {}

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
            feed_map[feed.title] = feed
            self.stdout.write(
                f"{'Created' if created else 'Updated'} feed: {feed.title}"
            )

        for feed_title, items in ARTICLES.items():
            feed = feed_map[feed_title]
            for index, (title, summary) in enumerate(items):
                url = f"https://example.com/demo/{feed.id}/{index}"
                # Deterministic placeholder images for Stories card previews.
                image_url = f"https://picsum.photos/seed/n2s-{feed.id}-{index}/800/500"
                Article.objects.update_or_create(
                    feed=feed,
                    url=url,
                    defaults={
                        "title": title,
                        "summary": summary,
                        "image_url": image_url,
                        "published_at": now - timedelta(hours=index + 1),
                    },
                )

        for order, prompt in enumerate(QUESTIONS):
            FollowUpQuestion.objects.update_or_create(
                prompt=prompt,
                defaults={"sort_order": order, "is_active": True},
            )

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
