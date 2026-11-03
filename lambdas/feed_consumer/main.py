import feedparser
from dataclasses import dataclass
from datetime import datetime

from web_api import list_feeds
from dotenv import load_dotenv

load_dotenv()

@dataclass
class FeedItem:
    id: str
    link: str
    thumbnail: str
    date: datetime
    title: str
    description: str

items = []
feeds = list_feeds()
for feed in feeds:
    print(f"{feed.id}: {feed.title} ({feed.url})")
    feed_items_raw = feedparser.parse(feed.url)

    for entry in d.entries:
        item = FeedItem(
            id=entry.id,
            link=entry.link,
            thumbnail=entry.media_thumbnail[0]['url'],
            date=datetime(*entry.published_parsed[:6]),
            title=entry.title,
            description=f"{entry.title} - {entry.summary_detail.value}",
        )
        items.append(item)

print(items)