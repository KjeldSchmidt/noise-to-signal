"""Seed multilingual curated catalog feeds + language on existing English rows."""

from django.db import migrations

# Frozen snapshot of the catalog expansion (keep in sync with seed_demo FEEDS).
FEEDS = [
    {
        "title": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "site_url": "https://www.bbc.com/news/world",
        "category": "World",
        "description": "Global headlines from the BBC World desk.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "site_url": "https://www.npr.org",
        "category": "General",
        "description": "US and world coverage with a public-radio voice.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "site_url": "https://www.theverge.com",
        "category": "Tech",
        "description": "Gadgets, platforms, and internet culture.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "site_url": "https://arstechnica.com",
        "category": "Tech",
        "description": "Deep tech reporting and analysis.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "Nature News",
        "url": "https://www.nature.com/nature.rss",
        "site_url": "https://www.nature.com/news",
        "category": "Science",
        "description": "Research news from Nature.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "The Guardian Technology",
        "url": "https://www.theguardian.com/uk/technology/rss",
        "site_url": "https://www.theguardian.com/uk/technology",
        "category": "Tech",
        "description": "Technology desk from The Guardian.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "Associated Press Top News",
        "url": "https://rsshub.app/apnews/topics/apf-topnews",
        "site_url": "https://apnews.com",
        "category": "World",
        "description": "Wire-style top stories (demo catalog entry).",
        "kind": "recommended",
        "language": "en",
    },
    {
        "title": "Le Monde",
        "url": "https://www.lemonde.fr/rss/une.xml",
        "site_url": "https://www.lemonde.fr",
        "category": "World",
        "description": "French front-page headlines from Le Monde.",
        "kind": "curated",
        "language": "fr",
    },
    {
        "title": "Franceinfo",
        "url": "https://www.francetvinfo.fr/titres.rss",
        "site_url": "https://www.francetvinfo.fr",
        "category": "World",
        "description": "Top titles from Franceinfo.",
        "kind": "curated",
        "language": "fr",
    },
    {
        "title": "Tagesschau",
        "url": "https://www.tagesschau.de/index~rss2.xml",
        "site_url": "https://www.tagesschau.de",
        "category": "World",
        "description": "German public-broadcasting top stories from ARD.",
        "kind": "curated",
        "language": "de",
    },
    {
        "title": "Spiegel Schlagzeilen",
        "url": "https://www.spiegel.de/schlagzeilen/index.rss",
        "site_url": "https://www.spiegel.de",
        "category": "World",
        "description": "German headlines from Der Spiegel.",
        "kind": "curated",
        "language": "de",
    },
    {
        "title": "AllAfrica Latest",
        "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "site_url": "https://allafrica.com",
        "category": "World",
        "description": "Aggregated Africa headlines from AllAfrica.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "site_url": "https://www.aljazeera.com",
        "category": "World",
        "description": "Middle East and world coverage from Al Jazeera English.",
        "kind": "curated",
        "language": "en",
    },
    {
        "title": "South China Morning Post",
        "url": "https://www.scmp.com/rss/91/feed/",
        "site_url": "https://www.scmp.com",
        "category": "World",
        "description": "Asia and world coverage from the SCMP.",
        "kind": "curated",
        "language": "en",
    },
]

# Feeds introduced by this expansion (safe to delete on reverse).
NEW_FEED_URLS = (
    "https://www.lemonde.fr/rss/une.xml",
    "https://www.francetvinfo.fr/titres.rss",
    "https://www.tagesschau.de/index~rss2.xml",
    "https://www.spiegel.de/schlagzeilen/index.rss",
    "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.scmp.com/rss/91/feed/",
)

RETIRED_FEED_URLS = ("https://hnrss.org/frontpage",)


def seed_catalog_feeds(apps, schema_editor):
    Feed = apps.get_model("news", "Feed")
    for data in FEEDS:
        Feed.objects.update_or_create(
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
    Feed.objects.filter(url__in=RETIRED_FEED_URLS, is_active=True).update(is_active=False)


def unseed_new_catalog_feeds(apps, schema_editor):
    Feed = apps.get_model("news", "Feed")
    Feed.objects.filter(url__in=NEW_FEED_URLS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0011_feed_language_subscriptions"),
    ]

    operations = [
        migrations.RunPython(seed_catalog_feeds, unseed_new_catalog_feeds),
    ]
